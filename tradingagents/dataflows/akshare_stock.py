from datetime import datetime
import threading
import time
import os

import akshare as ak
import pandas as pd

from .config import get_config
from .ticker_normalization import normalize_symbol_for_vendor


COLUMN_MAP = {
    "日期": "Date",
    "开盘": "Open",
    "收盘": "Close",
    "最高": "High",
    "最低": "Low",
    "成交量": "Volume",
    "成交额": "Amount",
    "振幅": "Amplitude",
    "涨跌幅": "ChangePercent",
    "涨跌额": "ChangeAmount",
    "换手率": "TurnoverRate",
}

_CACHE_LOCKS: dict[str, threading.Lock] = {}
_CACHE_LOCKS_GUARD = threading.Lock()
_AKSHARE_REQUEST_GATE = threading.Lock()


def _prefixed_a_share_symbol(symbol: str) -> str:
    if symbol.startswith(("6", "9")):
        return f"sh{symbol}"
    return f"sz{symbol}"


def _normalize_akshare_dataframe(data: pd.DataFrame, source: str) -> pd.DataFrame:
    if data is None or data.empty:
        return pd.DataFrame()

    if source == "eastmoney":
        normalized = data.rename(columns=COLUMN_MAP)
    elif source == "tencent":
        normalized = data.rename(
            columns={
                "date": "Date",
                "open": "Open",
                "close": "Close",
                "high": "High",
                "low": "Low",
                "amount": "Volume",
            }
        )
    elif source == "sina":
        normalized = data.rename(
            columns={
                "date": "Date",
                "open": "Open",
                "close": "Close",
                "high": "High",
                "low": "Low",
                "volume": "Volume",
                "amount": "Amount",
                "turnover": "TurnoverRate",
            }
        )
        if "TurnoverRate" in normalized.columns:
            normalized["TurnoverRate"] = pd.to_numeric(normalized["TurnoverRate"], errors="coerce") * 100
    else:
        raise ValueError(f"Unsupported akshare data source: {source}")

    if "Date" not in normalized.columns:
        raise ValueError(f"Unexpected Akshare response columns: {list(normalized.columns)}")

    normalized["Date"] = pd.to_datetime(normalized["Date"])
    normalized = normalized.sort_values("Date").reset_index(drop=True)

    numeric_columns = [
        "Open",
        "Close",
        "High",
        "Low",
        "Volume",
        "Amount",
        "Amplitude",
        "ChangePercent",
        "ChangeAmount",
        "TurnoverRate",
    ]
    for column in numeric_columns:
        if column in normalized.columns:
            normalized[column] = pd.to_numeric(normalized[column], errors="coerce")

    return normalized


def _fetch_from_eastmoney(symbol: str, start_date: str, end_date: str) -> pd.DataFrame:
    data = ak.stock_zh_a_hist(
        symbol=symbol,
        period="daily",
        start_date=start_date.replace("-", ""),
        end_date=end_date.replace("-", ""),
        adjust="qfq",
        timeout=15,
    )
    return _normalize_akshare_dataframe(data, "eastmoney")


def _fetch_from_tencent(symbol: str, start_date: str, end_date: str) -> pd.DataFrame:
    data = ak.stock_zh_a_hist_tx(
        symbol=_prefixed_a_share_symbol(symbol),
        start_date=start_date,
        end_date=end_date,
        adjust="qfq",
        timeout=15,
    )
    return _normalize_akshare_dataframe(data, "tencent")


def _fetch_from_sina(symbol: str, start_date: str, end_date: str) -> pd.DataFrame:
    data = ak.stock_zh_a_daily(
        symbol=_prefixed_a_share_symbol(symbol),
        start_date=start_date.replace("-", ""),
        end_date=end_date.replace("-", ""),
        adjust="qfq",
    )
    return _normalize_akshare_dataframe(data, "sina")


def _cache_path(symbol: str, start_date: str, end_date: str) -> str:
    config = get_config()
    os.makedirs(config["data_cache_dir"], exist_ok=True)
    return os.path.join(
        config["data_cache_dir"],
        f"{symbol}-AShare-{start_date}-{end_date}.csv",
    )


def _get_cache_lock(cache_file: str) -> threading.Lock:
    with _CACHE_LOCKS_GUARD:
        if cache_file not in _CACHE_LOCKS:
            _CACHE_LOCKS[cache_file] = threading.Lock()
        return _CACHE_LOCKS[cache_file]


def _read_cached_dataframe(cache_file: str) -> pd.DataFrame | None:
    if not os.path.exists(cache_file):
        return None
    data = pd.read_csv(cache_file)
    data["Date"] = pd.to_datetime(data["Date"])
    return data


def _fetch_akshare_dataframe(symbol: str, start_date: str, end_date: str) -> pd.DataFrame:
    config = get_config()
    normalized_symbol = normalize_symbol_for_vendor(
        symbol,
        "akshare",
        config.get("market_profile", "cn_a_share"),
    )
    cache_file = _cache_path(normalized_symbol, start_date, end_date)

    cached = _read_cached_dataframe(cache_file)
    if cached is not None:
        return cached

    lock = _get_cache_lock(cache_file)
    with lock:
        cached = _read_cached_dataframe(cache_file)
        if cached is not None:
            return cached

        last_error = None
        data = None
        fetchers = [
            _fetch_from_tencent,
            _fetch_from_sina,
            _fetch_from_eastmoney,
        ]
        for fetcher in fetchers:
            try:
                print(f"DEBUG: Akshare internal source '{fetcher.__name__}' for symbol '{normalized_symbol}'")
                with _AKSHARE_REQUEST_GATE:
                    data = fetcher(normalized_symbol, start_date, end_date)
                if data is not None and not data.empty:
                    print(
                        f"DEBUG: Akshare internal source '{fetcher.__name__}' succeeded with {len(data)} rows"
                    )
                    last_error = None
                    break
                print(f"DEBUG: Akshare internal source '{fetcher.__name__}' returned no rows")
            except Exception as exc:
                last_error = exc
                print(f"DEBUG: Akshare internal source '{fetcher.__name__}' failed: {exc}")
                time.sleep(1.0)

        if last_error is not None and (data is None or data.empty):
            raise last_error

        if data is None or data.empty:
            return pd.DataFrame()

        data.to_csv(cache_file, index=False)
        return data


def get_stock(symbol: str, start_date: str, end_date: str):
    datetime.strptime(start_date, "%Y-%m-%d")
    datetime.strptime(end_date, "%Y-%m-%d")

    data = _fetch_akshare_dataframe(symbol, start_date, end_date)
    if data.empty:
        raise ValueError(f"No data found for symbol '{symbol}' between {start_date} and {end_date}")

    filtered = data[(data["Date"] >= start_date) & (data["Date"] <= end_date)].copy()
    if filtered.empty:
        raise ValueError(f"No data found for symbol '{symbol}' between {start_date} and {end_date}")

    filtered["Date"] = filtered["Date"].dt.strftime("%Y-%m-%d")
    csv_string = filtered.to_csv(index=False)

    header = f"# Stock data for {symbol.upper()} from {start_date} to {end_date}\n"
    header += f"# Total records: {len(filtered)}\n"
    header += f"# Data retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
    return header + csv_string


def get_stock_dataframe(symbol: str, start_date: str, end_date: str) -> pd.DataFrame:
    data = _fetch_akshare_dataframe(symbol, start_date, end_date)
    if data.empty:
        return data
    return data[(data["Date"] >= start_date) & (data["Date"] <= end_date)].copy()
