#!/usr/bin/env python3
"""Stage 1.3 helper — pull recent high-signal industry news relevant to a ticker.

Reads the ai-news LLM payloads (optimized_llm_payload.json — the pillar-filtered, deduped
primary-source digest from SemiAnalysis / Fabricated Knowledge / Epoch AI / Next Platform /
DCD / …) across a **lookback window ending at the analysis date**, and surfaces the articles
that mention the name (by your alias terms) plus, separately, the rest of the recent payload
grouped by pillar for macro context. This upgrades the News & Secular-Driver Analyst from
generic yfinance headlines to the curated industry desk.

Why a window, not a single day: these feeds publish irregularly — a single day's folder is
often sparse and a ticker-relevant piece may have landed 2-3 days earlier. The window
(default 4 days) aggregates every available payload in [date-N+1 .. date], de-duplicates by
URL/title (keeping the most recent), and tags each hit with the day it came from.

Matching is substring (case-insensitive) over title + content against the alias terms you
pass — so pass ticker, company, CEO, and product/codename aliases for good recall.

Usage (from the TradingAgents repo root):
  python3 .claude/skills/trading-analysis/scripts/industry_news.py 2026-06-21 \
      "NVDA Nvidia Jensen Huang Blackwell Rubin CUDA" --lookback 4

Env:
  AINEWS_HOME  path to the ai-news project (default: /home/ewexler/projects/ai-news)
"""
import argparse, json, os, sys
from datetime import datetime, timedelta

DEFAULT_AINEWS_HOME = "/home/ewexler/projects/ai-news"


def load_window(home, end_date, lookback):
    """Aggregate payloads over [end_date-lookback+1 .. end_date]; dedup by URL/title,
    keeping the most recent occurrence. Returns (articles, days_with_data)."""
    try:
        end = datetime.strptime(end_date, "%Y-%m-%d")
    except ValueError:
        return [], []
    seen, articles, days = {}, [], []
    # walk oldest -> newest so the newest copy overwrites on dedup
    for delta in range(lookback - 1, -1, -1):
        d = (end - timedelta(days=delta)).strftime("%Y-%m-%d")
        payload = os.path.join(home, d, "optimized_llm_payload.json")
        if not os.path.exists(payload):
            continue
        try:
            with open(payload, encoding="utf-8") as f:
                day_articles = json.load(f)
        except Exception:
            continue
        days.append(d)
        for art in day_articles:
            key = (art.get("url") or art.get("title", "")).strip().lower()
            art = {**art, "fetched": d}
            seen[key] = art  # newer day wins
    articles = list(seen.values())
    return articles, days


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("date", help="analysis date YYYY-MM-DD (window ends here)")
    ap.add_argument("aliases", nargs="+", help="ticker / company / CEO / product alias terms")
    ap.add_argument("--lookback", type=int, default=4, help="days to look back (inclusive of date)")
    ap.add_argument("--max-context", type=int, default=8, help="non-matching articles to list for macro context")
    ap.add_argument("--home", default=os.environ.get("AINEWS_HOME", DEFAULT_AINEWS_HOME))
    args = ap.parse_args()

    articles, days = load_window(args.home, args.date, args.lookback)
    if not days:
        print(f"NO_PAYLOAD — no payloads found in the {args.lookback}-day window ending {args.date} "
              f"under {args.home}. Run ensure_news.py {args.date} first, or fall back to "
              f"ta_data.py news/global_news for this run.")
        return 0

    # accept aliases as separate args OR one quoted string; tokenize for substring recall
    terms = {t for a in args.aliases for t in a.lower().split() if len(t) >= 2}
    matched, other = [], []
    for art in articles:
        hay = (art.get("title", "") + " " + art.get("content", "")).lower()
        (matched if any(t in hay for t in terms) else other).append(art)
    matched.sort(key=lambda a: a.get("fetched", ""), reverse=True)

    print(f"# Industry News digest — {args.lookback}-day window ending {args.date}")
    print(f"days with data: {', '.join(days)}  ({len(articles)} unique high-signal articles)")
    print(f"matched on {args.aliases}: {len(matched)}")

    print(f"\n## TICKER-RELEVANT ARTICLES ({len(matched)})")
    if not matched:
        print("(none of the day's curated articles name this ticker — rely on the sector/pillar context below)")
    for i, art in enumerate(matched, 1):
        tags = ", ".join(art.get("tags", []))
        print(f"\n[{i}] {art.get('title','')}")
        print(f"    {art.get('source','')} | {art.get('date','')} | fetched {art.get('fetched','?')} | pillars: [{tags}]")
        print(f"    {art.get('url','')}")
        body = " ".join(art.get("content", "").split())
        print(f"    {body[:700]}{' …' if len(body) > 700 else ''}")

    print(f"\n## SECTOR / MACRO CONTEXT (other payload articles, up to {args.max_context})")
    by_pillar = {}
    for art in other:
        for p in art.get("tags", []) or ["untagged"]:
            by_pillar.setdefault(p, []).append(art)
    shown = 0
    for pillar in ("macro_finance", "silicon_hardware", "supply_chain_chokepoints",
                   "physical_infrastructure", "untagged"):
        items = by_pillar.get(pillar, [])
        if not items:
            continue
        print(f"\n  [{pillar.upper().replace('_',' ')}]")
        for art in items:
            if shown >= args.max_context:
                break
            print(f"    - {art.get('title','')[:88]}  ({art.get('source','')})")
            shown += 1
        if shown >= args.max_context:
            break

    print(f"\nnote: this is the recent curated industry desk ({args.lookback}-day window) — weight it as")
    print(f"      the News & Secular-Driver analyst input (~25% of the multi-year forecast). One-off")
    print(f"      headlines matter only if they change the multi-year trajectory.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
