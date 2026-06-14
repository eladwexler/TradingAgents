#!/usr/bin/env python3
"""Key-free market-data CLI for the trading-analysis skill.

This is a thin command-line wrapper over TradingAgents' existing data layer
(``tradingagents/dataflows``). It performs **no LLM calls** — it only fetches
and formats the same market data the framework's analyst agents would see, so
Claude itself can play the agent roles instead of paid LLM providers.

Default vendor is yfinance (no API key). Reddit and StockTwits use public
endpoints (no key). Alpha Vantage is only used as a fallback and only if
ALPHA_VANTAGE_API_KEY happens to be set; nothing here requires it.

Every subcommand prints the formatted block to stdout exactly as the
corresponding agent tool would receive it. On failure it prints a clear
``ERROR:`` / ``NO_DATA`` line and exits non-zero rather than fabricating data.

Usage examples:
    python ta_data.py identity AAPL
    python ta_data.py stock_data AAPL 2026-05-01 2026-06-01
    python ta_data.py indicators AAPL rsi,macd,close_50_sma 2026-06-01 30
    python ta_data.py snapshot AAPL 2026-06-01
    python ta_data.py fundamentals AAPL 2026-06-01
    python ta_data.py balance_sheet AAPL quarterly 2026-06-01
    python ta_data.py news AAPL 2026-05-25 2026-06-01
    python ta_data.py global_news 2026-06-01
    python ta_data.py insider AAPL
    python ta_data.py sentiment AAPL 2026-06-01      # news+stocktwits+reddit bundle
"""

from __future__ import annotations

import argparse
import sys
import traceback
from datetime import datetime, timedelta

# Make the project importable when the script is run from anywhere.
import os

_SKILL_DIR = os.path.dirname(os.path.abspath(__file__))
# scripts/ -> trading-analysis/ -> skills/ -> .claude/ -> <project root>
_PROJECT_ROOT = os.path.abspath(os.path.join(_SKILL_DIR, "..", "..", "..", ".."))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)


def _emit(text: str) -> None:
    """Print a data block, normalising None/empty to an explicit marker."""
    if text is None or (isinstance(text, str) and not text.strip()):
        print("NO_DATA: vendor returned an empty result.")
        return
    print(text)


def _seven_days_back(date_str: str) -> str:
    return (datetime.strptime(date_str, "%Y-%m-%d") - timedelta(days=7)).strftime("%Y-%m-%d")


# --- subcommand handlers --------------------------------------------------


def cmd_identity(args) -> None:
    """Deterministic company/asset identity, mirroring the run-start resolution.

    Lazy-imports agent_utils (which pulls langchain) so the rest of the CLI
    stays usable even if those extras are not installed.
    """
    try:
        from tradingagents.agents.utils.agent_utils import (
            resolve_instrument_identity,
            build_instrument_context,
        )
    except Exception:  # noqa: BLE001 — fall back to a local yfinance resolver
        import yfinance as yf

        try:
            info = yf.Ticker(args.ticker.upper()).info or {}
        except Exception as exc:  # noqa: BLE001
            print(f"ERROR: could not resolve identity for {args.ticker}: {exc}")
            return
        name = info.get("longName") or info.get("shortName")
        sector = info.get("sector")
        industry = info.get("industry")
        exchange = info.get("exchange")
        quote_type = info.get("quoteType")
        print(f"Ticker: {args.ticker}")
        print(f"Name: {name or '(unresolved)'}")
        if sector or industry:
            print(f"Business classification: {sector or '?'} / {industry or '?'}")
        if exchange:
            print(f"Exchange: {exchange}")
        if quote_type:
            print(f"Quote type: {quote_type}")
        return

    identity = resolve_instrument_identity(args.ticker)
    asset_type = "crypto" if args.ticker.upper().endswith(("-USD", "-USDT")) else "stock"
    print(build_instrument_context(args.ticker, asset_type=asset_type, identity=identity))


def cmd_stock_data(args) -> None:
    from tradingagents.dataflows.interface import route_to_vendor

    _emit(route_to_vendor("get_stock_data", args.symbol, args.start_date, args.end_date))


def cmd_indicators(args) -> None:
    from tradingagents.dataflows.interface import route_to_vendor

    indicators = [i.strip().lower() for i in args.indicator.split(",") if i.strip()]
    out = []
    for ind in indicators:
        try:
            out.append(route_to_vendor("get_indicators", args.symbol, ind, args.curr_date, args.look_back_days))
        except Exception as exc:  # noqa: BLE001
            out.append(f"ERROR computing indicator '{ind}': {exc}")
    _emit("\n\n".join(out))


def cmd_snapshot(args) -> None:
    from tradingagents.dataflows.market_data_validator import build_verified_market_snapshot

    _emit(build_verified_market_snapshot(args.symbol, args.curr_date, args.look_back_days))


def cmd_fundamentals(args) -> None:
    from tradingagents.dataflows.interface import route_to_vendor

    _emit(route_to_vendor("get_fundamentals", args.ticker, args.curr_date))


def cmd_balance_sheet(args) -> None:
    from tradingagents.dataflows.interface import route_to_vendor

    _emit(route_to_vendor("get_balance_sheet", args.ticker, args.freq, args.curr_date))


def cmd_cashflow(args) -> None:
    from tradingagents.dataflows.interface import route_to_vendor

    _emit(route_to_vendor("get_cashflow", args.ticker, args.freq, args.curr_date))


def cmd_income_statement(args) -> None:
    from tradingagents.dataflows.interface import route_to_vendor

    _emit(route_to_vendor("get_income_statement", args.ticker, args.freq, args.curr_date))


def cmd_news(args) -> None:
    from tradingagents.dataflows.interface import route_to_vendor

    _emit(route_to_vendor("get_news", args.ticker, args.start_date, args.end_date))


def cmd_global_news(args) -> None:
    from tradingagents.dataflows.interface import route_to_vendor

    _emit(route_to_vendor("get_global_news", args.curr_date, args.look_back_days, args.limit))


def cmd_insider(args) -> None:
    from tradingagents.dataflows.interface import route_to_vendor

    _emit(route_to_vendor("get_insider_transactions", args.ticker))


def cmd_stocktwits(args) -> None:
    from tradingagents.dataflows.stocktwits import fetch_stocktwits_messages

    _emit(fetch_stocktwits_messages(args.ticker, limit=args.limit))


def cmd_reddit(args) -> None:
    from tradingagents.dataflows.reddit import fetch_reddit_posts

    _emit(fetch_reddit_posts(args.ticker))


def _fmt_pct(x) -> str:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return "n/a"
    if v != v:  # NaN
        return "n/a"
    return f"{v:+.1%}"


def _forward_block(ticker: str) -> str:
    """Build the long-horizon (12-36mo) inputs block: analyst targets, forward
    multiples, consensus growth.

    Self-contained yfinance pull (these forward fields are not in the project's
    historical dataflows). Every piece is isolated so a missing field never
    aborts the block. This is the primary fundamental input for the prediction
    model — earnings growth, multiple level, and shareholder yield are the three
    drivers of multi-year return.
    """
    import yfinance as yf

    tk = ticker.upper()
    t = yf.Ticker(tk)
    info = t.info or {}

    cur = info.get("currentPrice") or info.get("regularMarketPrice")
    lines = [f"## FORWARD ESTIMATES & VALUATION — {tk}"]
    if cur:
        lines.append(f"Current price: {cur}")

    # --- analyst price targets (≈12mo) + implied return ---
    mean_t, med_t = info.get("targetMeanPrice"), info.get("targetMedianPrice")
    hi_t, lo_t = info.get("targetHighPrice"), info.get("targetLowPrice")
    n_an = info.get("numberOfAnalystOpinions")
    rec = info.get("recommendationKey")
    rec_mean = info.get("recommendationMean")
    if mean_t and cur:
        imp_mean = _fmt_pct(mean_t / cur - 1)
        imp_med = _fmt_pct(med_t / cur - 1) if med_t else "n/a"
        lines.append(
            f"Analyst targets (~12mo): mean {mean_t} ({imp_mean}), median {med_t} ({imp_med}), "
            f"high {hi_t}, low {lo_t} | {n_an} analysts | rec: {rec} ({rec_mean})"
        )

    # --- valuation multiples ---
    tpe, fpe = info.get("trailingPE"), info.get("forwardPE")
    peg = info.get("trailingPegRatio") or info.get("pegRatio")
    lines.append(f"Multiples: trailing P/E {tpe} | forward P/E {fpe} | PEG {peg}")

    teps, feps = info.get("trailingEps"), info.get("forwardEps")
    if teps and feps:
        lines.append(f"EPS: trailing {teps} | forward {feps} (implied {_fmt_pct(feps / teps - 1)} fwd EPS growth)")

    # --- shareholder yield ---
    dy, payout = info.get("dividendYield"), info.get("payoutRatio")
    if dy is not None:
        lines.append(f"Shareholder yield: dividend ~{dy}% | payout {payout}")

    # --- consensus growth (the key multi-year input) ---
    def _grow(df, period, col="growth"):
        try:
            return _fmt_pct(df.loc[period, col])
        except Exception:  # noqa: BLE001
            return "n/a"

    try:
        ee = t.earnings_estimate
        lines.append(f"Consensus EPS growth: current FY {_grow(ee, '0y')} | next FY {_grow(ee, '+1y')}")
    except Exception:  # noqa: BLE001
        pass
    try:
        re_ = t.revenue_estimate
        lines.append(f"Consensus revenue growth: current FY {_grow(re_, '0y')} | next FY {_grow(re_, '+1y')}")
    except Exception:  # noqa: BLE001
        pass
    try:
        ge = t.growth_estimates
        ltg = _grow(ge, "LTG", "stockTrend")
        if ltg != "n/a":
            lines.append(f"Long-term (3-5yr) growth estimate: {ltg}")
    except Exception:  # noqa: BLE001
        pass

    lines.append("NOTE: consensus estimates revise frequently and embed optimism bias — one input, not truth.")
    return "\n".join(lines)


def cmd_forward(args) -> None:
    try:
        _emit(_forward_block(args.ticker))
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: could not load forward estimates for {args.ticker}: {exc}")


def cmd_sentiment(args) -> None:
    """Bundle the three sentiment sources exactly like the sentiment analyst pre-fetch."""
    from tradingagents.dataflows.interface import route_to_vendor
    from tradingagents.dataflows.stocktwits import fetch_stocktwits_messages
    from tradingagents.dataflows.reddit import fetch_reddit_posts

    start = _seven_days_back(args.curr_date)
    news_block = route_to_vendor("get_news", args.ticker, start, args.curr_date)
    stocktwits_block = fetch_stocktwits_messages(args.ticker, limit=30)
    reddit_block = fetch_reddit_posts(args.ticker)

    print(f"### News headlines — past 7 days ({start} to {args.curr_date})")
    print("<start_of_news>")
    _emit(news_block)
    print("<end_of_news>\n")
    print("### StockTwits messages")
    print("<start_of_stocktwits>")
    _emit(stocktwits_block)
    print("<end_of_stocktwits>\n")
    print("### Reddit posts — r/wallstreetbets, r/stocks, r/investing")
    print("<start_of_reddit>")
    _emit(reddit_block)
    print("<end_of_reddit>")


def _section(title: str, body) -> str:
    """Wrap one data block with stable delimiters for the gather bundle."""
    bar = "=" * 70
    text = body if (body and str(body).strip()) else "NO_DATA: empty result."
    return f"{bar}\n## {title}\n{bar}\n{text}\n"


def cmd_gather(args) -> None:
    """Fetch the full analyst data set for TICKER on CURR_DATE in one pass.

    Each section is isolated: one source failing prints an ERROR line for that
    section but never aborts the bundle. This is the recommended entry point —
    Claude pulls everything once, then plays the agent roles over the result.
    """
    from tradingagents.dataflows.interface import route_to_vendor
    from tradingagents.dataflows.market_data_validator import build_verified_market_snapshot
    from tradingagents.dataflows.stocktwits import fetch_stocktwits_messages
    from tradingagents.dataflows.reddit import fetch_reddit_posts

    ticker, curr = args.ticker, args.curr_date
    price_start = (datetime.strptime(curr, "%Y-%m-%d") - timedelta(days=args.price_window)).strftime("%Y-%m-%d")
    news_start = _seven_days_back(curr)
    indicators = ["close_9_ema", "close_21_ema", "close_50_sma", "close_200_sma",
                   "close_10_ema", "macd", "rsi", "boll", "atr", "vwma"]
    is_crypto = ticker.upper().endswith(("-USD", "-USDT"))

    def safe(label, fn):
        try:
            return _section(label, fn())
        except Exception as exc:  # noqa: BLE001 — isolate per-section failures
            return _section(label, f"ERROR: {type(exc).__name__}: {exc}")

    print(f"# TradingAgents data bundle — {ticker} as of {curr}\n")

    # --- identity (lazy import; may pull langchain) ---
    try:
        from tradingagents.agents.utils.agent_utils import (
            resolve_instrument_identity, build_instrument_context,
        )
        ident = resolve_instrument_identity(ticker)
        ctx = build_instrument_context(ticker, "crypto" if is_crypto else "stock", ident)
    except Exception as exc:  # noqa: BLE001
        ctx = f"(identity resolver unavailable: {exc})"
    print(_section("INSTRUMENT IDENTITY", ctx))

    # --- market / technical ---
    print(safe("VERIFIED SNAPSHOT (source of truth)",
               lambda: build_verified_market_snapshot(ticker, curr, 30)))
    print(safe(f"PRICE HISTORY ({price_start} .. {curr})",
               lambda: route_to_vendor("get_stock_data", ticker, price_start, curr)))
    ind_out = []
    for ind in indicators:
        try:
            ind_out.append(route_to_vendor("get_indicators", ticker, ind, curr, 30))
        except Exception as exc:  # noqa: BLE001
            ind_out.append(f"ERROR for {ind}: {exc}")
    print(_section("TECHNICAL INDICATORS", "\n\n".join(ind_out)))

    # --- fundamentals (skipped for crypto) ---
    if is_crypto:
        print(_section("FUNDAMENTALS", "Skipped: crypto asset, company fundamentals not applicable."))
    else:
        print(safe("FORWARD ESTIMATES & VALUATION (12-36mo drivers)",
                   lambda: _forward_block(ticker)))
        print(safe("FUNDAMENTALS", lambda: route_to_vendor("get_fundamentals", ticker, curr)))
        print(safe("INCOME STATEMENT", lambda: route_to_vendor("get_income_statement", ticker, "quarterly", curr)))
        print(safe("BALANCE SHEET", lambda: route_to_vendor("get_balance_sheet", ticker, "quarterly", curr)))
        print(safe("CASH FLOW", lambda: route_to_vendor("get_cashflow", ticker, "quarterly", curr)))
        print(safe("INSIDER TRANSACTIONS", lambda: route_to_vendor("get_insider_transactions", ticker)))

    # --- news ---
    print(safe(f"TICKER NEWS ({news_start} .. {curr})",
               lambda: route_to_vendor("get_news", ticker, news_start, curr)))
    print(safe("GLOBAL / MACRO NEWS",
               lambda: route_to_vendor("get_global_news", curr, None, None)))

    # --- sentiment social sources ---
    print(safe("STOCKTWITS", lambda: fetch_stocktwits_messages(ticker, limit=30)))
    print(safe("REDDIT", lambda: fetch_reddit_posts(ticker)))

    print(f"\n# End of bundle — {ticker} @ {curr}")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="ta_data.py", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="command", required=True)

    s = sub.add_parser("gather", help="one-shot: fetch the full analyst data set for TICKER on CURR_DATE")
    s.add_argument("ticker"); s.add_argument("curr_date")
    s.add_argument("--price-window", type=int, default=90, help="days of price history (default 90)")
    s.set_defaults(func=cmd_gather)

    s = sub.add_parser("identity", help="resolve deterministic company/asset identity")
    s.add_argument("ticker")
    s.set_defaults(func=cmd_identity)

    s = sub.add_parser("stock_data", help="OHLCV price data over a date range")
    s.add_argument("symbol"); s.add_argument("start_date"); s.add_argument("end_date")
    s.set_defaults(func=cmd_stock_data)

    s = sub.add_parser("indicators", help="technical indicator(s); comma-separate names")
    s.add_argument("symbol"); s.add_argument("indicator"); s.add_argument("curr_date")
    s.add_argument("look_back_days", nargs="?", type=int, default=30)
    s.set_defaults(func=cmd_indicators)

    s = sub.add_parser("snapshot", help="verified OHLCV+indicator snapshot (source of truth)")
    s.add_argument("symbol"); s.add_argument("curr_date")
    s.add_argument("look_back_days", nargs="?", type=int, default=30)
    s.set_defaults(func=cmd_snapshot)

    s = sub.add_parser("fundamentals", help="comprehensive fundamentals report")
    s.add_argument("ticker"); s.add_argument("curr_date")
    s.set_defaults(func=cmd_fundamentals)

    for name, fn in (("balance_sheet", cmd_balance_sheet),
                     ("cashflow", cmd_cashflow),
                     ("income_statement", cmd_income_statement)):
        s = sub.add_parser(name, help=f"{name.replace('_', ' ')} statement")
        s.add_argument("ticker")
        s.add_argument("freq", nargs="?", default="quarterly", help="annual|quarterly")
        s.add_argument("curr_date", nargs="?", default=None)
        s.set_defaults(func=fn)

    s = sub.add_parser("news", help="ticker-specific news over a date range")
    s.add_argument("ticker"); s.add_argument("start_date"); s.add_argument("end_date")
    s.set_defaults(func=cmd_news)

    s = sub.add_parser("global_news", help="macro/global news")
    s.add_argument("curr_date")
    s.add_argument("look_back_days", nargs="?", type=int, default=None)
    s.add_argument("limit", nargs="?", type=int, default=None)
    s.set_defaults(func=cmd_global_news)

    s = sub.add_parser("insider", help="insider transactions")
    s.add_argument("ticker")
    s.set_defaults(func=cmd_insider)

    s = sub.add_parser("stocktwits", help="recent StockTwits messages")
    s.add_argument("ticker"); s.add_argument("limit", nargs="?", type=int, default=30)
    s.set_defaults(func=cmd_stocktwits)

    s = sub.add_parser("reddit", help="recent Reddit posts across finance subs")
    s.add_argument("ticker")
    s.set_defaults(func=cmd_reddit)

    s = sub.add_parser("sentiment", help="news+stocktwits+reddit bundle (sentiment analyst inputs)")
    s.add_argument("ticker"); s.add_argument("curr_date")
    s.set_defaults(func=cmd_sentiment)

    s = sub.add_parser("forward", help="analyst targets, forward multiples & consensus growth (12-36mo inputs)")
    s.add_argument("ticker")
    s.set_defaults(func=cmd_forward)

    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    try:
        args.func(args)
    except Exception as exc:  # noqa: BLE001 — never crash with a bare traceback
        print(f"ERROR: {type(exc).__name__}: {exc}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
