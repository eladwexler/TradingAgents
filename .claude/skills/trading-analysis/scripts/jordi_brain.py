#!/usr/bin/env python3
"""Jordi Brain bridge for the trading-analysis skill.

Queries the "Jordi brain" — a BM25 index over Jordi Visser's own words (every video on
his @JordiVisserLabs YouTube channel) plus a news lane — and returns the passages a
reader needs to judge whether a company sits **with or against Jordi Visser's macro / AI
thesis**: the AI capex super-cycle, compute scarcity vs. abundance, the deflationary AI
productivity boom ("the new QE is AI and crypto"), bitcoin as the purest AI-macro trade,
physical AI / robotics / robotaxis, and creative destruction (the "SaaS-pocalypse", ROIC
gaps, labor disruption). Claude synthesizes the verdict — is Jordi constructive on the
name (a thesis beneficiary) or cautious (on the wrong side of the disruption he warns about)?

Runs a battery of searches in one process (index loaded once):
  - direct mentions   (company / CEO / ticker aliases — you pass these) — split jordi-said vs news
  - thesis fit        (the Jordi theses it touches — you pass these)
  - tailwind lens     (fixed: his constructive macro-AI themes / who wins)
  - skepticism lens   (fixed: SaaS-pocalypse, ROIC gap, bubble, what gets disrupted)

Usage (from the TradingAgents repo root):
  python3 .claude/skills/trading-analysis/scripts/jordi_brain.py \
      "Palantir PLTR Karp" \
      --thesis "SaaS disruption agents software ontology AI productivity" \
      --k 5

Env:
  JORDI_HOME  path to the jordi-brain project (default: /home/ewexler/projects/jordi-brain)
"""
import argparse, importlib.util, os, sys

DEFAULT_JORDI_HOME = "/home/ewexler/projects/jordi-brain"
# Jordi's constructive macro-AI themes — who/what the build-out and productivity boom enrich
TAILWIND_Q = ("AI capex cycle compute scarcity accelerated bitcoin deflation productivity "
              "physical AI robotics robotaxi tokens scarcity abundance winners beneficiaries demand")
# where Jordi is cautious / what creative destruction breaks
SKEPTICISM_Q = ("SaaS disruption software replaced agents commoditized ROIC gap bubble overvalued "
                "hyperscaler leverage private credit labor weakness losers short what breaks")


def load_search_module(home):
    path = os.path.join(home, "index", "search.py")
    if not os.path.exists(path):
        sys.exit(f"[jordi_brain] search module not found at {path}\n"
                 f"Set JORDI_HOME or build the index (python3 index/build_index.py in the jordi-brain project).")
    spec = importlib.util.spec_from_file_location("jordi_search", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    if not os.path.exists(mod.CHUNKS):
        sys.exit(f"[jordi_brain] index not built: {mod.CHUNKS} missing. "
                 f"Run `python3 index/build_index.py` in {home}.")
    return mod


def src_tag(d):
    """Label a hit by provenance: what Jordi *said* vs third-party *news*."""
    s = d.get("source", "jordi")
    return "JORDI-SAID" if s == "jordi" else f"NEWS ({d.get('channel','')[:24]})"


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
    """(jordi_hits, news_hits) — what he said vs third-party reporting."""
    jor = [(s, d) for s, d in hits if d.get("source", "jordi") == "jordi"]
    nws = [(s, d) for s, d in hits if d.get("source", "jordi") != "jordi"]
    return jor, nws


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("company", nargs="+", help="company / CEO / ticker alias terms")
    ap.add_argument("--thesis", default="", help="Jordi-thesis terms it touches")
    ap.add_argument("--k", type=int, default=5)
    ap.add_argument("--home", default=os.environ.get("JORDI_HOME", DEFAULT_JORDI_HOME))
    args = ap.parse_args()

    mod = load_search_module(args.home)
    bm = mod.BM25(mod.load())
    direct_q = " ".join(args.company)

    print(f"# Jordi Brain — macro / AI thesis-fit evidence")
    print(f"corpus: {len(bm.docs)} chunks @ {args.home}")
    print(f"direct query: {direct_q!r}")
    if args.thesis:
        print(f"thesis query: {args.thesis!r}")

    wide = bm.search(direct_q, k=max(args.k * 4, 20), per_doc=2)
    jor_direct, news_direct = split_by_source(wide)

    emit("DIRECT MENTIONS — JORDI (what he said on the channel)", jor_direct[:args.k],
         empty="(Jordi does not mention this company directly in the transcript corpus — reason from thesis fit)")
    emit("NEWS MENTIONS (third-party coverage in the corpus)", news_direct[:args.k],
         empty="(no news item in the corpus mentions this — run `python3 work/fetch_news.py` to refresh)")
    if args.thesis:
        emit("THESIS FIT (Jordi's macro / AI framework)", bm.search(args.thesis, k=args.k, per_doc=1))
    emit("TAILWIND LENS (Jordi's constructive themes — who wins)",
         bm.search(TAILWIND_Q, k=4, per_doc=1))
    emit("SKEPTICISM / CREATIVE-DESTRUCTION LENS (what gets disrupted)",
         bm.search(SKEPTICISM_Q, k=3, per_doc=1))

    jor_top = jor_direct[0][0] if jor_direct else 0.0
    news_top = news_direct[0][0] if news_direct else 0.0
    print(f"\n## COVERAGE SIGNAL")
    print(f"jordi_direct_score={jor_top:.2f}  "
          f"({'Jordi discusses it' if jor_top >= 12 else 'thin / tangential — lean on thesis fit and say so' if jor_top > 0 else 'Jordi never mentions it — reason from thesis fit only'})")
    print(f"news_score={news_top:.2f}  "
          f"({'news coverage on record' if news_top >= 12 else 'only weak/indirect news references' if news_top > 0 else 'no news item on record (corpus may be stale — run work/fetch_news.py)'})")
    print("note: Jordi is a macro investor/commentator, not a company. Judge constructive-vs-cautious")
    print("      by how the name sits in his AI-capex / scarcity / creative-destruction framework,")
    print("      not merely by whether he named it.")


if __name__ == "__main__":
    main()
