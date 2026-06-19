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


def src_tag(d):
    """Label a hit by provenance: what Jensen *said* vs what NVIDIA *did/announced*."""
    s = d.get("source", "jensen")
    return "JENSEN-SAID" if s == "jensen" else f"NVDA-ANNOUNCED ({s})"


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
    """(jensen_hits, nvda_hits) — what he said vs what NVIDIA published."""
    jen = [(s, d) for s, d in hits if d.get("source", "jensen") == "jensen"]
    nv = [(s, d) for s, d in hits if d.get("source", "jensen") != "jensen"]
    return jen, nv


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

    # Pull a wide direct sweep, then separate Jensen's words from NVIDIA's actions so a
    # reader can answer both "did NVIDIA do anything here" and "did *he* mention it".
    wide = bm.search(direct_q, k=max(args.k * 4, 20), per_doc=2)
    jen_direct, nvda_direct = split_by_source(wide)

    emit("DIRECT MENTIONS — JENSEN (what he said)", jen_direct[:args.k],
         empty="(Jensen does not mention this company directly in the transcript corpus)")
    emit("NVIDIA ACTIONS / ANNOUNCEMENTS (what NVIDIA published)", nvda_direct[:args.k],
         empty="(no NVIDIA press/blog item mentions this — run `python3 work/fetch_nvidia.py` to refresh)")
    if args.sector:
        emit("SECTOR / THESIS FIT", bm.search(args.sector, k=args.k, per_doc=1))
    emit("COMPETITION / SUBSTITUTION RISK", bm.search(COMPETITION_Q, k=3, per_doc=1))
    emit("JENSEN PARTNERSHIP / INVESTMENT PHILOSOPHY", bm.search(PHILOSOPHY_Q, k=3, per_doc=1))

    # coverage signal: separate "Jensen mentioned it" from "NVIDIA acted on it"
    jen_top = jen_direct[0][0] if jen_direct else 0.0
    nvda_top = nvda_direct[0][0] if nvda_direct else 0.0
    print(f"\n## COVERAGE SIGNAL")
    print(f"jensen_top_score={jen_top:.2f}  "
          f"({'Jensen discusses it' if jen_top >= 12 else 'thin / tangential — lean on sector fit and say so' if jen_top > 0 else 'Jensen never mentions it — reason from sector fit only'})")
    print(f"nvda_action_score={nvda_top:.2f}  "
          f"({'NVIDIA has published action(s) involving it' if nvda_top >= 12 else 'only weak/indirect NVIDIA references' if nvda_top > 0 else 'no NVIDIA announcement on record (corpus may be stale — refresh feeds)'})")


if __name__ == "__main__":
    main()
