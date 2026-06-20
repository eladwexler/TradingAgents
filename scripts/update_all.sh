#!/usr/bin/env bash
# update_all.sh — refresh EVERYTHING in the TradingAgents project, in one command.
# Backs the /update skill. Each step is isolated: one failing never aborts the rest.
#
#   1. Brains      — scripts/update_brains.sh (NVIDIA news + Situational-Awareness essay +
#                    Jordi Visser's @JordiVisserLabs channel & news, incremental key-free
#                    YouTube discovery, purity-filtered auto-ingest, and BM25 index rebuild
#                    for all three brains: Jensen, Leopold, and Jordi).
#   2. Dashboard   — scripts/build_dashboard.py (regenerate dashboard/ HTML from the
#                    decision log + analyzed-stocks/).
#   3. Calibration — ta_memory.py pending + score (surface matured-but-unresolved
#                    forecasts to grade, and print the standing Brier/alpha scorecard).
#                    Resolution stays manual on purpose — it needs a written reflection.
#
# Usage:
#   scripts/update_all.sh              # everything
#   scripts/update_all.sh --no-brains  # skip the (slow) brain discovery/rebuild
#   scripts/update_all.sh --no-dash    # skip the dashboard rebuild
#   scripts/update_all.sh --brains-only | --dash-only
#
# Env: PYTHON (default python3); plus all update_brains.sh knobs (JENSEN_HOME,
#      LEOPOLD_HOME, DISCOVER_SINCE, …) and TRADINGAGENTS_MEMORY_LOG_PATH.
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY="${PYTHON:-python3}"
TA_MEM="$ROOT/.claude/skills/trading-analysis/scripts/ta_memory.py"

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
  if [ -f "$ROOT/scripts/build_dashboard.py" ]; then
    ( cd "$ROOT" && "$PY" scripts/build_dashboard.py ) || echo "  [warn] dashboard rebuild failed"
    echo "  -> open $ROOT/dashboard/index.html"
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
echo "==== update_all done ===="
