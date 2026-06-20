#!/usr/bin/env python3
"""Fetch a structured set of per-ticker financial metrics for the dashboard.

Mirrors the ta_memory.py `watch` pattern: this script does the NETWORK work
(yfinance) and writes a cache JSON; build_dashboard.py only *reads* that cache,
so the dashboard build itself stays offline-safe. update_all.sh runs this right
before the build (like it runs `watch`).

Universe = every tracked ticker (a directory under analyzed-stocks/). For each it
pulls valuation, profitability, balance-sheet/liquidity and catalyst fields that
the per-decision markdown only carried in prose, and computes a few derived ones
(FCF yield, Rule-of-40, implied analyst upside, 52-week range position). On a
per-ticker fetch error the previous cached entry is kept (offline → stale but
present), each entry carries its own `fetched_at`.

Output: metrics.json next to the decision log ($TRADINGAGENTS_MEMORY_LOG_PATH dir,
default ~/.tradingagents/memory/), so it persists across dashboard rebuilds.

Usage:
  python3 scripts/fetch_metrics.py                 # all tracked tickers
  python3 scripts/fetch_metrics.py AVGO MRVL CEG   # just these
  python3 scripts/fetch_metrics.py --out PATH      # override cache path
"""
import os, sys, json, glob, argparse, datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STOCKS = os.path.join(ROOT, "analyzed-stocks")
MEM = os.environ.get("TRADINGAGENTS_MEMORY_LOG_PATH",
                     os.path.expanduser("~/.tradingagents/memory/trading_memory.md"))
DEFAULT_OUT = os.path.join(os.path.dirname(MEM), "metrics.json")


def _num(x):
    try:
        f = float(x)
        return f if f == f else None  # drop NaN
    except (TypeError, ValueError):
        return None


def fetch_one(tk):
    """One ticker's metrics dict, or None if nothing could be fetched."""
    import yfinance as yf
    t = yf.Ticker(tk)
    info = t.info or {}
    if not info or len(info) < 5:
        return None
    g = info.get
    price = _num(g("currentPrice")) or _num(g("regularMarketPrice"))
    mcap = _num(g("marketCap"))
    fcf = _num(g("freeCashflow"))
    rev = _num(g("totalRevenue"))
    rev_g = _num(g("revenueGrowth"))
    pmar = _num(g("profitMargins"))
    tgt = _num(g("targetMeanPrice"))
    hi, lo = _num(g("fiftyTwoWeekHigh")), _num(g("fiftyTwoWeekLow"))

    m = {
        "price": price,
        "market_cap": mcap,
        "trailing_pe": _num(g("trailingPE")),
        "forward_pe": _num(g("forwardPE")),
        "peg": _num(g("trailingPegRatio")) or _num(g("pegRatio")),
        "ps": _num(g("priceToSalesTrailing12Months")),
        "ev_sales": _num(g("enterpriseToRevenue")),
        "ev_ebitda": _num(g("enterpriseToEbitda")),
        "gross_margin": _num(g("grossMargins")),
        "operating_margin": _num(g("operatingMargins")),
        "profit_margin": pmar,
        "rev_growth": rev_g,
        "beta": _num(g("beta")),
        "short_pct_float": _num(g("shortPercentOfFloat")),
        "short_ratio": _num(g("shortRatio")),
        "avg_volume": _num(g("averageVolume")),
        "float_shares": _num(g("floatShares")),
        "dividend_yield": _num(g("dividendYield")),
        "payout_ratio": _num(g("payoutRatio")),
        "target_mean": tgt,
        "wk52_high": hi,
        "wk52_low": lo,
        "fetched_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
    }
    # --- derived ---
    if fcf is not None and mcap:
        m["fcf_yield"] = fcf / mcap
    # Rule of 40 (software lens): YoY revenue growth + FCF margin (fallback profit margin)
    fcf_margin = (fcf / rev) if (fcf is not None and rev) else pmar
    if rev_g is not None and fcf_margin is not None:
        m["rule_of_40"] = (rev_g + fcf_margin) * 100
    if tgt and price:
        m["implied_upside"] = tgt / price - 1
    if price and hi is not None and lo is not None and hi > lo:
        m["pct_52w_range"] = (price - lo) / (hi - lo)
    if price and m.get("avg_volume"):
        m["avg_dollar_vol"] = price * m["avg_volume"]
    # next earnings date
    try:
        cal = t.calendar or {}
        ed = cal.get("Earnings Date")
        if isinstance(ed, (list, tuple)) and ed:
            ed = ed[0]
        if ed:
            m["next_earnings"] = str(ed)
    except Exception:
        pass
    # keep only populated fields
    return {k: v for k, v in m.items() if v is not None}


def main():
    ap = argparse.ArgumentParser(description="Fetch per-ticker financial metrics for the dashboard.")
    ap.add_argument("tickers", nargs="*", help="tickers (default: all tracked names)")
    ap.add_argument("--out", default=DEFAULT_OUT)
    args = ap.parse_args()

    tickers = [t.upper() for t in args.tickers] or sorted(
        os.path.basename(d) for d in glob.glob(os.path.join(STOCKS, "*")) if os.path.isdir(d))

    # load prior cache so failures degrade to stale-but-present
    cache = {}
    if os.path.exists(args.out):
        try:
            cache = json.load(open(args.out, encoding="utf-8")).get("metrics", {})
        except Exception:
            cache = {}

    ok = fail = 0
    for tk in tickers:
        try:
            m = fetch_one(tk)
            if m:
                cache[tk] = m
                ok += 1
                print(f"  {tk:6s} ok  (mcap={m.get('market_cap')}, fwdPE={m.get('forward_pe')})")
            else:
                fail += 1
                print(f"  {tk:6s} no data (kept prior)" if tk in cache else f"  {tk:6s} no data")
        except Exception as exc:
            fail += 1
            print(f"  {tk:6s} ERROR {type(exc).__name__}: {exc}" + (" (kept prior)" if tk in cache else ""))

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    today = datetime.date.today().isoformat()
    payload = {"generated": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"), "metrics": cache}
    json.dump(payload, open(args.out, "w", encoding="utf-8"), indent=2)
    # archive a dated snapshot so the dashboard can diff week-over-week (the
    # Financials-moves section of the Changes tab) — same pattern as X research_history.
    hist = os.path.join(os.path.dirname(args.out), "metrics_history")
    os.makedirs(hist, exist_ok=True)
    json.dump(payload, open(os.path.join(hist, f"{today}.json"), "w", encoding="utf-8"), indent=2)
    print(f"\nwrote {args.out}  ·  {ok} fetched, {fail} failed, {len(cache)} cached total"
          f"  ·  snapshot metrics_history/{today}.json")


if __name__ == "__main__":
    main()
