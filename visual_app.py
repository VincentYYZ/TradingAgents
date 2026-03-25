import io
import json
import queue
import threading
import traceback
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, ttk

from dotenv import load_dotenv

from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.market_profiles import MARKET_PROFILES, apply_market_profile


PROVIDER_DEFAULTS = {
    "openai": {
        "backend_url": "https://api.openai.com/v1",
        "quick_model": "gpt-4o-mini",
        "deep_model": "o4-mini",
    },
    "anthropic": {
        "backend_url": "https://api.anthropic.com/",
        "quick_model": "claude-3-5-haiku-latest",
        "deep_model": "claude-sonnet-4-0",
    },
    "google": {
        "backend_url": "https://generativelanguage.googleapis.com/v1",
        "quick_model": "gemini-2.0-flash",
        "deep_model": "gemini-2.5-pro-preview-06-05",
    },
    "openrouter": {
        "backend_url": "https://openrouter.ai/api/v1",
        "quick_model": "meta-llama/llama-3.3-8b-instruct:free",
        "deep_model": "deepseek/deepseek-chat-v3-0324:free",
    },
    "ollama": {
        "backend_url": "http://localhost:11434/v1",
        "quick_model": "qwen3:14b",
        "deep_model": "qwen3:14b",
    },
}

REPORT_TITLES = {
    "market_report": "Market Analysis",
    "sentiment_report": "Social Sentiment",
    "news_report": "News Analysis",
    "fundamentals_report": "Fundamentals Analysis",
    "investment_plan": "Research Team Decision",
    "trader_investment_plan": "Trading Team Plan",
    "final_trade_decision": "Portfolio Management Decision",
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

ALL_REPORT_SECTIONS = list(REPORT_TITLES.keys())
APP_STATE_FILE = Path(__file__).with_name(".visual_app_state.json")


def extract_content_string(content):
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        text_parts = []
        for item in content:
            if isinstance(item, dict):
                if item.get("type") == "text":
                    text_parts.append(item.get("text", ""))
                elif item.get("type") == "tool_use":
                    text_parts.append(f"[Tool: {item.get('name', 'unknown')}]")
            else:
                text_parts.append(str(item))
        return " ".join(text_parts)
    return str(content)


class QueueWriter(io.TextIOBase):
    def __init__(self, emit):
        self.emit = emit
        self.buffer = ""

    def write(self, text):
        if not text:
            return 0
        self.buffer += text
        while "\n" in self.buffer:
            line, self.buffer = self.buffer.split("\n", 1)
            if line.strip():
                self.emit("log", line)
        return len(text)

    def flush(self):
        if self.buffer.strip():
            self.emit("log", self.buffer)
        self.buffer = ""


class AnalysisWorker(threading.Thread):
    def __init__(self, selections, event_queue):
        super().__init__(daemon=True)
        self.selections = selections
        self.event_queue = event_queue
        self.statuses = {agent: "pending" for agent in STATUS_ORDER}
        self.reports = {section: "" for section in ALL_REPORT_SECTIONS}

    def emit(self, event_type, payload):
        self.event_queue.put((event_type, payload))

    def set_status(self, agent, status):
        if agent in self.statuses and self.statuses[agent] != status:
            self.statuses[agent] = status
            self.emit("status", self.statuses.copy())

    def set_report(self, section, content):
        if section in self.reports and content:
            self.reports[section] = content
            self.emit("report", {"section": section, "content": content})

    def set_research_team_status(self, status):
        for agent in ["Bull Researcher", "Bear Researcher", "Research Manager", "Trader"]:
            self.set_status(agent, status)

    def mark_initial_statuses(self):
        analyst_sequence = []
        if "market" in self.selections["analysts"]:
            analyst_sequence.append("Market Analyst")
        if "social" in self.selections["analysts"]:
            analyst_sequence.append("Social Analyst")
        if "news" in self.selections["analysts"]:
            analyst_sequence.append("News Analyst")
        if "fundamentals" in self.selections["analysts"]:
            analyst_sequence.append("Fundamentals Analyst")
        if analyst_sequence:
            self.set_status(analyst_sequence[0], "in_progress")

    def handle_chunk(self, chunk):
        messages = chunk.get("messages", [])
        if messages:
            last_message = messages[-1]
            if hasattr(last_message, "content"):
                self.emit("message", {"type": "Reasoning", "content": extract_content_string(last_message.content)})
            else:
                self.emit("message", {"type": "System", "content": str(last_message)})
            if hasattr(last_message, "tool_calls"):
                for tool_call in last_message.tool_calls:
                    if isinstance(tool_call, dict):
                        name = tool_call.get("name", "unknown")
                        args = tool_call.get("args", {})
                    else:
                        name = tool_call.name
                        args = tool_call.args
                    self.emit("tool", {"name": name, "args": args})

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
            if debate_state.get("bull_history"):
                latest_bull = debate_state["bull_history"].split("\n")[-1]
                if latest_bull:
                    self.emit("message", {"type": "Reasoning", "content": latest_bull})
                    current = self.reports.get("investment_plan", "")
                    content = f"### Bull Researcher Analysis\n{latest_bull}" if not current else current
                    self.set_report("investment_plan", content)
            if debate_state.get("bear_history"):
                latest_bear = debate_state["bear_history"].split("\n")[-1]
                if latest_bear:
                    self.emit("message", {"type": "Reasoning", "content": latest_bear})
                    current = self.reports.get("investment_plan", "")
                    prefix = current if current else ""
                    content = f"{prefix}\n\n### Bear Researcher Analysis\n{latest_bear}".strip()
                    self.set_report("investment_plan", content)
            if debate_state.get("judge_decision"):
                self.emit("message", {"type": "Reasoning", "content": f"Research Manager: {debate_state['judge_decision']}"})
                current = self.reports.get("investment_plan", "")
                content = f"{current}\n\n### Research Manager Decision\n{debate_state['judge_decision']}".strip()
                self.set_report("investment_plan", content)
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
                self.set_report("final_trade_decision", f"### Risky Analyst Analysis\n{risk_state['current_risky_response']}")
            if risk_state.get("current_safe_response"):
                self.set_status("Safe Analyst", "in_progress")
                self.set_report("final_trade_decision", f"### Safe Analyst Analysis\n{risk_state['current_safe_response']}")
            if risk_state.get("current_neutral_response"):
                self.set_status("Neutral Analyst", "in_progress")
                self.set_report("final_trade_decision", f"### Neutral Analyst Analysis\n{risk_state['current_neutral_response']}")
            if risk_state.get("judge_decision"):
                self.set_status("Portfolio Manager", "in_progress")
                self.emit("message", {"type": "Reasoning", "content": f"Portfolio Manager: {risk_state['judge_decision']}"})
                self.set_report("final_trade_decision", f"### Portfolio Manager Decision\n{risk_state['judge_decision']}")
                for agent in ["Risky Analyst", "Safe Analyst", "Neutral Analyst", "Portfolio Manager"]:
                    self.set_status(agent, "completed")

    def build_config(self):
        config = apply_market_profile(DEFAULT_CONFIG.copy(), self.selections["market_profile"])
        config["llm_provider"] = self.selections["llm_provider"]
        config["backend_url"] = self.selections["backend_url"]
        config["quick_think_llm"] = self.selections["quick_model"]
        config["deep_think_llm"] = self.selections["deep_model"]
        config["max_debate_rounds"] = self.selections["research_depth"]
        config["max_risk_discuss_rounds"] = self.selections["research_depth"]
        config["tool_vendors"] = {}
        if self.selections["embedding_model"]:
            config["embedding_model"] = self.selections["embedding_model"]
        return config

    def run(self):
        log_writer = QueueWriter(self.emit)
        try:
            load_dotenv()
            self.emit("run_state", {"state": "running", "message": "正在初始化分析任务..."})
            self.emit("status", self.statuses.copy())
            self.emit("message", {"type": "System", "content": f"Selected ticker: {self.selections['ticker']}"})
            self.emit("message", {"type": "System", "content": f"Analysis date: {self.selections['trade_date']}"})
            self.emit("message", {"type": "System", "content": f"Selected analysts: {', '.join(self.selections['analysts'])}"})
            self.mark_initial_statuses()
            config = self.build_config()
            with redirect_stdout(log_writer), redirect_stderr(log_writer):
                graph = TradingAgentsGraph(
                    selected_analysts=self.selections["analysts"],
                    debug=False,
                    config=config,
                )
                init_agent_state = graph.propagator.create_initial_state(
                    self.selections["ticker"],
                    self.selections["trade_date"],
                )
                args = graph.propagator.get_graph_args()
                trace = []
                for chunk in graph.graph.stream(init_agent_state, **args):
                    trace.append(chunk)
                    self.handle_chunk(chunk)
                final_state = trace[-1]
                decision = graph.process_signal(final_state["final_trade_decision"])
            for agent in self.statuses:
                self.statuses[agent] = "completed"
            self.emit("status", self.statuses.copy())
            self.emit("final", {"decision": decision, "state": final_state})
            self.emit("run_state", {"state": "completed", "message": "分析已完成"})
        except Exception as exc:
            self.emit("error", {"message": str(exc), "traceback": traceback.format_exc()})
            self.emit("run_state", {"state": "failed", "message": "分析执行失败"})
        finally:
            log_writer.flush()
            self.emit("done", None)


class TradingAgentsVisualApp:
    def __init__(self, root):
        self.root = root
        self.root.title("TradingAgents Visual Runner")
        self.root.geometry("1580x940")
        self.event_queue = queue.Queue()
        self.worker = None
        self.status_rows = {}
        self.report_widgets = {}
        self.active_report_tab = None
        self.config_path_var = tk.StringVar(value="local_ollama_config.json")
        self.results_dir_var = tk.StringVar(value=DEFAULT_CONFIG["results_dir"])
        self.last_output_dir_var = tk.StringVar(value="未保存")
        self.market_profile_var = tk.StringVar(value="cn_a_share")
        self.ticker_var = tk.StringVar(value=MARKET_PROFILES["cn_a_share"]["default_ticker"])
        self.trade_date_var = tk.StringVar(value=datetime.now().strftime("%Y-%m-%d"))
        self.llm_provider_var = tk.StringVar(value="ollama")
        self.backend_url_var = tk.StringVar(value=PROVIDER_DEFAULTS["ollama"]["backend_url"])
        self.quick_model_var = tk.StringVar(value=PROVIDER_DEFAULTS["ollama"]["quick_model"])
        self.deep_model_var = tk.StringVar(value=PROVIDER_DEFAULTS["ollama"]["deep_model"])
        self.embedding_model_var = tk.StringVar(value="nomic-embed-text")
        self.research_depth_var = tk.IntVar(value=1)
        self.run_state_var = tk.StringVar(value="未运行")
        self.progress_var = tk.DoubleVar(value=0.0)
        self.progress_label_var = tk.StringVar(value="Progress: 0/12 completed")
        self.active_agents_var = tk.StringVar(value="Running now: none")
        self.analyst_vars = {
            "market": tk.BooleanVar(value=True),
            "social": tk.BooleanVar(value=False),
            "news": tk.BooleanVar(value=True),
            "fundamentals": tk.BooleanVar(value=True),
        }
        self.current_run_selections = None
        self.configure_styles()
        self.build_ui()
        self.load_app_state()
        self.refresh_analyst_controls()
        self.update_progress_display()
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.root.after(150, self.process_events)

    def configure_styles(self):
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure("Status.Treeview", font=("TkDefaultFont", 12), rowheight=30)
        style.configure("Status.Treeview.Heading", font=("TkDefaultFont", 12, "bold"))

    def build_ui(self):
        self.root.columnconfigure(0, weight=0)
        self.root.columnconfigure(1, weight=1)
        self.root.rowconfigure(0, weight=1)

        left = ttk.Frame(self.root, padding=12)
        left.grid(row=0, column=0, sticky="ns")
        right = ttk.Frame(self.root, padding=12)
        right.grid(row=0, column=1, sticky="nsew")
        right.columnconfigure(0, weight=1)
        right.rowconfigure(1, weight=1)
        right.rowconfigure(2, weight=1)

        config_frame = ttk.LabelFrame(left, text="运行配置", padding=12)
        config_frame.grid(row=0, column=0, sticky="nsew")
        config_frame.columnconfigure(1, weight=1)

        row = 0
        self.add_entry_row(config_frame, row, "配置文件", self.config_path_var)
        row += 1
        button_row = ttk.Frame(config_frame)
        button_row.grid(row=row, column=0, columnspan=2, sticky="ew", pady=(0, 8))
        ttk.Button(button_row, text="加载配置", command=self.load_config_file).pack(side="left")
        ttk.Button(button_row, text="保存配置", command=self.save_config_file).pack(side="left", padx=(8, 0))
        ttk.Button(button_row, text="A股 + Ollama 预设", command=self.apply_cn_ollama_preset).pack(side="left", padx=(8, 0))
        row += 1

        self.add_combo_row(config_frame, row, "市场", self.market_profile_var, ["cn_a_share", "us_equity"], self.on_market_changed)
        row += 1
        self.add_entry_row(config_frame, row, "Ticker", self.ticker_var)
        row += 1
        self.add_entry_row(config_frame, row, "日期", self.trade_date_var)
        row += 1
        self.add_entry_row(config_frame, row, "结果目录", self.results_dir_var)
        row += 1
        self.add_combo_row(config_frame, row, "LLM Provider", self.llm_provider_var, list(PROVIDER_DEFAULTS.keys()), self.on_provider_changed)
        row += 1
        self.add_entry_row(config_frame, row, "Backend URL", self.backend_url_var)
        row += 1
        self.add_entry_row(config_frame, row, "Quick Model", self.quick_model_var)
        row += 1
        self.add_entry_row(config_frame, row, "Deep Model", self.deep_model_var)
        row += 1
        self.add_entry_row(config_frame, row, "Embedding Model", self.embedding_model_var)
        row += 1
        self.add_combo_row(config_frame, row, "研究深度", self.research_depth_var, [1, 3, 5])
        row += 1

        analyst_frame = ttk.LabelFrame(config_frame, text="Analysts", padding=8)
        analyst_frame.grid(row=row, column=0, columnspan=2, sticky="ew", pady=(8, 0))
        self.analyst_checks = {}
        for idx, name in enumerate(["market", "social", "news", "fundamentals"]):
            check = ttk.Checkbutton(analyst_frame, text=name, variable=self.analyst_vars[name])
            check.grid(row=idx // 2, column=idx % 2, sticky="w", padx=(0, 12), pady=4)
            self.analyst_checks[name] = check
        row += 1

        action_row = ttk.Frame(config_frame)
        action_row.grid(row=row, column=0, columnspan=2, sticky="ew", pady=(12, 0))
        self.run_button = ttk.Button(action_row, text="启动分析", command=self.start_analysis)
        self.run_button.pack(side="left")
        self.stop_note = ttk.Label(action_row, textvariable=self.run_state_var)
        self.stop_note.pack(side="left", padx=(10, 0))
        row += 1

        ttk.Label(config_frame, text="最近输出").grid(row=row, column=0, sticky="nw", pady=(10, 4))
        ttk.Label(config_frame, textvariable=self.last_output_dir_var, wraplength=260, justify="left").grid(row=row, column=1, sticky="w", pady=(10, 4))

        status_frame = ttk.LabelFrame(right, text="运行状态", padding=10)
        status_frame.grid(row=0, column=0, sticky="nsew", pady=(0, 10))
        status_frame.columnconfigure(0, weight=1)
        status_frame.rowconfigure(1, weight=1)
        progress_frame = ttk.Frame(status_frame)
        progress_frame.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 8))
        progress_frame.columnconfigure(0, weight=1)
        ttk.Progressbar(progress_frame, variable=self.progress_var, maximum=len(STATUS_ORDER)).grid(row=0, column=0, sticky="ew")
        ttk.Label(progress_frame, textvariable=self.progress_label_var).grid(row=1, column=0, sticky="w", pady=(4, 0))
        ttk.Label(progress_frame, textvariable=self.active_agents_var, foreground="#1f6feb").grid(row=2, column=0, sticky="w", pady=(4, 0))
        self.status_tree = ttk.Treeview(status_frame, columns=("status",), show="headings", height=12, style="Status.Treeview")
        self.status_tree.heading("status", text="状态")
        self.status_tree.column("status", width=180, anchor="center")
        self.status_tree.grid(row=1, column=0, sticky="nsew")
        scrollbar = ttk.Scrollbar(status_frame, orient="vertical", command=self.status_tree.yview)
        scrollbar.grid(row=1, column=1, sticky="ns")
        self.status_tree.configure(yscrollcommand=scrollbar.set)
        self.status_tree.tag_configure("pending", foreground="#8a6d3b", background="#fff7e6")
        self.status_tree.tag_configure("in_progress", foreground="#0b57d0", background="#e8f0fe")
        self.status_tree.tag_configure("completed", foreground="#1a7f37", background="#ecfdf3")
        self.status_tree.tag_configure("error", foreground="#b42318", background="#fef3f2")
        for agent in STATUS_ORDER:
            item = self.status_tree.insert("", "end", values=("pending",), text=agent)
            self.status_tree.item(item, text=agent)
            self.status_rows[agent] = item
        self.status_tree["show"] = "tree headings"
        self.status_tree.heading("#0", text="Agent")
        self.status_tree.column("#0", width=320, anchor="w")

        notebook = ttk.Notebook(right)
        notebook.grid(row=1, column=0, sticky="nsew", pady=(0, 10))

        log_tab = ttk.Frame(notebook)
        notebook.add(log_tab, text="日志")
        self.log_text = scrolledtext.ScrolledText(log_tab, wrap="word", font=("Consolas", 10))
        self.log_text.pack(fill="both", expand=True)

        message_tab = ttk.Frame(notebook)
        notebook.add(message_tab, text="消息")
        self.message_text = scrolledtext.ScrolledText(message_tab, wrap="word", font=("Consolas", 10))
        self.message_text.pack(fill="both", expand=True)

        tool_tab = ttk.Frame(notebook)
        notebook.add(tool_tab, text="工具调用")
        self.tool_text = scrolledtext.ScrolledText(tool_tab, wrap="word", font=("Consolas", 10))
        self.tool_text.pack(fill="both", expand=True)

        reports_tab = ttk.Frame(notebook)
        notebook.add(reports_tab, text="报告")
        reports_tab.columnconfigure(0, weight=1)
        reports_tab.rowconfigure(0, weight=1)
        self.report_notebook = ttk.Notebook(reports_tab)
        self.report_notebook.grid(row=0, column=0, sticky="nsew")
        for section, title in REPORT_TITLES.items():
            tab = ttk.Frame(self.report_notebook)
            tab.columnconfigure(0, weight=1)
            tab.rowconfigure(0, weight=1)
            widget = scrolledtext.ScrolledText(tab, wrap="word", font=("Consolas", 10))
            widget.grid(row=0, column=0, sticky="nsew")
            self.report_notebook.add(tab, text=title)
            self.report_widgets[section] = widget

        final_frame = ttk.LabelFrame(right, text="最终结果", padding=10)
        final_frame.grid(row=2, column=0, sticky="nsew")
        final_frame.columnconfigure(0, weight=1)
        final_frame.rowconfigure(0, weight=1)
        self.final_text = scrolledtext.ScrolledText(final_frame, wrap="word", font=("Consolas", 10))
        self.final_text.grid(row=0, column=0, sticky="nsew")

    def add_entry_row(self, parent, row, label, variable):
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", pady=4)
        entry = ttk.Entry(parent, textvariable=variable, width=34)
        entry.grid(row=row, column=1, sticky="ew", pady=4)
        return entry

    def add_combo_row(self, parent, row, label, variable, values, callback=None):
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", pady=4)
        combo = ttk.Combobox(parent, textvariable=variable, values=values, state="readonly", width=32)
        combo.grid(row=row, column=1, sticky="ew", pady=4)
        if callback:
            combo.bind("<<ComboboxSelected>>", callback)
        return combo

    def on_provider_changed(self, _event=None):
        provider = self.llm_provider_var.get()
        defaults = PROVIDER_DEFAULTS[provider]
        self.backend_url_var.set(defaults["backend_url"])
        self.quick_model_var.set(defaults["quick_model"])
        self.deep_model_var.set(defaults["deep_model"])
        if provider == "ollama" and not self.embedding_model_var.get().strip():
            self.embedding_model_var.set("nomic-embed-text")
        self.save_app_state()

    def on_market_changed(self, _event=None):
        market = self.market_profile_var.get()
        self.ticker_var.set(MARKET_PROFILES[market]["default_ticker"])
        self.refresh_analyst_controls()
        if market == "cn_a_share" and self.llm_provider_var.get() == "ollama" and not self.embedding_model_var.get().strip():
            self.embedding_model_var.set("nomic-embed-text")
        self.save_app_state()

    def apply_cn_ollama_preset(self):
        self.market_profile_var.set("cn_a_share")
        self.llm_provider_var.set("ollama")
        self.ticker_var.set(MARKET_PROFILES["cn_a_share"]["default_ticker"])
        self.backend_url_var.set(PROVIDER_DEFAULTS["ollama"]["backend_url"])
        self.quick_model_var.set(PROVIDER_DEFAULTS["ollama"]["quick_model"])
        self.deep_model_var.set(PROVIDER_DEFAULTS["ollama"]["deep_model"])
        self.embedding_model_var.set("nomic-embed-text")
        self.research_depth_var.set(1)
        self.analyst_vars["market"].set(True)
        self.analyst_vars["social"].set(False)
        self.analyst_vars["news"].set(True)
        self.analyst_vars["fundamentals"].set(True)
        self.refresh_analyst_controls()
        self.save_app_state()

    def refresh_analyst_controls(self):
        market = self.market_profile_var.get()
        supported = set(MARKET_PROFILES[market]["supported_analysts"])
        for name, check in self.analyst_checks.items():
            if name in supported:
                check.state(["!disabled"])
                if name == "market" and not self.analyst_vars[name].get():
                    self.analyst_vars[name].set(True)
            else:
                self.analyst_vars[name].set(False)
                check.state(["disabled"])

    def collect_selections(self):
        market_profile = self.market_profile_var.get().strip()
        if market_profile not in MARKET_PROFILES:
            raise ValueError("不支持的 market_profile")
        analysts = [name for name, var in self.analyst_vars.items() if var.get()]
        if not analysts:
            raise ValueError("至少选择一个 analyst")
        unsupported = [name for name in analysts if name not in MARKET_PROFILES[market_profile]["supported_analysts"]]
        if unsupported:
            raise ValueError(f"当前市场不支持这些 analysts: {', '.join(unsupported)}")
        trade_date = self.trade_date_var.get().strip()
        datetime.strptime(trade_date, "%Y-%m-%d")
        ticker = self.ticker_var.get().strip().upper()
        if not ticker:
            raise ValueError("Ticker 不能为空")
        backend_url = self.backend_url_var.get().strip()
        quick_model = self.quick_model_var.get().strip()
        deep_model = self.deep_model_var.get().strip()
        if not backend_url:
            raise ValueError("Backend URL 不能为空")
        if not quick_model or not deep_model:
            raise ValueError("Quick Model 和 Deep Model 都不能为空")
        return {
            "market_profile": market_profile,
            "ticker": ticker,
            "trade_date": trade_date,
            "llm_provider": self.llm_provider_var.get().strip().lower(),
            "backend_url": backend_url,
            "quick_model": quick_model,
            "deep_model": deep_model,
            "embedding_model": self.embedding_model_var.get().strip(),
            "research_depth": int(self.research_depth_var.get()),
            "analysts": analysts,
            "results_dir": self.results_dir_var.get().strip() or DEFAULT_CONFIG["results_dir"],
        }

    def load_config_file(self):
        initial_path = self.config_path_var.get().strip() or "local_ollama_config.json"
        file_path = filedialog.askopenfilename(initialdir=str(Path(initial_path).resolve().parent), filetypes=[("JSON", "*.json"), ("All files", "*")])
        if not file_path:
            return
        data = json.loads(Path(file_path).read_text())
        self.config_path_var.set(file_path)
        market = data.get("market_profile", self.market_profile_var.get())
        if market in MARKET_PROFILES:
            self.market_profile_var.set(market)
        provider = data.get("llm_provider", self.llm_provider_var.get())
        if provider in PROVIDER_DEFAULTS:
            self.llm_provider_var.set(provider)
        self.backend_url_var.set(data.get("backend_url", self.backend_url_var.get()))
        self.quick_model_var.set(data.get("quick_think_llm", self.quick_model_var.get()))
        self.deep_model_var.set(data.get("deep_think_llm", self.deep_model_var.get()))
        self.embedding_model_var.set(data.get("embedding_model", self.embedding_model_var.get()))
        self.trade_date_var.set(data.get("trade_date", self.trade_date_var.get()))
        self.ticker_var.set(data.get("ticker", self.ticker_var.get()))
        self.research_depth_var.set(int(data.get("max_debate_rounds", self.research_depth_var.get())))
        self.results_dir_var.set(data.get("results_dir", self.results_dir_var.get()))
        selected = set(data.get("selected_analysts", []))
        for name, var in self.analyst_vars.items():
            var.set(name in selected)
        self.refresh_analyst_controls()
        self.save_app_state()

    def save_config_file(self):
        try:
            selections = self.collect_selections()
        except Exception as exc:
            messagebox.showerror("配置错误", str(exc))
            return
        initial_path = self.config_path_var.get().strip() or "visual_config.json"
        file_path = filedialog.asksaveasfilename(initialfile=Path(initial_path).name, defaultextension=".json", filetypes=[("JSON", "*.json")])
        if not file_path:
            return
        data = {
            "ticker": selections["ticker"],
            "trade_date": selections["trade_date"],
            "selected_analysts": selections["analysts"],
            "market_profile": selections["market_profile"],
            "llm_provider": selections["llm_provider"],
            "backend_url": selections["backend_url"],
            "deep_think_llm": selections["deep_model"],
            "quick_think_llm": selections["quick_model"],
            "embedding_model": selections["embedding_model"],
            "max_debate_rounds": selections["research_depth"],
            "max_risk_discuss_rounds": selections["research_depth"],
            "results_dir": selections["results_dir"],
        }
        Path(file_path).write_text(json.dumps(data, ensure_ascii=False, indent=2))
        self.config_path_var.set(file_path)
        self.save_app_state()
        messagebox.showinfo("已保存", f"配置已保存到\n{file_path}")

    def get_ui_snapshot(self):
        return {
            "config_path": self.config_path_var.get().strip(),
            "results_dir": self.results_dir_var.get().strip(),
            "last_output_dir": self.last_output_dir_var.get().strip(),
            "market_profile": self.market_profile_var.get().strip(),
            "ticker": self.ticker_var.get().strip(),
            "trade_date": self.trade_date_var.get().strip(),
            "llm_provider": self.llm_provider_var.get().strip(),
            "backend_url": self.backend_url_var.get().strip(),
            "quick_model": self.quick_model_var.get().strip(),
            "deep_model": self.deep_model_var.get().strip(),
            "embedding_model": self.embedding_model_var.get().strip(),
            "research_depth": int(self.research_depth_var.get()),
            "selected_analysts": [name for name, var in self.analyst_vars.items() if var.get()],
        }

    def load_app_state(self):
        if not APP_STATE_FILE.exists():
            return
        try:
            data = json.loads(APP_STATE_FILE.read_text())
        except Exception:
            return
        if data.get("market_profile") in MARKET_PROFILES:
            self.market_profile_var.set(data["market_profile"])
        if data.get("llm_provider") in PROVIDER_DEFAULTS:
            self.llm_provider_var.set(data["llm_provider"])
        self.config_path_var.set(data.get("config_path", self.config_path_var.get()))
        self.results_dir_var.set(data.get("results_dir", self.results_dir_var.get()))
        self.last_output_dir_var.set(data.get("last_output_dir", self.last_output_dir_var.get()))
        self.ticker_var.set(data.get("ticker", self.ticker_var.get()))
        self.trade_date_var.set(data.get("trade_date", self.trade_date_var.get()))
        self.backend_url_var.set(data.get("backend_url", self.backend_url_var.get()))
        self.quick_model_var.set(data.get("quick_model", self.quick_model_var.get()))
        self.deep_model_var.set(data.get("deep_model", self.deep_model_var.get()))
        self.embedding_model_var.set(data.get("embedding_model", self.embedding_model_var.get()))
        self.research_depth_var.set(int(data.get("research_depth", self.research_depth_var.get())))
        selected = set(data.get("selected_analysts", []))
        for name, var in self.analyst_vars.items():
            var.set(name in selected)

    def save_app_state(self):
        try:
            APP_STATE_FILE.write_text(json.dumps(self.get_ui_snapshot(), ensure_ascii=False, indent=2))
        except Exception:
            return

    def build_output_dir(self, selections):
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        return Path(selections["results_dir"]) / selections["ticker"] / selections["trade_date"] / f"visual_app_{timestamp}"

    def persist_run_outputs(self, final_payload=None, error_payload=None):
        if not self.current_run_selections:
            return
        output_dir = self.build_output_dir(self.current_run_selections)
        reports_dir = output_dir / "reports"
        reports_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "config_used.json").write_text(json.dumps(self.current_run_selections, ensure_ascii=False, indent=2))
        (output_dir / "logs.txt").write_text(self.log_text.get("1.0", "end-1c"))
        (output_dir / "messages.txt").write_text(self.message_text.get("1.0", "end-1c"))
        (output_dir / "tool_calls.txt").write_text(self.tool_text.get("1.0", "end-1c"))
        for section, widget in self.report_widgets.items():
            content = widget.get("1.0", "end-1c").strip()
            if content:
                (reports_dir / f"{section}.md").write_text(content)
        if final_payload:
            (output_dir / "final_output.md").write_text(self.final_text.get("1.0", "end-1c"))
            (output_dir / "final_state.json").write_text(json.dumps(final_payload["state"], ensure_ascii=False, indent=2, default=str))
            (output_dir / "processed_decision.txt").write_text(str(final_payload["decision"]))
        if error_payload:
            (output_dir / "error.txt").write_text(error_payload["traceback"])
        self.last_output_dir_var.set(str(output_dir))
        self.save_app_state()

    def update_progress_display(self, statuses=None):
        current_statuses = statuses or {agent: self.status_tree.item(item, "values")[0] for agent, item in self.status_rows.items()}
        completed = sum(1 for status in current_statuses.values() if status == "completed")
        in_progress = sum(1 for status in current_statuses.values() if status == "in_progress")
        active_agents = [agent for agent, status in current_statuses.items() if status == "in_progress"]
        self.progress_var.set(completed)
        self.progress_label_var.set(f"Progress: {completed}/{len(STATUS_ORDER)} completed, {in_progress} in progress")
        self.active_agents_var.set(f"Running now: {', '.join(active_agents) if active_agents else 'none'}")

    def append_text(self, widget, content):
        widget.insert("end", content + "\n")
        widget.see("end")

    def reset_outputs(self):
        for widget in [self.log_text, self.message_text, self.tool_text, self.final_text, *self.report_widgets.values()]:
            widget.delete("1.0", "end")
        for agent, item in self.status_rows.items():
            self.status_tree.item(item, values=("pending",), tags=("pending",))
        self.run_state_var.set("准备运行")
        self.progress_var.set(0)
        self.update_progress_display()

    def start_analysis(self):
        if self.worker and self.worker.is_alive():
            messagebox.showwarning("运行中", "当前已有任务在运行，请等待完成。")
            return
        try:
            selections = self.collect_selections()
        except Exception as exc:
            messagebox.showerror("配置错误", str(exc))
            return
        self.reset_outputs()
        self.run_button.state(["disabled"])
        self.run_state_var.set("运行中...")
        self.current_run_selections = selections
        self.save_app_state()
        self.worker = AnalysisWorker(selections, self.event_queue)
        self.worker.start()

    def handle_status_update(self, statuses):
        for agent, status in statuses.items():
            if agent in self.status_rows:
                self.status_tree.item(self.status_rows[agent], values=(status,), tags=(status,))
        self.update_progress_display(statuses)

    def handle_report_update(self, payload):
        section = payload["section"]
        content = payload["content"]
        widget = self.report_widgets[section]
        widget.delete("1.0", "end")
        widget.insert("1.0", content)
        tab_index = ALL_REPORT_SECTIONS.index(section)
        self.report_notebook.select(tab_index)

    def handle_final(self, payload):
        state = payload["state"]
        decision = payload["decision"]
        output_parts = [f"Processed decision:\n\n{decision}"]
        for section in ALL_REPORT_SECTIONS:
            value = state.get(section)
            if value:
                output_parts.append(f"\n\n## {REPORT_TITLES[section]}\n\n{value}")
                self.handle_report_update({"section": section, "content": value})
        self.final_text.delete("1.0", "end")
        self.final_text.insert("1.0", "".join(output_parts))
        self.persist_run_outputs(final_payload=payload)

    def on_close(self):
        self.save_app_state()
        self.root.destroy()

    def process_events(self):
        while True:
            try:
                event_type, payload = self.event_queue.get_nowait()
            except queue.Empty:
                break
            if event_type == "log":
                self.append_text(self.log_text, payload)
            elif event_type == "message":
                self.append_text(self.message_text, f"[{payload['type']}] {payload['content']}")
            elif event_type == "tool":
                self.append_text(self.tool_text, f"{payload['name']}({payload['args']})")
            elif event_type == "status":
                self.handle_status_update(payload)
            elif event_type == "report":
                self.handle_report_update(payload)
            elif event_type == "final":
                self.handle_final(payload)
            elif event_type == "error":
                self.append_text(self.log_text, payload["traceback"])
                self.persist_run_outputs(error_payload=payload)
                messagebox.showerror("运行失败", payload["message"])
            elif event_type == "run_state":
                self.run_state_var.set(payload["message"])
            elif event_type == "done":
                self.run_button.state(["!disabled"])
        self.root.after(150, self.process_events)


def main():
    load_dotenv()
    root = tk.Tk()
    app = TradingAgentsVisualApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
