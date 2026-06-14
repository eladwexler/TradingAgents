#!/usr/bin/env python3
"""Jensen Brain bridge for the trading-analysis skill.

Queries the "Jensen brain" — a BM25 index over 100+ Jensen Huang interview/keynote
transcripts (built in the companion `jensen` project) — and returns the passages a
reader needs to judge whether **Jensen Huang / NVIDIA would strategically back** a
company. Claude synthesizes the actual verdict from these passages.

Runs a battery of searches in one process (index loaded once):
  - direct mentions  (company / CEO / product aliases — you pass these)
  - sector / thesis  (the NVIDIA theses the company touches — you pass these)
  - competition      (does it build rival silicon / a competing stack?)
  - philosophy       (fixed: how Jensen talks about partnering / backing companies)

Usage (from the TradingAgents repo root):
  python3 .claude/skills/trading-analysis/scripts/jensen_brain.py \
      "Tesla Elon Musk autonomous robotaxi Optimus Dojo" \
      --sector "autonomous vehicles physical AI robotics humanoid" \
      --k 5

Env:
  JENSEN_HOME  path to the jensen project (default: /home/ewexler/projects/jensen-brain)
"""
import argparse, importlib.util, os, sys

DEFAULT_JENSEN_HOME = "/home/ewexler/projects/jensen-brain"
PHILOSOPHY_Q = "we invest partner ecosystem startups we back bet on companies acquire build with"
COMPETITION_Q = "custom silicon ASIC build own chip competitor alternative rival GPU software stack"


def load_search_module(home):
    path = os.path.join(home, "index", "search.py")
    if not os.path.exists(path):
        sys.exit(f"[jensen_brain] search module not found at {path}\n"
                 f"Set JENSEN_HOME or build the index (python3 index/build_index.py in the jensen project).")
    spec = importlib.util.spec_from_file_location("jensen_search", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    if not os.path.exists(mod.CHUNKS):
        sys.exit(f"[jensen_brain] index not built: {mod.CHUNKS} missing. "
                 f"Run `python3 index/build_index.py` in {home}.")
    return mod


def emit(title, hits):
    print(f"\n## {title}  ({len(hits)} passages)")
    if not hits:
        print("(no matching passages — Jensen's corpus may not cover this directly)")
        return
    for rank, (score, d) in enumerate(hits, 1):
        snippet = " ".join(d["text"].split())
        if len(snippet) > 900:
            snippet = snippet[:900] + " …"
        print(f"\n[{rank}] score={score:.2f}  {d.get('date','?')}  {d.get('title','')[:80]}")
        print(f"    {d.get('url','')}")
        print(f"    {snippet}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("company", nargs="+", help="company / CEO / product alias terms")
    ap.add_argument("--sector", default="", help="sector / NVIDIA-thesis terms")
    ap.add_argument("--k", type=int, default=5)
    ap.add_argument("--home", default=os.environ.get("JENSEN_HOME", DEFAULT_JENSEN_HOME))
    args = ap.parse_args()

    mod = load_search_module(args.home)
    bm = mod.BM25(mod.load())
    direct_q = " ".join(args.company)

    print(f"# Jensen Brain — strategic-fit evidence")
    print(f"corpus: {len(bm.docs)} chunks @ {args.home}")
    print(f"direct query: {direct_q!r}")
    if args.sector:
        print(f"sector query: {args.sector!r}")

    direct = bm.search(direct_q, k=args.k, per_doc=1)
    emit("DIRECT MENTIONS", direct)
    if args.sector:
        emit("SECTOR / THESIS FIT", bm.search(args.sector, k=args.k, per_doc=1))
    emit("COMPETITION / SUBSTITUTION RISK", bm.search(COMPETITION_Q, k=3, per_doc=1))
    emit("JENSEN PARTNERSHIP / INVESTMENT PHILOSOPHY", bm.search(PHILOSOPHY_Q, k=3, per_doc=1))

    # coverage signal: top direct-hit score tells whether the company is really discussed
    top = direct[0][0] if direct else 0.0
    print(f"\n## COVERAGE SIGNAL")
    print(f"top_direct_score={top:.2f}  "
          f"({'well covered' if top >= 12 else 'thin / tangential — lean on sector fit and say so' if top > 0 else 'not mentioned — reason from sector fit only'})")


if __name__ == "__main__":
    main()
