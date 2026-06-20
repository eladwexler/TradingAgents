#!/usr/bin/env python3
"""Conviction model — turn a verdict into an actionable, 12-month-hold BUY tier.

WHY THIS EXISTS (grounded in eval/):
  * Beating SPY is the base rate in this universe (~58-70% of names did), so a raw
    P(beat SPY)≈0.55 carries no edge. Conviction is anchored to a HIGHER bar.
  * Momentum/technicals had NEGATIVE 12-month predictive power here, so they get
    ZERO weight in the hold decision (they belong to entry-timing only).
  * Dispersion was -90%..+4500%; avoiding blow-ups matters more than picking the
    top. So fundamentals/valuation/survivor act as a HARD VETO → AVOID, regardless
    of how strong the narrative ("brains") is.
  * The AI-cycle risk gauge leads on risk but can't time, so it scales POSITION
    SIZE, never in/out.

Output: a HIGH / MEDIUM / LOW / AVOID tier, a 0-100 score, the veto reasons, and a
suggested position size (% of a full unit) scaled by the current cycle risk.

Deterministic, stdlib-only. Reads metrics.json + the decision log + decision files.
Run:  python3 scripts/conviction.py            # ranked table for all tracked names
      python3 scripts/conviction.py NVDA MRVL  # just these
"""
from __future__ import annotations

import glob
import json
import os
import re
import sys

MEM = os.environ.get("TRADINGAGENTS_MEMORY_LOG_PATH",
                     os.path.expanduser("~/.tradingagents/memory/trading_memory.md"))
MEMDIR = os.path.dirname(MEM)
METRICS = os.path.join(MEMDIR, "metrics.json")
CYCLE_CSV = os.path.join(MEMDIR, "ai_cycle_history.csv")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ANALYZED = os.path.join(ROOT, "analyzed-stocks")
OUT = os.path.join(MEMDIR, "conviction.json")

# --- survivor / casualty map (from the ai-cycle-watch baskets) ---------------
# Survivors get a small bonus; casualties are HARD-VETOED for a 12m hold because
# they are the leveraged-capex / cash-burn profile that produced the deep losers.
SURVIVORS = {"NVDA", "AVGO", "ANET", "COHR", "MSFT", "GOOGL", "AMZN", "META", "MU",
             "VRT", "ETN", "GEV", "CEG", "PWR", "GLW", "CRDO", "MRVL", "QCOM",
             "ARM", "DELL", "PANW", "NOW"}
# leveraged "neocloud" / SPV-financed data-center operators the skill flags as casualties
CASUALTIES = {"CRWV", "NBIS", "APLD", "IREN", "CIFR", "CORZ", "SLNH"}

TIER_SIZE = {"HIGH": 1.0, "MEDIUM": 0.5, "LOW": 0.25, "AVOID": 0.0}


def cycle_risk() -> float:
    """Latest AI-cycle Risk_Score (0-100); default 50 if unavailable."""
    try:
        lines = open(CYCLE_CSV, encoding="utf-8").read().strip().splitlines()
        hdr = lines[0].split(",")
        i = hdr.index("Risk_Score")
        return float(lines[-1].split(",")[i])
    except Exception:
        return 50.0


def cycle_size_factor(risk: float) -> float:
    """Risk 50 → 1.0, 68 → ~0.78, 90 → ~0.52. Sizing overlay (never in/out)."""
    return max(0.4, min(1.0, 1.0 - max(0.0, risk - 50.0) / 100.0 * 1.2))


def latest_verdict(ticker: str) -> dict:
    """rating + P(beat) from the decision log; combined verdict from the latest file."""
    v = {"rating": None, "pbeat": None, "combined": None}
    # rating + P from the most recent memory-log entry for this ticker
    try:
        for ln in open(MEM, encoding="utf-8"):
            if not ln.startswith("[") or f"| {ticker} |" not in ln:
                continue
            parts = [p.strip() for p in ln.strip("[]\n").split("|")]
            if len(parts) >= 3:
                v["rating"] = parts[2]
            mP = re.search(r"P=([0-9.]+)", ln)
            if mP:
                v["pbeat"] = float(mP.group(1))
    except FileNotFoundError:
        pass
    # combined verdict from the latest decision file
    files = sorted(glob.glob(os.path.join(ANALYZED, ticker, "*_decision.md")))
    if files:
        md = open(files[-1], encoding="utf-8").read()
        m = re.search(r"Combined Strategic Verdict:\s*\**\s*([A-Z ]+?)\**\s*[(\-—.\n]", md)
        if m:
            v["combined"] = m.group(1).strip().upper()
        if v["pbeat"] is None:  # fall back to the 24mo forecast row
            mp = re.search(r"24\s*mo.*?\|\s*([01]?\.\d+)\s*\|?\s*$", md, re.M)
            if mp:
                v["pbeat"] = float(mp.group(1))
    return v


def score(ticker: str, m: dict, v: dict, risk: float) -> dict:
    """Compute the conviction tier for one name. Pure function of its inputs."""
    peg = m.get("peg")
    fpe = m.get("forward_pe")
    fcfy = m.get("fcf_yield")
    pm = m.get("profit_margin")
    om = m.get("operating_margin")
    revg = m.get("rev_growth")
    mcap = m.get("market_cap")
    up = m.get("implied_upside")
    comb = (v.get("combined") or "").upper()
    pbeat = v.get("pbeat")

    # Rule-of-40 is noise when growth is on a tiny/distorted base (rev_growth > 200%):
    # ignore it for scoring rather than reward a 6000%+ artifact.
    r40 = m.get("rule_of_40")
    if r40 is not None and (revg is None or revg > 2.0 or r40 > 150):
        r40 = None
    micro = mcap is not None and mcap < 2e9   # < $2B = speculative for a 12m hold

    # ---- HARD VETOES → AVOID (narrative cannot override these) ----
    vetoes = []
    burning = (pm is not None and pm < 0) and \
              ((fcfy is not None and fcfy < 0) or (fcfy is None and om is not None and om < 0)
               or (fcfy is None and om is None))
    if burning:
        vetoes.append("unprofitable cash-burner (survival risk)")
    # valuation veto is PEG-aware: only "extreme" when growth doesn't justify it.
    if (peg is not None and peg > 3.0) or (peg is None and fpe is not None and fpe > 70):
        vetoes.append("extreme valuation (growth doesn't justify the multiple)")
    if comb in ("EXPOSED", "OFFSIDE"):
        vetoes.append(f"secular thesis offside ({comb})")
    if ticker in CASUALTIES:
        vetoes.append("cycle-watch casualty (leveraged-capex / SPV neocloud)")

    reasons = []
    if vetoes:
        tier, sc = "AVOID", 0
        reasons = vetoes
    else:
        sc = 50
        # growth / durability
        if r40 is not None:
            if r40 >= 60: sc += 15; reasons.append(f"Rule-of-40 {r40:.0f} (elite)")
            elif r40 >= 40: sc += 10; reasons.append(f"Rule-of-40 {r40:.0f} (strong)")
            elif r40 >= 25: sc += 5
            elif r40 < 0: sc -= 10; reasons.append(f"Rule-of-40 {r40:.0f} (weak)")
        # cash generation
        if fcfy is not None:
            if fcfy >= 0.04: sc += 10; reasons.append(f"FCF yield {fcfy*100:.1f}%")
            elif fcfy > 0: sc += 5
            else: sc -= 5
        # valuation sanity (the risk control)
        if peg is not None:
            if peg <= 1.0: sc += 15; reasons.append(f"PEG {peg:.2f} (cheap vs growth)")
            elif peg <= 1.5: sc += 10; reasons.append(f"PEG {peg:.2f}")
            elif peg > 2.5: sc -= 5; reasons.append(f"PEG {peg:.2f} (rich)")
        elif fpe is not None:
            if fpe <= 25: sc += 5
            elif fpe > 45: sc -= 5; reasons.append(f"fwd P/E {fpe:.0f} (rich)")
        # secular gate
        if comb == "CONVICTION ALIGNED": sc += 10; reasons.append("4-brain conviction")
        elif comb == "ALIGNED": sc += 5; reasons.append("brains aligned")
        # basket-relative edge (anchored at 0.55, not 0.50)
        if pbeat is not None:
            sc += max(-10, min(10, round((pbeat - 0.55) * 100)))
            if pbeat >= 0.60: reasons.append(f"P(beat) {pbeat:.2f}")
        # analyst upside (small weight — weak signal)
        if up is not None:
            if up >= 0.25: sc += 5
            elif up < 0: sc -= 5; reasons.append(f"below analyst target ({up*100:.0f}%)")
        if ticker in SURVIVORS:
            sc += 5; reasons.append("designated survivor")
        sc = max(0, min(100, sc))

        gate_ok = comb in ("ALIGNED", "CONVICTION ALIGNED")
        pbeat_ok = pbeat is not None and pbeat >= 0.58
        if sc >= 70 and gate_ok and pbeat_ok:
            tier = "HIGH"
        elif sc >= 52:
            tier = "MEDIUM"
        else:
            tier = "LOW"
        # microcaps can't carry HIGH/MEDIUM conviction for a 12m hold — they are the
        # idiosyncratic dispersion tail (eval: -90%..+4500%); cap at LOW (small size).
        if micro and tier in ("HIGH", "MEDIUM"):
            tier = "LOW"
            reasons.insert(0, "microcap (<$2B) — speculative, size capped")

    size = round(TIER_SIZE[tier] * cycle_size_factor(risk) * 100)
    return {"ticker": ticker, "tier": tier, "score": sc, "size_pct": size,
            "vetoes": vetoes, "reasons": reasons,
            "rating": v.get("rating"), "pbeat": pbeat, "combined": comb or None}


def run(tickers=None) -> dict:
    metrics = json.load(open(METRICS, encoding="utf-8")).get("metrics", {}) \
        if os.path.exists(METRICS) else {}
    risk = cycle_risk()
    names = [t.upper() for t in tickers] if tickers else sorted(
        d for d in os.listdir(ANALYZED) if os.path.isdir(os.path.join(ANALYZED, d)))
    rows = []
    for t in names:
        m = metrics.get(t, {})
        if not m:
            continue
        rows.append(score(t, m, latest_verdict(t), risk))
    order = {"HIGH": 0, "MEDIUM": 1, "LOW": 2, "AVOID": 3}
    rows.sort(key=lambda r: (order[r["tier"]], -r["score"]))
    return {"cycle_risk": risk, "size_factor": round(cycle_size_factor(risk), 2),
            "rows": rows}


def main() -> int:
    res = run(sys.argv[1:] or None)
    json.dump(res, open(OUT, "w", encoding="utf-8"), indent=2)
    risk, sf = res["cycle_risk"], res["size_factor"]
    print(f"AI-cycle risk {risk:.0f}/100 → size factor {sf:.2f} "
          f"(every suggested size is scaled by this)\n")
    print(f"{'Ticker':<7}{'Tier':<8}{'Score':>6}{'Size':>6}  Why")
    print("-" * 78)
    for r in res["rows"]:
        why = "; ".join((r["vetoes"] or r["reasons"])[:3]) or "—"
        print(f"{r['ticker']:<7}{r['tier']:<8}{r['score']:>6}{r['size_pct']:>5}%  {why}")
    n = {}
    for r in res["rows"]:
        n[r["tier"]] = n.get(r["tier"], 0) + 1
    print(f"\n{n.get('HIGH',0)} HIGH · {n.get('MEDIUM',0)} MEDIUM · "
          f"{n.get('LOW',0)} LOW · {n.get('AVOID',0)} AVOID   → {OUT}")
    print("Size = % of a full position unit (tier × cycle factor). Not financial advice.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
