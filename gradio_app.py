import io
import json
import os
import socket
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
    "ollama": {
        "backend_url": "http://localhost:11434/v1",
        "quick_model": "qwen3:14b",
        "deep_model": "qwen3:14b",
        "embedding_model": "nomic-embed-text",
    },
}

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
        self.run_message = "未运行"
        self.output_dir = ""

    def set_status(self, agent, status):
        if agent in self.statuses:
            self.statuses[agent] = status

    def set_report(self, section, content):
        if section in self.reports and content:
            self.reports[section] = content

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

    def handle_chunk(self, chunk):
        messages = chunk.get("messages", [])
        if messages:
            last_message = messages[-1]
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
                self.set_report("investment_plan", f"{current}\n\n### Research Manager Decision\n{debate_state['judge_decision']}".strip())
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
                self.set_report("final_trade_decision", f"### Portfolio Manager Decision\n{risk_state['judge_decision']}")
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
            self.output_dir,
        )


def build_run_config(market_profile, ticker, trade_date, llm_provider, backend_url, quick_model, deep_model, embedding_model, research_depth, analysts, results_dir):
    config = apply_market_profile(DEFAULT_CONFIG.copy(), market_profile)
    config["llm_provider"] = llm_provider
    config["backend_url"] = backend_url
    config["quick_think_llm"] = quick_model
    config["deep_think_llm"] = deep_model
    config["max_debate_rounds"] = int(research_depth)
    config["max_risk_discuss_rounds"] = int(research_depth)
    config["results_dir"] = results_dir or DEFAULT_CONFIG["results_dir"]
    config["tool_vendors"] = {}
    if embedding_model:
        config["embedding_model"] = embedding_model
    return config


def build_config_json(market_profile, ticker, trade_date, llm_provider, backend_url, quick_model, deep_model, embedding_model, research_depth, analysts, results_dir):
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
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def analyst_choices_for_market(market_profile):
    supported = MARKET_PROFILES[market_profile]["supported_analysts"]
    return [(ANALYST_LABELS[item], item) for item in supported]


def load_config_file(file_path):
    if not file_path:
        return [gr.update() for _ in range(11)]
    data = json.loads(Path(file_path).read_text())
    market = data.get("market_profile", "cn_a_share")
    supported = MARKET_PROFILES.get(market, MARKET_PROFILES["cn_a_share"])["supported_analysts"]
    selected = [item for item in data.get("selected_analysts", supported[:1]) if item in supported]
    if not selected:
        selected = supported[:1]
    return [
        data.get("market_profile", "cn_a_share"),
        data.get("ticker", MARKET_PROFILES.get(market, MARKET_PROFILES["cn_a_share"])["default_ticker"]),
        data.get("trade_date", datetime.now().strftime("%Y-%m-%d")),
        data.get("results_dir", DEFAULT_CONFIG["results_dir"]),
        data.get("llm_provider", "ollama"),
        data.get("backend_url", PROVIDER_DEFAULTS[data.get("llm_provider", "ollama")]["backend_url"]),
        data.get("quick_think_llm", PROVIDER_DEFAULTS[data.get("llm_provider", "ollama")]["quick_model"]),
        data.get("deep_think_llm", PROVIDER_DEFAULTS[data.get("llm_provider", "ollama")]["deep_model"]),
        data.get("embedding_model", PROVIDER_DEFAULTS[data.get("llm_provider", "ollama")]["embedding_model"]),
        int(data.get("max_debate_rounds", 1)),
        gr.update(choices=analyst_choices_for_market(market), value=selected),
    ]


def apply_market_defaults(market_profile, selected_analysts):
    profile = MARKET_PROFILES[market_profile]
    supported = profile["supported_analysts"]
    selected = [item for item in (selected_analysts or []) if item in supported]
    if not selected:
        selected = supported[: min(3, len(supported))]
    return profile["default_ticker"], gr.update(choices=analyst_choices_for_market(market_profile), value=selected)


def apply_provider_defaults(provider):
    defaults = PROVIDER_DEFAULTS[provider]
    return defaults["backend_url"], defaults["quick_model"], defaults["deep_model"], defaults["embedding_model"]


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


def persist_outputs(collector, logs, results_dir):
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = Path(results_dir or DEFAULT_CONFIG["results_dir"]) / collector.selections["ticker"] / collector.selections["trade_date"] / f"gradio_app_{timestamp}"
    reports_dir = output_dir / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "config_used.json").write_text(json.dumps(collector.selections, ensure_ascii=False, indent=2))
    (output_dir / "logs.txt").write_text(logs)
    (output_dir / "messages.txt").write_text("\n".join(collector.messages))
    (output_dir / "tool_calls.txt").write_text("\n".join(collector.tools))
    for key, value in collector.reports.items():
        if value:
            (reports_dir / f"{key}.md").write_text(value)
    if collector.final_state is not None:
        (output_dir / "final_state.json").write_text(json.dumps(collector.final_state, ensure_ascii=False, indent=2, default=str))
        (output_dir / "processed_decision.txt").write_text(str(collector.decision))
    collector.output_dir = str(output_dir)


def run_analysis(market_profile, ticker, trade_date, results_dir, llm_provider, backend_url, quick_model, deep_model, embedding_model, research_depth, analysts):
    load_dotenv()
    ticker = (ticker or "").strip().upper()
    trade_date = (trade_date or "").strip()
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
        "trade_date": trade_date,
        "results_dir": (results_dir or DEFAULT_CONFIG["results_dir"]).strip(),
        "llm_provider": llm_provider,
        "backend_url": (backend_url or "").strip(),
        "quick_model": (quick_model or "").strip(),
        "deep_model": (deep_model or "").strip(),
        "embedding_model": (embedding_model or "").strip(),
        "research_depth": int(research_depth),
        "analysts": list(analysts),
    }
    collector = RunCollector(selections)
    collector.run_message = "正在初始化分析任务..."
    collector.add_message("系统", f"股票代码：{ticker}")
    collector.add_message("系统", f"分析日期：{trade_date}")
    collector.add_message("系统", f"已选分析师：{', '.join(ANALYST_LABELS[item] for item in analysts)}")
    collector.mark_initial_status()
    log_buffer = StreamBuffer()
    yield collector.output_tuple(log_buffer.content())

    try:
        config = build_run_config(**selections)
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
    default_provider = "ollama"
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
                ticker = gr.Textbox(label="股票代码", value=MARKET_PROFILES[default_market]["default_ticker"])
                trade_date = gr.Textbox(label="日期", value=datetime.now().strftime("%Y-%m-%d"))
                results_dir = gr.Textbox(label="结果目录", value=DEFAULT_CONFIG["results_dir"])
                llm_provider = gr.Dropdown(label="LLM 提供商", choices=provider_choices, value=default_provider)
                backend_url = gr.Textbox(label="后端地址", value=PROVIDER_DEFAULTS[default_provider]["backend_url"])
                quick_model = gr.Textbox(label="快速模型", value=PROVIDER_DEFAULTS[default_provider]["quick_model"])
                deep_model = gr.Textbox(label="深度模型", value=PROVIDER_DEFAULTS[default_provider]["deep_model"])
                embedding_model = gr.Textbox(label="Embedding 模型", value=PROVIDER_DEFAULTS[default_provider]["embedding_model"])
                research_depth = gr.Dropdown(label="研究深度", choices=[1, 3, 5], value=1)
                analysts = gr.CheckboxGroup(label="分析师团队", choices=analyst_choices_for_market(default_market), value=["market", "news", "fundamentals"])
                run_btn = gr.Button("启动分析", variant="primary", size="lg")
                output_dir = gr.Textbox(label="最近输出目录", interactive=False)

            with gr.Column(scale=2):
                run_state = gr.Markdown("未运行")
                progress_html = gr.HTML(value="")
                status_html = gr.HTML(value="")
                with gr.Tabs():
                    with gr.Tab("日志"):
                        logs = gr.Textbox(lines=18)
                    with gr.Tab("消息"):
                        messages = gr.Textbox(lines=18)
                    with gr.Tab("工具调用"):
                        tools = gr.Textbox(lines=18)
                    with gr.Tab("报告"):
                        market_report = gr.Markdown(label="市场分析")
                        sentiment_report = gr.Markdown(label="社交情绪分析")
                        news_report = gr.Markdown(label="新闻分析")
                        fundamentals_report = gr.Markdown(label="基本面分析")
                        investment_plan = gr.Markdown(label="研究团队结论")
                        trader_plan = gr.Markdown(label="交易团队计划")
                        final_decision = gr.Markdown(label="组合管理决策")

        config_inputs = [market_profile, ticker, trade_date, llm_provider, backend_url, quick_model, deep_model, embedding_model, research_depth, analysts, results_dir]
        config_outputs = config_json
        for component in config_inputs:
            component.change(fn=build_config_json, inputs=config_inputs, outputs=config_outputs)
        demo.load(fn=build_config_json, inputs=config_inputs, outputs=config_outputs)

        config_file.change(
            fn=load_config_file,
            inputs=config_file,
            outputs=[market_profile, ticker, trade_date, results_dir, llm_provider, backend_url, quick_model, deep_model, embedding_model, research_depth, analysts],
        )
        market_profile.change(fn=apply_market_defaults, inputs=[market_profile, analysts], outputs=[ticker, analysts])
        llm_provider.change(fn=apply_provider_defaults, inputs=llm_provider, outputs=[backend_url, quick_model, deep_model, embedding_model])
        preset_btn.click(fn=apply_cn_ollama_preset, outputs=[market_profile, ticker, llm_provider, backend_url, quick_model, deep_model, embedding_model, research_depth, analysts])

        run_btn.click(
            fn=run_analysis,
            inputs=[market_profile, ticker, trade_date, results_dir, llm_provider, backend_url, quick_model, deep_model, embedding_model, research_depth, analysts],
            outputs=[run_state, progress_html, status_html, logs, messages, tools, market_report, sentiment_report, news_report, fundamentals_report, investment_plan, trader_plan, final_decision, output_dir],
        )

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
    load_dotenv()
    app = build_app()
    preferred_port = int(os.getenv("GRADIO_SERVER_PORT", "7860"))
    server_port = find_available_port(preferred_port)
    print(f"启动 Gradio 服务，端口: {server_port}")
    app.launch(server_name="127.0.0.1", server_port=server_port, inbrowser=True)


if __name__ == "__main__":
    main()
