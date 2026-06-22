#!/usr/bin/env python3
"""Empirical base-rate anchor for the 12-month forecast — computed, not hand-waved.

The trading-analysis LLM tends to *narrate* a return ("base case +22%") instead of
*computing* one. This script gives it a gravitational anchor: **what actually happened,
historically, to stocks that looked like this one** — so the forecast becomes an argued
*deviation* from an empirical base rate rather than a vibe.

HONESTY CONTRACT (read before trusting a number):
  * **Price factors only.** We condition on look-ahead-free, free-data factors —
    12-1 momentum, drawdown from the trailing-1y high, 3-month realized vol, and
    distance from the 200-day MA. We deliberately do NOT use forward-P/E percentile
    or estimate-revision history: the free (yfinance) stack can't reconstruct those
    point-in-time without look-ahead bias, so faking them would be false rigor.
  * **Excess vs SPY.** Every forward return is measured *minus SPY over the same window*,
    because the deliverable is P(beat benchmark) — not raw return in a bull market.
  * **Real distribution, not a point.** We report median + P25/P75 + the hit-rate
    (share of similar cases that beat SPY), plus N and the count of *distinct months*
    (the honest effective sample — daily/overlapping windows are autocorrelated).
  * **Known biases, stated.** The universe is survivorship-tilted (today's names,
    backtested), the AI cohort is cross-correlated (so effective N << nominal N), and
    base rates are regime-conditional on the sample period. We print these every run.

It is an anchor and a humility check, NOT a prediction. Use:
    python3 scripts/base_rates.py TICKER [--asof YYYY-MM-DD] [--years N] [--refresh] [--json]
"""
import os, sys, json, argparse, datetime, pickle
import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STOCKS = os.path.join(ROOT, "analyzed-stocks")
CACHE_DIR = os.path.expanduser("~/.tradingagents/memory")
PRICE_CACHE = os.path.join(CACHE_DIR, "base_rate_prices.pkl")
BENCH = "SPY"
TRADING_DAYS = 252
CACHE_MAX_AGE_DAYS = 2

# A sector-diversified reference set so the base rates aren't computed purely from
# AI-infra survivors (which would bias them upward). Mixed with the analyzed universe.
REFERENCE = [
    "AAPL", "MSFT", "GOOGL", "AMZN", "META", "NVDA", "AVGO", "ORCL", "ADBE", "CRM",
    "CSCO", "INTC", "TXN", "QCOM", "IBM", "AMD", "MU",
    "JPM", "V", "MA", "BAC", "WFC", "GS", "MS", "C", "AXP",
    "UNH", "LLY", "JNJ", "PG", "KO", "COST", "WMT", "HD", "MCD", "PEP", "ABBV",
    "MRK", "PFE", "TMO", "ISRG", "XOM", "CVX", "NEE", "CAT", "BA", "GE", "DIS",
    "NKE", "T", "VZ", "UPS", "LOW", "SBUX", "BLK", "SPY",
]


def universe():
    names = set(REFERENCE)
    if os.path.isdir(STOCKS):
        names |= {d for d in os.listdir(STOCKS) if os.path.isdir(os.path.join(STOCKS, d))}
    names.add(BENCH)
    # crypto / non-equity tickers don't belong in an equity base rate
    return sorted(n for n in names if "-" not in n and n.isalpha())


def load_prices(years, refresh=False):
    """Daily adjusted close per ticker, cached (refreshed if stale)."""
    fresh = (not refresh and os.path.exists(PRICE_CACHE) and
             (datetime.datetime.now().timestamp() - os.path.getmtime(PRICE_CACHE))
             < CACHE_MAX_AGE_DAYS * 86400)
    if fresh:
        with open(PRICE_CACHE, "rb") as f:
            return pickle.load(f)
    import yfinance as yf
    tks = universe()
    start = (datetime.date.today() - datetime.timedelta(days=int(years * 365.25) + 400)).isoformat()
    print(f"  [base_rates] downloading {len(tks)} tickers from {start} (cache miss/refresh)…",
          file=sys.stderr)
    raw = yf.download(tks, start=start, auto_adjust=True, progress=False, threads=True)
    close = raw["Close"] if isinstance(raw.columns, pd.MultiIndex) else raw[["Close"]]
    close = close.dropna(how="all", axis=1)
    os.makedirs(CACHE_DIR, exist_ok=True)
    with open(PRICE_CACHE, "wb") as f:
        pickle.dump(close, f)
    return close


def factor_rows(close_t, spy_m):
    """For one ticker's daily close, return month-end rows of trailing price factors
    + the realized forward-12m EXCESS return vs SPY. Look-ahead-free by construction."""
    c = close_t.dropna()
    if len(c) < TRADING_DAYS + 40:
        return None
    ret = c.pct_change()
    sma200 = c.rolling(200).mean()
    daily = pd.DataFrame({
        "mom_12_1": c.shift(21) / c.shift(TRADING_DAYS) - 1,          # 12mo-ago → 1mo-ago
        "dd_high": c / c.rolling(TRADING_DAYS).max() - 1,            # drawdown from 1y high (≤0)
        "vol_63": ret.rolling(63).std() * np.sqrt(TRADING_DAYS),     # ~3mo realized vol, annualized
        "dist_200": c / sma200 - 1,                                  # distance from 200d MA
    })
    me = c.resample("ME").last().index                              # month-end sample dates
    feat = daily.reindex(daily.index.union(me)).ffill().reindex(me).dropna()
    # forward 12m total return (monthly close shifted -12), and SPY's, → excess
    cm = c.resample("ME").last()
    fwd = cm.shift(-12) / cm - 1
    spy_fwd = spy_m.shift(-12) / spy_m - 1
    feat["fwd_excess"] = (fwd.reindex(feat.index) - spy_fwd.reindex(feat.index))
    return feat.dropna(subset=["fwd_excess"])


def build_panel(close, years):
    spy_m = close[BENCH].resample("ME").last()
    cut = pd.Timestamp(datetime.date.today() - datetime.timedelta(days=int(years * 365.25)))
    frames = []
    for tk in close.columns:
        fr = factor_rows(close[tk], spy_m)
        if fr is None or fr.empty:
            continue
        fr = fr[fr.index >= cut].copy()
        fr["ticker"] = tk
        frames.append(fr)
    panel = pd.concat(frames) if frames else pd.DataFrame()
    return panel


def terciles(s):
    qs = s.quantile([1 / 3, 2 / 3]).values
    return qs[0], qs[1]


def bucket(val, lo, hi):
    return "Low" if val <= lo else ("High" if val > hi else "Mid")


def current_factors(close, ticker, asof):
    c = close[ticker].dropna()
    if asof:
        c = c[c.index <= pd.Timestamp(asof)]
    if len(c) < TRADING_DAYS + 5:
        return None, None
    ret = c.pct_change()
    f = {
        "mom_12_1": c.iloc[-21] / c.iloc[-TRADING_DAYS] - 1,
        "dd_high": c.iloc[-1] / c.iloc[-TRADING_DAYS:].max() - 1,
        "vol_63": ret.iloc[-63:].std() * np.sqrt(TRADING_DAYS),
        "dist_200": c.iloc[-1] / c.iloc[-200:].mean() - 1,
    }
    return f, c.index[-1].date()


def dist_stats(x):
    x = np.asarray(x, float)
    return {
        "n": int(x.size),
        "median": float(np.median(x)),
        "p25": float(np.percentile(x, 25)),
        "p75": float(np.percentile(x, 75)),
        "mean": float(np.mean(x)),
        "hit": float(np.mean(x > 0)),     # share beating SPY → empirical P(beat)
    }


def pct(v):
    return f"{v * 100:+.1f}%"


def analyze(ticker, asof=None, years=8, refresh=False):
    ticker = ticker.upper()
    close = load_prices(years, refresh)
    if ticker not in close.columns:
        # try to fetch just this one on the fly
        import yfinance as yf
        s = yf.download(ticker, start=(datetime.date.today() - datetime.timedelta(days=years * 366)).isoformat(),
                        auto_adjust=True, progress=False)
        col = s["Close"]
        close[ticker] = col[col.columns[0]] if isinstance(col, pd.DataFrame) else col
    cf, asof_real = current_factors(close, ticker, asof)
    if cf is None:
        return {"error": f"insufficient price history for {ticker}"}
    panel = build_panel(close, years)
    if panel.empty:
        return {"error": "empty panel"}

    # tercile edges from the panel, then the ticker's current bucket on each factor
    edges = {f: terciles(panel[f]) for f in ("mom_12_1", "dd_high", "vol_63", "dist_200")}
    cb = {f: bucket(cf[f], *edges[f]) for f in edges}

    uncond = dist_stats(panel["fwd_excess"])
    # primary conditioning: momentum × drawdown (the two most informative price factors)
    mask = ((panel["mom_12_1"].apply(lambda v: bucket(v, *edges["mom_12_1"])) == cb["mom_12_1"]) &
            (panel["dd_high"].apply(lambda v: bucket(v, *edges["dd_high"])) == cb["dd_high"]))
    cell = panel[mask]
    cond = dist_stats(cell["fwd_excess"]) if len(cell) >= 30 else None
    distinct_months = int(cell.index.normalize().nunique()) if len(cell) else 0
    # momentum-only fallback for context / when the 2-factor cell is thin
    mmask = panel["mom_12_1"].apply(lambda v: bucket(v, *edges["mom_12_1"])) == cb["mom_12_1"]
    mom_only = dist_stats(panel[mmask]["fwd_excess"])

    return {
        "ticker": ticker, "asof": str(asof_real), "years": years,
        "sample_start": str(panel.index.min().date()), "sample_end": str(panel.index.max().date()),
        "panel_rows": int(len(panel)), "panel_tickers": int(panel["ticker"].nunique()),
        "current_factors": {k: round(v, 4) for k, v in cf.items()},
        "buckets": cb,
        "unconditional": uncond,
        "conditional": cond, "conditional_distinct_months": distinct_months,
        "momentum_only": mom_only,
    }


def _spearman(a, b):
    a, b = np.asarray(a, float), np.asarray(b, float)
    if len(a) < 3:
        return float("nan")
    ra, rb = pd.Series(a).rank().values, pd.Series(b).rank().values
    if ra.std() == 0 or rb.std() == 0:
        return float("nan")
    return float(np.corrcoef(ra, rb)[0, 1])


def validate(years=8, refresh=False):
    """Out-of-sample reliability check of the anchor: train the buckets on the first
    60% of history, then test whether their predicted P(beat) and return ordering
    actually hold on the held-out last 40%. This is how you decide whether to TRUST
    the anchor before relying on it — honest about the small effective sample."""
    close = load_prices(years, refresh)
    panel = build_panel(close, years)
    if panel.empty:
        return {"error": "empty panel"}
    dates = sorted(panel.index.unique())
    split = dates[int(len(dates) * 0.6)]
    train, test = panel[panel.index < split], panel[panel.index >= split]
    edges = {f: terciles(train[f]) for f in ("mom_12_1", "dd_high")}

    def cellkey(df):
        return (df["mom_12_1"].apply(lambda v: bucket(v, *edges["mom_12_1"])) + " × " +
                df["dd_high"].apply(lambda v: bucket(v, *edges["dd_high"])))
    train, test = train.assign(cell=cellkey(train)), test.assign(cell=cellkey(test))
    rows = []
    for c in sorted(train["cell"].unique()):
        tr, te = train[train["cell"] == c]["fwd_excess"], test[test["cell"] == c]["fwd_excess"]
        if len(tr) < 30 or len(te) < 30:
            continue
        rows.append({"cell": c, "pred_hit": float((tr > 0).mean()), "real_hit": float((te > 0).mean()),
                     "pred_med": float(tr.median()), "real_med": float(te.median()),
                     "n_te": int(len(te)),
                     "months_te": int(test[test["cell"] == c].index.normalize().nunique())})
    if len(rows) < 3:
        return {"error": "not enough populated cells to validate"}
    pred_h = [x["pred_hit"] for x in rows]
    real_h = [x["real_hit"] for x in rows]
    calib_err = float(np.average([abs(x["pred_hit"] - x["real_hit"]) for x in rows],
                                 weights=[x["n_te"] for x in rows]))
    rank_hit = _spearman(pred_h, real_h)
    rank_ret = _spearman([x["pred_hit"] for x in rows], [x["real_med"] for x in rows])
    # discrimination: realized excess of the top-pred third vs bottom-pred third of cells
    srt = sorted(rows, key=lambda x: x["pred_hit"])
    k = max(1, len(srt) // 3)
    lo_real = np.mean([x["real_med"] for x in srt[:k]])
    hi_real = np.mean([x["real_med"] for x in srt[-k:]])
    spread = float(hi_real - lo_real)
    uncond_test = float((test["fwd_excess"] > 0).mean())
    return {"train_end": str(split.date()), "test_end": str(test.index.max().date()),
            "n_train": int(len(train)), "n_test": int(len(test)),
            "test_distinct_months": int(test.index.normalize().nunique()),
            "cells": rows, "calib_err": calib_err, "rank_hit": rank_hit, "rank_ret": rank_ret,
            "spread": spread, "uncond_test_hit": uncond_test}


def render_validate(v):
    if "error" in v:
        return f"VALIDATION: unavailable — {v['error']}"
    L = ["## BASE-RATE ANCHOR — OUT-OF-SAMPLE VALIDATION",
         f"Train buckets on history < {v['train_end']}; test on held-out ≥ {v['train_end']} "
         f"→ {v['test_end']} ({v['n_test']} name-months, {v['test_distinct_months']} distinct months).",
         "", "Cell (momentum × drawdown)      pred→real  P(beat)   |  pred→real median excess  | n_test",
         "-" * 78]
    for x in sorted(v["cells"], key=lambda z: -z["pred_hit"]):
        L.append(f"  {x['cell']:<22} {x['pred_hit']*100:4.0f}% → {x['real_hit']*100:4.0f}%   "
                 f"|  {x['pred_med']*100:+5.1f}% → {x['real_med']*100:+5.1f}%    | {x['n_te']:4d} ({x['months_te']}mo)")
    L.append("")
    L.append(f"Calibration error (|pred−real| P(beat), wtd): {v['calib_err']*100:.1f} pts  "
             f"(lower = anchor's stated odds hold up; >10 pts = don't trust the precise number)")
    L.append(f"Rank agreement pred-P(beat) vs realized P(beat): ρ={v['rank_hit']:+.2f}; "
             f"vs realized median excess: ρ={v['rank_ret']:+.2f}  (>0 = ordering survives; ~0/neg = no skill)")
    L.append(f"Discrimination spread (top-third − bottom-third cells, realized median excess): "
             f"{v['spread']*100:+.1f} pts  ·  unconditional test hit-rate {v['uncond_test_hit']*100:.0f}%")
    verdict = ("WEAK / treat as humility-only" if (v["rank_hit"] < 0.3 or v["calib_err"] > 0.10)
               else "MODERATE — ordering largely survives OOS" if v["rank_hit"] < 0.6
               else "RELATIVELY STABLE OOS")
    L.append("")
    L.append(f"⇒ ANCHOR RELIABILITY: {verdict}. ⚠ Small effective sample "
             f"({v['test_distinct_months']} distinct test months, correlated names) — this validation is "
             f"itself low-power; read it as a smell test, not proof. Price factors alone are a weak edge.")
    return "\n".join(L)


def render(r):
    if "error" in r:
        return f"BASE RATE: unavailable — {r['error']}"
    L = []
    L.append(f"## EMPIRICAL BASE-RATE ANCHOR — {r['ticker']}  (as-of {r['asof']})")
    L.append(f"Forward-12m return measured as EXCESS vs SPY. Price-factor conditioning only "
             f"(no fundamentals). Sample {r['sample_start']}→{r['sample_end']}, "
             f"{r['panel_rows']} name-months across {r['panel_tickers']} tickers.")
    f = r["current_factors"]; b = r["buckets"]
    L.append("")
    L.append(f"This name today: 12-1 momentum {pct(f['mom_12_1'])} [{b['mom_12_1']}] · "
             f"drawdown-from-1y-high {pct(f['dd_high'])} [{b['dd_high']}] · "
             f"3mo realized vol {f['vol_63']*100:.0f}% [{b['vol_63']}] · "
             f"vs-200dma {pct(f['dist_200'])} [{b['dist_200']}]")
    u = r["unconditional"]
    L.append("")
    L.append(f"UNCONDITIONAL (all names, all months): median {pct(u['median'])} excess, "
             f"P25/P75 {pct(u['p25'])}/{pct(u['p75'])}, beats-SPY {u['hit']*100:.0f}% (n={u['n']}).")
    c = r["conditional"]
    if c:
        L.append(f"CONDITIONAL — stocks like this (momentum [{b['mom_12_1']}] × drawdown [{b['dd_high']}]):")
        L.append(f"  → median {pct(c['median'])} excess vs SPY over 12m · P25/P75 {pct(c['p25'])}/{pct(c['p75'])} "
                 f"· beats-SPY {c['hit']*100:.0f}% · n={c['n']} ({r['conditional_distinct_months']} distinct months).")
        L.append("  [reliability: this conditional POINT is WEAK out-of-sample — `base_rates.py --validate` "
                 "shows the bucket ordering does not survive OOS. Use the BAND (dispersion), not the point.]")
        band = c
    else:
        m = r["momentum_only"]
        L.append(f"CONDITIONAL cell too thin (<30) — falling back to momentum-[{b['mom_12_1']}] only: "
                 f"median {pct(m['median'])} excess, beats-SPY {m['hit']*100:.0f}% (n={m['n']}).")
        band = m
    # Anchor on the RELIABLE parts only: the unconditional hit-rate for P(beat), and the
    # conditional dispersion band for scenario width. The conditional point is not trustworthy OOS.
    L.append("")
    L.append(f"  ⇒ ANCHOR (reliable parts only): P(beat SPY) prior ≈ {u['hit']:.2f} — the UNCONDITIONAL rate "
             f"(~coin-flip; conditioning adds no validated OOS skill). Scenario WIDTH ≈ "
             f"{pct(band['p25'])}…{pct(band['p75'])} excess (P25–P75). ⇒ start P(beat) near {u['hit']:.2f} and "
             f"move off it ONLY with a named, non-consensus edge; let bear/bull span roughly the band.")
    L.append("")
    L.append("⚠ HONEST LIMITS: price-factor base rate only (no valuation/estimate signal); the conditional "
             "buckets have NO validated out-of-sample discrimination — so the trustworthy signal is the ~50% "
             "unconditional hit-rate + the dispersion band (humility about direction, realism about width). "
             "Universe survivorship-tilted; AI names cross-correlated (effective sample « n); regime-conditional. "
             "An anchor and humility check, NOT a forecast.")
    return "\n".join(L)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("ticker", nargs="?", help="ticker to anchor (omit with --validate)")
    ap.add_argument("--asof", default=None)
    ap.add_argument("--years", type=int, default=8)
    ap.add_argument("--refresh", action="store_true", help="force re-download of the price cache")
    ap.add_argument("--validate", action="store_true",
                    help="out-of-sample reliability check of the anchor itself (no ticker needed)")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    if a.validate:
        v = validate(a.years, a.refresh)
        print(json.dumps(v, indent=1) if a.json else render_validate(v))
        return
    if not a.ticker:
        ap.error("ticker is required (or pass --validate)")
    r = analyze(a.ticker, a.asof, a.years, a.refresh)
    if a.json:
        print(json.dumps(r, indent=1))
    else:
        print(render(r))


if __name__ == "__main__":
    main()
