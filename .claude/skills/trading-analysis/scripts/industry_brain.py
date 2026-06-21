#!/usr/bin/env python3
"""Industry Brain bridge for the trading-analysis skill.

Queries the "Industry Brain" — a BM25 index over the ai-news primary-source corpus
(SemiAnalysis, Fabricated Knowledge, Epoch AI, Next Platform, Data Center Dynamics,
Semiconductor Engineering, EE Times, …) accumulated daily in the companion `ai-news`
project — and returns the passages a reader needs to judge whether the *hard industry
data* sits with or against a name's demand/supply/competitive position.

This is the ONLY hard-data lens in the pipeline. Every other brain is a personality or
crowd corpus (Jensen/Leopold/Jordi/Gavin transcripts, X sentiment); the Industry Brain
is grounded in what the primary semiconductor/datacenter/compute literature actually
reported — CoWoS/HBM allocation, hyperscaler capex guidance, foundry yields, power
constraints, oversupply/glut, share shifts. Claude synthesizes the verdict — is the
industry record a demand *tailwind* for the name, a *headwind* (oversupply / digestion /
displacement), or mixed?

Runs a battery of searches in one process (index loaded once):
  - direct mentions   (company / products / ticker aliases — you pass these)
  - pillar/theme fit  (the pillars/themes it touches — you pass these via --sector)
  - tailwind lens     (fixed: accelerating demand, supply tightness, capex inflows)
  - headwind lens     (fixed: oversupply, glut, capex digestion, displacement, share loss)

Usage (from the TradingAgents repo root):
  python3 .claude/skills/trading-analysis/scripts/industry_brain.py \
      "Nvidia NVDA Blackwell Rubin GPU CUDA" \
      --sector "silicon_hardware accelerator HBM CoWoS inference training datacenter capex" \
      --k 5

Env:
  AINEWS_HOME  path to the ai-news project (default: /home/ewexler/projects/ai-news)
"""
import argparse, importlib.util, os, sys

DEFAULT_AINEWS_HOME = "/home/ewexler/projects/ai-news"
# accelerating demand / supply tightness / capex flowing toward a name's products
TAILWIND_Q = ("demand strong accelerating sold out tight supply shortage backlog allocation "
              "capex increase ramp record bookings constraint outstrips supply leading edge win")
# oversupply / glut / digestion / displacement — what turns a name into a casualty
HEADWIND_Q = ("oversupply glut digestion capex cut slowdown inventory correction price decline "
              "displaced commoditized share loss delay cancellation lagging edge permanent glut weakness")


def load_search_module(home):
    path = os.path.join(home, "index", "search.py")
    if not os.path.exists(path):
        sys.exit(f"[industry_brain] search module not found at {path}\n"
                 f"Set AINEWS_HOME or build the index (python3 index/build_index.py in the ai-news project).")
    spec = importlib.util.spec_from_file_location("industry_search", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    if not os.path.exists(mod.CHUNKS):
        sys.exit(f"[industry_brain] index not built: {mod.CHUNKS} missing. "
                 f"Run `python3 index/build_index.py` in {home} (or let ensure_news.py do it).")
    return mod


def emit(title, hits, empty="(no matching passages — corpus may not cover this directly)"):
    print(f"\n## {title}  ({len(hits)} passages)")
    if not hits:
        print(empty)
        return
    for rank, (score, d) in enumerate(hits, 1):
        snippet = " ".join(d["text"].split())
        if len(snippet) > 900:
            snippet = snippet[:900] + " …"
        src = d.get("source", "") or "?"
        pillars = ",".join(d.get("pillars", [])) or "—"
        print(f"\n[{rank}] score={score:.2f}  [{src}]  {d.get('date','?')}  pillars:{pillars}")
        print(f"    {d.get('title','')[:90]}")
        print(f"    {d.get('url','')}")
        print(f"    {snippet}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("company", nargs="+", help="company / products / ticker alias terms")
    ap.add_argument("--sector", default="", help="pillar/theme terms it touches")
    ap.add_argument("--k", type=int, default=5)
    ap.add_argument("--home", default=os.environ.get("AINEWS_HOME", DEFAULT_AINEWS_HOME))
    args = ap.parse_args()

    mod = load_search_module(args.home)
    bm = mod.BM25(mod.load())
    direct_q = " ".join(args.company)

    print(f"# Industry Brain — primary-source demand/supply evidence")
    print(f"corpus: {len(bm.docs)} chunks @ {args.home}")
    print(f"direct query: {direct_q!r}")
    if args.sector:
        print(f"sector/theme query: {args.sector!r}")

    direct = bm.search(direct_q, k=args.k, per_doc=2)
    emit("DIRECT MENTIONS (the name in the primary-source literature)", direct,
         empty="(the corpus does not cover this name directly — reason from sector/theme fit and say so)")
    if args.sector:
        emit("SECTOR / THEME FIT (its pillars in the industry record)",
             bm.search(args.sector, k=args.k, per_doc=1))
    emit("TAILWIND LENS (accelerating demand / supply tightness / capex inflows)",
         bm.search(TAILWIND_Q, k=4, per_doc=1))
    emit("HEADWIND LENS (oversupply / digestion / displacement / share loss)",
         bm.search(HEADWIND_Q, k=4, per_doc=1))

    direct_top = direct[0][0] if direct else 0.0
    print(f"\n## COVERAGE SIGNAL")
    print(f"industry_direct_score={direct_top:.2f}  "
          f"({'covered in the primary-source literature' if direct_top >= 12 else 'thin / tangential — lean on sector fit and say so' if direct_top > 0 else 'not named in the corpus — reason from sector/theme fit only'})")
    print("note: the Industry Brain is hard-data, not opinion. Judge tailwind-vs-headwind by what the")
    print("      primary sources report about demand, supply, capex and competition for this name's")
    print("      products — it is the sanity check on the four personality brains, not a fifth opinion.")


if __name__ == "__main__":
    main()
