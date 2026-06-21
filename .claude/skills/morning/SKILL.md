---
name: morning
description: Print a STRICTLY READ-ONLY daily briefing for the TradingAgents project — the macro AI-cycle phase/stance + hedge candidates, open calls drifting against thesis (watch cache), open/matured forecasts, the calibration scorecard, stale tickers (no decision today), and data freshness — then a short suggested-actions list. It analyzes NOTHING: no /trading-analysis, no /run-news, no /ai-cycle-watch, no /update-all, no network, no LLM — it only reads artifacts that already exist and prints. Use when the user says "/morning", "morning report", "daily briefing", "what's on my plate", or wants a read-only status digest without refreshing or analyzing anything.
---

# Morning — read-only daily briefing

A one-glance digest of where things stand, assembled **only from artifacts that already
exist**. This skill is a **report**, not a refresh and not an analysis.

> **HARD RULE — analyzes nothing.** `/morning` must NEVER run `/trading-analysis`,
> `/run-news`, `/ai-cycle-watch`, `/update-all`, `ta_memory.py watch/resolve/log`, or any
> command that fetches, writes, or generates. It only *reads* (the latest cycle report, the
> decision log, the `under_pressure.json` watch cache, the filesystem) and prints. If the
> user wants fresh data, they run `/update-all` first; `/morning` reports on whatever is
> already current. It ends with a **suggested-actions list the user runs themselves** — it
> does not execute them.

## Run

From the repo root, run the read-only reporter and relay its output:

```bash
python3 scripts/morning_report.py
```

That single command prints all six sections (it shells out only to **read-only** commands —
`ta_memory.py pending`, `ta_memory.py score`, `update_all.sh --analysis-plan` — none of which
write or hit the network). Set `AINEWS_HOME` / `TRADINGAGENTS_MEMORY_LOG_PATH` if those live
off-default.

## What it prints
1. **Macro phase** — the latest `ai-cycle-reports/*_cycle.md` `STANCE:` line + `[HEDGE_CANDIDATES]`
   (with a staleness flag if the report is ≥3 days old).
2. **Open calls under pressure** — from the `under_pressure.json` cache written by the last
   `/update-all`'s `watch` step (not recomputed here). These are the names to consider
   re-analyzing.
3. **Open forecasts** — count + date range from the decision log, flagging any whose horizon
   has **matured** and can be resolved (usually none until ~24 months out).
4. **Calibration scorecard** — hit-rate / alpha / Brier, with the small-sample caveat.
5. **Stale tickers** — tracked names with no decision dated today (`--analysis-plan`).
6. **Data freshness** — when each layer (cycle report, Industry news + index, dashboard,
   decision log) was last refreshed; prompts `/update-all` if anything is stale.

## After running, report
Relay the digest, then **lead with the 1–3 things that actually need attention**: any
under-pressure name, any matured forecast to resolve, and whether the data is stale enough to
warrant `/update-all`. Keep it tight — this is a glance, not a deep dive. Do **not** start any
analysis off the back of it unless the user explicitly asks; just surface the suggested
actions for them to choose.

## Relationship to /update-all
- **`/update-all`** *refreshes* the data (six lenses + cycle + dashboard) — it generates.
- **`/morning`** *reports* on what's already there — it reads. Typical flow: run `/update-all`
  (or let the day's first `/trading-analysis` self-fetch news), then `/morning` for the
  to-do list. Running `/morning` alone is always safe and side-effect-free.
