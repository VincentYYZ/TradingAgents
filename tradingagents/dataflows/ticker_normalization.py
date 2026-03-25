import re


A_SHARE_BASE_PATTERN = re.compile(r"^\d{6}$")
A_SHARE_SUFFIX_PATTERN = re.compile(r"^(\d{6})\.(SH|SZ|SS)$")


def is_a_share_symbol(symbol: str) -> bool:
    if not symbol:
        return False
    normalized = symbol.strip().upper()
    return bool(A_SHARE_BASE_PATTERN.fullmatch(normalized) or A_SHARE_SUFFIX_PATTERN.fullmatch(normalized))


def detect_market_profile(symbol: str, configured_market_profile: str | None = None) -> str:
    if configured_market_profile and configured_market_profile != "auto":
        return configured_market_profile
    if is_a_share_symbol(symbol):
        return "cn_a_share"
    return "us_equity"


def _normalize_a_share_base(symbol: str) -> str:
    normalized = symbol.strip().upper()
    suffix_match = A_SHARE_SUFFIX_PATTERN.fullmatch(normalized)
    if suffix_match:
        return suffix_match.group(1)
    if A_SHARE_BASE_PATTERN.fullmatch(normalized):
        return normalized
    raise ValueError(
        "Unsupported A-share ticker format. Use a 6-digit code like 600519 or an exchange-suffixed code like 600519.SH."
    )


def _normalize_a_share_exchange(symbol: str) -> str:
    normalized = symbol.strip().upper()
    suffix_match = A_SHARE_SUFFIX_PATTERN.fullmatch(normalized)
    if suffix_match:
        exchange = suffix_match.group(2)
        if exchange == "SS":
            exchange = "SH"
        return exchange

    base = _normalize_a_share_base(normalized)
    if base.startswith(("6", "9")):
        return "SH"
    return "SZ"


def normalize_symbol_for_vendor(symbol: str, vendor: str, market_profile: str | None = None) -> str:
    resolved_market = detect_market_profile(symbol, market_profile)
    normalized = symbol.strip().upper()

    if resolved_market != "cn_a_share":
        return normalized

    base = _normalize_a_share_base(normalized)
    exchange = _normalize_a_share_exchange(normalized)

    if vendor == "akshare":
        return base

    if vendor == "akshare_em":
        return f"{exchange}{base}"

    if vendor == "yfinance":
        if exchange == "SZ":
            return f"{base}.SZ"
        return f"{base}.SS"

    return base
