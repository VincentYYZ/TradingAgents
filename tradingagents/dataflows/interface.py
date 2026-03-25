from typing import Annotated

from .akshare_fundamentals import (
    get_balance_sheet as get_akshare_balance_sheet,
    get_cashflow as get_akshare_cashflow,
    get_fundamentals as get_akshare_fundamentals,
    get_income_statement as get_akshare_income_statement,
)
from .akshare_indicator import get_indicator as get_akshare_indicator
from .akshare_stock import get_stock as get_akshare_stock
from .china_news import get_global_news as get_china_global_news, get_news as get_china_news
from .local import (
    get_YFin_data,
    get_finnhub_news,
    get_finnhub_company_insider_sentiment,
    get_finnhub_company_insider_transactions,
    get_simfin_balance_sheet,
    get_simfin_cashflow,
    get_simfin_income_statements,
    get_reddit_global_news,
    get_reddit_company_news,
)
from .y_finance import (
    get_YFin_data_online,
    get_stock_stats_indicators_window,
    get_balance_sheet as get_yfinance_balance_sheet,
    get_cashflow as get_yfinance_cashflow,
    get_income_statement as get_yfinance_income_statement,
    get_insider_transactions as get_yfinance_insider_transactions,
)
from .google import get_google_news
from .openai import get_stock_news_openai, get_global_news_openai, get_fundamentals_openai
from .alpha_vantage import (
    get_stock as get_alpha_vantage_stock,
    get_indicator as get_alpha_vantage_indicator,
    get_fundamentals as get_alpha_vantage_fundamentals,
    get_balance_sheet as get_alpha_vantage_balance_sheet,
    get_cashflow as get_alpha_vantage_cashflow,
    get_income_statement as get_alpha_vantage_income_statement,
    get_insider_transactions as get_alpha_vantage_insider_transactions,
    get_news as get_alpha_vantage_news,
)
from .alpha_vantage_common import AlphaVantageRateLimitError
from .config import get_config
from .ticker_normalization import normalize_symbol_for_vendor

TOOLS_CATEGORIES = {
    "core_stock_apis": {"description": "OHLCV stock price data", "tools": ["get_stock_data"]},
    "technical_indicators": {"description": "Technical analysis indicators", "tools": ["get_indicators"]},
    "fundamental_data": {
        "description": "Company fundamentals",
        "tools": ["get_fundamentals", "get_balance_sheet", "get_cashflow", "get_income_statement"],
    },
    "news_data": {
        "description": "News (public/insiders, original/processed)",
        "tools": ["get_news", "get_global_news", "get_insider_sentiment", "get_insider_transactions"],
    },
}

VENDOR_LIST = ["local", "yfinance", "alpha_vantage", "openai", "google", "akshare", "china_news"]

VENDOR_METHODS = {
    "get_stock_data": {
        "alpha_vantage": get_alpha_vantage_stock,
        "yfinance": get_YFin_data_online,
        "akshare": get_akshare_stock,
        "local": get_YFin_data,
    },
    "get_indicators": {
        "alpha_vantage": get_alpha_vantage_indicator,
        "yfinance": get_stock_stats_indicators_window,
        "akshare": get_akshare_indicator,
        "local": get_stock_stats_indicators_window,
    },
    "get_fundamentals": {
        "alpha_vantage": get_alpha_vantage_fundamentals,
        "openai": get_fundamentals_openai,
        "akshare": get_akshare_fundamentals,
    },
    "get_balance_sheet": {
        "alpha_vantage": get_alpha_vantage_balance_sheet,
        "yfinance": get_yfinance_balance_sheet,
        "akshare": get_akshare_balance_sheet,
        "local": get_simfin_balance_sheet,
    },
    "get_cashflow": {
        "alpha_vantage": get_alpha_vantage_cashflow,
        "yfinance": get_yfinance_cashflow,
        "akshare": get_akshare_cashflow,
        "local": get_simfin_cashflow,
    },
    "get_income_statement": {
        "alpha_vantage": get_alpha_vantage_income_statement,
        "yfinance": get_yfinance_income_statement,
        "akshare": get_akshare_income_statement,
        "local": get_simfin_income_statements,
    },
    "get_news": {
        "china_news": get_china_news,
        "alpha_vantage": get_alpha_vantage_news,
        "openai": get_stock_news_openai,
        "google": get_google_news,
        "local": [get_finnhub_news, get_reddit_company_news, get_google_news],
    },
    "get_global_news": {
        "china_news": get_china_global_news,
        "openai": get_global_news_openai,
        "local": get_reddit_global_news,
    },
    "get_insider_sentiment": {"local": get_finnhub_company_insider_sentiment},
    "get_insider_transactions": {
        "alpha_vantage": get_alpha_vantage_insider_transactions,
        "yfinance": get_yfinance_insider_transactions,
        "local": get_finnhub_company_insider_transactions,
    },
}

SYMBOL_FIRST_METHODS = {
    "get_stock_data",
    "get_indicators",
    "get_fundamentals",
    "get_balance_sheet",
    "get_cashflow",
    "get_income_statement",
    "get_news",
    "get_insider_sentiment",
    "get_insider_transactions",
}


def get_category_for_method(method: str) -> str:
    for category, info in TOOLS_CATEGORIES.items():
        if method in info["tools"]:
            return category
    raise ValueError(f"Method '{method}' not found in any category")


def get_vendor(category: str, method: str = None) -> str:
    config = get_config()
    if method:
        tool_vendors = config.get("tool_vendors", {})
        if method in tool_vendors:
            return tool_vendors[method]
    return config.get("data_vendors", {}).get(category, "default")


def _normalize_args_for_vendor(method: str, vendor: str, args: tuple) -> tuple:
    if not args or method not in SYMBOL_FIRST_METHODS:
        return args

    config = get_config()
    market_profile = config.get("market_profile", "us_equity")
    normalized_symbol = normalize_symbol_for_vendor(args[0], vendor, market_profile)
    return (normalized_symbol,) + tuple(args[1:])


def _should_disable_auto_fallback(method: str) -> bool:
    config = get_config()
    market_profile = config.get("market_profile", "us_equity")
    return market_profile == "cn_a_share" and method == "get_indicators"


def route_to_vendor(method: str, *args, **kwargs):
    category = get_category_for_method(method)
    vendor_config = get_vendor(category, method)
    primary_vendors = [v.strip() for v in vendor_config.split(",")]

    if method not in VENDOR_METHODS:
        raise ValueError(f"Method '{method}' not supported")

    all_available_vendors = list(VENDOR_METHODS[method].keys())
    fallback_vendors = primary_vendors.copy()
    if not _should_disable_auto_fallback(method):
        for vendor in all_available_vendors:
            if vendor not in fallback_vendors:
                fallback_vendors.append(vendor)

    primary_str = " → ".join(primary_vendors)
    fallback_str = " → ".join(fallback_vendors)
    print(f"DEBUG: {method} - Primary: [{primary_str}] | Full fallback order: [{fallback_str}]")

    results = []
    vendor_attempt_count = 0

    for vendor in fallback_vendors:
        if vendor not in VENDOR_METHODS[method]:
            if vendor in primary_vendors:
                print(f"INFO: Vendor '{vendor}' not supported for method '{method}', falling back to next vendor")
            continue

        vendor_impl = VENDOR_METHODS[method][vendor]
        vendor_attempt_count += 1
        vendor_type = "PRIMARY" if vendor in primary_vendors else "FALLBACK"
        print(f"DEBUG: Attempting {vendor_type} vendor '{vendor}' for {method} (attempt #{vendor_attempt_count})")

        if isinstance(vendor_impl, list):
            vendor_methods = [(impl, vendor) for impl in vendor_impl]
            print(f"DEBUG: Vendor '{vendor}' has multiple implementations: {len(vendor_methods)} functions")
        else:
            vendor_methods = [(vendor_impl, vendor)]

        vendor_results = []
        for impl_func, vendor_name in vendor_methods:
            try:
                call_args = _normalize_args_for_vendor(method, vendor_name, args)
                print(f"DEBUG: Calling {impl_func.__name__} from vendor '{vendor_name}'...")
                result = impl_func(*call_args, **kwargs)
                vendor_results.append(result)
                print(f"SUCCESS: {impl_func.__name__} from vendor '{vendor_name}' completed successfully")
            except AlphaVantageRateLimitError as e:
                if vendor == "alpha_vantage":
                    print("RATE_LIMIT: Alpha Vantage rate limit exceeded, falling back to next available vendor")
                    print(f"DEBUG: Rate limit details: {e}")
                continue
            except Exception as e:
                print(f"FAILED: {impl_func.__name__} from vendor '{vendor_name}' failed: {e}")
                continue

        if vendor_results:
            results.extend(vendor_results)
            result_summary = f"Got {len(vendor_results)} result(s)"
            print(f"SUCCESS: Vendor '{vendor}' succeeded - {result_summary}")
            if len(primary_vendors) == 1:
                print(f"DEBUG: Stopping after successful vendor '{vendor}' (single-vendor config)")
                break
        else:
            print(f"FAILED: Vendor '{vendor}' produced no results")

    if not results:
        print(f"FAILURE: All {vendor_attempt_count} vendor attempts failed for method '{method}'")
        raise RuntimeError(f"All vendor implementations failed for method '{method}'")

    print(f"FINAL: Method '{method}' completed with {len(results)} result(s) from {vendor_attempt_count} vendor attempt(s)")
    if len(results) == 1:
        return results[0]
    return "\n".join(str(result) for result in results)
