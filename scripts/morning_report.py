#!/usr/bin/env python3
"""morning_report.py — a STRICTLY READ-ONLY daily briefing for TradingAgents.

Prints a consolidated "what's on my plate today" report from artifacts that ALREADY exist.
It does **not** analyze anything: no /trading-analysis, no /run-news, no /ai-cycle-watch,
no /update-all, no network calls, no LLM. It only *reads* the latest cycle report, the
ta_memory decision log, the watch cache, and the filesystem, then prints. Backs the
/morning skill.

Sections:
  1. Macro phase        — latest ai-cycle-reports/*_cycle.md STANCE + hedge candidates (read)
  2. Under pressure      — under_pressure.json cache (from the last `ta_memory watch` run)
  3. Forecasts to resolve— `ta_memory.py pending` (read-only list of the decision log)
  4. Calibration         — `ta_memory.py score` (read-only; computed from resolved entries)
  5. Stale tickers       — `update_all.sh --analysis-plan` (fs scan: no decision dated today)
  6. Data freshness      — mtimes/dates of cycle report, ai-news corpus, dashboard, log

The pending/score/analysis-plan calls shell out to existing READ-ONLY commands (no network,
no writes). If you want fresh data, run /update-all FIRST — this report reflects whatever is
already current.

Usage (from the repo root):
  python3 scripts/morning_report.py

Env: PYTHON (default python3), AINEWS_HOME, TRADINGAGENTS_MEMORY_LOG_PATH.
"""
import glob
import json
import os
import re
import subprocess
import sys
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PY = os.environ.get("PYTHON", sys.executable or "python3")
TODAY = datetime.today().strftime("%Y-%m-%d")
TA_MEM = os.path.join(ROOT, ".claude", "skills", "trading-analysis", "scripts", "ta_memory.py")
UPDATE_ALL = os.path.join(ROOT, "scripts", "update_all.sh")
AINEWS_HOME = os.environ.get("AINEWS_HOME", "/home/ewexler/projects/ai-news")

MEM_LOG = os.environ.get("TRADINGAGENTS_MEMORY_LOG_PATH",
                         os.path.expanduser("~/.tradingagents/memory/trading_memory.md"))
UNDER_PRESSURE = os.path.join(os.path.dirname(MEM_LOG), "under_pressure.json")


def hr(title):
    print(f"\n{'='*72}\n{title}\n{'='*72}")


def days_old(date_str):
    try:
        return (datetime.today() - datetime.strptime(date_str, "%Y-%m-%d")).days
    except Exception:
        return None


def run_read(cmd):
    """Run a read-only command; return stdout (never raises)."""
    try:
        r = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=120)
        return (r.stdout or "") + (r.stderr if r.returncode else "")
    except Exception as e:
        return f"  (could not run {' '.join(cmd)}: {e})"


def section_macro():
    hr("1.  MACRO PHASE  (latest AI-cycle report — read-only)")
    reports = sorted(glob.glob(os.path.join(ROOT, "ai-cycle-reports", "*_cycle.md")))
    if not reports:
        print("  (no ai-cycle-reports/*_cycle.md found — run /ai-cycle-watch)")
        return
    latest = reports[-1]
    rdate = os.path.basename(latest)[:10]
    age = days_old(rdate)
    stale = f"  ⚠️ {age}d old — consider /ai-cycle-watch" if (age or 0) >= 3 else ""
    print(f"  report: {rdate}{stale}")
    with open(latest, encoding="utf-8") as f:
        txt = f.read()
    m = re.search(r"^STANCE:\s*(.+?)(?:\n\n|\n#)", txt, flags=re.S | re.M)
    if m:
        stance = " ".join(m.group(1).split())
        print(f"\n  STANCE: {stance[:700]}{' …' if len(stance) > 700 else ''}")
    hedge = re.search(r"\[HEDGE_CANDIDATES\]\s*(\[.*?\]|\{.*?\})", txt, flags=re.S)
    if hedge:
        try:
            data = json.loads(hedge.group(1))
            names = data if isinstance(data, list) else data.get("tickers", data)
            flat = []
            for it in (names if isinstance(names, list) else []):
                flat.append(it if isinstance(it, str) else it.get("ticker", str(it)))
            if flat:
                print(f"\n  HEDGE CANDIDATES (macro-flagged casualties — no new Buys): {', '.join(map(str, flat))}")
        except Exception:
            print("\n  HEDGE CANDIDATES: (present in report — see the file)")


def section_pressure():
    hr("2.  OPEN CALLS UNDER PRESSURE  (watch cache — from the last /update-all)")
    if not os.path.exists(UNDER_PRESSURE):
        print(f"  (no cache at {UNDER_PRESSURE} — run /update-all to populate the ⚠️ flags)")
        return
    try:
        with open(UNDER_PRESSURE, encoding="utf-8") as f:
            cache = json.load(f)
    except Exception as e:
        print(f"  (cache unreadable: {e})")
        return
    items = cache.get("flagged", cache) if isinstance(cache, dict) else cache
    rows = items if isinstance(items, list) else (items.get("flagged", []) if isinstance(items, dict) else [])
    asof = cache.get("as_of") or cache.get("date") if isinstance(cache, dict) else None
    if asof:
        print(f"  as of: {asof}")
    if not rows:
        print("  ✅ none — no open call is drifting hard against its thesis.")
        return
    for r in rows:
        if isinstance(r, dict):
            tk = r.get("ticker", "?")
            why = r.get("why") or r.get("reason") or r.get("note") or ""
            print(f"  ⚠️ {tk:6} {why}".rstrip())
        else:
            print(f"  ⚠️ {r}")
    print("\n  -> these are candidates to RE-ANALYZE on demand (you run /trading-analysis; morning does not).")


def section_pending():
    hr("3.  OPEN FORECASTS  (awaiting outcome — read-only summary)")
    if not os.path.exists(TA_MEM):
        print(f"  (ta_memory.py not found at {TA_MEM})")
        return
    out = run_read([PY, TA_MEM, "pending"]).strip()
    rows = re.findall(r"\[(\d{4}-\d{2}-\d{2})\s*\|\s*([A-Z0-9.]+)\s*\|\s*([A-Za-z]+)\s*\|", out)
    if not rows:
        print("  (none pending)")
        return
    dates = sorted({r[0] for r in rows})
    # a 24mo horizon logged this year cannot have matured; flag only entries >~23mo old
    matured = [r for r in rows if (days_old(r[0]) or 0) >= 23 * 30]
    print(f"  {len(rows)} open forecast(s) logged {dates[0]} → {dates[-1]}, awaiting their horizon.")
    if matured:
        print(f"  ⏰ {len(matured)} may have MATURED — resolve: "
              + ", ".join(f"{t}({d})" for d, t, _ in matured))
    else:
        print("  none have reached their horizon yet — nothing to resolve today.")
    print("  (full list: ta_memory.py pending)")


def section_calibration():
    hr("4.  CALIBRATION SCORECARD  (read-only — computed from resolved calls)")
    if not os.path.exists(TA_MEM):
        print(f"  (ta_memory.py not found at {TA_MEM})")
        return
    out = run_read([PY, TA_MEM, "score"]).strip()
    print("  " + out.replace("\n", "\n  ") if out else "  (no score available)")


def section_stale():
    hr("5.  STALE TICKERS  (no decision dated today — fs scan, read-only)")
    if not os.path.exists(UPDATE_ALL):
        print(f"  (update_all.sh not found at {UPDATE_ALL})")
        return
    out = run_read(["bash", UPDATE_ALL, "--analysis-plan"]).strip()
    tickers = [t for t in out.split() if t]
    if not tickers:
        print("  ✅ every tracked ticker has a decision dated today.")
        return
    print(f"  {len(tickers)} ticker(s) lack a decision for {TODAY}:")
    print("  " + ", ".join(tickers))
    print("\n  -> re-analyze on demand with /trading-analysis (morning does NOT analyze).")


def section_freshness():
    hr("6.  DATA FRESHNESS  (when each layer was last refreshed)")

    def fmtfile(path, label):
        if not os.path.exists(path):
            print(f"  {label:22} (absent)")
            return
        mt = datetime.fromtimestamp(os.path.getmtime(path)).strftime("%Y-%m-%d %H:%M")
        print(f"  {label:22} {mt}")

    # latest cycle report date
    reports = sorted(glob.glob(os.path.join(ROOT, "ai-cycle-reports", "*_cycle.md")))
    cyc = os.path.basename(reports[-1])[:10] if reports else "(none)"
    print(f"  {'AI-cycle report:':22} {cyc}")
    # latest ai-news folder
    if os.path.isdir(AINEWS_HOME):
        days = sorted(d for d in os.listdir(AINEWS_HOME)
                      if re.match(r"^\d{4}-\d{2}-\d{2}$", d))
        news = days[-1] if days else "(none)"
        idx = os.path.join(AINEWS_HOME, "index", "chunks.jsonl")
        print(f"  {'Industry news (latest):':22} {news}{'  ⚠️ not today' if news != TODAY else ''}")
        fmtfile(idx, "Industry index:")
    else:
        print(f"  {'Industry news:':22} (ai-news not found at {AINEWS_HOME})")
    fmtfile(os.path.join(ROOT, "dashboard", "index.html"), "Dashboard:")
    fmtfile(MEM_LOG, "Decision log:")
    print(f"\n  If any layer is stale, run /update-all (refreshes all six lenses + dashboard).")


def main():
    print(f"# ☀️  MORNING REPORT — {TODAY}")
    print("  read-only briefing — reflects existing artifacts; analyzes nothing.")
    print("  (run /update-all first if you want the data refreshed.)")
    section_macro()
    section_pressure()
    section_pending()
    section_calibration()
    section_stale()
    section_freshness()
    print(f"\n{'='*72}")
    print("SUGGESTED ACTIONS (for YOU to run — morning never executes these):")
    print("  • Re-analyze any ⚠️ under-pressure or just-reported-earnings name: /trading-analysis <TICKER>")
    print("  • Resolve any matured forecast above: ta_memory.py resolve …")
    print("  • Refresh data if a layer is stale: /update-all")
    print(f"  • Browse the full picture: open {os.path.join(ROOT, 'dashboard', 'index.html')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
