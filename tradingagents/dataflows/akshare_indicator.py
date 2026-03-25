from datetime import datetime
from dateutil.relativedelta import relativedelta

from stockstats import wrap

from .akshare_stock import get_stock_dataframe


INDICATOR_DESCRIPTIONS = {
    "close_50_sma": "50 SMA: A medium-term trend indicator. Usage: Identify trend direction and serve as dynamic support/resistance. Tips: It lags price; combine with faster indicators for timely signals.",
    "close_200_sma": "200 SMA: A long-term trend benchmark. Usage: Confirm overall market trend and identify golden/death cross setups. Tips: It reacts slowly; best for strategic trend confirmation rather than frequent trading entries.",
    "close_10_ema": "10 EMA: A responsive short-term average. Usage: Capture quick shifts in momentum and potential entry points. Tips: Prone to noise in choppy markets; use alongside longer averages for filtering false signals.",
    "macd": "MACD: Computes momentum via differences of EMAs. Usage: Look for crossovers and divergence as signals of trend changes. Tips: Confirm with other indicators in low-volatility or sideways markets.",
    "macds": "MACD Signal: An EMA smoothing of the MACD line. Usage: Use crossovers with the MACD line to trigger trades. Tips: Should be part of a broader strategy to avoid false positives.",
    "macdh": "MACD Histogram: Shows the gap between the MACD line and its signal. Usage: Visualize momentum strength and spot divergence early. Tips: Can be volatile; complement with additional filters in fast-moving markets.",
    "rsi": "RSI: Measures momentum to flag overbought/oversold conditions. Usage: Apply 70/30 thresholds and watch for divergence to signal reversals. Tips: In strong trends, RSI may remain extreme; always cross-check with trend analysis.",
    "boll": "Bollinger Middle: A 20 SMA serving as the basis for Bollinger Bands. Usage: Acts as a dynamic benchmark for price movement. Tips: Combine with the upper and lower bands to effectively spot breakouts or reversals.",
    "boll_ub": "Bollinger Upper Band: Typically 2 standard deviations above the middle line. Usage: Signals potential overbought conditions and breakout zones. Tips: Confirm signals with other tools; prices may ride the band in strong trends.",
    "boll_lb": "Bollinger Lower Band: Typically 2 standard deviations below the middle line. Usage: Indicates potential oversold conditions. Tips: Use additional analysis to avoid false reversal signals.",
    "atr": "ATR: Averages true range to measure volatility. Usage: Set stop-loss levels and adjust position sizes based on current market volatility. Tips: It's a reactive measure, so use it as part of a broader risk management strategy.",
    "vwma": "VWMA: A moving average weighted by volume. Usage: Confirm trends by integrating price action with volume data. Tips: Watch for skewed results from volume spikes; use in combination with other volume analyses.",
    "mfi": "MFI: A momentum indicator that uses both price and volume to measure buying and selling pressure. Usage: Identify overbought (>80) or oversold (<20) conditions and confirm trend strength. Tips: Use alongside RSI or MACD to confirm signals.",
}


def get_indicator(symbol: str, indicator: str, curr_date: str, look_back_days: int) -> str:
    if indicator not in INDICATOR_DESCRIPTIONS:
        raise ValueError(
            f"Indicator {indicator} is not supported. Please choose from: {list(INDICATOR_DESCRIPTIONS.keys())}"
        )

    end_dt = datetime.strptime(curr_date, "%Y-%m-%d")
    start_dt = end_dt - relativedelta(days=max(look_back_days + 400, 450))
    fetch_start = start_dt.strftime("%Y-%m-%d")

    data = get_stock_dataframe(symbol, fetch_start, curr_date)
    if data.empty:
        return f"No indicator data found for symbol '{symbol}' up to {curr_date}"

    data = data.copy()
    data["Date"] = data["Date"].dt.strftime("%Y-%m-%d")
    df = wrap(data)
    df[indicator]

    lower_bound = (end_dt - relativedelta(days=look_back_days)).strftime("%Y-%m-%d")
    relevant_dates = []
    current_dt = end_dt
    while current_dt >= datetime.strptime(lower_bound, "%Y-%m-%d"):
        relevant_dates.append(current_dt.strftime("%Y-%m-%d"))
        current_dt = current_dt - relativedelta(days=1)

    lines = []
    for date_str in relevant_dates:
        matching_rows = df[df["Date"].str.startswith(date_str)]
        if matching_rows.empty:
            value = "N/A: Not a trading day (weekend or holiday)"
        else:
            value = matching_rows[indicator].values[0]
        lines.append(f"{date_str}: {value}")

    description = INDICATOR_DESCRIPTIONS[indicator]
    return (
        f"## {indicator} values from {lower_bound} to {curr_date}:\n\n"
        + "\n".join(lines)
        + "\n\n"
        + description
    )
