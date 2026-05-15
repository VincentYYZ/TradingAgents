import re

from langchain_core.tools import tool
from typing import Annotated
from tradingagents.dataflows.interface import route_to_vendor


def _coerce_a_share_ticker(ticker: str) -> str:
    raw = str(ticker or "").strip().upper()
    prefix_match = re.search(r"\b(SH|SZ|SS)(\d{6})\b", raw)
    if prefix_match:
        return prefix_match.group(2)
    suffix_match = re.search(r"\b(\d{6})\.(SH|SZ|SS)\b", raw)
    if suffix_match:
        return suffix_match.group(1)
    base_match = re.search(r"\b\d{6}\b", raw)
    if base_match:
        return base_match.group(0)
    return raw

@tool
def get_news(
    ticker: Annotated[str, "Ticker symbol"],
    start_date: Annotated[str, "Start date in yyyy-mm-dd format"],
    end_date: Annotated[str, "End date in yyyy-mm-dd format"],
) -> str:
    """
    Retrieve news data for a given ticker symbol.
    Uses the configured news_data vendor.
    Args:
        ticker (str): Ticker symbol
        start_date (str): Start date in yyyy-mm-dd format
        end_date (str): End date in yyyy-mm-dd format
    Returns:
        str: A formatted string containing news data
    """
    normalized_ticker = _coerce_a_share_ticker(ticker)
    try:
        return route_to_vendor("get_news", normalized_ticker, start_date, end_date)
    except Exception as exc:
        message = str(exc)
        if "Unsupported A-share ticker format" in message or "All vendor implementations failed for method 'get_news'" in message:
            return (
                f"No company news data is available for ticker input '{ticker}' "
                f"between {start_date} and {end_date}. "
                f"The news tool expected a 6-digit A-share code, for example 600519."
            )
        raise

@tool
def get_global_news(
    curr_date: Annotated[str, "Current date in yyyy-mm-dd format"],
    look_back_days: Annotated[int, "Number of days to look back"] = 7,
    limit: Annotated[int, "Maximum number of articles to return"] = 5,
) -> str:
    """
    Retrieve global news data.
    Uses the configured news_data vendor.
    Args:
        curr_date (str): Current date in yyyy-mm-dd format
        look_back_days (int): Number of days to look back (default 7)
        limit (int): Maximum number of articles to return (default 5)
    Returns:
        str: A formatted string containing global news data
    """
    return route_to_vendor("get_global_news", curr_date, look_back_days, limit)

@tool
def get_insider_sentiment(
    ticker: Annotated[str, "ticker symbol for the company"],
    curr_date: Annotated[str, "current date you are trading at, yyyy-mm-dd"],
) -> str:
    """
    Retrieve insider sentiment information about a company.
    Uses the configured news_data vendor.
    Args:
        ticker (str): Ticker symbol of the company
        curr_date (str): Current date you are trading at, yyyy-mm-dd
    Returns:
        str: A report of insider sentiment data
    """
    return route_to_vendor("get_insider_sentiment", ticker, curr_date)

@tool
def get_insider_transactions(
    ticker: Annotated[str, "ticker symbol"],
    curr_date: Annotated[str, "current date you are trading at, yyyy-mm-dd"],
) -> str:
    """
    Retrieve insider transaction information about a company.
    Uses the configured news_data vendor.
    Args:
        ticker (str): Ticker symbol of the company
        curr_date (str): Current date you are trading at, yyyy-mm-dd
    Returns:
        str: A report of insider transaction data
    """
    return route_to_vendor("get_insider_transactions", ticker, curr_date)
