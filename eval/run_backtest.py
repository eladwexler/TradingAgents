#!/usr/bin/env python3
"""eval/ backtest benchmark — entry point.

Establishes the bar the platform must beat over the trailing 12 months and tests
whether the price/trend factor families it relies on had any cross-sectional edge
in this window. ZERO LLM judgment, ZERO forward knowledge in any signal.

Outputs (and only outputs) go to eval/results/. Nothing here writes to
~/.tradingagents/, analyzed-stocks/, the dashboard, or metrics.json.

Run:
    python3 eval/run_backtest.py
    python3 eval/run_backtest.py --config eval/config.yaml
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timedelta

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)

import data as D          # noqa: E402
import scoring as SC      # noqa: E402
import signals as SIG     # noqa: E402
from universe import load_universe  # noqa: E402


def _load_config(path: str) -> dict:
    try:
        import yaml
        with open(path) as f:
            return yaml.safe_load(f)
    except ModuleNotFoundError:
        return _load_config_no_yaml(path)


def _load_config_no_yaml(path: str) -> dict:
    """Minimal fallback parser so the harness runs without PyYAML installed."""
    cfg: dict = {}
    stack = [(-1, cfg)]
    with open(path) as f:
        for raw in f:
            line = raw.split("#", 1)[0].rstrip()
            if not line.strip():
                continue
            indent = len(line) - len(line.lstrip())
            key, _, val = line.strip().partition(":")
            while stack and indent <= stack[-1][0]:
                stack.pop()
            parent = stack[-1][1]
            val = val.strip()
            if val == "":
                node: dict = {}
                parent[key] = node
                stack.append((indent, node))
            else:
                parent[key] = _coerce(val)
    return cfg


def _coerce(v: str):
    v = v.strip().strip('"')
    if v.startswith("[") and v.endswith("]"):
        inner = v[1:-1].strip()
        return [x.strip().strip('"') for x in inner.split(",")] if inner else []
    try:
        return int(v)
    except ValueError:
        try:
            return float(v)
        except ValueError:
            return v


def _pct(x) -> str:
    return "—" if x is None else f"{x*100:+.1f}%"


def _num(x, d=3) -> str:
    return "—" if x is None else f"{x:.{d}f}"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default=os.path.join(HERE, "config.yaml"))
    ap.add_argument("--start", help="override window.start (as-of / entry date)")
    ap.add_argument("--end", help="override window.end (exit date)")
    args = ap.parse_args()
    cfg = _load_config(args.config)

    start = args.start or cfg["window"]["start"]
    end = args.end or cfg["window"]["end"]
    bench = cfg["benchmark_ticker"]
    cache = os.path.join(REPO_ROOT, cfg["cache_dir"])
    universe = load_universe(REPO_ROOT, cfg["universe"].get("exclude", []))

    print(f"Universe: {len(universe)} names | window {start} → {end} | benchmark {bench}")

    # ---- price series ----------------------------------------------------
    series: dict = {}
    bench_s = D.get_closes(bench, start, end, cache)
    if bench_s is None:
        print("FATAL: no benchmark price data.")
        return 1
    for t in universe:
        s = D.get_closes(t, start, end, cache)
        if s is not None:
            series[t] = s
    print(f"Price data resolved for {len(series)}/{len(universe)} names.")

    bench_ret = D.forward_return(bench_s, start, end)

    # ---- headline: 12-month buy-and-hold --------------------------------
    name_rets = {t: D.forward_return(series[t], start, end) for t in series}
    name_rets = {t: r for t, r in name_rets.items() if r is not None}
    basket = SC.basket_return(name_rets)
    basket_robust = SC.basket_stats(name_rets)
    suspect = SC.outliers(name_rets)
    hit, n_hit = SC.hit_rate_vs_benchmark(name_rets, bench_ret)

    # point-in-time signals AT the entry date
    sigs = {sn: {} for sn in SIG.SIGNAL_NAMES}
    for t in series:
        vals = SIG.compute_all(series[t], start, cfg)
        for sn in SIG.SIGNAL_NAMES:
            if vals[sn] is not None:
                sigs[sn][t] = vals[sn]

    outcomes = {t: (1 if r > bench_ret else 0) for t, r in name_rets.items()}
    null_brier = SC.brier({t: 0.5 for t in outcomes}, outcomes)

    headline_signals = {}
    for sn in SIG.SIGNAL_NAMES:
        ic = SC.spearman_ic(sigs[sn], name_rets)
        qs = SC.quintile_spread(sigs[sn], name_rets, cfg["signals"]["quintiles"])
        probs = SC.signal_to_prob(sigs[sn])
        br = SC.brier(probs, outcomes)
        headline_signals[sn] = {"ic_12m": ic, "quintile": qs, "brier": br}

    # ---- robustness: monthly-anchored short-horizon IC -------------------
    mcfg = cfg["monthly_ic"]
    fwd_days = mcfg["forward_trading_days"]
    anchors = _monthly_anchors(end, mcfg["anchors"], fwd_days)
    monthly = {sn: [] for sn in SIG.SIGNAL_NAMES}
    anchor_used = []
    for a in anchors:
        a_end = _shift_trading_days(bench_s, a, fwd_days)
        if a_end is None:
            continue
        fwd = {}
        asig = {sn: {} for sn in SIG.SIGNAL_NAMES}
        for t, s in series.items():
            r = D.forward_return(s, a, a_end)
            if r is None:
                continue
            fwd[t] = r
            vals = SIG.compute_all(s, a, cfg)
            for sn in SIG.SIGNAL_NAMES:
                if vals[sn] is not None:
                    asig[sn][t] = vals[sn]
        if len(fwd) < mcfg["min_names"]:
            continue
        anchor_used.append(a)
        for sn in SIG.SIGNAL_NAMES:
            ic = SC.spearman_ic(asig[sn], fwd)
            if ic is not None:
                monthly[sn].append(ic)

    monthly_summary = {}
    for sn in SIG.SIGNAL_NAMES:
        ics = monthly[sn]
        if ics:
            arr = pd.Series(ics)
            monthly_summary[sn] = {
                "mean_ic": float(arr.mean()),
                "std_ic": float(arr.std(ddof=0)),
                "n_anchors": len(ics),
                "pct_positive": float((arr > 0).mean()),
            }
        else:
            monthly_summary[sn] = {"mean_ic": None, "std_ic": None,
                                   "n_anchors": 0, "pct_positive": None}

    result = {
        "generated": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "window": {"start": start, "end": end},
        "benchmark": {"ticker": bench, "return_12m": bench_ret},
        "universe_n": len(universe),
        "priced_n": len(series),
        "headline": {
            "basket_equal_weight_return": basket,
            "basket_robust": basket_robust,
            "basket_alpha_vs_bench": (None if basket is None or bench_ret is None
                                      else basket - bench_ret),
            "hit_rate_vs_bench": hit,
            "names_scored": n_hit,
            "null_brier_coinflip": null_brier,
            "suspect_outliers": dict(sorted(suspect.items(), key=lambda kv: -kv[1])),
            "signals": headline_signals,
        },
        "monthly_ic": {
            "forward_trading_days": fwd_days,
            "anchors_used": len(anchor_used),
            "by_signal": monthly_summary,
        },
        "per_name_return": dict(sorted(name_rets.items(), key=lambda kv: -kv[1])),
    }

    rdir = os.path.join(HERE, "results")
    os.makedirs(rdir, exist_ok=True)
    tag = f"{start}_to_{end}"
    md = _render_md(result)
    # window-specific (kept side by side) + a generic "latest" copy
    for jp in (os.path.join(rdir, f"scorecard_{tag}.json"), os.path.join(rdir, "scorecard.json")):
        with open(jp, "w") as f:
            json.dump(result, f, indent=2)
    for mp in (os.path.join(rdir, f"scorecard_{tag}.md"), os.path.join(rdir, "scorecard.md")):
        with open(mp, "w") as f:
            f.write(md)

    print(f"\nWrote results/scorecard_{tag}.{{md,json}} (+ scorecard.{{md,json}} latest)\n")
    print(md)
    return 0


def _monthly_anchors(end: str, n: int, fwd_days: int) -> list:
    """n monthly anchor dates walking back from `end`, each leaving room for a
    forward window (so the most recent anchors that can't complete are dropped by
    the caller)."""
    e = datetime.strptime(end, "%Y-%m-%d")
    out = []
    # start far enough back that the first forward window can complete by `end`
    base = e - timedelta(days=int(fwd_days * 1.5))
    for i in range(n):
        out.append((base - timedelta(days=30 * i)).strftime("%Y-%m-%d"))
    return sorted(out)


def _shift_trading_days(bench_s, as_of: str, fwd_days: int):
    """Date `fwd_days` trading days after as_of, using the benchmark calendar.
    Returns None if there aren't enough trading days left in history."""
    idx = bench_s.index
    after = idx[idx >= pd.Timestamp(as_of)]
    if len(after) <= fwd_days:
        return None
    return after[fwd_days].strftime("%Y-%m-%d")


def _render_md(r: dict) -> str:
    h = r["headline"]
    br = r["benchmark"]
    L = []
    L.append(f"# eval/ Backtest Benchmark — {br['ticker']} hurdle\n")
    L.append(f"_Generated {r['generated']} · window {r['window']['start']} → "
             f"{r['window']['end']} · {r['priced_n']}/{r['universe_n']} names priced_\n")
    L.append("> Hindsight-free: no LLM judgment, no forward knowledge in any signal. "
             "This is the **bar the platform must beat**, plus whether its price/trend "
             "factors had cross-sectional edge this window.\n")

    rb = h.get("basket_robust") or {}
    L.append("## 1. The bar (12-month buy-and-hold)\n")
    L.append("| Strategy | Return | Alpha vs " + br["ticker"] + " |")
    L.append("|---|---|---|")
    L.append(f"| {br['ticker']} (the hurdle) | {_pct(br['return_12m'])} | — |")
    L.append(f"| Equal-weight basket — raw mean | {_pct(h['basket_equal_weight_return'])} "
             f"| {_pct(h['basket_alpha_vs_bench'])} |")
    L.append(f"| Equal-weight basket — **median name** | {_pct(rb.get('median'))} "
             f"| {_pct(None if rb.get('median') is None or br['return_12m'] is None else rb['median'] - br['return_12m'])} |")
    L.append(f"| Equal-weight basket — winsorized mean (cap +{int((rb.get('cap') or 3)*100)}%) "
             f"| {_pct(rb.get('winsorized_mean'))} "
             f"| {_pct(None if rb.get('winsorized_mean') is None or br['return_12m'] is None else rb['winsorized_mean'] - br['return_12m'])} |")
    L.append("")
    L.append(f"- **Hit-rate**: {_pct(h['hit_rate_vs_bench']) if h['hit_rate_vs_bench'] is not None else '—'} "
             f"of {h['names_scored']} names beat {br['ticker']} over the year "
             f"(coin-flip Brier null = {_num(h['null_brier_coinflip'])}).")
    sus = h.get("suspect_outliers") or {}
    if sus:
        L.append(f"- ⚠️ **Data-quality flag**: {len(sus)} name(s) show >+500% 12m returns — "
                 "likely penny-stock / reverse-split / ticker-reuse artifacts, not investable "
                 "outcomes. They inflate the raw mean; use the **median** and **winsorized** "
                 "rows as the honest bar. Suspect: "
                 + ", ".join(f"{t} {_pct(v)}" for t, v in list(sus.items())[:8]) + ".")
    L.append("")

    L.append("## 2. Did the platform's factor families have edge? (12m horizon)\n")
    L.append("| Signal (point-in-time at entry) | IC (rank corr) | Top−Bottom quintile | Brier vs 0.5 null |")
    L.append("|---|---|---|---|")
    for sn, d in h["signals"].items():
        qs = d["quintile"]
        spread = _pct(qs["spread"]) if qs else "—"
        brier = d["brier"]
        verdict = ""
        if brier is not None and h["null_brier_coinflip"] is not None:
            verdict = " ✅" if brier < h["null_brier_coinflip"] else " ❌"
        L.append(f"| {sn} | {_num(d['ic_12m'])} | {spread} | {_num(brier)}{verdict} |")
    L.append("")
    L.append("_IC>0 = signal ranked winners above losers. Brier below the 0.5 null (✅) = "
             "the factor added information; ❌ = no better than a coin flip._\n")

    m = r["monthly_ic"]
    L.append(f"## 3. Robustness — monthly IC ({m['forward_trading_days']}-day forward, "
             f"{m['anchors_used']} anchors)\n")
    L.append("| Signal | Mean IC | Std IC | % anchors IC>0 |")
    L.append("|---|---|---|---|")
    for sn, d in m["by_signal"].items():
        L.append(f"| {sn} | {_num(d['mean_ic'])} | {_num(d['std_ic'])} | "
                 f"{_pct(d['pct_positive']) if d['pct_positive'] is not None else '—'} |")
    L.append("")
    L.append("_A factor with real edge shows a consistently positive mean IC and a high "
             "share of positive anchors. Near-zero / sign-flipping mean = no robust edge._\n")

    pn = r["per_name_return"]
    if pn:
        top = list(pn.items())[:5]
        bot = list(pn.items())[-5:]
        L.append("## 4. Per-name 12m return (extremes)\n")
        L.append("Best: " + ", ".join(f"{t} {_pct(v)}" for t, v in top))
        L.append("")
        L.append("Worst: " + ", ".join(f"{t} {_pct(v)}" for t, v in bot))
        L.append("")

    L.append("---\n*Benchmark only. Establishes a baseline; it does not itself predict. "
             "Not financial advice.*")
    return "\n".join(L)


if __name__ == "__main__":
    raise SystemExit(main())
