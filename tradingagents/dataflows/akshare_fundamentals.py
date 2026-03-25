from datetime import datetime

import akshare as ak
import pandas as pd

from .config import get_config
from .ticker_normalization import normalize_symbol_for_vendor


ABSTRACT_PRIORITY_METRICS = [
    "归母净利润",
    "营业总收入",
    "营业总支出",
    "营业利润",
    "利润总额",
    "经营活动产生的现金流量净额",
    "总资产",
    "归属于母公司股东权益",
    "基本每股收益",
    "净资产收益率",
    "销售毛利率",
    "资产负债率",
]

BALANCE_SHEET_COLUMNS = [
    "REPORT_DATE_NAME",
    "REPORT_DATE",
    "NOTICE_DATE",
    "CURRENCY",
    "TOTAL_ASSETS",
    "TOTAL_LIABILITIES",
    "TOTAL_EQUITY",
    "TOTAL_PARENT_EQUITY",
    "TOTAL_CURRENT_ASSETS",
    "TOTAL_CURRENT_LIAB",
    "MONETARYFUNDS",
    "ACCOUNTS_RECE",
    "INVENTORY",
    "FIXED_ASSET",
]

CASHFLOW_COLUMNS = [
    "REPORT_DATE_NAME",
    "REPORT_DATE",
    "NOTICE_DATE",
    "CURRENCY",
    "TOTAL_OPERATE_INFLOW",
    "TOTAL_OPERATE_OUTFLOW",
    "NETCASH_OPERATE",
    "TOTAL_INVEST_INFLOW",
    "TOTAL_INVEST_OUTFLOW",
    "NETCASH_INVEST",
    "TOTAL_FINANCE_INFLOW",
    "TOTAL_FINANCE_OUTFLOW",
    "NETCASH_FINANCE",
    "END_CCE",
]

INCOME_STATEMENT_COLUMNS = [
    "REPORT_DATE_NAME",
    "REPORT_DATE",
    "NOTICE_DATE",
    "CURRENCY",
    "TOTAL_OPERATE_INCOME",
    "TOTAL_OPERATE_COST",
    "OPERATE_PROFIT",
    "TOTAL_PROFIT",
    "NETPROFIT",
    "PARENT_NETPROFIT",
    "DEDUCT_PARENT_NETPROFIT",
    "BASIC_EPS",
    "SALE_EXPENSE",
    "MANAGE_EXPENSE",
    "FINANCE_EXPENSE",
]


def _market_profile() -> str:
    return get_config().get("market_profile", "cn_a_share")


def _base_symbol(symbol: str) -> str:
    return normalize_symbol_for_vendor(symbol, "akshare", _market_profile())


def _em_symbol(symbol: str) -> str:
    return normalize_symbol_for_vendor(symbol, "akshare_em", _market_profile())


def _to_datetime(value: str) -> datetime:
    return datetime.strptime(value, "%Y-%m-%d")


def _filter_statement_rows(data: pd.DataFrame, curr_date: str | None, freq: str) -> pd.DataFrame:
    if data is None or data.empty:
        return pd.DataFrame()

    filtered = data.copy()
    if "REPORT_DATE" not in filtered.columns:
        return filtered

    filtered["REPORT_DATE"] = pd.to_datetime(filtered["REPORT_DATE"], errors="coerce")
    if "NOTICE_DATE" in filtered.columns:
        filtered["NOTICE_DATE"] = pd.to_datetime(filtered["NOTICE_DATE"], errors="coerce")

    if curr_date:
        current_dt = _to_datetime(curr_date)
        filtered = filtered[filtered["REPORT_DATE"] <= current_dt]

    freq_lower = (freq or "quarterly").lower()
    if freq_lower == "annual":
        filtered = filtered[filtered["REPORT_DATE"].dt.strftime("%m-%d") == "12-31"]

    filtered = filtered.sort_values("REPORT_DATE", ascending=False)
    return filtered.head(8).reset_index(drop=True)


def _select_available_columns(data: pd.DataFrame, desired_columns: list[str]) -> pd.DataFrame:
    available = [column for column in desired_columns if column in data.columns]
    if not available:
        return data.head(8)
    return data.loc[:, available]


def _finalize_statement_output(data: pd.DataFrame, title: str, ticker: str, freq: str) -> str:
    if data.empty:
        return f"No {title.lower()} data found for symbol '{ticker}'"

    formatted = data.copy()
    for date_column in ["REPORT_DATE", "NOTICE_DATE"]:
        if date_column in formatted.columns:
            formatted[date_column] = pd.to_datetime(formatted[date_column], errors="coerce").dt.strftime("%Y-%m-%d")

    header = f"# {title} data for {ticker.upper()} ({freq})\n"
    header += f"# Total records: {len(formatted)}\n"
    header += f"# Data retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
    return header + formatted.to_csv(index=False)


def get_fundamentals(ticker: str, curr_date: str) -> str:
    data = ak.stock_financial_abstract(symbol=_base_symbol(ticker))
    if data is None or data.empty:
        return f"No fundamentals data found for symbol '{ticker}'"

    summary = data.copy()
    if "选项" in summary.columns:
        summary = summary[summary["选项"] == "常用指标"]

    metric_column = "指标" if "指标" in summary.columns else summary.columns[0]
    prioritized = summary[summary[metric_column].isin(ABSTRACT_PRIORITY_METRICS)]
    if prioritized.empty:
        prioritized = summary.head(12)

    date_columns = []
    current_dt = _to_datetime(curr_date)
    for column in prioritized.columns:
        if isinstance(column, str) and column.isdigit() and len(column) == 8:
            column_dt = datetime.strptime(column, "%Y%m%d")
            if column_dt <= current_dt:
                date_columns.append(column)

    date_columns = sorted(date_columns, reverse=True)[:8]
    keep_columns = [column for column in ["选项", metric_column] if column in prioritized.columns] + date_columns
    formatted = prioritized.loc[:, keep_columns].reset_index(drop=True)

    header = f"# Fundamental summary for {ticker.upper()} as of {curr_date}\n"
    header += f"# Total metrics: {len(formatted)}\n"
    header += f"# Data retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
    return header + formatted.to_csv(index=False)


def get_balance_sheet(ticker: str, freq: str = "quarterly", curr_date: str = None) -> str:
    data = ak.stock_balance_sheet_by_report_em(symbol=_em_symbol(ticker))
    filtered = _filter_statement_rows(data, curr_date, freq)
    selected = _select_available_columns(filtered, BALANCE_SHEET_COLUMNS)
    return _finalize_statement_output(selected, "Balance Sheet", ticker, freq)


def get_cashflow(ticker: str, freq: str = "quarterly", curr_date: str = None) -> str:
    data = ak.stock_cash_flow_sheet_by_report_em(symbol=_em_symbol(ticker))
    filtered = _filter_statement_rows(data, curr_date, freq)
    selected = _select_available_columns(filtered, CASHFLOW_COLUMNS)
    return _finalize_statement_output(selected, "Cash Flow", ticker, freq)


def get_income_statement(ticker: str, freq: str = "quarterly", curr_date: str = None) -> str:
    data = ak.stock_profit_sheet_by_report_em(symbol=_em_symbol(ticker))
    filtered = _filter_statement_rows(data, curr_date, freq)
    selected = _select_available_columns(filtered, INCOME_STATEMENT_COLUMNS)
    return _finalize_statement_output(selected, "Income Statement", ticker, freq)
