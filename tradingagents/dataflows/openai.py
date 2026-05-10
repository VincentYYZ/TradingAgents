import os

from openai import OpenAI
from .config import get_config


def get_stock_news_openai(query, start_date, end_date):
    config = get_config()
    client = OpenAI(
        base_url=config["backend_url"],
        api_key=config.get("api_key") or os.getenv("OPENAI_API_KEY", "ollama"),
    )

    response = client.chat.completions.create(
        model=config["quick_think_llm"],
        messages=[
            {
                "role": "system",
                "content": f"Can you search Social Media for {query} from {start_date} to {end_date}? Make sure you only get the data posted during that period.",
            }
        ],
        temperature=1,
        max_tokens=4096,
        top_p=1,
    )

    return response.choices[0].message.content


def get_global_news_openai(curr_date, look_back_days=7, limit=5):
    config = get_config()
    client = OpenAI(
        base_url=config["backend_url"],
        api_key=config.get("api_key") or os.getenv("OPENAI_API_KEY", "ollama"),
    )

    response = client.chat.completions.create(
        model=config["quick_think_llm"],
        messages=[
            {
                "role": "system",
                "content": f"Can you search global or macroeconomics news from {look_back_days} days before {curr_date} to {curr_date} that would be informative for trading purposes? Make sure you only get the data posted during that period. Limit the results to {limit} articles.",
            }
        ],
        temperature=1,
        max_tokens=4096,
        top_p=1,
    )

    return response.choices[0].message.content


def get_fundamentals_openai(ticker, curr_date):
    config = get_config()
    client = OpenAI(
        base_url=config["backend_url"],
        api_key=config.get("api_key") or os.getenv("OPENAI_API_KEY", "ollama"),
    )

    response = client.chat.completions.create(
        model=config["quick_think_llm"],
        messages=[
            {
                "role": "system",
                "content": f"Can you search Fundamental for discussions on {ticker} during of the month before {curr_date} to the month of {curr_date}. Make sure you only get the data posted during that period. List as a table, with PE/PS/Cash flow/ etc",
            }
        ],
        temperature=1,
        max_tokens=4096,
        top_p=1,
    )

    return response.choices[0].message.content