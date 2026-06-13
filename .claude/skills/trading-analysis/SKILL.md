---
name: trading-analysis
description: Run a TradingAgents-style multi-agent stock/asset analysis without any LLM API key — Claude plays every agent role (analysts, bull/bear researchers, trader, risk debate, portfolio manager) while reusing the project's own data-fetching scripts. Use when the user asks to analyze a ticker, get a BUY/HOLD/SELL view, run "the trading agents", or do multi-agent financial analysis on a symbol and date.
---

# Trading Analysis (key-free, Claude-as-agents)

This skill reproduces the TradingAgents multi-agent pipeline **inside Claude Code, with no LLM API key**. The original framework spends one paid LLM call per agent; here **you (Claude) are the LLM** and play every role, while reusing the project's existing data layer via a thin CLI.

> Research scaffold only. This is **not** financial/investment/trading advice, and not a byte-for-byte reproduction of the LangGraph pipeline — you role-play the agents sequentially in one context rather than as independent model calls. Always carry the disclaimer into the final output.

## Inputs

Ask the user for (or infer from the request):
- **Ticker** — exchange-suffixed where non-US (`AAPL`, `0700.HK`, `7203.T`, `RELIANCE.NS`, `BTC-USD`).
- **Analysis date** — `YYYY-MM-DD`. Defaults to today if unspecified.
- Optional: **debate rounds** (default 1 bull/bear round, 1 risk round).

## The data CLI (no API key, no LLM)

All market data comes from `scripts/ta_data.py`, which wraps `tradingagents/dataflows`. Default vendor is yfinance (free); Reddit/StockTwits use public endpoints; Alpha Vantage is only a fallback and is never required. Run it with `python3` (or `python`) from the project root.

```
python3 .claude/skills/trading-analysis/scripts/ta_data.py <command> [args]
```

**Fast path — pull everything once:** `gather TICKER CURR_DATE` runs identity + verified snapshot + price history + 8 indicators + fundamentals/statements + insider + ticker & macro news + StockTwits + Reddit in a single call, with stable `## SECTION` delimiters and per-section error isolation. Prefer this, then play the agent roles over the bundle; fall back to the individual commands below only to dig deeper.

| Command | Args | Purpose |
|---|---|---|
| `gather` | `TICKER CURR_DATE [--price-window N]` | **One-shot full data bundle (recommended first call)** |
| `identity` | `TICKER` | Deterministic company/asset identity — anchor all reports to it |
| `stock_data` | `SYMBOL START END` | OHLCV price history |
| `indicators` | `SYMBOL NAMES CURR_DATE [LOOKBACK]` | Technical indicators; comma-separate names |
| `snapshot` | `SYMBOL CURR_DATE [LOOKBACK]` | **Verified** OHLCV + indicators — source of truth for exact numbers |
| `fundamentals` | `TICKER CURR_DATE` | Comprehensive fundamentals |
| `balance_sheet` / `cashflow` / `income_statement` | `TICKER [FREQ] [CURR_DATE]` | Financial statements (`FREQ`=annual\|quarterly) |
| `news` | `TICKER START END` | Ticker-specific news |
| `global_news` | `CURR_DATE [LOOKBACK] [LIMIT]` | Macro/global news |
| `insider` | `TICKER` | Insider transactions |
| `sentiment` | `TICKER CURR_DATE` | News + StockTwits + Reddit bundle (sentiment-analyst inputs) |
| `stocktwits` / `reddit` | `TICKER` | Individual social sources |

Indicator names: `close_50_sma`, `close_200_sma`, `close_10_ema`, `macd`, `macds`, `macdh`, `rsi`, `boll`, `boll_ub`, `boll_lb`, `atr`, `vwma`.

## The memory CLI (persistent decision log, no key)

`scripts/ta_memory.py` writes a markdown decision log **byte-compatible** with the real framework's `~/.tradingagents/memory/trading_memory.md`, so runs accumulate lessons and feed them back into later analyses — exactly like the original's reflection layer, but driven by you instead of a paid LLM.

```
python3 .claude/skills/trading-analysis/scripts/ta_memory.py <command> [args]
```

| Command | Args | Purpose |
|---|---|---|
| `recall` | `TICKER` | Past same-ticker + cross-ticker lessons — **inject at the start** |
| `log` | `TICKER DATE [--file f \| --text … \| stdin]` | Append the final decision as a pending entry — **run at the end** |
| `pending` | `[TICKER]` | List decisions still awaiting an outcome |
| `returns` | `TICKER DATE [--holding-days N]` | Compute realised raw + alpha-vs-benchmark return from prices |
| `resolve` | `TICKER DATE --reflection-file f [--holding-days N]` | Attach the realised return + your one-paragraph reflection to a pending entry |

Path: `$TRADINGAGENTS_MEMORY_LOG_PATH`, else `~/.tradingagents/memory/trading_memory.md` (override per-call with `--path`). Benchmark for alpha is auto-resolved from the ticker suffix (SPY for US, `^N225` for `.T`, etc.).

**Data integrity rule (non-negotiable):** Only state prices, levels, RSI/MACD/MA values, % moves, or support/resistance that appear in tool output. If a command prints `NO_DATA` / `NO_DATA_AVAILABLE` / `ERROR`, report the data as unavailable — **never estimate or fabricate a number.** When a tool output conflicts with the verified `snapshot`, treat the snapshot as truth and flag the discrepancy.

## Pipeline

Run the stages in order. Write each report to a section as you go; later stages consume earlier ones. Keep the internal debate in English for reasoning quality even if the final summary is requested in another language.

### Stage 0 — Recall + resolve identity
First run `ta_memory.py recall TICKER` and, if it returns prior lessons, weave them into your reasoning (they feed the Portfolio Manager just as in the original). Also resolve any matured pending entries while you're here: `ta_memory.py pending`, then for each that now has enough price history, write a one-paragraph reflection and `ta_memory.py resolve …` it.

Then run `ta_data.py identity TICKER` (or take it from the `gather` bundle). Use the resolved company/sector in every downstream section. Do not substitute a different company unless a later tool result explicitly disproves it. (For crypto `-USD` tickers, treat as an asset; fundamentals may be unavailable.)

### Stage 1 — Analyst team (gather + report)
Produce four standalone reports. Each ends with a Markdown summary table.

1. **Market / Technical Analyst.** Run `snapshot` (treat as source of truth), `stock_data`, then `indicators` for **up to 8 complementary** indicators (no redundant pairs, e.g. not both rsi and stochrsi). Briefly justify each chosen indicator for the current regime. Write a detailed, evidence-grounded trend report.
2. **Sentiment Analyst.** Run `sentiment TICKER CURR_DATE`. Read the StockTwits Bullish/Bearish ratio (≈70/30 mildly bullish; ≥90/10 possible over-extension/contrarian risk; 50/50 uncertain — weight by message count). Weight Reddit by engagement; flag cross-source divergences and data limits. Emit: **overall_band** (Bullish/Mildly Bullish/Neutral/Mixed/Mildly Bearish/Bearish), **overall_score** 0–10, **confidence** (low/med/high), and a narrative with a signal table.
3. **News Analyst.** Run `news TICKER START END` (≈7-day window) and `global_news CURR_DATE`. Summarize company-specific and macro developments relevant to trading.
4. **Fundamentals Analyst.** Run `fundamentals`, plus `balance_sheet`/`cashflow`/`income_statement` and `insider` as useful. Cover financial health (explicitly checking the PEG ratio), profile, history, red flags. (Skip/curtail for crypto.)

### Stage 2 — Research debate (bull vs bear)
Using all four analyst reports, run `max_debate_rounds` rounds (default 1). Each round:
- **Bull Researcher** — evidence-based case for the position: growth potential, competitive advantages, positive indicators; directly rebut the latest bear points. Conversational, engaging — argue, don't just list.
- **Bear Researcher** — case against: risks/challenges, competitive weaknesses, negative indicators; expose over-optimistic bull assumptions and rebut directly.

### Stage 3 — Research Manager → investment plan
Critically judge the debate and commit to a clear stance using exactly one rating: **Buy / Overweight / Hold / Underweight / Sell** (reserve Hold for genuinely balanced evidence). Produce an actionable investment plan for the trader.

### Stage 4 — Trader → transaction proposal
Turn the investment plan into a concrete proposal anchored in the analyst reports and plan: direction, conviction, rough sizing/entry logic, and key risks to monitor.

### Stage 5 — Risk debate (3-way)
Run `max_risk_discuss_rounds` rounds (default 1) over the trader's proposal:
- **Aggressive** analyst — champion high-reward/high-risk upside.
- **Conservative** analyst — protect capital, minimize volatility, flag downside.
- **Neutral** analyst — balanced, sustainable middle path; critique both extremes.

### Stage 6 — Portfolio Manager → final decision
Synthesize the risk debate **and any recalled past lessons** into the **final decision** with exactly one rating (**Buy / Overweight / Hold / Underweight / Sell**), decisive and grounded in specific evidence. Map to a clear **FINAL TRANSACTION PROPOSAL: BUY/HOLD/SELL** line, and include a specific **VERDICT FOR NEW INVESTORS** outlining whether it's a suitable entry point and the suggested investment horizon.

### Stage 7 — Persist the decision
Save the final decision to a per-ticker file **and** append it to the memory log so the next run can learn from it.

1. Write the decision to `analyzed-stocks/<TICKER>/<DATE>_decision.md` (repo-relative; create the dir if missing). Start the file with a `FINAL TRANSACTION PROPOSAL: **BUY/HOLD/SELL**` line, a `VERDICT FOR NEW INVESTORS:` line, and a `Rating: <5-tier>` line so the rating parses cleanly, followed by the decision summary, key evidence, and the plan.
2. Log it:
```
mkdir -p analyzed-stocks/TICKER
# (write the decision file to analyzed-stocks/TICKER/DATE_decision.md)
python3 .claude/skills/trading-analysis/scripts/ta_memory.py log TICKER DATE --file analyzed-stocks/TICKER/DATE_decision.md
```
The log entry is stored `pending`; a later run resolves it with the realised return once enough trading days have passed. The `analyzed-stocks/` tree is the human-readable archive; the memory log is the machine-readable feedback loop — keep both.

## Output format

Present, in this order:
1. **Final decision** up top: `FINAL TRANSACTION PROPOSAL: **BUY/HOLD/SELL**` + the five-tier rating + **VERDICT FOR NEW INVESTORS** + 2–3 sentence rationale.
2. Collapsible/clearly-headed sections for each stage (4 analyst reports → research debate + plan → trader proposal → risk debate → PM decision).
3. A one-line **data caveat** noting any source that returned no data / fell back, and the standard not-financial-advice disclaimer.

## Notes & failure modes
- First run needs the data deps: `pip install -r .claude/skills/trading-analysis/scripts/requirements.txt` (no keys). If a `ModuleNotFoundError` appears, install and retry.
- Social endpoints can rate-limit (Reddit 403 → auto RSS fallback; StockTwits/news may be sparse). Degrade gracefully and say so — do not invent sentiment.
- The decision log (`ta_memory.py`) **is** persisted and byte-compatible with the framework's `~/.tradingagents/memory/trading_memory.md`. LangGraph checkpoints/resume are **not** reproduced — point the user at the full `tradingagents` CLI if they need crash-resume.
