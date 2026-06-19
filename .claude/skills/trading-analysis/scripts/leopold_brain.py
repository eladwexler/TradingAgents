#!/usr/bin/env python3
"""Leopold Brain bridge for the trading-analysis skill.

Queries the "Leopold brain" — a BM25 index over Leopold Aschenbrenner's own words
(the *Situational Awareness: The Decade Ahead* essay + his long-form interviews,
built in the companion `leopold-brain` project) — and returns the passages a reader
needs to judge whether a company sits **with or against the Situational Awareness
thesis**: AGI by ~2027 via straight-line compute scaling, the intelligence explosion,
the trillion-dollar cluster, *power/electricity as the binding constraint*, chips/fabs,
locking down the labs, and the US-China superintelligence race. Claude synthesizes the
actual verdict from these passages — does Leopold's worldview make this a beneficiary
(tailwind) of the build-out or an orthogonal / disrupted name (headwind)?

Runs a battery of searches in one process (index loaded once):
  - direct mentions   (company / CEO / product aliases — you pass these)
  - thesis fit        (the Situational Awareness theses it touches — you pass these)
  - beneficiary lens  (fixed: who profits / what the binding constraints are)
  - skepticism lens   (fixed: bubble, overbuild, commoditization, what could go wrong)

Usage (from the TradingAgents repo root):
  python3 .claude/skills/trading-analysis/scripts/leopold_brain.py \
      "Vistra Constellation nuclear utility electricity power" \
      --thesis "power electricity buildout gigawatt datacenter energy constraint" \
      --k 5

Env:
  LEOPOLD_HOME  path to the leopold-brain project (default: /home/ewexler/projects/leopold-brain)
"""
import argparse, importlib.util, os, sys

DEFAULT_LEOPOLD_HOME = "/home/ewexler/projects/leopold-brain"
# what/who the build-out enriches, and the constraints that gate it (compute, power, chips)
BENEFICIARY_Q = ("trillion dollar cluster power electricity natural gas gigawatt chips fabs "
                 "HBM semiconductors capex buildout Nvidia revenue who profits demand")
# where Leopold is skeptical / what breaks the trade
SKEPTICISM_Q = ("bubble overvalued overbuild commoditized margins competition export controls "
                "bottleneck risk wall scaling stalls what could go wrong")


def load_search_module(home):
    path = os.path.join(home, "index", "search.py")
    if not os.path.exists(path):
        sys.exit(f"[leopold_brain] search module not found at {path}\n"
                 f"Set LEOPOLD_HOME or build the index (python3 index/build_index.py in the leopold-brain project).")
    spec = importlib.util.spec_from_file_location("leopold_search", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    if not os.path.exists(mod.CHUNKS):
        sys.exit(f"[leopold_brain] index not built: {mod.CHUNKS} missing. "
                 f"Run `python3 index/build_index.py` in {home}.")
    return mod


def src_tag(d):
    """Label a hit by provenance: the canonical essay vs a spoken interview."""
    s = d.get("source", "essay")
    return "ESSAY" if s == "essay" else f"INTERVIEW ({d.get('channel','')[:24]})"


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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("company", nargs="+", help="company / CEO / product alias terms")
    ap.add_argument("--thesis", default="", help="Situational-Awareness-thesis terms it touches")
    ap.add_argument("--k", type=int, default=5)
    ap.add_argument("--home", default=os.environ.get("LEOPOLD_HOME", DEFAULT_LEOPOLD_HOME))
    args = ap.parse_args()

    mod = load_search_module(args.home)
    bm = mod.BM25(mod.load())
    direct_q = " ".join(args.company)

    print(f"# Leopold Brain — Situational-Awareness thesis-fit evidence")
    print(f"corpus: {len(bm.docs)} chunks @ {args.home}")
    print(f"direct query: {direct_q!r}")
    if args.thesis:
        print(f"thesis query: {args.thesis!r}")

    direct = bm.search(direct_q, k=max(args.k, 5), per_doc=2)
    emit("DIRECT MENTIONS — does Leopold name it?", direct[:args.k],
         empty="(Leopold does not name this company directly in the corpus — reason from thesis fit)")
    if args.thesis:
        emit("THESIS FIT (Situational Awareness build-out)", bm.search(args.thesis, k=args.k, per_doc=1))
    emit("BENEFICIARY / BOTTLENECK LENS (who profits, what gates the build-out)",
         bm.search(BENEFICIARY_Q, k=4, per_doc=1))
    emit("SKEPTICISM / WHAT-BREAKS-THE-TRADE LENS", bm.search(SKEPTICISM_Q, k=3, per_doc=1))

    # coverage signal: does he name it, and does the thesis lane light up at all
    direct_top = direct[0][0] if direct else 0.0
    print(f"\n## COVERAGE SIGNAL")
    print(f"leopold_direct_score={direct_top:.2f}  "
          f"({'Leopold names/discusses it' if direct_top >= 12 else 'thin / tangential — lean on thesis fit and say so' if direct_top > 0 else 'Leopold never names it — reason from thesis fit only'})")
    print("note: Leopold is an essayist/investor, not a company — there is no 'announcements' lane.")
    print("      A name absent from the corpus is normal; judge it by how squarely it sits in the")
    print("      compute / power / chips / labs build-out, not by whether he happened to mention it.")


if __name__ == "__main__":
    main()
