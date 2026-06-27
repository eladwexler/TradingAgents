#!/usr/bin/env python3
"""Dan Ives Brain bridge for the trading-analysis skill.

Queries the "Dan Ives brain" — a BM25 index over Dan Ives's own words (media appearances
on CNBC, Bloomberg, Fox Business, Yahoo Finance…) plus a news lane — and returns the
passages a reader needs to judge whether **Dan Ives (Wedbush Securities) would rate a
company a top pick** in his "4th industrial revolution" / "Golden Age of AI" framework.
His central lens: is this a direct AI monetization beneficiary with strong Big Tech /
cloud / cybersecurity / EV tailwinds?

Runs a battery of searches in one process (index loaded once):
  - direct mentions   (company / CEO / ticker aliases — you pass these) — split DAN-SAID vs NEWS
  - thesis fit        (the Dan Ives theses it touches — you pass these)
  - bull lens         (fixed: his constructive AI-tech themes / who wins)
  - skepticism lens   (fixed: regulatory risk, China, commoditization, what he avoids)

Usage (from the TradingAgents repo root):
  python3 .claude/skills/trading-analysis/scripts/dan_ives_brain.py \\
      "Microsoft MSFT Satya Nadella Azure OpenAI" \\
      --thesis "AI monetization cloud enterprise software golden age" \\
      --k 5

Env:
  DAN_IVES_HOME  path to the dan-ives-brain project (default: /home/ewexler/projects/dan-ives-brain)
"""
import argparse, importlib.util, os, sys

DEFAULT_DAN_IVES_HOME = "/home/ewexler/projects/dan-ives-brain"
# Dan's constructive AI-tech frame: "4th industrial revolution", AI monetization, Big Tech winners
BULL_Q = ("AI monetization 4th industrial revolution golden age tech bull cloud software "
          "cybersecurity Microsoft Apple Tesla EV autonomous top pick outperform buy "
          "secular growth digital transformation enterprise")
# where Dan is cautious / what he flags as risk
SKEPTICISM_Q = ("regulatory risk China exposure commoditization overvalued bubble sell "
                "underperform avoid headwind antitrust competition risk weakness earnings miss")


def load_search_module(home):
    path = os.path.join(home, "index", "search.py")
    if not os.path.exists(path):
        sys.exit(f"[dan_ives_brain] search module not found at {path}\n"
                 f"Set DAN_IVES_HOME or build the index (python3 index/build_index.py in the dan-ives-brain project).")
    spec = importlib.util.spec_from_file_location("dan_ives_search", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    if not os.path.exists(mod.CHUNKS):
        sys.exit(f"[dan_ives_brain] index not built: {mod.CHUNKS} missing. "
                 f"Run `python3 index/build_index.py` in {home}.")
    return mod


def src_tag(d):
    """Label a hit by provenance: what Dan *said* vs third-party *news*."""
    s = d.get("source", "dan_ives")
    return "DAN-SAID" if s == "dan_ives" else f"NEWS ({d.get('channel','')[:24]})"


def emit(title, hits, empty="(no matching passages — corpus may not cover this directly)"):
    print(f"\n## {title}  ({len(hits)} passages)")
    if not hits:
        print(empty)
        return
    for rank, (score, d) in enumerate(hits, 1):
        snippet = " ".join(d["text"].split())
        if len(snippet) > 900:
            snippet = snippet[:900] + " …"
        print(f"\n[{rank}] score={score:.2f}  [{src_tag(d)}]  {d.get('date','?')}  {d.get('title','')[:80]}")
        print(f"    {d.get('url','')}")
        print(f"    {snippet}")


def split_by_source(hits):
    dan = [(s, d) for s, d in hits if d.get("source", "dan_ives") == "dan_ives"]
    nws = [(s, d) for s, d in hits if d.get("source", "dan_ives") != "dan_ives"]
    return dan, nws


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("company", nargs="+", help="company / CEO / ticker alias terms")
    ap.add_argument("--thesis", default="", help="Dan Ives thesis terms it touches")
    ap.add_argument("--k", type=int, default=5)
    ap.add_argument("--home", default=os.environ.get("DAN_IVES_HOME", DEFAULT_DAN_IVES_HOME))
    args = ap.parse_args()

    mod = load_search_module(args.home)
    bm = mod.BM25(mod.load())
    direct_q = " ".join(args.company)

    print(f"# Dan Ives Brain — sell-side AI-tech conviction evidence")
    print(f"corpus: {len(bm.docs)} chunks @ {args.home}")
    print(f"direct query: {direct_q!r}")
    if args.thesis:
        print(f"thesis query: {args.thesis!r}")

    wide = bm.search(direct_q, k=max(args.k * 4, 20), per_doc=2)
    dan_direct, news_direct = split_by_source(wide)

    emit("DIRECT MENTIONS — DAN IVES (what he said)", dan_direct[:args.k],
         empty="(Dan Ives does not mention this company directly in the corpus — judge by framework fit)")
    emit("NEWS MENTIONS (third-party coverage in the corpus)", news_direct[:args.k],
         empty="(no news item in the corpus mentions this — run `python3 work/fetch_news.py` to refresh)")
    if args.thesis:
        emit("THESIS FIT (Dan's 4th-industrial-revolution / AI-monetization framework)", bm.search(args.thesis, k=args.k, per_doc=1))
    emit("BULL LENS (Dan's constructive AI-tech themes — who wins)",
         bm.search(BULL_Q, k=4, per_doc=1))
    emit("SKEPTICISM LENS (what Dan flags as risk / avoids)",
         bm.search(SKEPTICISM_Q, k=3, per_doc=1))

    dan_top = dan_direct[0][0] if dan_direct else 0.0
    news_top = news_direct[0][0] if news_direct else 0.0
    print(f"\n## COVERAGE SIGNAL")
    print(f"dan_direct_score={dan_top:.2f}  "
          f"({'Dan Ives discusses it directly' if dan_top >= 12 else 'thin / tangential — lean on framework fit and say so' if dan_top > 0 else 'Dan Ives never mentions it — reason from framework fit only'})")
    print(f"news_score={news_top:.2f}  "
          f"({'news coverage on record' if news_top >= 12 else 'only weak/indirect news references' if news_top > 0 else 'no news item on record (corpus may be stale — run work/fetch_news.py)'})")
    print("note: Dan Ives covers US large-cap tech, cybersecurity, and EV. A name outside his")
    print("      universe typically means Insufficient evidence — don't infer a Top Pick from")
    print("      generic AI-bull passages. A Top Pick needs a direct, named endorsement from him.")


if __name__ == "__main__":
    main()
