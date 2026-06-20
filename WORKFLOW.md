# Operating Workflow — daily & weekly

How to actually run this project on a cadence. It has two kinds of work:

- **Data refresh** (scripted, no LLM) — the 5 lens "brains", the dashboard, the calibration
  scorecard. One command: `scripts/update_all.sh`.
- **Fresh forecasts** (LLM, on demand) — `/trading-analysis <TICKER>`, where Claude plays
  every agent. **You run these yourself**, on the whole watchlist or a chosen few.
  `/update-all` does **not** run them.

The dashboard (`dashboard/index.html`) is the read-out: best-call leaderboards, the
**🔬 Research** tab (X/FinTwit trends + most-bullish names), and the **🔔 Changes** tab
(what moved since the previous run).

---

## TL;DR

```bash
# ── WEEKLY (full cycle) ─────────────────────────────────────────────
scripts/update_all.sh --brains-only          # 1. refresh all 5 brains first
/ai-cycle-watch                               # 2. refresh the macro phase (uses fresh brains)
scripts/update_all.sh --analysis-plan         # 3. see which tickers are stale, then…
/trading-analysis <TICKER>                    #    …run on demand for each (resumable)
scripts/update_all.sh --no-brains             # 4. final dashboard + calibration

# ── DAILY (light) ───────────────────────────────────────────────────
scripts/update_brains.sh x && python3 scripts/build_dashboard.py   # fresh X sentiment/research
/trading-analysis <TICKER>                    # analyze anything topical on demand
# open dashboard/index.html → 🔔 Changes
```

---

## Weekly flow (the full cycle)

Order matters: **brains → analyses → dashboard**, so forecasts cite fresh corpora and the
Changes/Research tabs reflect the new run.

### 1. Refresh the brains (data, scripted)
```bash
scripts/update_all.sh --brains-only
```
Updates all five lenses — Jensen (NVIDIA news), Leopold (Situational-Awareness essay),
Jordi (@JordiVisserLabs), Gavin (guest appearances), and **X** (keyless FinTwit/AI posts +
news + `research.json` snapshot). Idempotent; offline → warns and rebuilds from disk.
Report each brain's before→after chunk count.

> Per-brain control if needed: `scripts/update_brains.sh [jensen|leopold|jordi|gavin|x|both]`.

### 2. Update the macro cycle (LLM)
```text
/ai-cycle-watch
```
Run right after the brains so it uses the freshest corpora. It writes
`ai-cycle-reports/<DATE>_cycle.md` — the macro **phase / stance** that `/trading-analysis`
Stage 0 reads for its macro-adjusted call, so do this **before** the analyses.
(The `/update-all` skill runs this step automatically; run it by hand only if you're doing
the staged commands.)

### 3. Re-analyze the tickers (forecasts, on demand — you)
See what's stale (tracked names with no decision dated today — a **resumable** worklist):
```bash
scripts/update_all.sh --analysis-plan
```
Then for each ticker run the full pipeline:
```bash
/trading-analysis <TICKER>
```
- Each run persists `analyzed-stocks/<TICKER>/<DATE>_decision.md`, logs the forecast
  (`P=`, horizon) for Brier scoring, and rebuilds the dashboard (Stage 7).
- It's fine to do these in **batches** across sessions — re-run `--analysis-plan` to see
  what's left; finished-today tickers drop off the list.
- Analyze a **new** name just by running it; it appears as a **🆕 New name** in Changes.

### 4. Final dashboard + calibration (data, scripted)
```bash
scripts/update_all.sh --no-brains
```
Rebuilds the dashboard (now reflecting every fresh analysis, with the **🔔 Changes** diff and
inline Research deltas), lists **matured-but-unresolved** forecasts, and prints the
**Brier/alpha scorecard**.

### 5. Review & resolve
- Open `dashboard/index.html` → **🔔 Changes** for the week's flips / metric moves / new
  names / X-research shifts; **🔬 Research** for hot trends + most-bullish names.
- **Resolve matured forecasts** (manual — needs a written reflection):
  ```bash
  python3 .claude/skills/trading-analysis/scripts/ta_memory.py pending
  python3 .claude/skills/trading-analysis/scripts/ta_memory.py resolve <TICKER> <DATE> \
      --horizon-months 24 --reflection-file <notes.md>
  ```

---

## Daily flow (light touch)

You don't need the full cycle daily. Pick what's useful:

- **Fresh X sentiment / Research only** (fast, no forecasts):
  ```bash
  scripts/update_brains.sh x && python3 scripts/build_dashboard.py
  ```
- **Analyze something topical** on demand: `/trading-analysis <TICKER>` (auto-persists +
  rebuilds the dashboard).
- **Just rebuild the dashboard** after editing a decision file:
  ```bash
  scripts/update_all.sh --dash-only
  ```
- Check **🔔 Changes** — it diffs the newest run against the previous one (works at daily
  granularity too; "latest run" = newest decision date ±3 days).

---

## What `/update-all` does (and doesn't)

The `/update-all` **skill** bundles the brains + macro cycle + dashboard + calibration; the
`update_all.sh` **script** does only the no-model parts.

| Phase | Command | In `/update-all`? | LLM? |
|---|---|---|---|
| Brains (5 corpora + indexes) | `scripts/update_all.sh --brains-only` | ✅ | no |
| Macro cycle (phase/stance) | `/ai-cycle-watch` | ✅ (skill runs it) | **yes** |
| Dashboard (incl. Changes/Research) | part of `update_all.sh` | ✅ | no |
| Calibration (pending + Brier scorecard) | part of `update_all.sh` | ✅ | no |
| **Per-ticker forecasts** | **`/trading-analysis <TICKER>`** (you, on demand) | ❌ separate | **yes** |

`scripts/update_all.sh` (no flags) = brains + dashboard + calibration in one shot. It
**cannot** run `/trading-analysis` (no model in a shell script); it just prints an FYI of how
many tickers are stale.

---

## Reference

**Commands**
- `scripts/update_all.sh [--brains-only|--no-brains|--dash-only|--analysis-plan]`
- `scripts/update_brains.sh [jensen|leopold|jordi|gavin|x|both|ingest]`
- `python3 scripts/build_dashboard.py` — rebuild `dashboard/index.html`
- `python3 .claude/skills/trading-analysis/scripts/ta_memory.py [recall|pending|returns|resolve|score] …`

**Docs**
- `scripts/DASHBOARD.md` — dashboard internals (tabs, buckets, Changes/Research diff)
- `scripts/UPDATE_BRAINS.md` — brain corpora, purity filter, adding sources
- `.claude/skills/<name>/SKILL.md` — each skill (`trading-analysis`, `update-all`,
  `update-brains`, the `*-brain` lenses)

**Env knobs** (optional)
- `JENSEN_HOME` / `LEOPOLD_HOME` / `JORDI_HOME` / `GAVIN_HOME` / `X_HOME` — brain project paths
- `NITTER_INSTANCES` — comma-separated Nitter base URLs for the X account lane
- `DISCOVER_SINCE` / `DISCOVER_QUERIES` — YouTube discovery window/queries
- `TRADINGAGENTS_MEMORY_LOG_PATH` — decision-log path (default `~/.tradingagents/memory/trading_memory.md`)

**Troubleshooting**
- *Nitter empty for the X account lane* — flaky/down; the Google-News proxy lane carries it.
  Set `NITTER_INSTANCES` to a live mirror to restore curated-account posts.
- *Brain step slow / offline* — it makes live `yt-dlp` searches; offline it warns and
  rebuilds from disk. Use `--no-brains` to skip.
- *Reddit 403/429 in an analysis* — public-endpoint rate limit; sentiment degrades to
  StockTwits-only, which is expected and noted in the output.

> Research scaffold only — **not** financial, investment, or trading advice.
