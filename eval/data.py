"""Thin, self-contained, keyless yfinance price wrapper for the eval harness.

Deliberately has NO imports from the `tradingagents` package or the skill scripts,
so the benchmark can never write into or otherwise pollute the live analysis.
Daily closes are cached to disk under the configured cache_dir as plain CSV.
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta
from typing import Optional

import pandas as pd


def _cache_path(cache_dir: str, ticker: str) -> str:
    os.makedirs(cache_dir, exist_ok=True)
    safe = ticker.replace("/", "_").replace(".", "_")
    return os.path.join(cache_dir, f"{safe}.csv")


def get_closes(ticker: str, start: str, end: str, cache_dir: str) -> Optional[pd.Series]:
    """Return a tz-naive daily Close series for [start, end], or None if no data.

    Pads the request a little so the as-of and target dates are covered even when
    they land on weekends/holidays. Caches the full pull per ticker.
    """
    path = _cache_path(cache_dir, ticker)
    pad_start = (datetime.strptime(start, "%Y-%m-%d") - timedelta(days=400)).strftime("%Y-%m-%d")
    pad_end = (datetime.strptime(end, "%Y-%m-%d") + timedelta(days=7)).strftime("%Y-%m-%d")

    df: Optional[pd.DataFrame] = None
    if os.path.exists(path):
        try:
            cached = pd.read_csv(path, index_col=0, parse_dates=True)
            have_start, have_end = cached.index.min(), cached.index.max()
            if have_start <= pd.Timestamp(pad_start) and have_end >= pd.Timestamp(end):
                df = cached
        except Exception:  # noqa: BLE001 — corrupt cache → refetch
            df = None

    if df is None:
        import yfinance as yf
        try:
            raw = yf.Ticker(ticker).history(start=pad_start, end=pad_end, auto_adjust=True)
        except Exception as exc:  # noqa: BLE001
            print(f"WARN: fetch failed for {ticker}: {exc}")
            return None
        if raw is None or raw.empty or "Close" not in raw:
            return None
        df = raw[["Close"]].copy()
        df.index = df.index.tz_localize(None)
        df.to_csv(path)

    s = df["Close"].dropna()
    s.index = pd.to_datetime(s.index).tz_localize(None)
    return s if not s.empty else None


def close_on_or_before(s: pd.Series, date_str: str) -> Optional[float]:
    """Last close at or before `date_str` (handles weekends/holidays)."""
    if s is None or s.empty:
        return None
    cutoff = pd.Timestamp(date_str)
    sub = s[s.index <= cutoff]
    return float(sub.iloc[-1]) if not sub.empty else None


def close_on_or_after(s: pd.Series, date_str: str) -> Optional[float]:
    if s is None or s.empty:
        return None
    cutoff = pd.Timestamp(date_str)
    sub = s[s.index >= cutoff]
    return float(sub.iloc[0]) if not sub.empty else None


def forward_return(s: pd.Series, as_of: str, end: str) -> Optional[float]:
    """Buy-and-hold return from the close on/before `as_of` to close on/before `end`."""
    p0 = close_on_or_before(s, as_of)
    p1 = close_on_or_before(s, end)
    if p0 is None or p1 is None or p0 <= 0:
        return None
    return p1 / p0 - 1.0
