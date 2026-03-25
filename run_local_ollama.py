import argparse
import json
from pathlib import Path

from dotenv import load_dotenv

from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.graph.trading_graph import TradingAgentsGraph


def parse_args():
    parser = argparse.ArgumentParser(description="Run TradingAgents with a local Ollama model.")
    parser.add_argument("--config", default="local_ollama_config.json", help="Path to the JSON config file.")
    parser.add_argument("--ticker", help="Ticker symbol to analyze.")
    parser.add_argument("--date", dest="trade_date", help="Trade date in YYYY-MM-DD format.")
    parser.add_argument("--model", help="Override both deep and quick thinking models.")
    parser.add_argument(
        "--analysts",
        nargs="+",
        choices=["market", "social", "news", "fundamentals"],
        help="Analyst nodes to enable.",
    )
    parser.add_argument("--debug", action="store_true", help="Enable LangGraph debug streaming.")
    return parser.parse_args()


def main():
    load_dotenv()
    args = parse_args()

    config_path = Path(args.config)
    runtime_config = json.loads(config_path.read_text())

    selected_analysts = args.analysts or runtime_config.pop("selected_analysts", ["market"])
    ticker = args.ticker or runtime_config.pop("ticker", "NVDA")
    trade_date = args.trade_date or runtime_config.pop("trade_date", "2024-05-10")

    if args.model:
        runtime_config["deep_think_llm"] = args.model
        runtime_config["quick_think_llm"] = args.model

    config = DEFAULT_CONFIG.copy()
    config.update(runtime_config)

    ta = TradingAgentsGraph(
        selected_analysts=selected_analysts,
        debug=args.debug,
        config=config,
    )
    _, decision = ta.propagate(ticker, trade_date)

    print(f"Ticker: {ticker}")
    print(f"Trade date: {trade_date}")
    print(f"Model: {config['quick_think_llm']}")
    print(f"Analysts: {', '.join(selected_analysts)}")
    print()
    print("Final decision:")
    print()
    print(decision)


if __name__ == "__main__":
    main()
