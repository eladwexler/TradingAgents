---
name: trading-analysis
description: Run a TradingAgents-style multi-agent stock/asset analysis without any LLM API key, producing a calibrated 12–36 month return forecast — Claude plays every agent role (analysts, bull/bear researchers, trader, risk debate, portfolio manager) while reusing the project's own data-fetching scripts. Outputs bear/base/bull total-return scenarios, expected CAGR, and P(beats benchmark), then logs the forecast for later Brier-scoring. Concludes with four qualitative secular lenses — a "Jensen Brain Verdict" (would Jensen Huang / NVIDIA strategically back the company, from an index of 100+ Jensen interviews), a "Leopold Brain Verdict" (does the company fit Leopold Aschenbrenner's Situational Awareness AGI-build-out thesis, from his essay + interviews), a "Jordi Brain Verdict" (does the company sit with or against Jordi Visser's macro / AI-capex / creative-destruction thesis, from his @JordiVisserLabs channel), and a "Gavin Brain Verdict" (would Gavin Baker back it as an AI winner — is AI sustaining or disruptive to its moat — strict, from his long-form guest appearances) — then fuses all four into one strict "Combined Strategic Verdict", and overlays a separate "X Brain Verdict" (what X/Twitter FinTwit is saying — crowd sentiment + AI-trend buzz, keyless; not part of the fusion). Use when the user asks to analyze a ticker, get a BUY/HOLD/SELL view or a multi-year price/return prediction, run "the trading agents", or do multi-agent financial analysis on a symbol and date.
---

# Trading Analysis — 12–36 month prediction tool (key-free, Claude-as-agents)

This skill runs the TradingAgents multi-agent pipeline **inside Claude Code, with no LLM API key**, and orients it toward one job: **a calibrated forecast of multi-year (12–36 month) total return and the probability of beating the benchmark.** The original framework spends one paid LLM call per agent; here **you (Claude) are the LLM** and play every role, while reusing the project's existing data layer via a thin CLI.

**This is a prediction tool, not a day-trading scanner.** The deliverable is an explicit, falsifiable forecast that gets logged with a probability and a horizon, then scored against realised returns once the horizon matures. Short-horizon technicals and retail sentiment are *timing/risk inputs only* — they never drive the multi-year thesis. The drivers that matter over 12–36 months are: **durable earnings/FCF growth, the valuation multiple and how it re-rates, the balance sheet's ability to survive a drawdown, and the secular (AI-cycle) demand curve.**

> Research scaffold only. This is **not** financial/investment/trading advice, and not a byte-for-byte reproduction of the LangGraph pipeline — you role-play the agents sequentially in one context rather than as independent model calls. A multi-year point forecast is inherently uncertain; always carry the disclaimer and the bear/base/bull range into the final output.

## Inputs

Ask the user for (or infer from the request):
- **Ticker** — exchange-suffixed where non-US (`AAPL`, `0700.HK`, `7203.T`, `RELIANCE.NS`, `BTC-USD`).
- **Analysis date** — `YYYY-MM-DD`. Defaults to today if unspecified.
- **Forecast horizon** — 12, 24, or 36 months. **Default 24.** Always report all three where possible (12/24/36) and treat 24mo as the headline.
- Optional: **debate rounds** (default 1 bull/bear round, 1 risk round).

## The data CLI (no API key, no LLM)

All market data comes from `scripts/ta_data.py`, which wraps `tradingagents/dataflows`. Default vendor is yfinance (free); Reddit/StockTwits use public endpoints; Alpha Vantage is only a fallback and is never required. Run it with `python3` (or `python`) from the project root.

```
python3 .claude/skills/trading-analysis/scripts/ta_data.py <command> [args]
```

**Fast path — pull everything once:** `gather TICKER CURR_DATE` runs identity + verified snapshot + price history + 8 indicators + **forward estimates/valuation** + fundamentals/statements + insider + ticker & macro news + StockTwits + Reddit in a single call, with stable `## SECTION` delimiters and per-section error isolation. Prefer this, then play the agent roles over the bundle; fall back to the individual commands below only to dig deeper.

| Command | Args | Purpose |
|---|---|---|
| `gather` | `TICKER CURR_DATE [--price-window N]` | **One-shot full data bundle (recommended first call)** |
| `identity` | `TICKER` | Deterministic company/asset identity — anchor all reports to it |
| `stock_data` | `SYMBOL START END` | OHLCV price history |
| `indicators` | `SYMBOL NAMES CURR_DATE [LOOKBACK]` | Technical indicators; comma-separate names |
| `snapshot` | `SYMBOL CURR_DATE [LOOKBACK]` | **Verified** OHLCV + indicators — source of truth for exact numbers |
| `forward` | `TICKER` | **Analyst targets, forward P/E & PEG, consensus EPS/revenue growth, LTG, yield — the core 12–36mo inputs** |
| `fundamentals` | `TICKER CURR_DATE` | Comprehensive fundamentals |
| `balance_sheet` / `cashflow` / `income_statement` | `TICKER [FREQ] [CURR_DATE]` | Financial statements (`FREQ`=annual\|quarterly) |
| `news` | `TICKER START END` | Ticker-specific news |
| `global_news` | `CURR_DATE [LOOKBACK] [LIMIT]` | Macro/global news |
| `insider` | `TICKER` | Insider transactions |
| `sentiment` | `TICKER CURR_DATE` | News + StockTwits + Reddit bundle (sentiment-analyst inputs) |
| `stocktwits` / `reddit` | `TICKER` | Individual social sources |

Indicator names: `close_9_ema`, `close_21_ema`, `close_50_sma`, `close_200_sma`, `close_10_ema`, `macd`, `macds`, `macdh`, `rsi`, `boll`, `boll_ub`, `boll_lb`, `atr`, `vwma`, `mfi`.

## The memory CLI (persistent decision log, no key)

`scripts/ta_memory.py` writes a markdown decision log **byte-compatible** with the real framework's `~/.tradingagents/memory/trading_memory.md`, so runs accumulate lessons and feed them back into later analyses — exactly like the original's reflection layer, but driven by you instead of a paid LLM.

```
python3 .claude/skills/trading-analysis/scripts/ta_memory.py <command> [args]
```

| Command | Args | Purpose |
|---|---|---|
| `recall` | `TICKER` | Past same-ticker + cross-ticker lessons — **inject at the start** |
| `log` | `TICKER DATE [--file f \| --text … \| stdin] --prob P --horizon-months M` | Append the final decision + **forecast probability + horizon** as a pending entry — **run at the end** |
| `pending` | `[TICKER]` | List decisions still awaiting an outcome |
| `returns` | `TICKER DATE [--horizon-months M \| --holding-days N]` | Realised raw + alpha + **CAGR** from prices (use for interim mark-to-market) |
| `resolve` | `TICKER DATE --reflection-file f [--horizon-months M] [--force]` | Attach realised return + your reflection once the **horizon has matured** (blocks early unless `--force`) |
| `score` | `[TICKER]` | **Calibration scorecard**: hit-rate, mean alpha/CAGR, Brier score + skill vs base rate, alpha-by-rating-tier |

Path: `$TRADINGAGENTS_MEMORY_LOG_PATH`, else `~/.tradingagents/memory/trading_memory.md` (override per-call with `--path`). Benchmark for alpha is auto-resolved from the ticker suffix (SPY for US, `^N225` for `.T`, etc.).

**The forecast is the product.** Every `log` must carry `--prob` (your probability the stock beats its benchmark over the horizon, 0–1) and `--horizon-months`. Those let `score` compute a **Brier score** later — the only honest measure of whether the framework predicts or just narrates. Resolution is horizon-aware: `resolve` refuses to close an entry before ~95% of the horizon has elapsed (override with `--force`), so a 24-month call is graded at 24 months, not on noise.

**Data integrity rule (non-negotiable):** Only state prices, levels, RSI/MACD/MA values, % moves, or support/resistance that appear in tool output. If a command prints `NO_DATA` / `NO_DATA_AVAILABLE` / `ERROR`, report the data as unavailable — **never estimate or fabricate a number.** When a tool output conflicts with the verified `snapshot`, treat the snapshot as truth and flag the discrepancy.

## Pipeline

Run the stages in order. Write each report to a section as you go; later stages consume earlier ones. Keep the internal debate in English for reasoning quality even if the final summary is requested in another language.

### Stage 0 — Recall, score, macro context, + resolve identity
First run `ta_memory.py recall TICKER` and, if it returns prior lessons, weave them into your reasoning (they feed the Portfolio Manager just as in the original). Then run `ta_memory.py score` to see the framework's standing track record (hit-rate, mean alpha, Brier) — if it shows a systematic bias (e.g. bullish ratings underperforming, or fading momentum), correct for it this run.

Also resolve any **matured** pending entries while you're here: `ta_memory.py pending`, then for each whose horizon has elapsed, write a one-paragraph reflection and `ta_memory.py resolve TICKER DATE --horizon-months M --reflection-file …` it. Entries whose horizon has **not** elapsed should be left pending — do an interim `returns … --horizon-months M` mark-to-market for context only, don't resolve early.

Next, check the `ai-cycle-reports/` directory for the latest `*_cycle.md` report. If one exists, read it to grasp the current **Macro AI Phase** and **STANCE**. This macro context will be used to upgrade the final decision later.

Then run `ta_data.py identity TICKER` (or take it from the `gather` bundle). Use the resolved company/sector in every downstream section. Do not substitute a different company unless a later tool result explicitly disproves it. (For crypto `-USD` tickers, treat as an asset; fundamentals may be unavailable.)

### Stage 1 — Analyst team (gather + report)
Produce four standalone reports. Each ends with a Markdown summary table. **Weighting for the multi-year forecast: Fundamentals/valuation dominate (~50%), News/secular-drivers ~25%, Technicals ~15% (regime + entry timing only), Sentiment ~10% (contrarian check only).** Do not let a stretched RSI or euphoric StockTwits feed override a durable-growth, reasonable-valuation thesis — that is the classic short-horizon error this tool exists to avoid.

1. **Market / Technical Analyst.** Run `snapshot` (treat as source of truth), `stock_data`, then `indicators` for **up to 8 complementary** indicators (no redundant pairs, e.g. not both rsi and stochrsi). Briefly justify each for the current regime. **Frame this as regime + entry-timing context for a multi-year position — not the thesis.** Distinguish "the trend is broken" (thesis-relevant) from "short-term overbought" (timing-only; a reason to scale in, never to forecast lower 2-year returns). Note the 200-day trend, drawdown depth from highs, and realised volatility (ATR) for position sizing.
   **The snapshot includes an automatic Shay Boloor Verdict classification on the Daily Timeframe** (9 EMA / 21 EMA / 50 SMA / 200 SMA), with SMA slope quality, volume confirmation, and a 21-EMA extension warning. **Treat this as entry-timing context only — it does NOT change the multi-year forecast or the BASE/MACRO decision.** It answers one narrow question: *if you were opening a new position today, is this a good moment to do so?* A 🔴 BEARISH reading (price below the 200 SMA) is a timing signal, not a sell — for a durable-growth thesis a sub-200-SMA price is often a better accumulation zone, so never let the verdict override a fundamentals-driven BUY. The three qualifiers matter for *timing and sizing a new entry*: (a) *SMA slope* — price above a flat/declining 200 SMA is weaker than above a rising one; (b) *volume* — breakouts on thin volume lack conviction; (c) *extension* — even in a bullish structure, price stretched ≥15–25% above the 21 EMA means risk/reward for *new* entries is poor (the classic AI-infra momentum trap — buying MRVL/CRDO/NBIS after the explosive move when the 9/21 gap is already blown out). When the extension warning fires, the thesis is unchanged but new-money sizing should be smaller and the VERDICT FOR NEW INVESTORS must note the stretched entry. For someone who **already holds** the name, the verdict is informational only — surface it in the appendix, not as a reason to trim a multi-year position.
2. **Sentiment Analyst.** Run `sentiment TICKER CURR_DATE`. Read the StockTwits Bullish/Bearish ratio (≈70/30 mildly bullish; ≥90/10 possible over-extension/contrarian risk; 50/50 uncertain — weight by message count). Weight Reddit by engagement; flag cross-source divergences and data limits. **Over a 12–36mo horizon, retail sentiment is a weak, mostly contrarian signal** — euphoria is a mild caution, capitulation a mild positive; neither sets the forecast. Emit: **overall_band**, **overall_score** 0–10, **confidence**, and a short signal table.
3. **News & Secular-Driver Analyst.** Run `news TICKER START END` (≈7-day window) and `global_news CURR_DATE`. Summarize company-specific and macro developments, but emphasize the **durable, multi-year drivers**: AI-capex demand curve, design wins / backlog / contracted revenue, competitive moat shifts, regulatory/structural changes. Cross-reference the `ai-cycle-reports` macro phase. One-off headlines matter only insofar as they change the multi-year trajectory.
4. **Fundamentals & Valuation Analyst (most important for this tool).** Run `forward TICKER` **and** `fundamentals`, plus `balance_sheet`/`cashflow`/`income_statement` and `insider` as useful. Cover: growth durability (revenue/EPS/FCF trajectory and consensus LTG), margins and returns on capital, **valuation** (trailing & forward P/E, PEG, where the multiple sits vs history), balance-sheet survivability through a drawdown (debt, interest cover, cash runway — critical for pre-profit AI-infra names), and red flags (insider selling, dilution). Then build the **Expected-Return Model** below. (Skip/curtail for crypto — use demand/flow/scarcity instead.)

#### The Expected-Return Model (required — this produces the forecast)
Decompose expected annualized return over the horizon into the **three sources of long-run equity return**, for three scenarios (bear / base / bull):

> **Total return ≈ (earnings or FCF growth) + (multiple re-rating) + (shareholder yield)**

- **Growth**: annualized revenue/EPS/FCF growth you actually believe — anchor on consensus from `forward`, then *haircut for optimism bias* and the AI-cycle phase. State your number and why it differs from consensus.
- **Multiple re-rating**: where the P/E (or EV/S for pre-profit) is today vs. a defensible terminal multiple at the horizon. High-multiple names should usually carry **multiple compression** in the base case even with strong growth — make this explicit; it's the #1 thing valuation-blind momentum theses miss.
- **Yield**: dividend + net buyback.

Combine into **bear / base / bull total-return paths to the horizon**, assign rough probabilities, and from those derive: the **expected total return**, the **P(beats benchmark)**, and the implied **5-tier rating**. The benchmark's own expected return over the horizon (~6–8%/yr for SPY as a default anchor, state your assumption) is the hurdle for alpha.

### Stage 2 — Research debate (bull vs bear)
Using all four analyst reports, run `max_debate_rounds` rounds (default 1). Each round:
- **Bull Researcher** — evidence-based case for the position: growth potential, competitive advantages, positive indicators; directly rebut the latest bear points. Conversational, engaging — argue, don't just list.
- **Bear Researcher** — case against: risks/challenges, competitive weaknesses, negative indicators; expose over-optimistic bull assumptions and rebut directly.

### Stage 3 — Research Manager → investment plan
Critically judge the debate and commit to a clear stance using exactly one rating: **Buy / Overweight / Hold / Underweight / Sell** (reserve Hold for genuinely balanced evidence). Produce an actionable investment plan for the trader.

**Rating scale in plain words** ("weight" = how big a slice of the portfolio the stock gets vs. a neutral benchmark weight). Always gloss the chosen rating in plain language in the final output so a non-expert understands it:
- **Buy** — "Own a lot of this." Strong conviction; full or larger-than-normal position.
- **Overweight** — "Own more than average, but not a hero bet." Positive with caveats (e.g. high risk); take a position **smaller than a Buy**, sized for the risk.
- **Hold** — "Neither add nor sell." Evidence is genuinely two-sided; keep existing holdings, no new money.
- **Underweight** — "Own less than average." Lean negative but not a hard exit; trim or hold only a token amount.
- **Sell** — "Don't own it." Exit or avoid.

### Stage 4 — Trader → transaction proposal
Turn the investment plan into a concrete proposal anchored in the analyst reports and plan: direction, conviction, rough sizing/entry logic, and key risks to monitor.

### Stage 5 — Risk debate (3-way)
Run `max_risk_discuss_rounds` rounds (default 1) over the trader's proposal:
- **Aggressive** analyst — champion high-reward/high-risk upside.
- **Conservative** analyst — protect capital, minimize volatility, flag downside.
- **Neutral** analyst — balanced, sustainable middle path; critique both extremes.

### Stage 6 — Portfolio Manager → final decision + calibrated forecast
Synthesize the risk debate, the Expected-Return Model, **and any recalled past lessons** into a **Base Decision** (bottom-up). Then factor in the **Macro Phase / Stance** from the latest `ai-cycle-reports` (Stage 0) for a **Macro-Adjusted Decision**: if the cycle is in Late Phase 2 or Phase 3, haircut growth and apply more multiple compression — heavily penalize high-leverage infrastructure or AI wrappers to enforce top-down risk management on the bottom-up pick.

**CRITICAL HEDGE CHECK:** Check if the ticker being analyzed appears in the `[HEDGE_CANDIDATES]` JSON block of the latest cycle report. If it does, automatically flag it as a HIGH-VULNERABILITY SHORT TARGET, forbid a "Buy" rating, and explicitly state that it was flagged by the macro cycle as a casualty.

**Emit the forecast — this is the deliverable.** Produce a forecast block with, for the headline 24mo horizon (and 12/36 where you can):

- **Expected total return** at the horizon (the probability-weighted blend of your bear/base/bull paths), with the three scenario paths and their probabilities shown.
- **Expected CAGR** (annualized).
- **P(beats benchmark)** over the horizon — a single number in 0–1. Be honest and avoid false precision: most real forecasts land in 0.35–0.75; reserve >0.80 for genuinely lopsided setups. This is what gets Brier-scored.
- **Confidence** (low/med/high) and the dominant swing factor (what would most change the call).

Then map to the decision lines (the 5-tier rating must be *consistent* with the expected return vs. the benchmark hurdle — don't rate Buy with a below-benchmark base case):
- **FINAL TRANSACTION PROPOSAL (BASE): BUY/HOLD/SELL** (with the 5-tier rating)
- **FINAL TRANSACTION PROPOSAL (MACRO-ADJUSTED): BUY/HOLD/SELL** (with the 5-tier rating)

Include a specific **VERDICT FOR NEW INVESTORS** stating whether it's a suitable entry over the 12–36mo horizon, explicitly stating the projected target prices in dollars, given both views and the bear-case drawdown they must be able to survive.

### Stage 6.5 — Jensen Brain Verdict (NVIDIA strategic-fit lens)
After the PM decision, add a **Jensen Brain Verdict**: would **Jensen Huang / NVIDIA
strategically back this company** (invest, partner, acquire, or champion it), judged
only from what Jensen has actually said? This is a separate **qualitative** lens — a
secular sanity-check on whether the name sits with or against NVIDIA's platform — and
it appears **at the end of the verdict**. It does **not** alter the Brier-scored
forecast, the Expected-Return Model, or the BASE/MACRO ratings (keep those clean);
treat it like the Shay Boloor verdict — surfaced, not score-moving.

Run the bridge to the Jensen brain (a BM25 index over 100+ Jensen interview/keynote
transcripts in the companion `jensen` project). From the repo root, pass good alias
terms — company, CEO, flagship products/tickers — plus the NVIDIA theses it touches:

```
python3 .claude/skills/trading-analysis/scripts/jensen_brain.py \
    "<company> <CEO> <products/aliases>" \
    --sector "<the NVIDIA theses it touches: accelerated computing / AI factories / physical AI / robotics / autonomous vehicles / sovereign AI / digital biology / CUDA ecosystem>" \
    --k 5
```
(Set `JENSEN_HOME` if the jensen project lives elsewhere; default `/home/ewexler/projects/jensen-brain`.
 If the bridge reports the index is missing, note Jensen Brain as unavailable and skip — do not fabricate.)

The bridge returns four passage groups (direct mentions, sector/thesis fit,
competition/substitution risk, partnership philosophy) and a **coverage signal**.
From them, decide one verdict, grounded in Jensen's recurring theses — companies that
**consume/extend** the NVIDIA platform lean *Likely*; those building **substitutes**
(rival GPUs/ASICs/TPUs, competing stacks) lean *Unlikely*; distinguish *Jensen
praising/using* a company from *NVIDIA backing* it. Map to:

- **Jensen Brain Verdict:** Likely back / Possible / Unlikely back / Insufficient evidence — with confidence (low/med/high).
- **Why:** 2–4 bullets tying the company to specific Jensen theses + its NVIDIA relationship (customer / partner / supplier / competitor).
- **In his words:** 1–3 short quoted snippets, each cited `(<date> — <video title>, <url>)`. Quote only retrieved text; never invent quotes. If `top_direct_score` is low, say the corpus is thin and lean on sector fit.

### Stage 6.6 — Leopold Brain Verdict (Situational Awareness thesis-fit lens)
After the Jensen verdict, add a **Leopold Brain Verdict**: does the company sit **with or
against Leopold Aschenbrenner's *Situational Awareness* thesis** — a beneficiary/enabler
of the AGI build-out (a thesis *tailwind*) or orthogonal / likely disrupted (a *headwind*),
judged only from what Leopold has actually written or said? This is the second
**qualitative** secular lens — where Jensen reads NVIDIA-platform fit, Leopold reads
fit with the compute-scaling / trillion-dollar-cluster / **power-as-binding-constraint** /
chips-&-fabs / lock-down-the-labs / US-China-race build-out. Like Jensen's, it is
**surfaced, not score-moving**: it does **not** alter the Brier-scored forecast, the
Expected-Return Model, or the BASE/MACRO ratings.

Run the bridge to the Leopold brain (a BM25 index over his *Situational Awareness* essay
+ long-form interviews in the companion `leopold-brain` project). From the repo root, pass
good alias terms — company, CEO, flagship products/tickers — plus the theses it touches:

```
python3 .claude/skills/trading-analysis/scripts/leopold_brain.py \
    "<company> <CEO> <products/aliases>" \
    --thesis "<the Situational Awareness theses it touches: compute scaling / trillion-dollar cluster / power & electricity / chips & fabs & HBM / AGI labs / security / US-China race>" \
    --k 5
```
(Set `LEOPOLD_HOME` if the leopold-brain project lives elsewhere; default `/home/ewexler/projects/leopold-brain`.
 If the bridge reports the index is missing, note Leopold Brain as unavailable and skip — do not fabricate.)

The bridge returns four passage groups (direct mentions, thesis fit, beneficiary/bottleneck
lens, skepticism/what-breaks-the-trade lens) and a **coverage signal**. Leopold is an
essayist/investor, not a company — there is **no announcements lane**, and a name he never
mentions is normal; judge by how squarely it sits in the build-out, not by whether he named
it. From them, decide one verdict — names squarely in **compute / power / grid / chips /
fabs / leading labs** lean *Thesis tailwind*; names the build-out **commoditizes or AGI
disrupts** (labor-arbitrage services, moats AGI erodes) or that are simply orthogonal lean
*Thesis headwind*. Map to:

- **Leopold Brain Verdict:** Thesis tailwind / Possible / Thesis headwind / Insufficient evidence — with confidence (low/med/high).
- **Why:** 2–4 bullets tying the company to specific Situational Awareness theses + where it sits in the build-out (enabler / beneficiary / commoditized / disrupted / orthogonal).
- **In his words:** 1–3 short quoted snippets, each cited `(<date> — <title>, <url>)`. Quote only retrieved text; never invent quotes. If `leopold_direct_score` is low, say the corpus does not name it and lean on thesis fit.

### Stage 6.65 — Jordi Brain Verdict (macro / AI thesis-fit lens)
After the Leopold verdict, add a **Jordi Brain Verdict**: does the company sit **with or
against Jordi Visser's macro / AI thesis** — a *beneficiary* of the AI capex super-cycle,
compute scarcity, the deflationary AI productivity boom ("the new QE is AI and crypto"),
bitcoin-as-macro-trade and physical-AI / robotics build-out (a thesis *tailwind*), or on
the wrong side of the **creative destruction** he warns about — the "SaaS-pocalypse",
widening **ROIC gaps**, over-levered hyperscalers, labor disruption (a thesis *headwind*)?
Judged only from what Jordi has actually said. This is the third **qualitative** secular
lens — where Jensen reads NVIDIA-platform fit and Leopold reads the AGI-build-out thesis,
Jordi reads the **markets / macro-cycle** fit. Like the others it is **surfaced, not
score-moving**: it does **not** alter the Brier-scored forecast, the Expected-Return Model,
or the BASE/MACRO ratings.

Run the bridge to the Jordi brain (a BM25 index over every @JordiVisserLabs video + a news
lane). From the repo root, pass good alias terms — company, CEO, ticker — plus the Jordi
theses it touches:

```
python3 .claude/skills/trading-analysis/scripts/jordi_brain.py \
    "<company> <CEO> <ticker/aliases>" \
    --thesis "<the Jordi theses it touches: AI capex cycle / compute scarcity / deflation & productivity / bitcoin / physical AI / robotics / SaaS disruption / ROIC gap / agents>" \
    --k 5
```
(Set `JORDI_HOME` if the jordi-brain project lives elsewhere; default `/home/ewexler/projects/jordi-brain`.
 If the bridge reports the index is missing, note Jordi Brain as unavailable and skip — do not fabricate.)

The bridge returns five passage groups (direct mentions split JORDI-SAID vs NEWS, thesis
fit, a tailwind lens, a skepticism/creative-destruction lens) and a **coverage signal**.
Jordi is a macro investor/commentator, not a company — a name he never names is normal;
judge by how the company sits in his framework. From them, decide one verdict — names
squarely in **AI-capex beneficiaries / compute & power scarcity / physical-AI / bitcoin-macro**
or genuine **productivity / disruption winners** lean *Constructive*; names his thesis says
get **commoditized or disrupted** (legacy seat-priced SaaS, widening-ROIC-gap businesses,
over-levered hyperscalers, labor-arbitrage services) lean *Cautious*. Map to:

- **Jordi Brain Verdict:** Constructive / Possible / Cautious / Insufficient evidence — with confidence (low/med/high).
- **Why:** 2–4 bullets tying the company to specific Jordi theses + where it sits in his framework (capex beneficiary / scarcity winner / productivity winner / commoditized / disrupted / orthogonal).
- **In his words:** 1–3 short quoted snippets, each cited `(<date> — <video title>, <url>)`. Quote only retrieved text; never invent quotes. If `jordi_direct_score` is low, say the corpus does not name it and lean on thesis fit.

### Stage 6.66 — Gavin Brain Verdict (AI-winner conviction lens — STRICT)
After the Jordi verdict, add a **Gavin Brain Verdict**: would **Gavin Baker (Atreides
Management) back this company as an AI winner**, judged through his central question —
*"is AI **sustaining** (strengthens the incumbent's moat: proprietary data, distribution,
scale, compute access) or **disruptive** (erodes it)?"* This is the fourth **qualitative**
secular lens — where Jensen reads NVIDIA-platform fit, Leopold the AGI-build-out thesis,
and Jordi the macro/markets cycle, Gavin reads it as a **concentrated AI stock-picker**.
Like the others it is **surfaced, not score-moving**: it does **not** alter the Brier-scored
forecast, the Expected-Return Model, or the BASE/MACRO ratings.

**Be STRICT.** Gavin is opinionated and concentrated — reserve the positive verdict for
**strong, direct, repeated** evidence (a known holding / emphatic endorsement of the
*specific* name). Praise of a *theme* is **not** backing a *stock*. Default to Possible or
Insufficient when the corpus is thin; never inflate a tangential mention into a pick.

Run the bridge to the Gavin brain (a BM25 index over his long-form guest appearances —
BG2, Invest Like the Best, Aleph, a16z, Sohn, TBPN… — plus a news lane). From the repo
root, pass alias terms — company, CEO, ticker — plus the Gavin theses it touches:

```
python3 .claude/skills/trading-analysis/scripts/gavin_brain.py \
    "<company> <CEO> <ticker/aliases>" \
    --thesis "<the Gavin theses it touches: compute / accelerators / inference vs training / custom silicon / proprietary data / distribution / power / sustaining-vs-disruptive>" \
    --k 5
```
(Set `GAVIN_HOME` if the gavin-brain project lives elsewhere; default `/home/ewexler/projects/gavin-brain`.
 If the bridge reports the index is missing, note Gavin Brain as unavailable and skip — do not fabricate.)

The bridge returns five passage groups (direct mentions split GAVIN-SAID vs NEWS, thesis
fit, a sustaining-vs-disruptive lens, a skepticism lens) and a **coverage signal**. Decide
one verdict under the strict bar — a clear compute/data/distribution **moat winner** Gavin
directly and repeatedly backs leans *Conviction pick*; a business he frames as **disrupted
or commoditized** by AI leans *Cautious*; a framework-fit-but-no-direct-call leans
*Possible*; absent/thin leans *Insufficient*. Map to:

- **Gavin Brain Verdict:** Conviction pick / Possible / Cautious / Insufficient evidence — with confidence (low/med/high).
- **Why:** 2–4 bullets on the sustaining-vs-disruptive read + whether it's a compute/data/distribution moat winner or a disruption casualty, and whether he backs the *specific name* vs the theme.
- **In his words:** 1–3 short quoted snippets, each cited `(<date> — <venue/title>, <url>)`. Quote only retrieved text; never invent quotes. **If `gavin_direct_score` is low, do NOT issue a Conviction pick** — lean Possible/Insufficient and say the corpus is thin.

### Stage 6.67 — X Brain Verdict (FinTwit crowd-sentiment + trend overlay)
After the Gavin verdict, add an **X Brain Verdict**: what does **X (Twitter) FinTwit**
think — is the crowd *net bullish or bearish* on the name, and does it ride a *currently-hot
AI trend*? Judged only from what was actually posted (a keyless BM25 index over curated
FinTwit/AI accounts via Nitter RSS + a Google-News proxy lane). This is a **crowd-sentiment
overlay**, distinct from the four secular brains: it is **not a thesis**, it is the *latest,
noisiest* signal, and it is **explicitly NOT part of the Combined Strategic Verdict** (Stage
6.7 still fuses only Jensen/Leopold/Jordi/Gavin). Like the others it is **surfaced, not
score-moving**: it does **not** alter the forecast or the BASE/MACRO ratings. Treat crowd
sentiment with care — it is frequently a late or contrarian signal.

Run the bridge to the X brain. From the repo root, pass alias terms — company, CEO, ticker,
`$cashtag` — plus the hot AI trends the name touches:

```
python3 .claude/skills/trading-analysis/scripts/x_brain.py \
    "<company> <CEO> <$cashtag/aliases>" \
    --trend "<hot AI trends it touches: AI capex / inference / custom silicon / HBM / networking-optics / power / nuclear / robotics / agents / neocloud>" \
    --k 5
```
(Set `X_HOME` if the x-brain project lives elsewhere; default `/home/ewexler/projects/x-brain`.
 If the bridge reports the index is missing, note X Brain as unavailable and skip — do not fabricate.)

The bridge returns five passage groups (direct mentions split X-POST vs X-NEWS, a bullish
lens, a bearish lens, a trend lens) and a two-part **coverage signal** (`x_post_score`,
`x_news_score`). Decide one verdict by weighing the **bull-vs-bear balance** and **trend
alignment** — heavier convincing bullish chatter on a hot trend leans *Bullish buzz*; a
dominant crash/bubble/downgrade tone leans *Bearish*; two-sided or off-trend leans *Mixed*;
both scores thin leans *Insufficient chatter*. Map to:

- **X Brain Verdict:** Bullish buzz / Mixed / Bearish / Insufficient chatter — with confidence (low/med/high).
- **Why:** 2–4 bullets on the bull-vs-bear balance, the trend it rides (or not), and whether the signal is account-driven or news-lane-only (note if Nitter was down).
- **In their words:** 1–3 short quoted snippets, each cited `(<date> — @account or source, <url>)`. Quote only retrieved text; never invent posts. If both coverage scores are ~0, say the crowd isn't discussing it.

### Stage 6.7 — Combined Strategic Verdict (strict)
Finally, fuse the four secular lenses into **one strict Combined Strategic Verdict** — the
single answer to *"is this name on the right side of the AI build-out?"* All four brains
already answer that (Jensen from NVIDIA's platform, Leopold from the Situational Awareness
thesis, Jordi from the macro / AI-capex / creative-destruction cycle, Gavin from the
AI-stock-picker sustaining-vs-disruptive lens); this collapses them deterministically so
the call is reproducible, not vibes.

Score each brain **+1 / 0 / −1**:
- **Jensen:** *Likely back* = +1, *Possible* = 0, *Unlikely back* = −1.
- **Leopold:** *Thesis tailwind* = +1, *Possible* = 0, *Thesis headwind* = −1.
- **Jordi:** *Constructive* = +1, *Possible* = 0, *Cautious* = −1.
- **Gavin:** *Conviction pick* = +1, *Possible* = 0, *Cautious* = −1.

Treat any *Insufficient evidence* as **0 but flagged thin**. Then map strictly — a genuine
**sign split** (at least one +1 *and* at least one −1) is always **CONTESTED**, regardless
of the sum; otherwise go by the sum of the four (range −4..+4):

| Condition | Combined Strategic Verdict |
|---|---|
| any +1 **and** any −1 present (lenses disagree) | **CONTESTED** — name the split |
| no negatives, sum **+3 or +4** | **CONVICTION ALIGNED** — squarely on the right side of all lenses |
| no negatives, sum **+1 or +2** | **ALIGNED** |
| sum **0**, no disagreement (all neutral/thin) | **NEUTRAL** (or **INSUFFICIENT** if all four were thin) |
| no positives, sum **−1 or −2** | **EXPOSED** |
| no positives, sum **−3 or −4** | **OFFSIDE** — on the wrong side of all lenses |

Then **reconcile with the financial call** (the MACRO-ADJUSTED proposal from Stage 6) in
one or two strict sentences. The Combined Strategic Verdict is still **non-score-moving**
— it does not change the forecast or the BASE/MACRO ratings — but it is the master secular
overlay, so divergence must be stated plainly: e.g. a financial **BUY** under a
**CONTESTED/EXPOSED/OFFSIDE** strategic verdict means *the secular tailwind is not assured —
size smaller and treat it as a trade, not a franchise hold*; a financial **HOLD/SELL** under
**CONVICTION ALIGNED** means *the franchise is on-side but the entry/price/cycle isn't —
revisit on a pullback*. When they agree, say so and let conviction compound. Always carry
the **thin-evidence flag** if either brain was Insufficient.

### Stage 7 — Persist the decision
Save the final decision to a per-ticker file **and** append it to the memory log so the next run can learn from it.

1. Write the decision to `analyzed-stocks/<TICKER>/<DATE>_decision.md` (repo-relative; create the dir if missing). Start the file with the base proposal, macro-adjusted proposal, the `VERDICT FOR NEW INVESTORS:` line, the ratings, **and the forecast block (expected total return + scenarios + P(beats benchmark) + horizon)** so they parse cleanly, followed by the decision summary, key evidence, the plan, and at the end the **`Jensen Brain Verdict:` line**, the **`Leopold Brain Verdict:` line**, the **`Jordi Brain Verdict:` line**, the **`Gavin Brain Verdict:` line**, the **`X Brain Verdict:` line** (the FinTwit sentiment overlay — separate from the four brains), and the **`Combined Strategic Verdict:` line** (with its reconciliation sentence).
2. Log it **with the forecast probability and horizon** (so it can be Brier-scored at maturity):
```
mkdir -p analyzed-stocks/TICKER
# (write the decision file to analyzed-stocks/TICKER/DATE_decision.md)
python3 .claude/skills/trading-analysis/scripts/ta_memory.py log TICKER DATE \
    --file analyzed-stocks/TICKER/DATE_decision.md \
    --prob 0.66 --horizon-months 24
```
3. Refresh the HTML dashboard so the new verdict is viewable and the best-call
   leaderboards update: `python3 scripts/build_dashboard.py` (regenerates
   `dashboard/index.html` + a per-decision page from `scripts/templates/`; pure stdlib,
   reads the memory log + `analyzed-stocks/`). See `scripts/DASHBOARD.md`.

The entry is stored `pending` with its `P=` and `H=` tokens; a later run resolves it (`resolve … --horizon-months 24`) with the realised raw/alpha/CAGR **once the horizon matures**, and `score` then folds it into the calibration stats. The `analyzed-stocks/` tree is the human-readable archive; the memory log is the machine-readable feedback loop that tells you whether the predictions are any good — keep both.

## Output format

Present, in this order:
1. **Forecast** up top, as a compact table — the headline product:

   | Horizon | Bear Price | Base Price | Bull Price | Expected Return | Target Price | CAGR | P(beat benchmark) |
   |---|---|---|---|---|---|---|---|
   | 12mo | $... | $... | $... | ...% | $... | ...% | 0.xx |
   | 24mo | $... | $... | $... | ...% | $... | ...% | 0.xx |
   | 36mo | $... | $... | $... | ...% | $... | ...% | 0.xx |

   …with the scenario probabilities and the one dominant swing factor noted beneath.
2. **Decision**: both `FINAL TRANSACTION PROPOSAL (BASE): **BUY/HOLD/SELL**` and `FINAL TRANSACTION PROPOSAL (MACRO-ADJUSTED): **BUY/HOLD/SELL**` + their five-tier ratings (with a short plain-words gloss, e.g. *Overweight — "own more than average, but sized small for the risk"*) + **VERDICT FOR NEW INVESTORS** combining both views into a 2–3 sentence rationale anchored on the horizon and the survivable bear-case drawdown. **For a new buyer, fold the Shay Boloor Verdict in here as entry-timing only** — i.e. whether to start the position now or wait for a better entry — without letting it move the BASE/MACRO call. If the extension warning fired, explicitly note that the entry is stretched and that new-money sizing should be smaller.
   Then, **at the very end of the verdict**, append the three secular lenses and their fusion, in this order, none of which move the BASE/MACRO call or the forecast numbers:
   - **Jensen Brain Verdict** (Stage 6.5): `Jensen Brain Verdict: **Likely back / Possible / Unlikely back / Insufficient evidence**` + confidence, 2–4 why-bullets, and 1–3 cited quotes. A qualitative NVIDIA-strategic-fit lens.
   - **Leopold Brain Verdict** (Stage 6.6): `Leopold Brain Verdict: **Thesis tailwind / Possible / Thesis headwind / Insufficient evidence**` + confidence, 2–4 why-bullets, and 1–3 cited quotes. A qualitative Situational-Awareness-thesis-fit lens.
   - **Jordi Brain Verdict** (Stage 6.65): `Jordi Brain Verdict: **Constructive / Possible / Cautious / Insufficient evidence**` + confidence, 2–4 why-bullets, and 1–3 cited quotes. A qualitative macro / AI-capex / creative-destruction thesis-fit lens.
   - **Gavin Brain Verdict** (Stage 6.66): `Gavin Brain Verdict: **Conviction pick / Possible / Cautious / Insufficient evidence**` + confidence, 2–4 why-bullets, and 1–3 cited quotes. A strict AI-stock-picker (sustaining-vs-disruptive) lens.
   - **X Brain Verdict** (Stage 6.67): `X Brain Verdict: **Bullish buzz / Mixed / Bearish / Insufficient chatter**` + confidence, 2–4 why-bullets, and 1–3 cited posts. A FinTwit crowd-sentiment + AI-trend overlay — **separate from the four secular brains and NOT part of the Combined Strategic Verdict**; place it after Gavin and before Combined.
   - **Combined Strategic Verdict** (Stage 6.7): `Combined Strategic Verdict: **CONVICTION ALIGNED / ALIGNED / NEUTRAL / CONTESTED / EXPOSED / OFFSIDE / INSUFFICIENT**` derived strictly from the four brains' scores (sign-split ⇒ CONTESTED), followed by the one-to-two-sentence reconciliation with the MACRO-ADJUSTED financial call (and the thin-evidence flag if any brain was Insufficient).
3. Collapsible/clearly-headed sections for each stage (4 analyst reports incl. the Expected-Return Model → research debate + plan → trader proposal → risk debate → PM decision).
4. A one-line **data caveat** noting any source that returned no data / fell back, plus the reminder that a multi-year point forecast is uncertain, and the standard not-financial-advice disclaimer.
5. **Appendix — Shay Boloor Verdict (timing reference).** Reproduce the snapshot's verdict (🟢 BULLISH / 🟡 HOLD / 🔴 BEARISH), the levels table, and any qualifier warnings (slope, volume, extension). This is the at-a-glance momentum/structure read for **timing a new entry** and an informational check for **someone already holding** — it does not feed the multi-year forecast or justify trimming an existing position.

## Notes & failure modes
- First run needs the data deps: `pip install -r .claude/skills/trading-analysis/scripts/requirements.txt` (no keys). If a `ModuleNotFoundError` appears, install and retry.
- Social endpoints can rate-limit (Reddit 403 → auto RSS fallback; StockTwits/news may be sparse). Degrade gracefully and say so — do not invent sentiment.
- The decision log (`ta_memory.py`) **is** persisted and byte-compatible with the framework's `~/.tradingagents/memory/trading_memory.md`. LangGraph checkpoints/resume are **not** reproduced — point the user at the full `tradingagents` CLI if they need crash-resume.
