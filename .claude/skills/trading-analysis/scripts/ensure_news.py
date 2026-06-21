#!/usr/bin/env python3
"""Freshness gate for the ai-news industry corpus — run once per analysis date.

Idempotent by design: the first /trading-analysis run on a given calendar day fetches the
day's primary-source AI/semiconductor news, processes it into the LLM payload, and rebuilds
the Industry Brain BM25 index. Every later run that same day sees the payload already exists
and SKIPS the fetch — so the news pipeline runs at most once per date, no matter how many
tickers you analyze.

Decision table (DATE defaults to today):
  - payload for DATE already exists                -> SKIP   (ensure index exists; never re-fetch)
  - payload missing AND DATE == today              -> FETCH  (news-today.py + process-news.py + reindex)
  - payload missing AND DATE in the past           -> NO_BACKFILL (RSS only carries ~24h; just ensure index)

Prints a status line and the absolute payload path (for the Stage 1.3 News analyst) plus the
index path (for the Industry Brain). Exit code is always 0 unless the corpus is unusable.

Usage (from the TradingAgents repo root):
  python3 .claude/skills/trading-analysis/scripts/ensure_news.py [YYYY-MM-DD]

Env:
  AINEWS_HOME  path to the ai-news project (default: /home/ewexler/projects/ai-news)
"""
import os, subprocess, sys
from datetime import datetime, timedelta

DEFAULT_AINEWS_HOME = "/home/ewexler/projects/ai-news"


def recent_window(home, end_date, lookback=4):
    """List the days in [end-lookback+1 .. end] that actually have a payload."""
    try:
        end = datetime.strptime(end_date, "%Y-%m-%d")
    except ValueError:
        return []
    out = []
    for delta in range(lookback - 1, -1, -1):
        d = (end - timedelta(days=delta)).strftime("%Y-%m-%d")
        if os.path.exists(os.path.join(home, d, "optimized_llm_payload.json")):
            out.append(d)
    return out


def run(cmd, cwd):
    print(f"  $ {' '.join(cmd)}")
    r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if r.stdout.strip():
        print("    " + r.stdout.strip().replace("\n", "\n    "))
    if r.returncode != 0:
        print(f"    [warn] exit {r.returncode}: {r.stderr.strip()[:300]}")
    return r.returncode == 0


def build_index(home):
    return run([sys.executable, "index/build_index.py"], home)


def main():
    date = sys.argv[1] if len(sys.argv) > 1 else datetime.today().strftime("%Y-%m-%d")
    home = os.environ.get("AINEWS_HOME", DEFAULT_AINEWS_HOME)
    today = datetime.today().strftime("%Y-%m-%d")

    folder = os.path.join(home, date)
    payload = os.path.join(folder, "optimized_llm_payload.json")
    index = os.path.join(home, "index", "chunks.jsonl")

    if not os.path.isdir(home):
        print(f"STATUS: UNAVAILABLE — ai-news project not found at {home} (set AINEWS_HOME). "
              f"Skip the Industry Brain / news upgrade this run; do not fabricate.")
        return 0

    if os.path.exists(payload):
        status = "SKIP"
        print(f"STATUS: {status} — news already fetched for {date}; not re-running the pipeline.")
        if not os.path.exists(index):
            print("  index missing despite payload — building it now:")
            build_index(home)
    elif date == today:
        status = "FETCH"
        print(f"STATUS: {status} — no payload for {date}; running the news pipeline once.")
        run([sys.executable, "news-today.py"], home)
        run([sys.executable, "process-news.py", folder], home)
        build_index(home)
    else:
        status = "NO_BACKFILL"
        print(f"STATUS: {status} — {date} is in the past and the RSS feeds only carry ~24h; "
              f"cannot backfill. Using the existing historical index.")
        if not os.path.exists(index):
            build_index(home)

    window = recent_window(home, date, lookback=4)
    print(f"RECENT WINDOW (4d ending {date}): {', '.join(window) if window else '(none — corpus empty/stale)'}")
    print(f"  -> Stage 1.3 should pass --lookback 4 to industry_news.py since feeds publish irregularly.")
    print(f"PAYLOAD: {payload}{'' if os.path.exists(payload) else '  (absent — Stage 1.3 falls back to ta_data news)'}")
    print(f"INDEX:   {index}{'' if os.path.exists(index) else '  (absent — Industry Brain unavailable)'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
