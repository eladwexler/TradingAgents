#!/usr/bin/env python3
"""X Brain bridge for the trading-analysis skill.

Queries the "X brain" — a keyless BM25 index over X (Twitter) FinTwit/AI chatter: a
curated-account lane (posts pulled via Nitter RSS, source "x") plus a Google-News proxy
lane (source "x-news") — and returns the passages a reader needs to judge the **crowd's
sentiment + trend alignment** on a company: is FinTwit net bullish or bearish on the name,
and does it sit on a currently-hot AI trend? Claude synthesizes the fused verdict.

Runs a battery of searches in one process (index loaded once):
  - direct mentions   (company / CEO / $cashtag aliases — you pass these) — split x-post vs x-news
  - bullish lens      (fixed: bullish-chatter terms ∩ the name)
  - bearish lens      (fixed: bearish-chatter terms ∩ the name)
  - trend lens        (the hot AI trends it touches — you pass these, or fixed defaults)

Usage (from the TradingAgents repo root):
  python3 .claude/skills/trading-analysis/scripts/x_brain.py \
      "NVDA Nvidia Jensen $NVDA" \
      --trend "AI capex datacenter inference custom silicon networking" \
      --k 5

Env:
  X_HOME  path to the x-brain project (default: /home/ewexler/projects/x-brain)
"""
import argparse, importlib.util, os, sys

DEFAULT_X_HOME = "/home/ewexler/projects/x-brain"
# what bullish / bearish FinTwit chatter looks like (fixed lenses)
BULL_Q = ("bullish buy long calls breakout accumulate undervalued ripping squeeze beat upgrade "
          "all-time high surge rally outperform conviction strong momentum buy the dip winner")
BEAR_Q = ("bearish sell short puts dump overvalued crash topped downgrade miss plunge weak bubble "
          "correction tumble avoid warning rollover downtrend loser risk")
# default hot AI trends (used if --trend not passed)
TREND_Q = ("AI capex datacenter spending inference compute custom silicon ASIC HBM memory networking "
           "optics power electricity nuclear robotics humanoid agents neocloud sovereign AI")


def load_search_module(home):
    path = os.path.join(home, "index", "search.py")
    if not os.path.exists(path):
        sys.exit(f"[x_brain] search module not found at {path}\n"
                 f"Set X_HOME or build the index (python3 index/build_index.py in the x-brain project).")
    spec = importlib.util.spec_from_file_location("x_search", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    if not os.path.exists(mod.CHUNKS):
        sys.exit(f"[x_brain] index not built: {mod.CHUNKS} missing. "
                 f"Run `python3 index/build_index.py` in {home}.")
    return mod


def src_tag(d):
    """Label a hit by lane: a curated account's post vs the news proxy lane."""
    s = d.get("source", "x")
    return f"X-POST (@{d.get('channel','')[:20]})" if s == "x" else f"X-NEWS ({d.get('channel','')[:20]})"


def emit(title, hits, empty="(no matching passages — corpus may not cover this directly)"):
    print(f"\n## {title}  ({len(hits)} passages)")
    if not hits:
        print(empty)
        return
    for rank, (score, d) in enumerate(hits, 1):
        snippet = " ".join(d["text"].split())
        if len(snippet) > 700:
            snippet = snippet[:700] + " …"
        print(f"\n[{rank}] score={score:.2f}  [{src_tag(d)}]  {d.get('date','?')}  {d.get('title','')[:80]}")
        print(f"    {d.get('url','')}")
        print(f"    {snippet}")


def split_by_source(hits):
    """(post_hits, news_hits) — curated-account posts vs the news proxy lane."""
    posts = [(s, d) for s, d in hits if d.get("source", "x") == "x"]
    news = [(s, d) for s, d in hits if d.get("source", "x") != "x"]
    return posts, news


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("company", nargs="+", help="company / CEO / $cashtag alias terms")
    ap.add_argument("--trend", default="", help="hot AI-trend terms it touches")
    ap.add_argument("--k", type=int, default=5)
    ap.add_argument("--home", default=os.environ.get("X_HOME", DEFAULT_X_HOME))
    args = ap.parse_args()

    mod = load_search_module(args.home)
    bm = mod.BM25(mod.load())
    direct_q = " ".join(args.company)

    print(f"# X Brain — FinTwit sentiment + AI-trend evidence")
    print(f"corpus: {len(bm.docs)} chunks @ {args.home}")
    print(f"direct query: {direct_q!r}")
    if args.trend:
        print(f"trend query: {args.trend!r}")

    wide = bm.search(direct_q, k=max(args.k * 4, 20), per_doc=2)
    posts_direct, news_direct = split_by_source(wide)

    emit("DIRECT MENTIONS — CURATED ACCOUNTS (what FinTwit/AI accounts posted)", posts_direct[:args.k],
         empty="(no curated-account post names this directly — Nitter may be down; lean on the news lane)")
    emit("DIRECT MENTIONS — NEWS PROXY LANE (coverage of the chatter)", news_direct[:args.k],
         empty="(no news-lane item names this — run `python3 work/fetch_trends.py` to refresh)")
    # sentiment lenses: the name's aliases ∩ bullish / bearish chatter
    emit("BULLISH LENS (name ∩ bullish chatter)",
         bm.search(direct_q + " " + BULL_Q, k=args.k, per_doc=1))
    emit("BEARISH LENS (name ∩ bearish chatter)",
         bm.search(direct_q + " " + BEAR_Q, k=args.k, per_doc=1))
    emit("TREND LENS (hot AI trends it touches)",
         bm.search(args.trend or TREND_Q, k=4, per_doc=1))

    post_top = posts_direct[0][0] if posts_direct else 0.0
    news_top = news_direct[0][0] if news_direct else 0.0
    print(f"\n## COVERAGE SIGNAL")
    print(f"x_post_score={post_top:.2f}  "
          f"({'curated accounts discuss it' if post_top >= 10 else 'thin / tangential — lean on the news lane' if post_top > 0 else 'no curated post names it (Nitter may be down)'})")
    print(f"x_news_score={news_top:.2f}  "
          f"({'news-lane coverage on record' if news_top >= 10 else 'only weak/indirect coverage' if news_top > 0 else 'no news item on record (corpus may be stale — run work/fetch_trends.py)'})")
    print("note: this is CROWD sentiment + trend buzz, a coarse lexicon signal — not a")
    print("      thesis and not score-moving. Weigh bullish-vs-bearish lens balance and whether")
    print("      the name rides a hot AI trend; thin coverage => Insufficient chatter, say so.")
    print("      For aggregate trends + the most-bullish-names ranking, see index/research.json.")


if __name__ == "__main__":
    main()
