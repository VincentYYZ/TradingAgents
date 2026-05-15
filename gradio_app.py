import io
import json
import os
import re
import socket
import threading
import textwrap
import traceback
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime
from pathlib import Path

import gradio as gr
from dotenv import load_dotenv

from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.market_profiles import MARKET_PROFILES, apply_market_profile


PROVIDER_DEFAULTS = {
    "openai": {
        "backend_url": "https://api.openai.com/v1",
        "quick_model": "gpt-4o-mini",
        "deep_model": "o4-mini",
        "embedding_model": "text-embedding-3-small",
    },
    "anthropic": {
        "backend_url": "https://api.anthropic.com/",
        "quick_model": "claude-3-5-haiku-latest",
        "deep_model": "claude-sonnet-4-0",
        "embedding_model": "text-embedding-3-small",
    },
    "google": {
        "backend_url": "https://generativelanguage.googleapis.com/v1",
        "quick_model": "gemini-2.0-flash",
        "deep_model": "gemini-2.5-pro-preview-06-05",
        "embedding_model": "text-embedding-3-small",
    },
    "openrouter": {
        "backend_url": "https://openrouter.ai/api/v1",
        "quick_model": "meta-llama/llama-3.3-8b-instruct:free",
        "deep_model": "deepseek/deepseek-chat-v3-0324:free",
        "embedding_model": "text-embedding-3-small",
    },
    "lucen_openai": {
        "backend_url": "https://lucen.cc",
        "quick_model": "gpt-5.5",
        "deep_model": "gpt-5.5",
        "embedding_model": "text-embedding-3-small",
    },
    "luchikey_openai": {
        "backend_url": "https://sub2api.luchikey.cn/v1",
        "quick_model": "gpt-5.5",
        "deep_model": "gpt-5.5",
        "embedding_model": "text-embedding-3-small",
    },
    "vllm": {
        "backend_url": "http://127.0.0.1:8000/v1",
        "quick_model": "Qwen3.6-27B",
        "deep_model": "Qwen3.6-27B",
        "embedding_model": "",
    },
    "ollama": {
        "backend_url": "http://localhost:11434/v1",
        "quick_model": "qwen3.6:35b",
        "deep_model": "qwen3.6:35b",
        "embedding_model": "nomic-embed-text",
    },
}


LLM_PROVIDERS_LOCAL_PATH = Path(__file__).resolve().parent / "llm_providers.local.json"
LLM_PROVIDERS_EXAMPLE_PATH = Path(__file__).resolve().parent / "llm_providers.example.json"


def _read_llm_provider_file(path, include_api_keys):
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"WARNING: Failed to load LLM provider config from {path}: {exc}")
        return {}
    providers = data.get("providers", data)
    if not isinstance(providers, dict):
        return {}
    result = {}
    for name, values in providers.items():
        if not isinstance(values, dict):
            continue
        cleaned = dict(values)
        if not include_api_keys:
            cleaned.pop("api_key", None)
        result[str(name)] = cleaned
    return result


def load_llm_provider_overrides():
    merged = {}
    for path, include_api_keys in (
        (LLM_PROVIDERS_EXAMPLE_PATH, False),
        (LLM_PROVIDERS_LOCAL_PATH, True),
    ):
        if not path.exists():
            continue
        for name, values in _read_llm_provider_file(path, include_api_keys).items():
            merged.setdefault(name, {}).update(values)
    return merged


LLM_PROVIDER_OVERRIDES = load_llm_provider_overrides()

for provider_name, provider_values in LLM_PROVIDER_OVERRIDES.items():
    defaults = PROVIDER_DEFAULTS.setdefault(provider_name, {})
    for key in ("backend_url", "quick_model", "deep_model", "embedding_model"):
        if provider_values.get(key) is not None:
            defaults[key] = provider_values.get(key, "")


def get_provider_config(provider):
    config = dict(PROVIDER_DEFAULTS.get(provider, {}))
    config.update(LLM_PROVIDER_OVERRIDES.get(provider, {}))
    return config


def get_provider_api_key(provider):
    config = get_provider_config(provider)
    return (config.get("api_key") or "").strip()


ANALYST_LABELS = {
    "market": "市场分析师",
    "social": "社交情绪分析师",
    "news": "新闻分析师",
    "fundamentals": "基本面分析师",
}

AGENT_LABELS = {
    "Market Analyst": "市场分析师",
    "Social Analyst": "社交情绪分析师",
    "News Analyst": "新闻分析师",
    "Fundamentals Analyst": "基本面分析师",
    "Bull Researcher": "看多研究员",
    "Bear Researcher": "看空研究员",
    "Research Manager": "研究经理",
    "Trader": "交易员",
    "Risky Analyst": "激进风险分析师",
    "Neutral Analyst": "中性风险分析师",
    "Safe Analyst": "稳健风险分析师",
    "Portfolio Manager": "组合经理",
}

STATUS_ORDER = [
    "Market Analyst",
    "Social Analyst",
    "News Analyst",
    "Fundamentals Analyst",
    "Bull Researcher",
    "Bear Researcher",
    "Research Manager",
    "Trader",
    "Risky Analyst",
    "Neutral Analyst",
    "Safe Analyst",
    "Portfolio Manager",
]

STATUS_GROUPS = {
    "分析师团队": ["Market Analyst", "Social Analyst", "News Analyst", "Fundamentals Analyst"],
    "研究团队": ["Bull Researcher", "Bear Researcher", "Research Manager"],
    "交易团队": ["Trader"],
    "风险团队": ["Risky Analyst", "Neutral Analyst", "Safe Analyst"],
    "组合管理": ["Portfolio Manager"],
}

REPORT_TITLES = {
    "market_report": "市场分析",
    "sentiment_report": "社交情绪分析",
    "news_report": "新闻分析",
    "fundamentals_report": "基本面分析",
    "investment_plan": "研究团队结论",
    "trader_investment_plan": "交易团队计划",
    "final_trade_decision": "组合管理决策",
}

REPORT_KEYS = list(REPORT_TITLES.keys())
STATUS_THEME = {
    "pending": ("#8a6d3b", "#fff7e6", "等待中"),
    "in_progress": ("#0b57d0", "#e8f0fe", "进行中"),
    "completed": ("#1a7f37", "#ecfdf3", "已完成"),
    "error": ("#b42318", "#fef3f2", "错误"),
}

REPORT_TEXT_REPLACEMENTS = {
    "### Research Manager Decision": "### 研究经理决策",
    "### Portfolio Manager Decision": "### 组合经理决策",
    "## Error": "## 错误详情",
    "Technical indicator": "技术指标",
    "is temporarily unavailable for symbol": "暂时不可用，股票代码",
    "Reason:": "原因：",
    "No data found for symbol": "未找到对应股票数据，股票代码",
    "No indicator data found for symbol": "未找到技术指标数据，股票代码",
    "up to": "截至",
    "between": "区间",
}


def extract_content_string(content):
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict):
                if item.get("type") == "text":
                    parts.append(item.get("text", ""))
                elif item.get("type") == "tool_use":
                    parts.append(f"[Tool: {item.get('name', 'unknown')}]")
            else:
                parts.append(str(item))
        return " ".join(parts)
    return str(content)


def localize_report_text(content):
    text = extract_content_string(content).strip()
    if not text:
        return ""
    for source, target in REPORT_TEXT_REPLACEMENTS.items():
        text = text.replace(source, target)
    return text


def format_report_content(section, content):
    localized = localize_report_text(content)
    if not localized:
        return ""
    title = REPORT_TITLES.get(section, "报告")
    if localized.startswith("#"):
        return localized
    return f"# {title}\n\n{localized}"


class StreamBuffer(io.TextIOBase):
    def __init__(self):
        self.buffer = ""
        self.lines = []

    def write(self, text):
        if not text:
            return 0
        self.buffer += text
        while "\n" in self.buffer:
            line, self.buffer = self.buffer.split("\n", 1)
            if line.strip():
                self.lines.append(line)
        return len(text)

    def flush(self):
        if self.buffer.strip():
            self.lines.append(self.buffer)
        self.buffer = ""

    def content(self):
        merged = self.lines[:]
        if self.buffer.strip():
            merged.append(self.buffer)
        return "\n".join(merged)


class RunCollector:
    def __init__(self, selections):
        self.selections = selections
        self.statuses = {agent: "pending" for agent in STATUS_ORDER}
        self.messages = []
        self.tools = []
        self.reports = {key: "" for key in REPORT_KEYS}
        self.final_state = None
        self.decision = ""
        self.full_report = ""
        self.run_message = "未运行"
        self.output_dir = ""
        self.exported_md_path = ""
        self.token_usage = {"input": 0, "output": 0, "total": 0}
        self._counted_usage_keys = set()

    def set_status(self, agent, status):
        if agent in self.statuses:
            self.statuses[agent] = status

    def set_report(self, section, content):
        if section in self.reports and content:
            self.reports[section] = format_report_content(section, content)

    def set_research_team_status(self, status):
        for agent in ["Bull Researcher", "Bear Researcher", "Research Manager", "Trader"]:
            self.set_status(agent, status)

    def mark_initial_status(self):
        for candidate in ["market", "social", "news", "fundamentals"]:
            if candidate in self.selections["analysts"]:
                self.set_status(f"{candidate.capitalize()} Analyst" if candidate != "fundamentals" else "Fundamentals Analyst", "in_progress")
                break

    def add_message(self, kind, content):
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.messages.append(f"[{timestamp}] [{kind}] {content}")

    def add_tool(self, name, args):
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.tools.append(f"[{timestamp}] {name}({args})")

    def merge_usage(self, message):
        usage = getattr(message, "usage_metadata", None)
        response_metadata = getattr(message, "response_metadata", None) or {}
        if not usage:
            usage = response_metadata.get("token_usage") or response_metadata.get("usage") or {}
        if not usage:
            return

        if not isinstance(usage, dict):
            usage = dict(usage)

        input_tokens = int(usage.get("input_tokens") or usage.get("prompt_tokens") or 0)
        output_tokens = int(usage.get("output_tokens") or usage.get("completion_tokens") or 0)
        total_tokens = int(usage.get("total_tokens") or 0) or (input_tokens + output_tokens)

        if input_tokens <= 0 and output_tokens <= 0 and total_tokens <= 0:
            return

        message_key = getattr(message, "id", None) or response_metadata.get("id") or (
            f"{type(message).__name__}|{extract_content_string(getattr(message, 'content', ''))[:200]}|"
            f"{input_tokens}|{output_tokens}|{total_tokens}"
        )
        if message_key in self._counted_usage_keys:
            return
        self._counted_usage_keys.add(message_key)

        self.token_usage["input"] += input_tokens
        self.token_usage["output"] += output_tokens
        self.token_usage["total"] += total_tokens

    def token_usage_markdown(self):
        total_tokens = self.token_usage["total"] or (self.token_usage["input"] + self.token_usage["output"])
        if total_tokens <= 0:
            return "Token 使用量：—"
        return (
            f"Token 使用量：总计 `{total_tokens}`，输入 `{self.token_usage['input']}`，"
            f"输出 `{self.token_usage['output']}`"
        )

    def handle_chunk(self, chunk):
        messages = chunk.get("messages", [])
        if messages:
            last_message = messages[-1]
            self.merge_usage(last_message)
            if hasattr(last_message, "content"):
                self.add_message("Reasoning", extract_content_string(last_message.content))
            else:
                self.add_message("System", str(last_message))
            if hasattr(last_message, "tool_calls"):
                for tool_call in last_message.tool_calls:
                    if isinstance(tool_call, dict):
                        self.add_tool(tool_call.get("name", "unknown"), tool_call.get("args", {}))
                    else:
                        self.add_tool(tool_call.name, tool_call.args)

        if chunk.get("market_report"):
            self.set_report("market_report", chunk["market_report"])
            self.set_status("Market Analyst", "completed")
            if "social" in self.selections["analysts"]:
                self.set_status("Social Analyst", "in_progress")
            elif "news" in self.selections["analysts"]:
                self.set_status("News Analyst", "in_progress")
            elif "fundamentals" in self.selections["analysts"]:
                self.set_status("Fundamentals Analyst", "in_progress")
            else:
                self.set_research_team_status("in_progress")

        if chunk.get("sentiment_report"):
            self.set_report("sentiment_report", chunk["sentiment_report"])
            self.set_status("Social Analyst", "completed")
            if "news" in self.selections["analysts"]:
                self.set_status("News Analyst", "in_progress")
            elif "fundamentals" in self.selections["analysts"]:
                self.set_status("Fundamentals Analyst", "in_progress")
            else:
                self.set_research_team_status("in_progress")

        if chunk.get("news_report"):
            self.set_report("news_report", chunk["news_report"])
            self.set_status("News Analyst", "completed")
            if "fundamentals" in self.selections["analysts"]:
                self.set_status("Fundamentals Analyst", "in_progress")
            else:
                self.set_research_team_status("in_progress")

        if chunk.get("fundamentals_report"):
            self.set_report("fundamentals_report", chunk["fundamentals_report"])
            self.set_status("Fundamentals Analyst", "completed")
            self.set_research_team_status("in_progress")

        debate_state = chunk.get("investment_debate_state")
        if debate_state:
            self.set_research_team_status("in_progress")
            if debate_state.get("judge_decision"):
                current = self.reports.get("investment_plan", "")
                appended = f"### 研究经理决策\n{debate_state['judge_decision']}"
                self.set_report("investment_plan", f"{current}\n\n{appended}".strip())
                self.set_research_team_status("completed")
                self.set_status("Risky Analyst", "in_progress")

        if chunk.get("trader_investment_plan"):
            self.set_report("trader_investment_plan", chunk["trader_investment_plan"])
            self.set_status("Trader", "completed")
            self.set_status("Risky Analyst", "in_progress")

        risk_state = chunk.get("risk_debate_state")
        if risk_state:
            if risk_state.get("current_risky_response"):
                self.set_status("Risky Analyst", "in_progress")
            if risk_state.get("current_safe_response"):
                self.set_status("Safe Analyst", "in_progress")
            if risk_state.get("current_neutral_response"):
                self.set_status("Neutral Analyst", "in_progress")
            if risk_state.get("judge_decision"):
                self.set_report("final_trade_decision", f"### 组合经理决策\n{risk_state['judge_decision']}")
                for agent in ["Risky Analyst", "Safe Analyst", "Neutral Analyst", "Portfolio Manager"]:
                    self.set_status(agent, "completed")

    def mark_error(self):
        for agent, status in self.statuses.items():
            if status == "in_progress":
                self.statuses[agent] = "error"

    def mark_completed(self):
        for agent in self.statuses:
            self.statuses[agent] = "completed"

    def progress_html(self):
        completed = sum(1 for status in self.statuses.values() if status == "completed")
        in_progress = [agent for agent, status in self.statuses.items() if status == "in_progress"]
        percent = int((completed / len(STATUS_ORDER)) * 100)
        running = "、".join(AGENT_LABELS[agent] for agent in in_progress) if in_progress else "无"
        return (
            f"<div style='padding:12px;border:1px solid #e5e7eb;border-radius:12px;background:#fff;'>"
            f"<div style='font-weight:600;margin-bottom:8px;'>进度：已完成 {completed}/{len(STATUS_ORDER)}</div>"
            f"<div style='height:12px;background:#eef2ff;border-radius:999px;overflow:hidden;'>"
            f"<div style='height:12px;width:{percent}%;background:linear-gradient(90deg,#2563eb,#7c3aed);'></div></div>"
            f"<div style='margin-top:8px;color:#334155;'>当前运行：<strong>{running}</strong></div></div>"
        )

    def status_html(self):
        sections = []
        for group_name, agents in STATUS_GROUPS.items():
            cards = []
            for agent in agents:
                status = self.statuses[agent]
                fg, bg, label = STATUS_THEME[status]
                cards.append(
                    f"<div style='padding:12px;border:1px solid #e5e7eb;border-radius:12px;background:{bg};min-height:72px;'>"
                    f"<div style='font-size:15px;font-weight:700;color:#0f172a;margin-bottom:8px;'>{AGENT_LABELS[agent]}</div>"
                    f"<div style='display:inline-block;padding:4px 10px;border-radius:999px;background:#fff;color:{fg};font-weight:700;font-size:13px;'>{label}</div>"
                    f"</div>"
                )
            sections.append(
                f"<div style='margin-bottom:16px;'>"
                f"<div style='font-size:16px;font-weight:700;margin-bottom:10px;color:#0f172a;'>{group_name}</div>"
                f"<div style='display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:10px;'>{''.join(cards)}</div>"
                f"</div>"
            )
        return "".join(sections)

    def output_tuple(self, logs):
        return (
            self.run_message,
            self.token_usage_markdown(),
            self.progress_html(),
            self.status_html(),
            logs,
            "\n".join(self.messages),
            "\n".join(self.tools),
            self.reports["market_report"],
            self.reports["sentiment_report"],
            self.reports["news_report"],
            self.reports["fundamentals_report"],
            self.reports["investment_plan"],
            self.reports["trader_investment_plan"],
            self.reports["final_trade_decision"],
            self.full_report,
            self.output_dir,
            self.exported_md_path,
        )


def build_run_config(market_profile, ticker, trade_date, llm_provider, backend_url, quick_model, deep_model, embedding_model, research_depth, analysts, results_dir, api_key=None):
    config = apply_market_profile(DEFAULT_CONFIG.copy(), market_profile)
    provider_config = get_provider_config(llm_provider)
    config["llm_provider"] = llm_provider
    config["backend_url"] = backend_url
    config["quick_think_llm"] = quick_model
    config["deep_think_llm"] = deep_model
    if llm_provider == "vllm":
        config["llm_timeout_seconds"] = max(float(config.get("llm_timeout_seconds", 180)), 600)
        config["llm_max_tokens"] = min(int(config.get("llm_max_tokens", 2048)), 2048)
        config["vllm_disable_thinking"] = True
    if llm_provider == "luchikey_openai":
        config["backend_url"] = backend_url.rstrip("/") if backend_url else provider_config.get("backend_url", PROVIDER_DEFAULTS["luchikey_openai"]["backend_url"])
        if not config["backend_url"].endswith("/v1"):
            config["backend_url"] = f"{config['backend_url']}/v1"
        config["llm_default_headers"] = {
            "User-Agent": "Mozilla/5.0",
            "Accept": "application/json",
        }
    config["max_debate_rounds"] = int(research_depth)
    config["max_risk_discuss_rounds"] = int(research_depth)
    config["results_dir"] = results_dir or DEFAULT_CONFIG["results_dir"]
    config["tool_vendors"] = {}
    if embedding_model:
        config["embedding_model"] = embedding_model
    resolved_api_key = (api_key or "").strip() or get_provider_api_key(llm_provider)
    if resolved_api_key:
        config["api_key"] = resolved_api_key
    return config


def build_config_json(*args):
    if len(args) == 11:
        market_profile, ticker, trade_date, llm_provider, backend_url, quick_model, deep_model, embedding_model, research_depth, analysts, results_dir = args
        md_export_dir = ""
    else:
        market_profile, ticker, trade_date, llm_provider, backend_url, quick_model, deep_model, embedding_model, research_depth, analysts, results_dir, md_export_dir = args
    payload = {
        "ticker": (ticker or "").strip().upper(),
        "trade_date": (trade_date or "").strip(),
        "selected_analysts": list(analysts or []),
        "market_profile": market_profile,
        "llm_provider": llm_provider,
        "backend_url": (backend_url or "").strip(),
        "deep_think_llm": (deep_model or "").strip(),
        "quick_think_llm": (quick_model or "").strip(),
        "embedding_model": (embedding_model or "").strip(),
        "max_debate_rounds": int(research_depth),
        "max_risk_discuss_rounds": int(research_depth),
        "results_dir": (results_dir or DEFAULT_CONFIG["results_dir"]).strip(),
        "md_export_dir": (md_export_dir or "").strip(),
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def provider_default_value(provider, key, fallback=""):
    return get_provider_config(provider).get(key, fallback)


def analyst_choices_for_market(market_profile):
    supported = MARKET_PROFILES[market_profile]["supported_analysts"]
    return [(ANALYST_LABELS[item], item) for item in supported]


def load_config_file(file_path):
    if not file_path:
        return [gr.update() for _ in range(13)]
    data = json.loads(Path(file_path).read_text())
    market = data.get("market_profile", "cn_a_share")
    supported = MARKET_PROFILES.get(market, MARKET_PROFILES["cn_a_share"])["supported_analysts"]
    selected = [item for item in data.get("selected_analysts", supported[:1]) if item in supported]
    if not selected:
        selected = supported[:1]
    provider = data.get("llm_provider", "ollama")
    provider_config = get_provider_config(provider)
    return [
        data.get("market_profile", "cn_a_share"),
        data.get("ticker", MARKET_PROFILES.get(market, MARKET_PROFILES["cn_a_share"])["default_ticker"]),
        data.get("trade_date", datetime.now().strftime("%Y-%m-%d")),
        data.get("results_dir", DEFAULT_CONFIG["results_dir"]),
        data.get("md_export_dir", DEFAULT_CONFIG.get("md_export_dir", "")),
        provider,
        data.get("backend_url", provider_config.get("backend_url", "")),
        data.get("quick_think_llm", provider_config.get("quick_model", "")),
        data.get("deep_think_llm", provider_config.get("deep_model", "")),
        data.get("embedding_model", provider_config.get("embedding_model", "")),
        int(data.get("max_debate_rounds", 1)),
        gr.update(choices=analyst_choices_for_market(market), value=selected),
        get_provider_api_key(provider) or os.getenv("OPENAI_API_KEY", ""),
    ]


def apply_market_defaults(market_profile, selected_analysts):
    profile = MARKET_PROFILES[market_profile]
    supported = profile["supported_analysts"]
    selected = [item for item in (selected_analysts or []) if item in supported]
    if not selected:
        selected = supported[: min(3, len(supported))]
    return profile["default_ticker"], gr.update(choices=analyst_choices_for_market(market_profile), value=selected)


def apply_provider_defaults(provider):
    defaults = get_provider_config(provider)
    api_key = get_provider_api_key(provider) or os.getenv("OPENAI_API_KEY", "")
    return defaults["backend_url"], defaults["quick_model"], defaults["deep_model"], defaults["embedding_model"], api_key


def fetch_sector_fund_flow_chart(indicator, sector_type, top_n):
    try:
        import akshare as ak
        import pandas as pd
    except Exception as exc:
        raise gr.Error(f"缺少板块资金流依赖：{exc}")

    indicator = indicator or "今日"
    sector_type = sector_type or "行业资金流"
    top_n = int(top_n or 20)

    try:
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            df = ak.stock_sector_fund_flow_rank(indicator=indicator, sector_type=sector_type)
    except Exception as exc:
        raise gr.Error(f"获取板块资金流失败：{exc}")

    if df is None or df.empty:
        raise gr.Error("未获取到板块资金流数据")

    df = df.copy()
    name_col = next((col for col in ["名称", "板块名称", "行业", "概念"] if col in df.columns), df.columns[0])
    flow_col = next((col for col in ["主力净流入-净额", "主力净流入", "今日主力净流入-净额", "净额"] if col in df.columns), None)
    pct_col = next((col for col in ["涨跌幅", "今日涨跌幅", "涨跌幅%"] if col in df.columns), None)

    if flow_col is None:
        candidate_cols = [col for col in df.columns if "净流入" in str(col) or "净额" in str(col)]
        if candidate_cols:
            flow_col = candidate_cols[0]
    if flow_col is None:
        raise gr.Error(f"未找到主力净流入字段，当前字段：{', '.join(map(str, df.columns))}")

    chart_df = df[[name_col, flow_col] + ([pct_col] if pct_col else [])].copy()
    chart_df[flow_col] = pd.to_numeric(chart_df[flow_col], errors="coerce")
    chart_df = chart_df.dropna(subset=[flow_col])
    chart_df["主力净流入_亿元"] = chart_df[flow_col] / 100000000
    chart_df = chart_df.rename(columns={name_col: "板块"})

    top_in = chart_df.sort_values("主力净流入_亿元", ascending=False).head(top_n)
    top_out = chart_df.sort_values("主力净流入_亿元", ascending=True).head(top_n)
    display_df = pd.concat([top_in, top_out], ignore_index=True).drop_duplicates(subset=["板块"])
    display_df = display_df.sort_values("主力净流入_亿元", ascending=True)

    table_cols = ["板块", "主力净流入_亿元"]
    if pct_col:
        table_cols.append(pct_col)
    table_df = display_df[table_cols].sort_values("主力净流入_亿元", ascending=False)
    table_df["主力净流入_亿元"] = table_df["主力净流入_亿元"].round(2)

    title = f"{sector_type} · {indicator} · 主力资金流向 Top {top_n}"
    return display_df, table_df, title


def capture_qa_context(full_report_md, llm_provider, backend_url, quick_model, deep_model, api_key):
    """在分析完成后捕获 Q&A 需要的上下文（报告 + LLM 配置）。"""
    return {
        "report": full_report_md or "",
        "llm_provider": llm_provider,
        "backend_url": backend_url,
        "model": deep_model or quick_model,
        "api_key": (api_key or "").strip() or get_provider_api_key(llm_provider) or os.getenv("OPENAI_API_KEY", ""),
    }


def answer_report_question(user_message, history, qa_context):
    """基于已生成的报告内容，使用当前选择的模型回答用户提问。"""
    history = list(history or [])
    if not user_message or not user_message.strip():
        return history, ""

    if not qa_context or not qa_context.get("report"):
        history.append((user_message, "⚠️ 请先完成一次分析，生成报告后再提问。"))
        return history, ""

    provider = (qa_context.get("llm_provider") or "").lower()
    api_key = qa_context.get("api_key") or os.getenv("OPENAI_API_KEY", "ollama")

    try:
        if provider in {"openai", "ollama", "openrouter", "vllm", "lucen_openai", "luchikey_openai"}:
            from openai import OpenAI

            qa_backend_url = qa_context["backend_url"]
            default_headers = None
            if provider == "luchikey_openai":
                qa_backend_url = qa_backend_url.rstrip("/")
                if not qa_backend_url.endswith("/v1"):
                    qa_backend_url = f"{qa_backend_url}/v1"
                default_headers = {
                    "User-Agent": "Mozilla/5.0",
                    "Accept": "application/json",
                }
            client = OpenAI(
                base_url=qa_backend_url,
                api_key=api_key,
                default_headers=default_headers,
            )

            system_prompt = (
                "你是一位资深的金融分析助手。以下是针对某只股票的完整分析报告，"
                "请严格根据报告内容回答用户的问题。若报告中没有相关信息，请明确说明。"
                "回答请使用中文，条理清晰、引用报告中的具体数据或观点。\n\n"
                f"===== 分析报告开始 =====\n{qa_context['report']}\n===== 分析报告结束 ====="
            )

            messages = [{"role": "system", "content": system_prompt}]
            # 保留最近 10 轮对话上下文
            for user_msg, bot_msg in history[-10:]:
                if user_msg:
                    messages.append({"role": "user", "content": user_msg})
                if bot_msg:
                    messages.append({"role": "assistant", "content": bot_msg})
            messages.append({"role": "user", "content": user_message})

            resp = client.chat.completions.create(
                model=qa_context["model"],
                messages=messages,
                temperature=0.3,
                max_tokens=2048,
            )
            answer = resp.choices[0].message.content or "（模型未返回内容）"
        else:
            answer = f"⚠️ 暂不支持 provider: {provider}。请使用 OpenAI-compatible 提供商。"
    except Exception as exc:
        answer = f"❌ 调用模型失败: {type(exc).__name__}: {exc}"

    history.append((user_message, answer))
    return history, ""


def clear_qa_history():
    return [], ""


def apply_cn_ollama_preset():
    supported = MARKET_PROFILES["cn_a_share"]["supported_analysts"]
    return (
        "cn_a_share",
        MARKET_PROFILES["cn_a_share"]["default_ticker"],
        "ollama",
        PROVIDER_DEFAULTS["ollama"]["backend_url"],
        PROVIDER_DEFAULTS["ollama"]["quick_model"],
        PROVIDER_DEFAULTS["ollama"]["deep_model"],
        PROVIDER_DEFAULTS["ollama"]["embedding_model"],
        1,
        gr.update(choices=analyst_choices_for_market("cn_a_share"), value=["market", "news", "fundamentals"]),
    )


def _normalize_pdf_line(line):
    normalized = line.replace("```text", "").replace("```", "")
    normalized = normalized.replace("### ", "").replace("## ", "").replace("# ", "")
    normalized = normalized.replace("|", "  ")
    return normalized.rstrip()


def _wrap_pdf_line(line, width=34):
    if not line:
        return [""]
    if len(line) <= width:
        return [line]
    return textwrap.wrap(line, width=width, break_long_words=True, break_on_hyphens=False)


def build_full_report_markdown(collector):
    lines = [
        f"# TradingAgents 完整分析报告（{collector.selections.get('display_name') or collector.selections['ticker']} - {collector.selections['ticker']}）",
        "",
        "## 任务信息",
        f"- 市场：{collector.selections['market_profile']}",
        f"- 股票代码：{collector.selections['ticker']}",
        f"- 公司名称：{collector.selections.get('display_name') or collector.selections['ticker']}",
        f"- 分析日期：{collector.selections['trade_date']}",
        f"- LLM 提供商：{collector.selections['llm_provider']}",
        "",
    ]

    for key in REPORT_KEYS:
        content = (collector.reports.get(key) or "").strip()
        if not content:
            continue
        lines.append(f"## {REPORT_TITLES[key]}")
        lines.append("")
        lines.append(content)
        lines.append("")

    if collector.decision:
        lines.append("## 处理后的最终决策")
        lines.append("")
        lines.append(str(collector.decision))
        lines.append("")

    return "\n".join(lines).strip()


def _resolve_export_dir(export_dir, warning_collector=None):
    export_dir = (export_dir or "").strip()
    if not export_dir:
        return None

    export_dir = os.path.expanduser(export_dir)
    win_drive_match = re.match(r'^([a-zA-Z]):[/\\]', export_dir)
    if win_drive_match:
        drive_letter = win_drive_match.group(1).lower()
        wsl_mount = f"/mnt/{drive_letter}"
        if os.path.isdir(wsl_mount):
            export_dir = wsl_mount + export_dir[2:]
        else:
            abs_path = str(Path(export_dir).resolve())
            if warning_collector is not None:
                warning_collector.add_message(
                    "系统",
                    f"检测到 Windows 路径 '{export_dir}'，当前为非 WSL Linux 环境。"
                    f"文件将保存到绝对路径：{abs_path}。如需保存到 Windows 盘符，请使用 WSL 或填写 Linux 绝对路径（如 /home/xxx/reports）。"
                )
            export_dir = abs_path

    target_dir = Path(export_dir)
    if not target_dir.is_absolute():
        target_dir = target_dir.resolve()
    return target_dir


def export_full_report_markdown(collector, md_path):
    export_dir = _resolve_export_dir(collector.selections.get("md_export_dir"), warning_collector=collector)
    if export_dir is None:
        collector.exported_md_path = str(md_path)
        return

    export_dir.mkdir(parents=True, exist_ok=True)
    target_path = export_dir / md_path.name
    target_path.write_text(collector.full_report)
    collector.exported_md_path = str(target_path)


def persist_outputs(collector, logs, results_dir):
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = Path(results_dir or DEFAULT_CONFIG["results_dir"]) / collector.selections["ticker"] / collector.selections["trade_date"] / f"gradio_app_{timestamp}"
    reports_dir = output_dir / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "config_used.json").write_text(json.dumps(collector.selections, ensure_ascii=False, indent=2))
    (output_dir / "logs.txt").write_text(logs)
    (output_dir / "messages.txt").write_text("\n".join(collector.messages))
    (output_dir / "tool_calls.txt").write_text("\n".join(collector.tools))
    collector.full_report = build_full_report_markdown(collector)
    safe_name = _safe_filename_part(collector.selections.get("display_name") or collector.selections["ticker"])
    safe_ticker = _safe_filename_part(collector.selections["ticker"])
    md_filename_parts = [p for p in ["full_report", safe_name, safe_ticker] if p]
    md_path = output_dir / ("_".join(md_filename_parts) + ".md")
    md_path.write_text(collector.full_report)
    for key, value in collector.reports.items():
        if value:
            (reports_dir / f"{key}.md").write_text(value)
    if collector.final_state is not None:
        (output_dir / "final_state.json").write_text(json.dumps(collector.final_state, ensure_ascii=False, indent=2, default=str))
        (output_dir / "processed_decision.txt").write_text(str(collector.decision))
    collector.output_dir = str(output_dir)
    try:
        export_full_report_markdown(collector, md_path)
    except Exception as exc:
        collector.exported_md_path = str(md_path)
        collector.add_message("系统", f"MD 额外导出失败：{exc}")


_A_SHARE_NAME_MAP_CACHE = None
_A_SHARE_INDUSTRY_BY_CODE = {}
_A_SHARE_CONCEPTS_BY_CODE = {}
_A_SHARE_INDUSTRY_BOARD_NAMES = None
_A_SHARE_CONCEPT_BOARD_NAMES = None
_A_SHARE_INDUSTRY_SCANNED_BOARDS = set()
_A_SHARE_CONCEPT_SCANNED_BOARDS = set()
_A_SHARE_BOARD_CACHE_LOCK = threading.Lock()


def _get_a_share_name_map():
    """加载 A 股代码<->名称映射，惰性缓存。"""
    global _A_SHARE_NAME_MAP_CACHE
    if _A_SHARE_NAME_MAP_CACHE is not None:
        return _A_SHARE_NAME_MAP_CACHE
    code_to_name, name_to_code = {}, {}
    try:
        import akshare as ak
        df = ak.stock_info_a_code_name()
        for _, row in df.iterrows():
            code = str(row["code"]).strip().zfill(6)
            name = str(row["name"]).strip()
            if code and name:
                code_to_name[code] = name
                name_to_code[name] = code
    except Exception as exc:
        print(f"WARN: 加载 A 股代码名称映射失败: {exc}")
    _A_SHARE_NAME_MAP_CACHE = (code_to_name, name_to_code)
    return _A_SHARE_NAME_MAP_CACHE


def _normalize_constituent_code(value):
    digits = re.sub(r"\D", "", str(value or ""))
    if len(digits) >= 6:
        return digits[-6:]
    return ""


def _extract_constituent_codes(df):
    if df is None or getattr(df, "empty", True):
        return []
    for column in ["代码", "证券代码", "股票代码", "成分股代码"]:
        if column in df.columns:
            codes = []
            for value in df[column].tolist():
                code = _normalize_constituent_code(value)
                if code:
                    codes.append(code)
            return codes
    return []


def _get_em_board_names(board_type):
    global _A_SHARE_INDUSTRY_BOARD_NAMES, _A_SHARE_CONCEPT_BOARD_NAMES
    with _A_SHARE_BOARD_CACHE_LOCK:
        if board_type == "industry" and _A_SHARE_INDUSTRY_BOARD_NAMES is not None:
            return _A_SHARE_INDUSTRY_BOARD_NAMES
        if board_type == "concept" and _A_SHARE_CONCEPT_BOARD_NAMES is not None:
            return _A_SHARE_CONCEPT_BOARD_NAMES

    board_names = []
    try:
        import akshare as ak

        fetcher = ak.stock_board_industry_name_em if board_type == "industry" else ak.stock_board_concept_name_em
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            df = fetcher()
        if df is not None and not df.empty and "板块名称" in df.columns:
            board_names = [str(item).strip() for item in df["板块名称"].tolist() if str(item).strip()]
    except Exception as exc:
        print(f"WARN: 加载{board_type}板块名称失败: {exc}")

    with _A_SHARE_BOARD_CACHE_LOCK:
        if board_type == "industry":
            _A_SHARE_INDUSTRY_BOARD_NAMES = board_names
        else:
            _A_SHARE_CONCEPT_BOARD_NAMES = board_names
    return board_names


def _scan_industry_for_code(code):
    with _A_SHARE_BOARD_CACHE_LOCK:
        cached = _A_SHARE_INDUSTRY_BY_CODE.get(code)
    if cached:
        return cached

    board_names = _get_em_board_names("industry")
    if not board_names:
        return ""

    try:
        import akshare as ak

        for board_name in board_names:
            with _A_SHARE_BOARD_CACHE_LOCK:
                if board_name in _A_SHARE_INDUSTRY_SCANNED_BOARDS:
                    continue
            try:
                with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                    df = ak.stock_board_industry_cons_em(symbol=board_name)
                codes = _extract_constituent_codes(df)
            except Exception:
                codes = []
            with _A_SHARE_BOARD_CACHE_LOCK:
                _A_SHARE_INDUSTRY_SCANNED_BOARDS.add(board_name)
                for member_code in codes:
                    _A_SHARE_INDUSTRY_BY_CODE.setdefault(member_code, board_name)
                if code in _A_SHARE_INDUSTRY_BY_CODE:
                    return _A_SHARE_INDUSTRY_BY_CODE[code]
    except Exception as exc:
        print(f"WARN: 扫描行业板块失败: {exc}")
    return ""


def _scan_concepts_for_code(code, limit=3):
    with _A_SHARE_BOARD_CACHE_LOCK:
        cached = list(_A_SHARE_CONCEPTS_BY_CODE.get(code, []))
    if len(cached) >= limit:
        return cached[:limit]

    board_names = _get_em_board_names("concept")
    if not board_names:
        return cached[:limit]

    try:
        import akshare as ak

        for board_name in board_names:
            with _A_SHARE_BOARD_CACHE_LOCK:
                if board_name in _A_SHARE_CONCEPT_SCANNED_BOARDS:
                    continue
            try:
                with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                    df = ak.stock_board_concept_cons_em(symbol=board_name)
                codes = _extract_constituent_codes(df)
            except Exception:
                codes = []
            with _A_SHARE_BOARD_CACHE_LOCK:
                _A_SHARE_CONCEPT_SCANNED_BOARDS.add(board_name)
                for member_code in codes:
                    bucket = _A_SHARE_CONCEPTS_BY_CODE.setdefault(member_code, [])
                    if board_name not in bucket:
                        bucket.append(board_name)
                cached = list(_A_SHARE_CONCEPTS_BY_CODE.get(code, []))
                if len(cached) >= limit:
                    return cached[:limit]
    except Exception as exc:
        print(f"WARN: 扫描概念板块失败: {exc}")
    return list(_A_SHARE_CONCEPTS_BY_CODE.get(code, []))[:limit]


def resolve_a_share_sector_tags(code, market_profile, concept_limit=3):
    if market_profile != "cn_a_share":
        return "", ""
    normalized_code = _normalize_constituent_code(code)
    if not normalized_code:
        return "", ""
    industry = _scan_industry_for_code(normalized_code)
    concepts = _scan_concepts_for_code(normalized_code, limit=concept_limit)
    return industry or "", "、".join(concepts)


def resolve_ticker_and_name(item, market_profile):
    """把用户输入（代码或名称）解析为 (代码, 名称)。"""
    item = (item or "").strip()
    if not item:
        return None, None
    if market_profile == "cn_a_share":
        # 去掉可能的 .SH / .SZ 后缀
        code_part = item.split(".")[0].strip()
        code_to_name, name_to_code = _get_a_share_name_map()
        if code_part.isdigit():
            code = code_part.zfill(6)
            return code, code_to_name.get(code, code)
        # 名称完全匹配
        if item in name_to_code:
            return name_to_code[item], item
        # 名称模糊匹配（包含关系）
        for name, code in name_to_code.items():
            if item in name:
                return code, name
        # 解析不出来，原样返回
        return item, item
    return item.upper(), item.upper()


def parse_ticker_list(tickers_text):
    """从文本中解析多个 ticker（原样保留，不做大小写转换以支持中文名称）。"""
    if not tickers_text:
        return []
    raw = re.split(r"[\s,，;；、|]+", tickers_text.strip())
    seen = set()
    result = []
    for item in raw:
        item = item.strip()
        if item and item not in seen:
            seen.add(item)
            result.append(item)
    return result


def _decision_label_from_token(token):
    normalized = str(token or "").strip().upper()
    if normalized == "BUY" or normalized == "买入":
        return "🟢 买入"
    if normalized == "SELL" or normalized == "卖出":
        return "🔴 卖出"
    if normalized == "HOLD" or normalized == "持有":
        return "🟡 持有"
    return ""


def _extract_decision_label(decision_text):
    """优先从明确的最终决策段落中提取 买入/卖出/持有，避免正文关键词误判。"""
    if not decision_text:
        return ""
    text = str(decision_text)

    explicit_patterns = [
        r"##\s*处理后的最终决策\s*(?:\n|\r|\r\n)+\s*[*`#>\- ]*(BUY|SELL|HOLD|买入|卖出|持有)\b",
        r"FINAL\s+TRANSACTION\s+PROPOSAL\s*[:：]\s*\**\s*(BUY|SELL|HOLD)\b",
        r"(?:最终决策|最终建议|操作建议|明确建议|组合经理决策)[:：\s]*\**\s*(BUY|SELL|HOLD|买入|卖出|持有)\b",
    ]
    for pattern in explicit_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            label = _decision_label_from_token(match.group(1))
            if label:
                return label

    tail_text = "\n".join(text.strip().splitlines()[-8:])
    for pattern in [r"\b(BUY|SELL|HOLD)\b", r"(买入|卖出|持有)"]:
        matches = re.findall(pattern, tail_text, re.IGNORECASE)
        if matches:
            label = _decision_label_from_token(matches[-1])
            if label:
                return label

    return ""


def _safe_filename_part(text):
    """把名称中的非法字符替换为下划线，用于文件名。"""
    if not text:
        return ""
    cleaned = re.sub(r"[^\w\u4e00-\u9fa5\-]+", "_", str(text)).strip("_")
    return cleaned[:60]


def _build_batch_summary_md(batch_rows, current_idx, total):
    if not batch_rows and current_idx == 0:
        return ""
    lines = [
        "| # | 输入 | 代码 | 名称 | 行业 | 概念板块 | 状态 | 决策 | 输出目录 |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for idx, row in enumerate(batch_rows, 1):
        status_icon = {"success": "✅ 成功", "failed": "❌ 失败", "running": "⏳ 进行中"}.get(row["status"], row["status"])
        out = row.get("output_dir") or ""
        lines.append(
            f"| {idx} | {row.get('input', '')} | {row.get('ticker', '')} | {row.get('name', '')} | "
            f"{row.get('industry', '')} | {row.get('concepts', '')} | {status_icon} | {row.get('decision', '')} | `{out}` |"
        )
    return "\n".join(lines)


def _write_batch_report_markdown(batch_rows, batch_reports, trade_date, results_dir, md_export_dir):
    target_dir = _resolve_export_dir(md_export_dir) or Path(results_dir or DEFAULT_CONFIG["results_dir"]).resolve()
    target_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    target_path = target_dir / f"batch_report_{trade_date}_{timestamp}.md"

    lines = [
        "# 批量分析汇总报告",
        "",
        f"- 分析日期：{trade_date}",
        f"- 生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"- 股票数量：{len(batch_rows)}",
        "",
        "## 批量结果概览",
        "",
        _build_batch_summary_md(batch_rows, len(batch_rows), len(batch_rows)),
        "",
    ]

    for idx, report in enumerate(batch_reports, 1):
        lines.extend([
            "---",
            "",
            f"# {idx}. {report.get('name') or report.get('ticker')}",
            "",
            f"- 股票代码：{report.get('ticker', '')}",
            f"- 决策：{report.get('decision', '—')}",
            "",
            report.get("full_report", "").strip(),
            "",
        ])

    target_path.write_text("\n".join(lines).strip() + "\n")
    return str(target_path)


def run_batch_analysis(market_profile, tickers_text, trade_date, results_dir, md_export_dir, llm_provider, backend_url, quick_model, deep_model, embedding_model, research_depth, analysts, api_key):
    """批量分析入口：遍历多个 ticker，逐个调用单股分析逻辑，累计可下载文件。"""
    raw_items = parse_ticker_list(tickers_text)
    if not raw_items:
        raise gr.Error("Ticker 不能为空（可输入多个，使用逗号或换行分隔；支持代码或公司名称）")

    # 预解析：把用户输入（代码或名称）→ (代码, 名称)
    resolved = []
    seen_codes = set()
    for raw in raw_items:
        code, name = resolve_ticker_and_name(raw, market_profile)
        if not code:
            continue
        if code in seen_codes:
            continue
        seen_codes.add(code)
        resolved.append({"input": raw, "ticker": code, "name": name})

    if not resolved:
        raise gr.Error("无法解析出任何有效的股票代码")

    batch_rows = []
    batch_files = []
    batch_reports = []
    last_output = None

    for idx, entry in enumerate(resolved, 1):
        ticker = entry["ticker"]
        name = entry["name"]
        batch_rows.append({
            "input": entry["input"],
            "ticker": ticker,
            "name": name,
            "industry": "",
            "concepts": "",
            "status": "running",
            "decision": "",
            "output_dir": "",
        })
        summary_md = _build_batch_summary_md(batch_rows, idx, len(resolved))

        try:
            for output_tuple in _run_single_analysis(
                market_profile, ticker, trade_date, results_dir, md_export_dir, llm_provider, backend_url,
                quick_model, deep_model, embedding_model, research_depth, analysts, api_key,
                display_name=name,
            ):
                last_output = output_tuple
                yield output_tuple + (summary_md, batch_files)
        except gr.Error:
            raise
        except Exception:
            batch_rows[-1]["status"] = "failed"
            summary_md = _build_batch_summary_md(batch_rows, idx, len(resolved))
            if last_output is not None:
                yield last_output + (summary_md, batch_files)
            continue

        # 单股完成后，提取产出文件 + 决策
        if last_output is not None:
            out_dir = last_output[-2]
            exported_md_path = last_output[-1]
            final_decision_md = last_output[13]
            full_report_md = last_output[14]
            batch_rows[-1]["output_dir"] = out_dir or ""
            batch_rows[-1]["decision"] = _extract_decision_label(full_report_md) or _extract_decision_label(final_decision_md) or "—"
            industry, concepts = resolve_a_share_sector_tags(ticker, market_profile)
            batch_rows[-1]["industry"] = industry or "—"
            batch_rows[-1]["concepts"] = concepts or "—"

            batch_reports.append({
                "ticker": ticker,
                "name": name,
                "decision": batch_rows[-1]["decision"],
                "full_report": full_report_md,
                "exported_md_path": exported_md_path,
            })
            batch_rows[-1]["status"] = "success" if full_report_md else "failed"
            summary_md = _build_batch_summary_md(batch_rows, idx, len(resolved))
            yield last_output + (summary_md, batch_files)

    # 最终：把 run_state 改成完成提示
    if last_output is not None:
        final_tuple = list(last_output)
        success_count = sum(1 for r in batch_rows if r["status"] == "success")
        final_tuple[0] = f"批量分析完成：{success_count}/{len(resolved)} 成功"
        summary_md = _build_batch_summary_md(batch_rows, len(resolved), len(resolved))
        batch_files = []
        if batch_reports:
            try:
                batch_files = [_write_batch_report_markdown(batch_rows, batch_reports, trade_date, results_dir, md_export_dir)]
            except Exception:
                batch_files = []
        yield tuple(final_tuple) + (summary_md, batch_files)


def _run_single_analysis(market_profile, ticker, trade_date, results_dir, md_export_dir, llm_provider, backend_url, quick_model, deep_model, embedding_model, research_depth, analysts, api_key, display_name=None):
    load_dotenv(override=True)
    ticker = (ticker or "").strip().upper()
    display_name = (display_name or "").strip() or ticker
    trade_date = (trade_date or "").strip()
    api_key = (api_key or "").strip()
    try:
        datetime.strptime(trade_date, "%Y-%m-%d")
    except ValueError:
        raise gr.Error("日期格式必须是 YYYY-MM-DD")
    if not ticker:
        raise gr.Error("Ticker 不能为空")
    if not analysts:
        raise gr.Error("至少选择一个 analyst")
    supported = set(MARKET_PROFILES[market_profile]["supported_analysts"])
    invalid = [item for item in analysts if item not in supported]
    if invalid:
        raise gr.Error(f"当前市场不支持这些 analysts: {', '.join(invalid)}")

    selections = {
        "market_profile": market_profile,
        "ticker": ticker,
        "display_name": display_name,
        "trade_date": trade_date,
        "results_dir": (results_dir or DEFAULT_CONFIG["results_dir"]).strip(),
        "md_export_dir": (md_export_dir or "").strip(),
        "llm_provider": llm_provider,
        "backend_url": (backend_url or "").strip(),
        "quick_model": (quick_model or "").strip(),
        "deep_model": (deep_model or "").strip(),
        "embedding_model": (embedding_model or "").strip(),
        "research_depth": int(research_depth),
        "analysts": list(analysts),
    }
    if selections["llm_provider"] == "vllm" and (
        "lucen.cc" in selections["backend_url"].lower()
        or selections["quick_model"] == PROVIDER_DEFAULTS["lucen_openai"]["quick_model"]
        or selections["deep_model"] == PROVIDER_DEFAULTS["lucen_openai"]["deep_model"]
    ):
        raise gr.Error(
            "LLM 配置不一致：你选择了 vLLM，但后端地址或模型仍然是 lucen_openai 的默认值。"
            "请点击 LLM 提供商下拉框重新选择 vllm，确认后端地址为 http://127.0.0.1:8000/v1，"
            "并确认快速/深度模型为本地 vLLM 模型名。"
        )
    collector = RunCollector(selections)
    collector.run_message = "正在初始化分析任务..."
    collector.add_message("系统", f"股票代码：{ticker}（{display_name}）")
    collector.add_message("系统", f"分析日期：{trade_date}")
    collector.add_message("系统", f"已选分析师：{', '.join(ANALYST_LABELS[item] for item in analysts)}")
    collector.add_message("系统", f"LLM 提供商：{selections['llm_provider']}")
    collector.add_message("系统", f"LLM 后端地址：{selections['backend_url']}")
    collector.add_message("系统", f"快速模型：{selections['quick_model']}")
    collector.add_message("系统", f"深度模型：{selections['deep_model']}")
    collector.mark_initial_status()
    log_buffer = StreamBuffer()
    yield collector.output_tuple(log_buffer.content())

    try:
        config_kwargs = {k: v for k, v in selections.items() if k not in {"display_name", "md_export_dir"}}
        config = build_run_config(**config_kwargs, api_key=api_key)
        with redirect_stdout(log_buffer), redirect_stderr(log_buffer):
            graph = TradingAgentsGraph(selected_analysts=selections["analysts"], debug=False, config=config)
            init_state = graph.propagator.create_initial_state(selections["ticker"], selections["trade_date"])
            args = graph.propagator.get_graph_args()
            trace = []
            for chunk in graph.graph.stream(init_state, **args):
                trace.append(chunk)
                collector.handle_chunk(chunk)
                collector.run_message = "分析运行中..."
                yield collector.output_tuple(log_buffer.content())
            collector.final_state = trace[-1]
            collector.decision = graph.process_signal(collector.final_state["final_trade_decision"])
            for key in REPORT_KEYS:
                if key in collector.final_state and collector.final_state[key]:
                    collector.set_report(key, collector.final_state[key])
        collector.mark_completed()
        collector.run_message = "分析已完成"
        persist_outputs(collector, log_buffer.content(), selections["results_dir"])
        yield collector.output_tuple(log_buffer.content())
    except Exception as exc:
        error_trace = traceback.format_exc()
        collector.mark_error()
        collector.run_message = f"分析失败: {exc}"
        collector.add_message("错误", str(exc))
        collector.set_report(
            "final_trade_decision",
            f"## 错误详情\n\n{exc}\n\n```text\n{error_trace}\n```",
        )
        error_logs = log_buffer.content()
        if error_logs:
            error_logs += "\n\n"
        error_logs += error_trace
        persist_outputs(collector, error_logs, selections["results_dir"])
        yield collector.output_tuple(error_logs)
        return


def build_app():
    market_choices = list(MARKET_PROFILES.keys())
    provider_choices = list(PROVIDER_DEFAULTS.keys())
    default_market = "cn_a_share"
    default_provider = "lucen_openai"
    default_supported = MARKET_PROFILES[default_market]["supported_analysts"]

    with gr.Blocks(title="TradingAgents 可视化运行器") as demo:
        gr.Markdown("# TradingAgents 可视化运行器")
        gr.Markdown("配置参数、启动分析，并实时查看智能体状态、日志、报告和最终决策。")

        with gr.Row():
            with gr.Column(scale=4):
                config_file = gr.File(label="导入配置 JSON", type="filepath")
            with gr.Column(scale=2):
                preset_btn = gr.Button("A股 + Ollama 预设", variant="primary")
            with gr.Column(scale=4):
                config_json = gr.Textbox(label="当前配置 JSON 预览", lines=8)

        with gr.Row():
            with gr.Column(scale=1):
                market_profile = gr.Dropdown(label="市场", choices=market_choices, value=default_market)
                ticker = gr.Textbox(
                    label="股票代码（支持批量，多个用逗号或换行分隔）",
                    value=MARKET_PROFILES[default_market]["default_ticker"],
                    lines=3,
                    placeholder="例如：600519, 000001\n或一行一个：\n600519\n000001",
                )
                trade_date = gr.Textbox(label="日期", value=datetime.now().strftime("%Y-%m-%d"))
                results_dir = gr.Textbox(label="结果目录", value=DEFAULT_CONFIG["results_dir"])
                md_export_dir = gr.Textbox(label="MD 自动保存目录（本地文件夹路径）", value=DEFAULT_CONFIG.get("md_export_dir", ""), placeholder="例如：/home/yourname/reports；留空则仅保存在结果目录中")
                llm_provider = gr.Dropdown(label="LLM 提供商", choices=provider_choices, value=default_provider)
                backend_url = gr.Textbox(label="后端地址", value=get_provider_config(default_provider)["backend_url"])
                api_key = gr.Textbox(label="API Key", type="password", value=get_provider_api_key(default_provider) or os.getenv("OPENAI_API_KEY", ""))
                quick_model = gr.Textbox(label="快速模型", value=get_provider_config(default_provider)["quick_model"])
                deep_model = gr.Textbox(label="深度模型", value=get_provider_config(default_provider)["deep_model"])
                embedding_model = gr.Textbox(label="Embedding 模型", value=get_provider_config(default_provider)["embedding_model"])
                research_depth = gr.Dropdown(label="研究深度", choices=[1, 3, 5], value=1)
                analysts = gr.CheckboxGroup(label="分析师团队", choices=analyst_choices_for_market(default_market), value=["market", "news", "fundamentals"])
                run_btn = gr.Button("启动分析", variant="primary", size="lg")
                output_dir = gr.Textbox(label="最近输出目录", interactive=False)
                exported_md_path = gr.Textbox(label="最近导出的 MD 路径", interactive=False)

            with gr.Column(scale=2):
                run_state = gr.Markdown("未运行")
                token_usage_md = gr.Markdown("Token 使用量：—")
                progress_html = gr.HTML(value="")
                status_html = gr.HTML(value="")
                with gr.Tabs():
                    with gr.Tab("日志"):
                        logs = gr.Textbox(lines=18)
                    with gr.Tab("消息"):
                        messages = gr.Textbox(lines=18)
                    with gr.Tab("工具调用"):
                        tools = gr.Textbox(lines=18)
                    with gr.Tab("板块资金流"):
                        gr.Markdown("展示 A 股行业、概念、地域板块的主力资金流入/流出，不写入最终报告。")
                        with gr.Row():
                            sector_indicator = gr.Dropdown(
                                label="周期",
                                choices=["今日", "5日", "10日"],
                                value="今日",
                            )
                            sector_type = gr.Dropdown(
                                label="板块类型",
                                choices=["行业资金流", "概念资金流", "地域资金流"],
                                value="行业资金流",
                            )
                            sector_top_n = gr.Slider(
                                label="流入/流出 Top N",
                                minimum=5,
                                maximum=50,
                                value=20,
                                step=1,
                            )
                            sector_refresh_btn = gr.Button("刷新板块资金流", variant="primary")
                        sector_chart_title = gr.Markdown("尚未加载板块资金流数据")
                        sector_flow_plot = gr.BarPlot(
                            x="主力净流入_亿元",
                            y="板块",
                            title="板块资金流",
                            tooltip=["板块", "主力净流入_亿元"],
                            height=560,
                        )
                        sector_flow_table = gr.Dataframe(label="板块资金流明细", interactive=False)
                    with gr.Tab("报告"):
                        market_report = gr.Markdown(label="市场分析")
                        sentiment_report = gr.Markdown(label="社交情绪分析")
                        news_report = gr.Markdown(label="新闻分析")
                        fundamentals_report = gr.Markdown(label="基本面分析")
                        investment_plan = gr.Markdown(label="研究团队结论")
                        trader_plan = gr.Markdown(label="交易团队计划")
                        final_decision = gr.Markdown(label="组合管理决策")
                        full_report = gr.Markdown(label="完整报告")
                    with gr.Tab("批量结果"):
                        gr.Markdown("批量分析完成的股票列表与可下载 Markdown 报告。")
                        batch_summary_md = gr.Markdown(value="（尚未运行）")
                        batch_files_dl = gr.Files(label="下载已完成的报告文件", interactive=False)
                    with gr.Tab("报告问答"):
                        gr.Markdown(
                            "分析完成后，可在此针对报告内容向当前选择的模型继续追问。"
                            "模型会基于已生成的完整报告回答你的问题。"
                        )
                        qa_context_state = gr.State(value={})
                        qa_chatbot = gr.Chatbot(label="报告问答", height=420)
                        qa_input = gr.Textbox(
                            label="你的问题",
                            placeholder="例如：这份报告对基本面的评估有哪些关键结论？",
                            lines=2,
                        )
                        with gr.Row():
                            qa_send_btn = gr.Button("发送", variant="primary")
                            qa_clear_btn = gr.Button("清空对话")

        config_inputs = [market_profile, ticker, trade_date, llm_provider, backend_url, quick_model, deep_model, embedding_model, research_depth, analysts, results_dir, md_export_dir]
        config_outputs = config_json
        for component in config_inputs:
            component.change(fn=build_config_json, inputs=config_inputs, outputs=config_outputs)
        demo.load(fn=build_config_json, inputs=config_inputs, outputs=config_outputs)

        config_file.change(
            fn=load_config_file,
            inputs=config_file,
            outputs=[market_profile, ticker, trade_date, results_dir, md_export_dir, llm_provider, backend_url, quick_model, deep_model, embedding_model, research_depth, analysts, api_key],
        )
        market_profile.change(fn=apply_market_defaults, inputs=[market_profile, analysts], outputs=[ticker, analysts])
        llm_provider.change(fn=apply_provider_defaults, inputs=llm_provider, outputs=[backend_url, quick_model, deep_model, embedding_model, api_key])
        preset_btn.click(fn=apply_cn_ollama_preset, outputs=[market_profile, ticker, llm_provider, backend_url, quick_model, deep_model, embedding_model, research_depth, analysts])
        sector_refresh_btn.click(
            fn=fetch_sector_fund_flow_chart,
            inputs=[sector_indicator, sector_type, sector_top_n],
            outputs=[sector_flow_plot, sector_flow_table, sector_chart_title],
        )

        run_btn.click(
            fn=run_batch_analysis,
            inputs=[market_profile, ticker, trade_date, results_dir, md_export_dir, llm_provider, backend_url, quick_model, deep_model, embedding_model, research_depth, analysts, api_key],
            outputs=[run_state, token_usage_md, progress_html, status_html, logs, messages, tools, market_report, sentiment_report, news_report, fundamentals_report, investment_plan, trader_plan, final_decision, full_report, output_dir, exported_md_path, batch_summary_md, batch_files_dl],
        ).then(
            fn=capture_qa_context,
            inputs=[full_report, llm_provider, backend_url, quick_model, deep_model, api_key],
            outputs=qa_context_state,
        )

        qa_send_btn.click(
            fn=answer_report_question,
            inputs=[qa_input, qa_chatbot, qa_context_state],
            outputs=[qa_chatbot, qa_input],
        )
        qa_input.submit(
            fn=answer_report_question,
            inputs=[qa_input, qa_chatbot, qa_context_state],
            outputs=[qa_chatbot, qa_input],
        )
        qa_clear_btn.click(fn=clear_qa_history, outputs=[qa_chatbot, qa_input])

    return demo


def find_available_port(start_port: int, max_attempts: int = 20) -> int:
    for port in range(start_port, start_port + max_attempts):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                sock.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    raise OSError(f"无法在端口范围 {start_port}-{start_port + max_attempts - 1} 中找到可用端口")


def main():
    load_dotenv(override=True)
    app = build_app()
    preferred_port = int(os.getenv("GRADIO_SERVER_PORT", "7860"))
    server_port = find_available_port(preferred_port)
    print(f"启动 Gradio 服务，端口: {server_port}")
    app.launch(server_name="127.0.0.1", server_port=server_port, inbrowser=True)


if __name__ == "__main__":
    main()
