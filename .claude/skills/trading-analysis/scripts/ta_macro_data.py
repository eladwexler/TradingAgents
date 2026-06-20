#!/usr/bin/env python3
"""Macro data CLI for the ai-cycle-watch skill.

Fetches quantitative macro indicators (Treasury yields, GPU proxy metrics, Mag7 Valuations)
to replace qualitative WebSearches with hard programmatic data.
"""

import argparse
import sys

try:
    import yfinance as yf
except ImportError:
    print("ERROR: yfinance is required. Run: pip install yfinance", file=sys.stderr)
    sys.exit(1)


def _emit(text: str) -> None:
    if not text or not str(text).strip():
        print("NO_DATA: vendor returned an empty result.")
        return
    print(text)

def cmd_macro(args) -> None:
    """Fetch 10-year treasury yield and High Yield bond proxy."""
    lines = ["## MACRO INDICATORS"]
    
    # 10-Year Treasury Yield (^TNX)
    try:
        tnx = yf.Ticker("^TNX")
        tnx_price = tnx.info.get("regularMarketPrice") or tnx.info.get("currentPrice") or tnx.fast_info.get("last_price")
        if tnx_price:
            lines.append(f"10-Year Treasury Yield (^TNX): {tnx_price:.2f}%")
        else:
            lines.append("10-Year Treasury Yield (^TNX): NO_DATA")
    except Exception as e:
        lines.append(f"10-Year Treasury Yield (^TNX): ERROR ({e})")

    # High Yield Corporate Bond ETF (HYG)
    try:
        hyg = yf.Ticker("HYG")
        hyg_price = hyg.info.get("regularMarketPrice") or hyg.info.get("currentPrice") or hyg.fast_info.get("last_price")
        if hyg_price:
            lines.append(f"High Yield Bond ETF Proxy (HYG): ${hyg_price:.2f}")
        else:
            lines.append("High Yield Bond ETF Proxy (HYG): NO_DATA")
    except Exception as e:
        lines.append(f"High Yield Bond ETF Proxy (HYG): ERROR ({e})")

    _emit("\n".join(lines))

def cmd_valuation(args) -> None:
    """Fetch average Forward P/E for the Mag7 basket."""
    lines = ["## MAG7 VALUATION HEATMAP"]
    mag7_tickers = ["MSFT", "AAPL", "NVDA", "GOOGL", "AMZN", "META", "TSLA"]
    forward_pes = []
    
    for ticker in mag7_tickers:
        try:
            t = yf.Ticker(ticker)
            fpe = t.info.get("forwardPE")
            if fpe:
                forward_pes.append(fpe)
                lines.append(f"{ticker} Forward P/E: {fpe:.2f}")
        except Exception:
            pass
            
    if forward_pes:
        avg_fpe = sum(forward_pes) / len(forward_pes)
        lines.append(f"**Mag7 Average Forward P/E: {avg_fpe:.2f}**")
    else:
        lines.append("Mag7 Average Forward P/E: NO_DATA")
        
    _emit("\n".join(lines))

def cmd_software_canary(args) -> None:
    """Fetch revenue growth for the Application/Software canary basket."""
    lines = ["## SOFTWARE / APPLICATION CANARY (Phase 3 ROI)"]
    # Proxies for software layer
    software_tickers = ["PLTR", "CRM", "SNOW", "PATH"]
    lines.append(f"Basket: {', '.join(software_tickers)}")
    
    for ticker in software_tickers:
        try:
            t = yf.Ticker(ticker)
            rev_growth = t.info.get("revenueGrowth")
            if rev_growth is not None:
                lines.append(f"{ticker} YoY Revenue Growth: {rev_growth * 100:.1f}%")
        except Exception:
            pass

    _emit("\n".join(lines))

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="ta_macro_data.py", description=__doc__)
    sub = p.add_subparsers(dest="command", required=True)

    s = sub.add_parser("macro", help="Fetch 10-year treasury yield and High Yield bond proxy")
    s.set_defaults(func=cmd_macro)

    s = sub.add_parser("valuation", help="Fetch Mag7 Valuation Heatmap (Forward P/E)")
    s.set_defaults(func=cmd_valuation)

    s = sub.add_parser("software_canary", help="Fetch YoY Revenue Growth for software wrappers")
    s.set_defaults(func=cmd_software_canary)

    return p

def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    if not hasattr(args, "func"):
        build_parser().print_help()
        return 1
    try:
        args.func(args)
    except Exception as exc:
        print(f"ERROR: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    return 0

if __name__ == "__main__":
    sys.exit(main())
