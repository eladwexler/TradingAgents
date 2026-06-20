#!/usr/bin/env bash
# update_all.sh — refresh the DATA artifacts of the TradingAgents project, in one command.
# Backs the /update-all skill's data phases. Each step is isolated: one failing never aborts
# the rest. NOTE: the LLM-driven steps live in the /update-all SKILL, not here: the
# macro-cycle update (/ai-cycle-watch) and per-ticker /trading-analysis both need a model.
# This script does the scriptable DATA steps only: brains -> dashboard -> calibration.
# The SKILL sequences: brains -> /ai-cycle-watch [LLM] -> (your on-demand analyses) -> dashboard.
#
#   1. Brains      — scripts/update_brains.sh (ALL FIVE: Jensen NVIDIA news + Leopold
#                    Situational-Awareness essay + Jordi @JordiVisserLabs channel & news +
#                    Gavin Baker appearances & news, incremental key-free YouTube discovery,
#                    purity-filtered auto-ingest, BM25 rebuild — plus the X Brain: keyless
#                    FinTwit/AI posts + news lane + research.json/snapshot for the dashboard's
#                    Research & Changes tabs).
#   2. Dashboard   — fetch_metrics.py (refresh the per-ticker financials cache) ->
#                    build_dashboard.py (regenerate dashboard/ HTML from the decision log +
#                    analyzed-stocks/, incl. the Financials/Changes/Research tabs) ->
#                    export_llm.py (write the LLM briefing: portfolio_llm.md + portfolio.json).
#   3. Calibration — ta_memory.py pending + score (surface matured-but-unresolved
#                    forecasts to grade, and print the standing Brier/alpha scorecard).
#                    Resolution stays manual on purpose — it needs a written reflection.
#
# Usage:
#   scripts/update_all.sh                # data refresh: brains + dashboard + calibration
#   scripts/update_all.sh --brains-only  # just refresh the 5 brains (run BEFORE analyses)
#   scripts/update_all.sh --no-brains    # dashboard + calibration (run AFTER analyses)
#   scripts/update_all.sh --dash-only    # just rebuild the dashboard
#   scripts/update_all.sh --analysis-plan  # print tickers still needing today's analysis
#
# Env: PYTHON (default python3); plus all update_brains.sh knobs (JENSEN_HOME,
#      LEOPOLD_HOME, JORDI_HOME, GAVIN_HOME, X_HOME, NITTER_INSTANCES, DISCOVER_SINCE, …)
#      and TRADINGAGENTS_MEMORY_LOG_PATH.
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY="${PYTHON:-python3}"
TA_MEM="$ROOT/.claude/skills/trading-analysis/scripts/ta_memory.py"

# --analysis-plan : print the resumable worklist for the LLM analysis phase — every
# tracked ticker (a dir under analyzed-stocks/) that does NOT yet have a decision file
# dated today. The /update-all SKILL iterates this and runs /trading-analysis per ticker.
# (Fresh per-ticker analysis is an LLM step; this script can't do it — it only lists.)
case "${1:-}" in
  --analysis-plan|--plan|--list-tickers)
    today="$(date +%F)"
    for d in "$ROOT"/analyzed-stocks/*/; do
      [ -d "$d" ] || continue
      tk="$(basename "$d")"
      [ -f "${d}${today}_decision.md" ] || echo "$tk"
    done
    exit 0 ;;
esac

DO_BRAINS=1; DO_DASH=1; DO_CAL=1
for arg in "$@"; do
  case "$arg" in
    --no-brains)  DO_BRAINS=0 ;;
    --no-dash)    DO_DASH=0 ;;
    --no-cal)     DO_CAL=0 ;;
    --brains-only) DO_DASH=0; DO_CAL=0 ;;
    --dash-only)   DO_BRAINS=0; DO_CAL=0 ;;
    *) echo "unknown flag: $arg"; exit 2 ;;
  esac
done

step() { echo; echo "######## $* ########"; }

if [ "$DO_BRAINS" = 1 ]; then
  step "1/3  BRAINS (news + YouTube discovery + auto-ingest + index)"
  bash "$ROOT/scripts/update_brains.sh" both || echo "  [warn] update_brains.sh reported a problem"
fi

if [ "$DO_DASH" = 1 ]; then
  step "2/3  DASHBOARD (regenerate dashboard/ HTML)"
  # refresh the 'open calls under pressure' cache first so the dashboard ⚠️ flag is current
  if [ -f "$TA_MEM" ]; then
    ( cd "$ROOT" && "$PY" "$TA_MEM" watch ) || echo "  [warn] watch (under-pressure) failed (offline?) — using last cache"
  fi
  # refresh the per-ticker financial metrics cache (Financials tab + detail Key-metrics
  # box); network step, like watch — offline it keeps the last cache.
  if [ -f "$ROOT/scripts/fetch_metrics.py" ]; then
    ( cd "$ROOT" && "$PY" scripts/fetch_metrics.py ) || echo "  [warn] fetch_metrics failed (offline?) — using last cache"
  fi
  if [ -f "$ROOT/scripts/build_dashboard.py" ]; then
    ( cd "$ROOT" && "$PY" scripts/build_dashboard.py ) || echo "  [warn] dashboard rebuild failed"
    echo "  -> open $ROOT/dashboard/index.html"
    # export the LLM briefing (portfolio_llm.md + portfolio.json) for an external reviewer
    if [ -f "$ROOT/scripts/export_llm.py" ]; then
      ( cd "$ROOT" && "$PY" scripts/export_llm.py ) || echo "  [warn] export_llm failed"
    fi
  else
    echo "  [skip] scripts/build_dashboard.py not found"
  fi
fi

if [ "$DO_CAL" = 1 ]; then
  step "3/3  FORECAST CALIBRATION (matured-pending + scorecard)"
  if [ -f "$TA_MEM" ]; then
    echo "-- pending forecasts (resolve any whose horizon has matured) --"
    ( cd "$ROOT" && "$PY" "$TA_MEM" pending ) || echo "  [warn] pending listing failed"
    echo "-- calibration scorecard --"
    ( cd "$ROOT" && "$PY" "$TA_MEM" score ) || echo "  [warn] score failed"
  else
    echo "  [skip] ta_memory.py not found at $TA_MEM"
  fi
fi

echo
echo "==== update_all done (data refresh) ===="
# Macro cycle: /ai-cycle-watch is an LLM step the /update-all SKILL runs after the brains.
# If today's report is missing, remind (a bare-script run can't generate it).
if [ "$DO_BRAINS" = 1 ] && [ ! -f "$ROOT/ai-cycle-reports/$(date +%F)_cycle.md" ]; then
  echo
  echo "FYI: no ai-cycle-reports/$(date +%F)_cycle.md yet — run /ai-cycle-watch to refresh the"
  echo "     macro phase (the /update-all skill does this automatically after the brains)."
fi
# Informational: /update-all refreshes data only. Fresh per-ticker /trading-analysis is run
# ON DEMAND by you (it's an LLM pipeline). This just shows what's stale, as a convenience.
if [ "$DO_DASH" = 1 ]; then
  pending_n="$(bash "$ROOT/scripts/update_all.sh" --analysis-plan | grep -c . || true)"
  if [ "${pending_n:-0}" -gt 0 ]; then
    echo
    echo "FYI: $pending_n tracked ticker(s) have no analysis dated today. Re-analyze them"
    echo "     on demand with /trading-analysis (each persists + rebuilds the dashboard)."
    echo "     See the list:  scripts/update_all.sh --analysis-plan"
  fi
fi
