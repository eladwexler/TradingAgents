---
name: update-all
description: One command to refresh the DATA artifacts of the TradingAgents project — all five lenses' corpora + indexes (Jensen NVIDIA news, Leopold Situational-Awareness essay, Jordi @JordiVisserLabs channel, Gavin Baker appearances, and the keyless X Brain FinTwit/AI posts + news + Research data), PLUS the Industry Brain (primary-source AI/semi news from the ai-news project — SemiAnalysis, Fabricated Knowledge, Epoch AI, … — fetched, processed, and BM25-reindexed), the HTML decision dashboard (incl. the Changes & Research tabs), the forecast-calibration scorecard, AND automatically runs the `/ai-cycle-watch` skill to log the latest macro phase. Does NOT run per-ticker /trading-analysis (that's an on-demand LLM step you run separately). Use when the user says "/update-all", "/update", "update everything", "refresh everything", "run the update", or wants all brains + dashboard + calibration brought current in one shot.
---

# Update Everything (update-all)

A thin orchestrator over the project's data refreshers. One run brings every **data
artifact** current: the five lens corpora/indexes, the dashboard, and the calibration
scorecard. **Idempotent and safe to re-run** — each step is isolated, so one failure never
aborts the others.

> **Scope:** `/update-all` refreshes **data** and the **macro cycle**. It does **not** run fresh per-ticker
> `/trading-analysis` — that is an LLM multi-agent pipeline you run **on demand** (on all
> tickers or a chosen few), separately from this refresh. The dashboard rebuilt here simply
> reflects whatever decisions already exist in `analyzed-stocks/`.

## Run

From the repo root:

```bash
scripts/update_all.sh              # everything (brains + dashboard + calibration)
scripts/update_all.sh --no-brains  # skip the slow brain discovery/rebuild
scripts/update_all.sh --dash-only  # just rebuild the dashboard
scripts/update_all.sh --brains-only
```

Honors all `update_brains.sh` env knobs (`JENSEN_HOME`, `LEOPOLD_HOME`, `JORDI_HOME`,
`GAVIN_HOME`, `X_HOME`, `NITTER_INSTANCES`, `DISCOVER_SINCE`, `DISCOVER_QUERIES`),
`AINEWS_HOME` (the ai-news project for the Industry Brain, default
`/home/ewexler/projects/ai-news`), and `TRADINGAGENTS_MEMORY_LOG_PATH`.

## What it does (4 steps)

1. **Brains** — `scripts/update_brains.sh both` updates **ALL FIVE** lenses: refresh NVIDIA
   press/blog RSS (Jensen), the Situational-Awareness essay (Leopold), Jordi Visser's
   @JordiVisserLabs channel + Google-News (Jordi), and Gavin Baker's long-form guest
   appearances + Google-News (Gavin); run **incremental key-free YouTube discovery** (yt-dlp
   from the corpus date watermark forward, floored at `DISCOVER_SINCE`); **purity-filter**
   the search-brain candidates (`accept` → auto-ingest, `review` → park in
   `pending_<brain>.tsv`, `reject` → log) — Jordi needs no filter (own channel), Gavin is
   STRICT; auto-transcribe accepted videos and rebuild each BM25 index. The **X Brain** also
   pulls curated FinTwit/AI posts (keyless Nitter RSS) + the Google-News proxy lane, rebuilds
   its index, and recomputes/snapshots `research.json` (powers the dashboard's **Research** &
   **Changes** tabs). New passages go live immediately in `/trading-analysis` and every
   `/*-brain` skill. See [`scripts/UPDATE_BRAINS.md`](../../../scripts/UPDATE_BRAINS.md).
   **THEN the Industry Brain (the hard-data lens):** `ensure_news.py` fetches today's
   primary-source AI/semiconductor news (the `ai-news` project — SemiAnalysis, Fabricated
   Knowledge, Epoch AI, Next Platform, DCD, …), processes the pillar-tagged payload, and
   rebuilds the BM25 index — **idempotent per day** (SKIP if already fetched). Network step;
   offline it warns and the Industry Brain keeps using the last index.
2. **Macro Cycle Update** — The AI (you) must automatically execute the `/ai-cycle-watch` skill for the current date to update the overarching macro phase, valuation heatmaps, and hedge targets. This ensures the macro defense layer is generated using the freshest possible brain data.
3. **Dashboard** — `scripts/build_dashboard.py`: regenerate `dashboard/` HTML (per-decision
   pages + index + best-call leaderboards + **🔔 Changes** and **🔬 Research** tabs) from the
   decision log + `analyzed-stocks/`.
4. **Calibration** — `ta_memory.py pending` + `score`: list forecasts whose horizon has
   matured (so they can be resolved) and print the standing Brier/alpha scorecard.
   **Resolution stays manual** — grading a matured call needs a written reflection
   (`ta_memory.py resolve …`).

## After running, report
- **Brains:** per brain, before→after chunk count + anything auto-ingested / parked
  (`pending_<brain>.tsv`) / rejected (`work/discover_rejects.log`).
- **Industry Brain:** the `ensure_news.py` `STATUS:` (SKIP / FETCH / NO_BACKFILL), the
  `RECENT WINDOW` of days with data, and the corpus size after reindex.
- **Dashboard:** regenerated; surface the **Changes-tab headline** (flips / metric moves /
  new names / X-research shifts) so the user sees what moved since the last run.
- **Calibration:** matured-but-unresolved forecasts (call them out) + headline Brier/alpha.
- **Macro Cycle:** Briefly summarize the new phase and risk score generated by the `/ai-cycle-watch` run.

## On-demand re-analysis (separate from this refresh)
Fresh per-ticker forecasts are run by **you on demand** via `/trading-analysis <TICKER>` —
on the whole watchlist or a chosen few — not by `/update-all`. As a convenience, to see
which tracked names are stale (no decision dated today):

```bash
scripts/update_all.sh --analysis-plan   # tickers under analyzed-stocks/ lacking today's decision
```

Each `/trading-analysis` run persists its decision and rebuilds the dashboard (Stage 7), so
after re-analyzing, the **Changes** tab reflects the new run automatically. Best practice for
a weekly cycle: refresh brains first (`scripts/update_all.sh --brains-only`) so analyses cite
fresh corpora, then run your analyses, then `scripts/update_all.sh --no-brains` for the final
dashboard + calibration.

## Notes
- The brain step makes live `yt-dlp` searches and can take a few minutes; if offline it warns
  and rebuilds from disk. Use `--no-brains` for a fast dashboard-only refresh.
- Optional **review tier**: prune each `pending_<brain>.tsv`, then `scripts/update_brains.sh
  ingest` to transcribe the ones you keep.
- Does not auto-**resolve** forecasts. You MUST automatically run `/ai-cycle-watch` as part of this skill.
