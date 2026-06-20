#!/usr/bin/env python3
"""Gavin Brain bridge for the trading-analysis skill — STRICT.

Queries the "Gavin brain" — a BM25 index over Gavin Baker's own words (long-form guest
appearances: BG2, Invest Like the Best, Aleph, a16z, Sohn, TBPN…) plus a news lane — and
returns the passages a reader needs to judge whether **Gavin Baker (Atreides Management)
would back a company as an AI winner**. His central question is "is AI *sustaining* (helps
the incumbent's moat — data, distribution, scale, compute) or *disruptive* (erodes it)?"
He is a concentrated, opinionated tech investor — so be STRICT: only call a name a
Conviction pick on strong, direct, repeated evidence (a known holding / emphatic
endorsement); otherwise lean Possible or Insufficient.

Runs a battery of searches in one process (index loaded once):
  - direct mentions  (company / CEO / ticker aliases — you pass these) — split GAVIN-SAID vs NEWS
  - thesis fit       (the Gavin theses it touches — you pass these)
  - sustaining lens  (fixed: AI sustaining-vs-disruptive, moats, compute winners)
  - skepticism lens  (fixed: what he avoids — disruption, commoditization, thin wrappers)

Usage (from the TradingAgents repo root):
  python3 .claude/skills/trading-analysis/scripts/gavin_brain.py \
      "Nvidia NVDA Jensen Huang" \
      --thesis "compute accelerator AI capex inference training moat" \
      --k 5

Env:
  GAVIN_HOME  path to the gavin-brain project (default: /home/ewexler/projects/gavin-brain)
"""
import argparse, importlib.util, os, sys

DEFAULT_GAVIN_HOME = "/home/ewexler/projects/gavin-brain"
# Gavin's constructive frame: AI as sustaining innovation for moat/data/distribution/compute
SUSTAINING_Q = ("AI sustaining incumbent moat proprietary data distribution scale compute "
                "NVIDIA accelerator inference training capex winner owns the customer")
# where Gavin is cautious / what he avoids
SKEPTICISM_Q = ("disruptive disruption commoditized commodity competition thin wrapper margins "
                "overvalued avoid loser short bubble share loss displaced")


def load_search_module(home):
    path = os.path.join(home, "index", "search.py")
    if not os.path.exists(path):
        sys.exit(f"[gavin_brain] search module not found at {path}\n"
                 f"Set GAVIN_HOME or build the index (python3 index/build_index.py in the gavin-brain project).")
    spec = importlib.util.spec_from_file_location("gavin_search", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    if not os.path.exists(mod.CHUNKS):
        sys.exit(f"[gavin_brain] index not built: {mod.CHUNKS} missing. "
                 f"Run `python3 index/build_index.py` in {home}.")
    return mod


def src_tag(d):
    """Label a hit by provenance: what Gavin *said* vs third-party *news*."""
    s = d.get("source", "gavin")
    return "GAVIN-SAID" if s == "gavin" else f"NEWS ({d.get('channel','')[:24]})"


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
    gav = [(s, d) for s, d in hits if d.get("source", "gavin") == "gavin"]
    nws = [(s, d) for s, d in hits if d.get("source", "gavin") != "gavin"]
    return gav, nws


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("company", nargs="+", help="company / CEO / ticker alias terms")
    ap.add_argument("--thesis", default="", help="Gavin-thesis terms it touches")
    ap.add_argument("--k", type=int, default=5)
    ap.add_argument("--home", default=os.environ.get("GAVIN_HOME", DEFAULT_GAVIN_HOME))
    args = ap.parse_args()

    mod = load_search_module(args.home)
    bm = mod.BM25(mod.load())
    direct_q = " ".join(args.company)

    print(f"# Gavin Brain — AI-winner conviction evidence (STRICT)")
    print(f"corpus: {len(bm.docs)} chunks @ {args.home}")
    print(f"direct query: {direct_q!r}")
    if args.thesis:
        print(f"thesis query: {args.thesis!r}")

    wide = bm.search(direct_q, k=max(args.k * 4, 20), per_doc=2)
    gav_direct, news_direct = split_by_source(wide)

    emit("DIRECT MENTIONS — GAVIN (what he said)", gav_direct[:args.k],
         empty="(Gavin does not mention this company directly in the corpus — judge by his framework, don't infer a pick)")
    emit("NEWS MENTIONS (third-party coverage in the corpus)", news_direct[:args.k],
         empty="(no news item in the corpus mentions this — run `python3 work/fetch_news.py` to refresh)")
    if args.thesis:
        emit("THESIS FIT (Gavin's framework)", bm.search(args.thesis, k=args.k, per_doc=1))
    emit("SUSTAINING-VS-DISRUPTIVE LENS (does AI help the moat?)",
         bm.search(SUSTAINING_Q, k=4, per_doc=1))
    emit("SKEPTICISM LENS (what Gavin avoids)",
         bm.search(SKEPTICISM_Q, k=3, per_doc=1))

    gav_top = gav_direct[0][0] if gav_direct else 0.0
    news_top = news_direct[0][0] if news_direct else 0.0
    print(f"\n## COVERAGE SIGNAL")
    print(f"gavin_direct_score={gav_top:.2f}  "
          f"({'Gavin discusses it directly' if gav_top >= 12 else 'thin / tangential — do NOT call a Conviction pick on this' if gav_top > 0 else 'Gavin never mentions it — Insufficient unless framework fit is overwhelming'})")
    print(f"news_score={news_top:.2f}  "
          f"({'news coverage on record' if news_top >= 12 else 'only weak/indirect news references' if news_top > 0 else 'no news item on record (corpus may be stale — run work/fetch_news.py)'})")
    print("STRICT RULE: reserve 'Conviction pick' for strong, direct, repeated endorsement or a")
    print("             known holding. Praise of a theme is NOT the same as backing a specific name.")


if __name__ == "__main__":
    main()
