#!/usr/bin/env python3
"""eval/ cycle-timing backtest — does the AI-cycle "risk score" actually lead?

The time-series companion to run_backtest.py (which is cross-sectional). It builds
a mechanical, point-in-time "cycle risk score" from the *measurable* subset of the
ai-cycle-watch canaries and tests whether a HIGH score anticipated DRAWDOWNS in the
equal-weight AI basket over 2021→present.

Honesty boundary — same as the cross-sectional eval:
  * Only the QUANTITATIVE canaries are testable here. The qualitative ones
    (capex-guidance tone, GPU lead times, financing circularity) and the narrative
    "brains" cannot be backfilled and are NOT in this score.
  * Every signal uses only trailing data; forward windows are out-of-sample.
  * Regime thresholds use a TRAILING rolling percentile (no peeking at the future
    distribution), so the score is not tuned to the answer.
  * 2021→2026 is ~one cycle with very few independent drawdowns — low statistical
    power. A good number here is suggestive, not proof.

Writes only to eval/results/. No imports from tradingagents/ or the skill scripts.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)

import data as D                       # noqa: E402
from universe import load_universe     # noqa: E402
from run_backtest import _load_config, _num, _pct  # noqa: E402

HIST_START = "2021-01-01"


def _series_frame(tickers, start, end, cache) -> pd.DataFrame:
    cols = {}
    for t in tickers:
        s = D.get_closes(t, start, end, cache)
        if s is not None and len(s) > 200:
            cols[t] = s
    if not cols:
        return pd.DataFrame()
    df = pd.DataFrame(cols).sort_index()
    # business-day grid, forward-fill short gaps only
    idx = pd.date_range(df.index.min(), df.index.max(), freq="B")
    return df.reindex(idx).ffill(limit=3)


def _roll_pct(s: pd.Series, window: int = 252, min_p: int = 120) -> pd.Series:
    """Trailing rolling percentile of the latest value (point-in-time, 0..1)."""
    def _last_rank(x):
        return (x <= x[-1]).mean()
    return s.rolling(window, min_periods=min_p).apply(_last_rank, raw=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default=os.path.join(HERE, "config.yaml"))
    ap.add_argument("--end", help="override end date (default config window.end)")
    args = ap.parse_args()
    cfg = _load_config(args.config)
    end = args.end or cfg["window"]["end"]
    cache = os.path.join(REPO_ROOT, cfg["cache_dir"])
    universe = load_universe(REPO_ROOT, cfg["universe"].get("exclude", []))

    print(f"Building basket from {len(universe)} names, {HIST_START} → {end} …")
    px = _series_frame(universe, HIST_START, end, cache)
    if px.empty:
        print("FATAL: no price data.")
        return 1
    print(f"  {px.shape[1]} names with usable history.")

    # ---- equal-weight basket (names enter as they get history; no backfill) ----
    rets = px.pct_change()
    basket_ret = rets.mean(axis=1, skipna=True)            # equal-weight daily return
    n_names = rets.notna().sum(axis=1)
    basket_ret = basket_ret.where(n_names >= 5)             # need >=5 names live
    basket = (1 + basket_ret.fillna(0)).cumprod()
    basket = basket.where(n_names >= 5)

    # ---- macro canaries ----
    tnx = D.get_closes("^TNX", HIST_START, end, cache)     # 10yr yield (x10)
    hyg = D.get_closes("HYG", HIST_START, end, cache)      # HY credit proxy
    tnx = tnx.reindex(px.index).ffill() if tnx is not None else None
    hyg = hyg.reindex(px.index).ffill() if hyg is not None else None

    # ---- canary components (higher = MORE risk), all trailing ----
    comp = {}
    comp["extension"] = basket / basket.rolling(200, min_periods=100).mean() - 1.0
    above200 = (px > px.rolling(200, min_periods=100).mean()).sum(axis=1) / n_names
    comp["breadth_risk"] = 1.0 - above200                  # weak breadth = risk
    comp["momentum_heat"] = basket.pct_change(126)         # overheated = reversal risk
    if tnx is not None:
        comp["rates"] = tnx                                # higher yield = risk
    if hyg is not None:
        comp["credit_stress"] = (hyg.rolling(126, min_periods=60).max() - hyg) \
            / hyg.rolling(126, min_periods=60).max()       # drawdown from 6m high

    # normalize each to trailing percentile, average → 0..100 risk score
    pcts = pd.DataFrame({k: _roll_pct(v) for k, v in comp.items()})
    risk = pcts.mean(axis=1, skipna=True) * 100.0
    risk = risk.dropna()

    # ---- forward outcomes on the basket (out-of-sample) ----
    out = {}
    for h in (63, 126):
        out[f"fwd_{h}"] = basket.shift(-h) / basket - 1.0
    fwd = pd.DataFrame(out)

    df = pd.concat([risk.rename("risk"), fwd, basket.rename("basket")], axis=1).dropna(
        subset=["risk", "fwd_63"])

    # ---- (1) does high risk predict low forward return? (Spearman) ----
    def _spear(a, b):
        m = a.notna() & b.notna()
        if m.sum() < 60:
            return None
        ra, rb = a[m].rank(), b[m].rank()
        if ra.std() == 0 or rb.std() == 0:
            return None
        return float(np.corrcoef(ra, rb)[0, 1])

    ic63 = _spear(df["risk"], df["fwd_63"])
    ic126 = _spear(df["risk"], df["fwd_126"]) if "fwd_126" in df else None

    # ---- (2) regime-conditional forward return (point-in-time regime) ----
    regime_pct = _roll_pct(risk, window=504, min_p=200)    # 2y trailing percentile
    df2 = pd.concat([df, regime_pct.rename("rp")], axis=1).dropna(subset=["rp"])
    red = df2[df2["rp"] >= 0.80]
    green = df2[df2["rp"] <= 0.50]
    regime = {
        "red_n": int(len(red)),
        "red_fwd63_mean": float(red["fwd_63"].mean()) if len(red) else None,
        "red_fwd63_hit_negative": float((red["fwd_63"] < 0).mean()) if len(red) else None,
        "green_n": int(len(green)),
        "green_fwd63_mean": float(green["fwd_63"].mean()) if len(green) else None,
        "all_fwd63_mean": float(df2["fwd_63"].mean()),
        "all_fwd63_hit_negative": float((df2["fwd_63"] < 0).mean()),
    }

    # ---- (3) timing strategy vs buy-and-hold (the practical test) ----
    pos = (regime_pct < 0.80).astype(float)                # risk-off when Red regime
    pos = pos.reindex(basket_ret.index).shift(1).fillna(0) # act NEXT day → no lookahead
    strat_ret = basket_ret.fillna(0) * pos
    strat = _stats(strat_ret)
    bh = _stats(basket_ret.fillna(0))

    result = {
        "generated": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "history": {"start": str(px.index.min().date()), "end": str(px.index.max().date()),
                    "names": int(px.shape[1]), "canaries": list(comp.keys())},
        "predictive_ic": {"risk_vs_fwd63": ic63, "risk_vs_fwd126": ic126,
                          "note": "negative = high risk preceded low forward return (good)"},
        "regime_conditional": regime,
        "timing_strategy": {"risk_managed": strat, "buy_and_hold": bh},
    }

    rdir = os.path.join(HERE, "results")
    os.makedirs(rdir, exist_ok=True)
    with open(os.path.join(rdir, "cycle_scorecard.json"), "w") as f:
        json.dump(result, f, indent=2)
    md = _render(result)
    with open(os.path.join(rdir, "cycle_scorecard.md"), "w") as f:
        f.write(md)
    print(f"\nWrote results/cycle_scorecard.{{md,json}}\n")
    print(md)
    return 0


def _stats(daily: pd.Series) -> dict:
    d = daily.dropna()
    if len(d) < 60:
        return {}
    eq = (1 + d).cumprod()
    yrs = len(d) / 252.0
    cagr = eq.iloc[-1] ** (1 / yrs) - 1 if eq.iloc[-1] > 0 else None
    vol = float(d.std() * np.sqrt(252))
    sharpe = float((d.mean() * 252) / (d.std() * np.sqrt(252))) if d.std() > 0 else None
    dd = float((eq / eq.cummax() - 1).min())
    return {"cagr": None if cagr is None else float(cagr), "vol": vol,
            "sharpe": sharpe, "max_drawdown": dd,
            "pct_time_invested": float((d != 0).mean())}


def _render(r: dict) -> str:
    h, ic, rg = r["history"], r["predictive_ic"], r["regime_conditional"]
    st, bh = r["timing_strategy"]["risk_managed"], r["timing_strategy"]["buy_and_hold"]
    L = []
    L.append("# eval/ Cycle-Timing Backtest — does the AI-cycle risk score lead?\n")
    L.append(f"_Generated {r['generated']} · basket history {h['start']} → {h['end']} · "
             f"{h['names']} names_\n")
    L.append("> Tests ONLY the measurable canaries (" + ", ".join(h["canaries"]) +
             "). Qualitative canaries + the narrative brains are NOT in this score and "
             "are untestable here. ~one cycle of data = low power: suggestive, not proof.\n")

    L.append("## 1. Does a high risk score precede weak forward returns?\n")
    L.append("| Forward window | Rank corr (risk → return) | Reads |")
    L.append("|---|---|---|")
    L.append(f"| 63 trading days | {_num(ic['risk_vs_fwd63'])} | "
             f"{'predictive ✅' if (ic['risk_vs_fwd63'] or 0) < -0.05 else 'no lead ❌'} |")
    L.append(f"| 126 trading days | {_num(ic['risk_vs_fwd126'])} | "
             f"{'predictive ✅' if (ic['risk_vs_fwd126'] or 0) < -0.05 else 'no lead ❌'} |")
    L.append("\n_Negative = the score was high before the basket fell (the canary led). "
             "Near-zero / positive = no predictive lead._\n")
    L.append("> ⚠️ **Power caveat:** forward windows overlap heavily (63-/126-day), so the "
             "effective independent sample is a handful of episodes — chiefly the 2022 "
             "rate-shock drawdown. A strong IC here can rest on **one or two events**; do not "
             "read it as a stable, repeatable edge.\n")

    L.append("## 2. Forward 63-day return by regime (point-in-time)\n")
    L.append("| Regime | N days | Mean fwd-63 return | % of windows negative |")
    L.append("|---|---|---|---|")
    L.append(f"| 🔴 Red (risk in top 20%) | {rg['red_n']} | {_pct(rg['red_fwd63_mean'])} "
             f"| {_pct(rg['red_fwd63_hit_negative'])} |")
    L.append(f"| 🟢 Green (risk in bottom 50%) | {rg['green_n']} | {_pct(rg['green_fwd63_mean'])} | — |")
    L.append(f"| All days (base rate) | — | {_pct(rg['all_fwd63_mean'])} "
             f"| {_pct(rg['all_fwd63_hit_negative'])} |")
    L.append("\n_If the score leads, Red-regime forward returns are clearly worse than the "
             "base rate and negative more often._\n")

    L.append("## 3. Risk-managed timing vs buy-and-hold (the practical test)\n")
    L.append("| Strategy | CAGR | Vol | Sharpe | Max drawdown | % time invested |")
    L.append("|---|---|---|---|---|---|")
    L.append(f"| Risk-off when Red | {_pct(st.get('cagr'))} | {_pct(st.get('vol'))} | "
             f"{_num(st.get('sharpe'),2)} | {_pct(st.get('max_drawdown'))} | "
             f"{_pct(st.get('pct_time_invested'))} |")
    L.append(f"| Buy & hold basket | {_pct(bh.get('cagr'))} | {_pct(bh.get('vol'))} | "
             f"{_num(bh.get('sharpe'),2)} | {_pct(bh.get('max_drawdown'))} | 100.0% |")
    L.append("\n_Timing 'works' only if it cuts max drawdown / lifts Sharpe WITHOUT giving "
             "back most of the CAGR. Most market-timing signals fail this — they exit late "
             "and miss the rebound._\n")

    L.append("---\n*Benchmark only. Establishes whether the timing engine has any historical "
             "lead; it is not itself a forecast. Not financial advice.*")
    return "\n".join(L)


if __name__ == "__main__":
    raise SystemExit(main())
