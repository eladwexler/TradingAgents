---
name: daily
description: The end-of-day operating routine for the TradingAgents project — refresh the cheap, high-value DATA daily (industry news, live prices/mark-to-market, dashboard, drift flags, hard macro indicators), then TRIAGE: print the short "re-run these today" list (drift / big move / checkpoint-due), the matured forecasts to resolve, and the calibration scorecard. It does the daily DATA work and tells you which few names to re-analyze — it does NOT run /trading-analysis on the book itself (mass daily re-forecasting destroys the calibration loop). Use when the user says "/daily", "run the daily", "end of day", "after close routine", or wants the day's refresh + what's-due triage. For the heavier weekly brain-corpus + full macro-cycle refresh use /update-all; for a pure read-only digest use /morning.
---

# Daily — end-of-day refresh + triage

The once-a-day routine. It keeps the **data** current (so the dashboard marks every open
call to today's price and the News/Changes tabs are fresh) and then **triages** — surfacing
the handful of names with a real reason to be re-analyzed, the calls that have matured for
grading, and the standing track record.

> **HARD RULE — does NOT re-forecast the book.** `/daily` must NEVER run `/trading-analysis`
> on all (or many) tickers. Re-running a 12–36mo forecast daily logs thousands of overlapping,
> never-matured calls and **destroys the calibration loop** — the one thing that makes the
> system trustworthy. `/daily` *identifies* the few names that are due; **you** trigger the
> re-run on those, deliberately. It also does NOT do the slow weekly brain-corpus video
> discovery (that's `/update-all`).

## What it does (run in order, from the repo root)

### 1. Industry-news freshness (idempotent, daily)
```
python3 .claude/skills/trading-analysis/scripts/ensure_news.py $(date +%F)
```
Fetches today's primary-source AI/semi news once (SKIP if already fetched). Feeds the
Industry desk + the dashboard News tab.

### 2a. Refresh the X FinTwit/news lane (RSS only — fast, no video discovery)
```
scripts/update_brains.sh x
```
Pulls the curated FinTwit/AI posts (keyless Nitter RSS) + the Google-News stock-chatter lane,
rebuilds the X index, and recomputes `research.json` — so the dashboard's **🗞️ News** (bullish
stock-news) and **🔬 Research** tabs are *daily-fresh*, not just the industry desk. This is the
X Brain **only** (RSS); it does NOT touch the slow yt-dlp video discovery for the personality
brains (Jensen/Leopold/Jordi/Gavin) — that stays weekly in `/update-all`. Degrades gracefully
if Nitter instances are down (keeps the last corpus); say so if it falls back.

### 2b. Data refresh + mark-to-market + drift flags + dashboard
```
scripts/update_all.sh --dash-only
```
This runs `ta_memory.py watch` (writes `under_pressure.json` — open calls drifting against
thesis), refreshes the per-ticker `metrics.json` (live prices), recomputes conviction, then
**rebuilds the 🗞️ News feed (`build_news_feed.py`) from the freshly-refreshed industry desk
(step 1) + X lane (step 2a)** and the **dashboard** (every open call re-marked to today's
price). Cheap, no LLM, no slow brain discovery.

### 3. Hard macro check (decide if the cycle needs a refresh)
```
python3 .claude/skills/trading-analysis/scripts/ta_macro_data.py macro
python3 .claude/skills/trading-analysis/scripts/ta_macro_data.py valuation
```
Read the latest `ai-cycle-reports/*_cycle.md` STANCE. **Run `/ai-cycle-watch` only if** a hard
threshold has newly crossed (10Y ≥ 4.5%, Mag7 avg fwd P/E ≥ 35, HYG −5% MoM) **or** the latest
cycle report is older than ~3 days — otherwise carry the existing stance (the macro phase does
not change day to day). Don't auto-run the full LLM cycle every day.

### 4. What's due — the re-run triage (the actionable output)
```
python3 scripts/reanalysis_triggers.py
```
Prints the prioritized **RE-RUN these** list (🔴 DRIFT vs thesis · 🟠 MOVE ≥20% since entry ·
🟡 CHECKPOINT 3/6/9/12mo elapsed) and the **MATURED — resolve** list (horizon elapsed → grade,
don't re-run). This is the heart of `/daily`: usually a few names or none.

### 5. Calibration
```
python3 .claude/skills/trading-analysis/scripts/ta_memory.py pending
python3 .claude/skills/trading-analysis/scripts/ta_memory.py score
```
List forecasts awaiting an outcome and print the standing hit-rate/alpha/Brier (with its
small-sample caveat). Resolution stays manual (a matured call needs a written reflection).

## After running, report (a short digest + suggested actions)
- **Macro:** the current cycle STANCE + phase + risk score, the two hard indicators, and
  whether a `/ai-cycle-watch` refresh was triggered (and why).
- **Drift:** count + names from `under_pressure.json` (open calls moving against thesis).
- **Re-run today:** the `reanalysis_triggers.py` list — the few names with a real trigger
  (or "nothing to re-forecast ✅"). **List them as suggestions; do not run them.**
- **Resolve:** any matured forecasts to grade.
- **Calibration:** headline hit-rate / Brier with the n caveat.
- **Data freshness:** dashboard rebuilt at <time>; industry news STATUS (SKIP/FETCH).
- End with a 2–4 line **suggested actions** list, e.g. *"Re-run /trading-analysis on NVDA
  (MOVE +22%) and resolve the matured AVGO call; otherwise nothing required."*

## What it deliberately does NOT do
- **No `/trading-analysis`** on the book (it names the few that are due; you trigger them).
- **No slow yt-dlp video discovery** for the personality brains (Jensen/Leopold/Jordi/Gavin) —
  that's the weekly `/update-all`. `/daily` refreshes prices, industry news, the **X FinTwit/news
  lane (RSS, step 2a)**, the dashboard (News + Research tabs), drift, and the hard macro data —
  but not the four personality corpora.
- **No auto-resolve** of forecasts (grading needs a written reflection).

## Cadence
Run once after the close, daily — ideally cron the data steps (1–2) and let the triage (4–5)
+ digest be the part you actually read. The full weekly refresh (brain corpora + a logged
`/ai-cycle-watch`) is `/update-all`; the pure read-only status digest is `/morning`.

## Notes & failure modes
- Network steps (1, the metrics fetch in 2) degrade gracefully offline — they keep the last
  cache and the dashboard still rebuilds; say so if a fetch failed.
- `reanalysis_triggers.py` does NOT detect earnings-since-last-analysis (no earnings feed on
  the free stack) — watch report dates manually and re-run a name after it reports.
- The re-run triggers read only caches step 2 already produced — no extra per-ticker network.
