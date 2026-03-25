from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timedelta
import io

import akshare as ak
import pandas as pd

from .ticker_normalization import normalize_symbol_for_vendor


MAX_COMPANY_ITEMS = 20


def _base_symbol(symbol: str) -> str:
    return normalize_symbol_for_vendor(symbol, "china_news", "cn_a_share")


def _daterange(start_date: str, end_date: str):
    start_dt = datetime.strptime(start_date, "%Y-%m-%d")
    end_dt = datetime.strptime(end_date, "%Y-%m-%d")
    current_dt = start_dt
    while current_dt <= end_dt:
        yield current_dt
        current_dt += timedelta(days=1)


def _call_silenced(func, *args, **kwargs):
    stdout_buffer = io.StringIO()
    stderr_buffer = io.StringIO()
    with redirect_stdout(stdout_buffer), redirect_stderr(stderr_buffer):
        return func(*args, **kwargs)


def _format_company_news_rows(symbol: str, rows: pd.DataFrame, source_label: str, start_date: str, end_date: str) -> str:
    if rows.empty:
        return f"No China company news found for symbol '{symbol}' between {start_date} and {end_date}"

    sections = []
    for _, row in rows.iterrows():
        published_at = row.get("published_at", "")
        title = row.get("title", "Untitled")
        body = row.get("body", "")
        source = row.get("source", source_label)
        link = row.get("link", "")

        section = f"### [{published_at}] {title} (source: {source})\n\n{body}"
        if link:
            section += f"\n\nLink: {link}"
        sections.append(section)

    header = f"## China company news for {symbol.upper()} from {start_date} to {end_date} ({source_label})\n\n"
    return header + "\n\n".join(sections)


def _recent_company_news(base_symbol: str, start_date: str, end_date: str) -> pd.DataFrame:
    data = _call_silenced(ak.stock_news_em, symbol=base_symbol)
    if data is None or data.empty:
        return pd.DataFrame(columns=["published_at", "title", "body", "source", "link"])

    rows = data.copy()
    rows["发布时间"] = pd.to_datetime(rows["发布时间"], errors="coerce")
    start_dt = pd.Timestamp(start_date)
    end_dt = pd.Timestamp(end_date) + pd.Timedelta(days=1) - pd.Timedelta(seconds=1)
    rows = rows[(rows["发布时间"] >= start_dt) & (rows["发布时间"] <= end_dt)]
    if rows.empty:
        return pd.DataFrame(columns=["published_at", "title", "body", "source", "link"])

    rows = rows.sort_values("发布时间", ascending=False).head(MAX_COMPANY_ITEMS)
    return pd.DataFrame({
        "published_at": rows["发布时间"].dt.strftime("%Y-%m-%d %H:%M:%S"),
        "title": rows["新闻标题"].fillna(""),
        "body": rows["新闻内容"].fillna(""),
        "source": rows["文章来源"].fillna("东方财富"),
        "link": rows["新闻链接"].fillna(""),
    })


def _historical_announcements(base_symbol: str, start_date: str, end_date: str) -> pd.DataFrame:
    collected = []
    for current_dt in _daterange(start_date, end_date):
        daily = _call_silenced(ak.stock_notice_report, symbol="全部", date=current_dt.strftime("%Y%m%d"))
        if daily is None or daily.empty:
            continue

        filtered = daily.copy()
        filtered["代码"] = filtered["代码"].astype(str).str.zfill(6)
        filtered = filtered[filtered["代码"] == base_symbol]
        if filtered.empty:
            continue

        filtered["公告日期"] = pd.to_datetime(filtered["公告日期"], errors="coerce")
        collected.append(filtered)

    if not collected:
        return pd.DataFrame(columns=["published_at", "title", "body", "source", "link"])

    merged = pd.concat(collected, ignore_index=True)
    merged = merged.sort_values("公告日期", ascending=False).head(MAX_COMPANY_ITEMS)
    return pd.DataFrame({
        "published_at": merged["公告日期"].dt.strftime("%Y-%m-%d"),
        "title": merged["公告标题"].fillna(""),
        "body": merged["公告类型"].fillna("交易所公告"),
        "source": "交易所公告",
        "link": merged["网址"].fillna(""),
    })


def get_news(symbol: str, start_date: str, end_date: str) -> str:
    base_symbol = _base_symbol(symbol)
    recent_news = _recent_company_news(base_symbol, start_date, end_date)
    if not recent_news.empty:
        return _format_company_news_rows(symbol, recent_news, "东方财富新闻", start_date, end_date)

    announcements = _historical_announcements(base_symbol, start_date, end_date)
    if not announcements.empty:
        return _format_company_news_rows(symbol, announcements, "交易所公告", start_date, end_date)

    return f"No China company news or exchange notices found for symbol '{symbol}' between {start_date} and {end_date}"


def _fetch_cctv_news(date_str: str) -> pd.DataFrame:
    data = _call_silenced(ak.news_cctv, date=date_str)
    if data is None or data.empty:
        return pd.DataFrame(columns=["published_at", "title", "body", "source"])

    rows = data.copy().head(20)
    return pd.DataFrame({
        "published_at": pd.to_datetime(rows["date"], format="%Y%m%d", errors="coerce"),
        "title": rows["title"].fillna(""),
        "body": rows["content"].fillna(""),
        "source": "央视新闻",
    })


def _fetch_economic_calendar(date_str: str) -> pd.DataFrame:
    data = _call_silenced(ak.news_economic_baidu, date=date_str)
    if data is None or data.empty:
        return pd.DataFrame(columns=["published_at", "title", "body", "source"])

    rows = data.copy().head(10)
    timestamps = pd.to_datetime(rows["日期"].astype(str) + " " + rows["时间"].astype(str), errors="coerce")
    titles = rows["事件"].fillna("")
    bodies = (
        "地区: " + rows["地区"].fillna("")
        + " | 公布: " + rows["公布"].astype(str)
        + " | 预期: " + rows["预期"].astype(str)
        + " | 前值: " + rows["前值"].astype(str)
        + " | 重要性: " + rows["重要性"].astype(str)
    )
    return pd.DataFrame({
        "published_at": timestamps,
        "title": titles,
        "body": bodies,
        "source": "百度财经日历",
    })


def get_global_news(curr_date: str, look_back_days: int = 7, limit: int = 5) -> str:
    end_dt = datetime.strptime(curr_date, "%Y-%m-%d")
    start_dt = end_dt - timedelta(days=look_back_days)

    collected = []
    for current_dt in _daterange(start_dt.strftime("%Y-%m-%d"), curr_date):
        provider_date = current_dt.strftime("%Y%m%d")
        cctv_rows = _fetch_cctv_news(provider_date)
        if not cctv_rows.empty:
            collected.append(cctv_rows)
            continue

        economic_rows = _fetch_economic_calendar(provider_date)
        if not economic_rows.empty:
            collected.append(economic_rows)

    if not collected:
        return f"No China macro or policy news found from {start_dt.strftime('%Y-%m-%d')} to {curr_date}"

    merged = pd.concat(collected, ignore_index=True)
    merged = merged.dropna(subset=["published_at"])
    merged = merged.sort_values("published_at", ascending=False).head(limit)

    sections = []
    for _, row in merged.iterrows():
        published_at = pd.to_datetime(row["published_at"], errors="coerce").strftime("%Y-%m-%d %H:%M:%S")
        title = row["title"]
        body = row["body"]
        source = row["source"]
        sections.append(f"### [{published_at}] {title} (source: {source})\n\n{body}")

    header = f"## China macro and policy news from {start_dt.strftime('%Y-%m-%d')} to {curr_date}\n\n"
    return header + "\n\n".join(sections)
