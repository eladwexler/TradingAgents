#!/usr/bin/env python3
"""Decision facts per name — the economics that matter for a ≥12-month hold.

Deliberately NOT a score. An earlier version produced a 0-100 "conviction" number
and HIGH/MEDIUM/AVOID tiers from hand-picked weights and hardcoded name lists —
false precision over an unvalidated heuristic. This instead surfaces the *raw,
decision-relevant facts* per name, plus the one read that is a direct, transparent
function of real economics: the PATH TO PROFITABILITY. You judge.

Per name it reports:
  * path to profit — Profitable / Scaling (credible path) / Burning (no path)
  * gross & operating margin, FCF yield, revenue growth   (the underlying numbers)
  * valuation read — from PEG, else EV/Sales, else forward P/E
  * secular fit (Combined Strategic Verdict) and P(beat) from the latest analysis

No weights, no tiers, no hardcoded survivor/casualty lists. stdlib only.
Run:  python3 scripts/conviction.py            # facts for all tracked names
      python3 scripts/conviction.py NVDA NBIS  # just these
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
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ANALYZED = os.path.join(ROOT, "analyzed-stocks")
OUT = os.path.join(MEMDIR, "conviction.json")

# Standard, transparent thresholds (industry-conventional, not tuned to an outcome).
STRONG_GROSS, OK_GROSS = 0.50, 0.35     # unit economics: losses are about scaling, not a broken model
FAST_GROWTH = 0.25                       # growth to grow into the cost base


def latest_verdict(ticker: str) -> dict:
    """rating + P(beat) from the decision log; combined verdict from the latest file."""
    v = {"rating": None, "pbeat": None, "combined": None}
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
    files = sorted(glob.glob(os.path.join(ANALYZED, ticker, "*_decision.md")))
    if files:
        md = open(files[-1], encoding="utf-8").read()
        m = re.search(r"Combined Strategic Verdict:\s*\**\s*([A-Z ]+?)\**\s*[(\-—.\n]", md)
        if m:
            v["combined"] = m.group(1).strip().upper()
    return v


def path_to_profit(gm, om, fcfy, revg, fpe):
    """Direct, transparent read of the economics — no weights.

    Profitable        : generates cash / positive operating margin.
    Scaling (path)    : burning, but healthy unit economics + (fast growth or the market
                        already prices positive forward earnings) → losses close as it scales.
    Burning (no path) : burning with weak unit economics or stalling growth.
    """
    profitable = (fcfy is not None and fcfy > 0) or (om is not None and om > 0)
    if profitable:
        return "Profitable", True
    burning = (fcfy is not None and fcfy < 0) or (om is not None and om < 0)
    if not burning:
        return "—", None
    strong_unit = gm is not None and gm >= STRONG_GROSS
    ok_unit = gm is not None and gm >= OK_GROSS
    growing = revg is not None and revg >= FAST_GROWTH
    fwd_profit = fpe is not None and fpe > 0
    has_path = (strong_unit and (growing or fwd_profit)) or (ok_unit and growing and fwd_profit)
    return ("Scaling (path)" if has_path else "Burning (no path)"), has_path


def valuation_read(peg, evs, fpe, revg):
    """One transparent label from the best available multiple (PEG > EV/Sales > fwd P/E).

    PEG is skipped when growth is distorted (rev_growth > 200%) — a near-zero PEG off a
    tiny base reads 'cheap' while the name trades at an extreme sales multiple.
    """
    if peg is not None and (revg is None or revg <= 2.0):
        return ("cheap" if peg <= 1 else "fair" if peg <= 2 else
                "rich" if peg <= 3 else "extreme"), f"PEG {peg:.2f}"
    if evs is not None:
        return ("extreme" if evs > 40 else "rich" if evs > 20 else "fair"), f"{evs:.0f}x sales"
    if fpe is not None and fpe > 0:
        return ("fair" if fpe <= 25 else "rich" if fpe <= 45 else "extreme"), f"fwd P/E {fpe:.0f}"
    return "—", "—"


def facts(ticker: str, m: dict, v: dict) -> dict:
    gm, om = m.get("gross_margin"), m.get("operating_margin")
    fcfy, revg = m.get("fcf_yield"), m.get("rev_growth")
    peg, fpe, evs = m.get("peg"), m.get("forward_pe"), m.get("ev_sales")
    r40 = m.get("rule_of_40")
    if r40 is not None and (revg is None or revg > 2.0 or r40 > 150):
        r40 = None  # distorted by a tiny/huge-growth base — drop rather than mislead
    path, _ = path_to_profit(gm, om, fcfy, revg, fpe)
    val, val_basis = valuation_read(peg, evs, fpe, revg)
    return {
        "ticker": ticker, "path": path,
        "gross_margin": gm, "operating_margin": om, "fcf_yield": fcfy, "rev_growth": revg,
        "rule_of_40": r40, "ev_sales": evs, "peg": peg, "forward_pe": fpe,
        "valuation": val, "valuation_basis": val_basis,
        "implied_upside": m.get("implied_upside"), "market_cap": m.get("market_cap"),
        "combined": v.get("combined"), "pbeat": v.get("pbeat"), "rating": v.get("rating"),
    }


# Display order for the path column (Profitable first … no-path last).
PATH_ORDER = {"Profitable": 0, "Scaling (path)": 1, "Burning (no path)": 2, "—": 3}


def run(tickers=None) -> dict:
    metrics = json.load(open(METRICS, encoding="utf-8")).get("metrics", {}) \
        if os.path.exists(METRICS) else {}
    names = [t.upper() for t in tickers] if tickers else sorted(
        d for d in os.listdir(ANALYZED) if os.path.isdir(os.path.join(ANALYZED, d)))
    rows = [facts(t, metrics.get(t, {}), latest_verdict(t)) for t in names if metrics.get(t)]
    rows.sort(key=lambda r: (PATH_ORDER.get(r["path"], 3),
                             -(r["pbeat"] or 0)))
    return {"rows": rows}


def _pct(x):
    return "—" if x is None else f"{x*100:+.0f}%"


def main() -> int:
    res = run(sys.argv[1:] or None)
    json.dump(res, open(OUT, "w", encoding="utf-8"), indent=2)
    print("Decision facts — NOT a score. Path to profit + the economics behind it.\n")
    print(f"{'Ticker':<7}{'Path':<18}{'GM':>6}{'OpM':>6}{'FCFy':>7}{'RevG':>7}"
          f"{'Val':>9}{'Secular':>14}{'P':>6}")
    print("-" * 80)
    for r in res["rows"]:
        pb = f"{r['pbeat']:.2f}" if r["pbeat"] is not None else "—"
        sec = (r["combined"] or "—")[:13]
        val = r["valuation"] or "—"
        print(f"{r['ticker']:<7}{r['path']:<18}{_pct(r['gross_margin']):>6}"
              f"{_pct(r['operating_margin']):>6}{_pct(r['fcf_yield']):>7}{_pct(r['rev_growth']):>7}"
              f"{val:>9}{sec:>14}{pb:>6}")
    print(f"\n{len(res['rows'])} names → {OUT}")
    print("No weights, no tiers — read the facts and judge. Not financial advice.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
