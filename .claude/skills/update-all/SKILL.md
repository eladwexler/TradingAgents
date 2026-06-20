---
name: update-all
description: One command to refresh EVERYTHING in the TradingAgents project — all four secular-lens brains (Jensen, Leopold, Jordi & Gavin Baker: NVIDIA news + Situational-Awareness essay + Jordi Visser's @JordiVisserLabs channel + Gavin Baker's long-form guest appearances & news, incremental key-free YouTube discovery with purity-filtered auto-ingest, and BM25 index rebuild), the HTML decision dashboard, and the forecast-calibration readout (matured-pending forecasts + Brier/alpha scorecard). Use when the user says "/update-all", "/update", "update everything", "refresh everything", "run the update", or wants all project data/artifacts brought current in one shot.
---

# Update Everything (update-all)

A thin orchestrator over the project's existing refreshers. One run brings every
data artifact current: the two secular-lens brains, the dashboard, and the forecast
scorecard. It is **idempotent and safe to re-run** — each step is isolated, so one
failure never aborts the others.

## Run

From the repo root:

```bash
scripts/update_all.sh              # everything (default)
scripts/update_all.sh --no-brains  # skip the slow brain discovery/rebuild
scripts/update_all.sh --dash-only  # just rebuild the dashboard
scripts/update_all.sh --brains-only
```

Honors all `update_brains.sh` env knobs (`JENSEN_HOME`, `LEOPOLD_HOME`, `DISCOVER_SINCE`,
`DISCOVER_QUERIES`, `DISCOVER_N`) and `TRADINGAGENTS_MEMORY_LOG_PATH`.

## What it does (3 steps)

1. **Brains** — `scripts/update_brains.sh both` (updates ALL four brains): refresh NVIDIA
   press/blog RSS (Jensen), the Situational-Awareness essay (Leopold), Jordi Visser's
   @JordiVisserLabs channel + Google-News (Jordi), and Gavin Baker's long-form guest
   appearances + Google-News (Gavin); run **incremental key-free YouTube discovery** (yt-dlp
   from the corpus date watermark forward, floored at `DISCOVER_SINCE`, default Jan 2026);
   **purity-filter** the search-brain candidates (`accept` → auto-ingest, `review` → park
   in `pending_<brain>.tsv`, `reject` → log) — Jordi needs no filter (own channel), Gavin is
   STRICT (only allowlisted long-form venues auto-ingest); auto-transcribe accepted videos
   and rebuild all four BM25 indexes. New passages go live immediately in `/trading-analysis`,
   `/jensen-brain`, `/leopold-brain`, `/jordi-brain`, `/gavin-brain`.
   See [`scripts/UPDATE_BRAINS.md`](../../../scripts/UPDATE_BRAINS.md).
2. **Dashboard** — `scripts/build_dashboard.py`: regenerate `dashboard/` HTML (per-decision
   pages + index + best-call leaderboards) from the decision log + `analyzed-stocks/`.
3. **Calibration** — `ta_memory.py pending` + `score`: list forecasts whose horizon has
   matured (so they can be resolved) and print the standing Brier/alpha scorecard.
   **Resolution stays manual** — grading a matured call needs a written reflection
   (`ta_memory.py resolve …`), which is a judgement step, not a refresh.

## After running, report

- Per brain: the **before→after chunk count**, and any videos **auto-ingested** vs
  **parked for review** (`pending_<brain>.tsv`) vs **rejected** (`work/discover_rejects.log`).
- Dashboard: that `dashboard/index.html` was regenerated.
- Calibration: how many forecasts are **matured-but-unresolved** (call these out so the
  user can resolve them) and the headline scorecard numbers.

## Notes
- The brain step makes live `yt-dlp` searches and can take a few minutes; if offline it
  warns and rebuilds from whatever is on disk. Use `--no-brains` for a fast dashboard-only refresh.
- If the user wants the optional **review tier** ingested too (the `pending_<brain>.tsv`
  candidates the purity filter wasn't sure about), have them prune those files, then run
  `scripts/update_brains.sh ingest`.
- This does **not** auto-resolve forecasts or run a new `/ai-cycle-watch` report — those
  are analysis actions, not refreshes. Offer them as follow-ups if relevant.
