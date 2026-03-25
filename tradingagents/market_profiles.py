from copy import deepcopy


MARKET_PROFILES = {
    "us_equity": {
        "display_name": "US Equity",
        "supported_analysts": ["market", "social", "news", "fundamentals"],
        "default_ticker": "SPY",
        "ticker_examples": ["SPY", "AAPL", "NVDA"],
        "data_vendors": {
            "core_stock_apis": "yfinance",
            "technical_indicators": "yfinance",
        },
    },
    "cn_a_share": {
        "display_name": "China A-Share",
        "supported_analysts": ["market", "fundamentals", "news"],
        "default_ticker": "600519.SH",
        "ticker_examples": ["600519.SH", "000001.SZ", "601318.SH"],
        "data_vendors": {
            "core_stock_apis": "akshare",
            "technical_indicators": "akshare",
            "fundamental_data": "akshare",
            "news_data": "china_news",
        },
    },
}


def get_market_profile(profile_name: str) -> dict:
    if profile_name not in MARKET_PROFILES:
        raise ValueError(f"Unsupported market profile: {profile_name}")
    return deepcopy(MARKET_PROFILES[profile_name])


def apply_market_profile(config: dict, market_profile: str) -> dict:
    updated = deepcopy(config)
    profile = get_market_profile(market_profile)

    updated["market_profile"] = market_profile
    data_vendors = deepcopy(updated.get("data_vendors", {}))
    data_vendors.update(profile.get("data_vendors", {}))
    updated["data_vendors"] = data_vendors

    return updated


def get_default_ticker_for_market(market_profile: str) -> str:
    profile = get_market_profile(market_profile)
    return profile["default_ticker"]


def get_supported_analysts(market_profile: str) -> list[str]:
    profile = get_market_profile(market_profile)
    return list(profile["supported_analysts"])


def validate_selected_analysts(market_profile: str, selected_analysts) -> None:
    supported = set(get_supported_analysts(market_profile))
    normalized = [getattr(analyst, "value", analyst) for analyst in selected_analysts]
    invalid = [analyst for analyst in normalized if analyst not in supported]

    if invalid:
        supported_list = ", ".join(sorted(supported))
        invalid_list = ", ".join(invalid)
        raise ValueError(
            f"Market profile '{market_profile}' does not support analysts: {invalid_list}. "
            f"Supported analysts: {supported_list}."
        )
