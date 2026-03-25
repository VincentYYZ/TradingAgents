from enum import Enum


class AnalystType(str, Enum):
    MARKET = "market"
    SOCIAL = "social"
    NEWS = "news"
    FUNDAMENTALS = "fundamentals"


class MarketProfileType(str, Enum):
    US_EQUITY = "us_equity"
    CN_A_SHARE = "cn_a_share"
