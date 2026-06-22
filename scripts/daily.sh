#!/usr/bin/env bash
# daily.sh — the scriptable, no-LLM core of the /daily routine (cron-friendly).
#
# Runs the daily DATA refresh + TRIAGE: industry news, the X FinTwit/news lane (RSS),
# live prices/mark-to-market + dashboard, hard macro indicators, the "what's due to
# re-run" list, and the calibration scorecard.
#
# What this script CANNOT do (needs the /daily SKILL = a Claude invocation):
#   - the *conditional* full /ai-cycle-watch (LLM) when a macro threshold newly crosses
#     (this script only PRINTS the hard indicators + flags staleness),
#   - the synthesized digest + suggested-actions prose.
# It NEVER runs /trading-analysis — it only NAMES the few tickers that are due.
#
# Usage:  scripts/daily.sh           (run after the close)
#         scripts/daily.sh --no-x    (skip the X RSS lane — fastest)
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"; cd "$ROOT"
PY="${PY:-python3}"
TA=".claude/skills/trading-analysis/scripts"
DATE="$(date +%F)"
DO_X=1; [ "${1:-}" = "--no-x" ] && DO_X=0

step(){ echo; echo "==================== $* ===================="; }

step "1. Industry-news freshness ($DATE)"
$PY "$TA/ensure_news.py" "$DATE" 2>&1 | head -3 || echo "  [warn] ensure_news failed (offline?) — using last index"

if [ "$DO_X" = 1 ]; then
  step "2a. X FinTwit/news lane (RSS, best-effort, 5-min cap)"
  timeout 300 scripts/update_brains.sh x 2>&1 | tail -4 || echo "  [warn] X lane slow/down — using last corpus"
fi

step "2b. Data refresh + mark-to-market + drift + dashboard"
scripts/update_all.sh --dash-only 2>&1 | grep -iE "under pressure|fetched|wrote|built|warn" | tail -8 \
  || echo "  [warn] dashboard refresh failed"

step "3. Hard macro check"
$PY "$TA/ta_macro_data.py" macro 2>&1 | tail -2 || true
$PY "$TA/ta_macro_data.py" valuation 2>&1 | tail -1 || true
latest="$(ls -t ai-cycle-reports/*_cycle.md 2>/dev/null | head -1)"
if [ -n "$latest" ]; then
  age=$(( ( $(date +%s) - $(stat -c %Y "$latest") ) / 86400 ))
  echo "  latest cycle report: $(basename "$latest") (${age}d old)"
  [ "$age" -gt 3 ] && echo "  ⚠ cycle report >3d old → run the /daily SKILL or /ai-cycle-watch (LLM; not scriptable)"
fi

step "4. What's due — re-run triage (the actionable output)"
$PY scripts/reanalysis_triggers.py 2>&1 || echo "  [warn] triggers failed"

step "5. Calibration"
echo "  open pending forecasts: $($PY "$TA/ta_memory.py" pending 2>/dev/null | grep -c '^\[')"
$PY "$TA/ta_memory.py" score 2>&1 | sed -n '1,5p' || true

echo
echo "==================== daily.sh done ===================="
echo "No-LLM core only. For the conditional /ai-cycle-watch + the synthesized digest,"
echo "run the /daily SKILL instead. Re-run /trading-analysis ONLY on names flagged in step 4."
