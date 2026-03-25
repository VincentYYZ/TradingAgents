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
        for attempt in range(3):
            try:
                with _AKSHARE_REQUEST_GATE:
                    data = ak.stock_zh_a_hist(
                        symbol=normalized_symbol,
                        period="daily",
                        start_date=start_date.replace("-", ""),
                        end_date=end_date.replace("-", ""),
                        adjust="qfq",
                    )
                last_error = None
                break
            except Exception as exc:
                last_error = exc
                if attempt < 2:
                    time.sleep(1.0 + attempt)

        if last_error is not None:
            raise last_error

        if data is None or data.empty:
            return pd.DataFrame()

        data = data.rename(columns=COLUMN_MAP)
        if "Date" not in data.columns:
            raise ValueError(f"Unexpected Akshare response columns: {list(data.columns)}")

        data["Date"] = pd.to_datetime(data["Date"])
        data = data.sort_values("Date").reset_index(drop=True)

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
            if column in data.columns:
                data[column] = pd.to_numeric(data[column], errors="coerce")

        data.to_csv(cache_file, index=False)
        return data


def get_stock(symbol: str, start_date: str, end_date: str):
    datetime.strptime(start_date, "%Y-%m-%d")
    datetime.strptime(end_date, "%Y-%m-%d")

    data = _fetch_akshare_dataframe(symbol, start_date, end_date)
    if data.empty:
        return f"No data found for symbol '{symbol}' between {start_date} and {end_date}"

    filtered = data[(data["Date"] >= start_date) & (data["Date"] <= end_date)].copy()
    if filtered.empty:
        return f"No data found for symbol '{symbol}' between {start_date} and {end_date}"

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
