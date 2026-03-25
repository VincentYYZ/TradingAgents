# A-Share And China News Adaptation Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Extend TradingAgents so it can analyze China A-share tickers and Chinese financial/news context with production-usable data vendors.

**Architecture:** Reuse the existing vendor-routed tool abstraction in `tradingagents/dataflows/interface.py`, but add China-specific vendors and normalize them into the current `get_stock_data`, `get_indicators`, `get_fundamentals`, `get_news`, and `get_global_news` tool contracts. Add market-aware prompt/config logic so A-share runs do not rely on US-only concepts such as SEC insider data or Alpha Vantage news.

**Tech Stack:** Python, LangGraph, LangChain tools, pandas, yfinance, akshare, tushare, existing CLI/config system.

---

## Workstream 1: Scope And Market Model

**Files:**
- Modify: `tradingagents/default_config.py`
- Modify: `tradingagents/dataflows/config.py`
- Modify: `cli/main.py`
- Modify: `cli/utils.py`
- Create: `tradingagents/market_profiles.py`

**Plan:**
- Add an explicit `market_profile` config, defaulting to `us_equity`.
- Add `cn_a_share` as a first-class market profile.
- Define market-profile capabilities, such as:
  - supported ticker formats
  - default data vendors
  - whether insider/SEC-style tools are available
  - default language for news/prompting
  - exchange calendar assumptions
- Expose market-profile selection in CLI before analyst/model selection.

## Workstream 2: Ticker Normalization

**Files:**
- Create: `tradingagents/dataflows/ticker_normalization.py`
- Modify: `tradingagents/agents/utils/core_stock_tools.py`
- Modify: `tradingagents/agents/utils/fundamental_data_tools.py`
- Modify: `tradingagents/agents/utils/news_data_tools.py`

**Plan:**
- Add a normalization layer that converts user input into provider-specific symbols.
- Support common A-share input forms:
  - `600519`
  - `600519.SH`
  - `000001.SZ`
  - Chinese company names when a lookup table is available
- Ensure each vendor adapter receives the symbol format it expects.

## Workstream 3: China Market Data Vendor

**Files:**
- Create: `tradingagents/dataflows/akshare_stock.py`
- Create: `tradingagents/dataflows/akshare_indicator.py`
- Modify: `tradingagents/dataflows/interface.py`
- Modify: `tradingagents/dataflows/y_finance.py`

**Plan:**
- Implement `akshare`-backed OHLCV retrieval for A-share symbols.
- Implement indicator calculation from Akshare price data, either by:
  - normalizing into the same dataframe shape used by `stockstats`, or
  - reusing current indicator code after a dataframe adapter.
- Register a new vendor, e.g. `akshare`, under:
  - `core_stock_apis`
  - `technical_indicators`
- Keep `yfinance` for US profiles, but do not rely on it as the primary A-share source.

## Workstream 4: China Fundamentals Vendor

**Files:**
- Create: `tradingagents/dataflows/tushare_fundamentals.py`
- Possibly create: `tradingagents/dataflows/akshare_fundamentals.py`
- Modify: `tradingagents/dataflows/interface.py`
- Modify: `tradingagents/default_config.py`

**Plan:**
- Implement A-share fundamentals via `tushare` or `akshare`.
- Map current tool contracts to China-appropriate data:
  - `get_fundamentals`
  - `get_balance_sheet`
  - `get_cashflow`
  - `get_income_statement`
- Remove US-specific assumptions such as SEC-centric metadata.
- Add config support for `fundamental_data = "tushare"` or `"akshare"`.

## Workstream 5: Chinese Company News Vendor

**Files:**
- Create: `tradingagents/dataflows/china_news.py`
- Modify: `tradingagents/dataflows/interface.py`
- Modify: `tradingagents/agents/utils/news_data_tools.py`
- Modify: `tradingagents/dataflows/google.py`

**Plan:**
- Add a China-specific news adapter that returns normalized article records.
- Likely sources:
  - Akshare news endpoints where available
  - Eastmoney / Sina / Juchao / Shanghai & Shenzhen exchange announcements
  - Tushare news endpoints if licensed
- Normalize output to the existing string-report contract expected by agents.
- Fix the current `google` adapter signature mismatch so vendor routing stays internally consistent.

## Workstream 6: Chinese Macro / Policy News

**Files:**
- Extend: `tradingagents/dataflows/china_news.py`
- Modify: `tradingagents/dataflows/interface.py`
- Modify: `tradingagents/agents/analysts/news_analyst.py`

**Plan:**
- Implement `get_global_news` equivalent for China context, focused on:
  - 宏观政策
  - 证监会 / 央行 / 财政部 / 发改委公告
  - 行业监管与产业政策
  - 国内经济数据发布
- Add a market-profile-aware fallback so `cn_a_share` runs do not use US/world-only news framing.

## Workstream 7: Prompt And Agent Adaptation

**Files:**
- Modify: `tradingagents/agents/analysts/fundamentals_analyst.py`
- Modify: `tradingagents/agents/analysts/news_analyst.py`
- Modify: `tradingagents/agents/analysts/social_media_analyst.py`
- Modify: `tradingagents/agents/managers/risk_manager.py`
- Modify: `tradingagents/agents/managers/research_manager.py`

**Plan:**
- Remove or conditionalize US-only concepts for `cn_a_share`:
  - SEC filings
n  - insider sentiment/insider transaction assumptions
  - English web/news assumptions
- Add market-profile-aware prompt snippets for A-share:
  - policy sensitivity
  - retail-driven momentum
  - sector rotation themes
  - exchange announcements and halt/resume events
  - state-owned enterprise factors where relevant
- Ensure analyst prompts explicitly mention Chinese-language news and A-share conventions.

## Workstream 8: Optional Social / Sentiment Strategy For China

**Files:**
- Create: `tradingagents/dataflows/china_social.py`
- Modify: `tradingagents/dataflows/interface.py`
- Modify: `tradingagents/agents/analysts/social_media_analyst.py`

**Plan:**
- Decide whether to support social sentiment at all for A-share v1.
- Recommended v1: do not treat US-style Reddit/social sentiment as core.
- Replace with China-relevant discussion sources only if you have a compliant, reliable source.
- Otherwise rename/reframe the social analyst into a broader “market sentiment / public opinion” analyst using company + news text, not raw social scraping.

## Workstream 9: Feature Flags And Safe Defaults

**Files:**
- Modify: `tradingagents/default_config.py`
- Modify: `tradingagents/graph/trading_graph.py`
- Modify: `cli/main.py`

**Plan:**
- For `cn_a_share`, disable unsupported tools by config instead of letting them fail at runtime.
- Example:
  - disable insider-sentiment tools
  - skip `get_insider_transactions` when market profile is A-share
  - default selected analysts to `market + news + fundamentals`
- Add explicit runtime validation so misconfigured vendors fail fast with a readable error.

## Workstream 10: CLI And UX

**Files:**
- Modify: `cli/main.py`
- Modify: `cli/utils.py`

**Plan:**
- Add market selection: `US Equity` vs `China A-Share`.
- Filter vendor/model prompts based on market profile.
- Add China-specific ticker examples in the prompt, such as `600519.SH` and `000001.SZ`.
- Surface active vendors in the UI so users can tell whether they are using Akshare/Tushare/China news.

## Workstream 11: Caching, Rate Limits, And Data Freshness

**Files:**
- Modify: `tradingagents/default_config.py`
- Modify: China vendor modules above
- Possibly create: `tradingagents/dataflows/cache_utils.py`

**Plan:**
- Cache Akshare/Tushare/news responses under `data_cache_dir`.
- Add TTLs appropriate for:
  - intraday/close prices
  - daily announcements
  - quarterly fundamentals
- Make date filtering exchange-calendar-aware to avoid asking for data on non-trading days.

## Workstream 12: Tests

**Files:**
- Create: `tests/dataflows/test_ticker_normalization.py`
- Create: `tests/dataflows/test_akshare_stock.py`
- Create: `tests/dataflows/test_tushare_fundamentals.py`
- Create: `tests/dataflows/test_china_news.py`
- Create: `tests/graph/test_cn_a_share_config.py`
- Create: `tests/cli/test_cn_market_selection.py`

**Plan:**
- Add unit tests for ticker normalization and vendor routing.
- Add fixture-based tests that verify A-share symbols return normalized outputs.
- Add regression tests for the current `get_news` signature mismatch.
- Add config tests that ensure unsupported US-only tools are disabled under `cn_a_share`.

## Recommended Delivery Phases

**Phase 1: Minimum viable A-share support**
- Add `market_profile`
- Add ticker normalization
- Add Akshare stock data + indicators
- Make prompts A-share-aware
- CLI market selection
- Run only `Market Analyst`

**Phase 2: Fundamentals**
- Add Tushare/Akshare fundamentals
- Adapt fundamentals analyst prompt
- Enable `Fundamentals Analyst`

**Phase 3: Chinese news**
- Add China news and macro news vendors
- Fix current `get_news` contract mismatch
- Enable `News Analyst`

**Phase 4: Sentiment and production hardening**
- Rework social/sentiment strategy for China
- Add caches, retries, validation, and more tests

## Recommendation

The project is structurally viable for A-share adaptation because its tool layer is already vendor-routed and category-based. The fastest correct strategy is not to bolt Chinese data onto the existing US-oriented vendors, but to add a first-class `cn_a_share` market profile and China-specific vendor modules while preserving the current agent graph.
