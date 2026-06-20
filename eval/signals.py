"""Point-in-time mechanical signals.

Every signal is computed from prices *up to and including* the as-of date only —
nothing here can see the future. These are the price/trend factor families the
platform's technical analysts lean on, reduced to deterministic rules so they can
be scored without any LLM hindsight.

Valuation factors are intentionally excluded: keyless point-in-time fundamentals
are not available, and substituting today's P/E for a past as-of date would be
lookahead bias.
"""
from __future__ import annotations

from typing import Optional

import pandas as pd


def _hist(s: pd.Series, as_of: str) -> pd.Series:
    """Closes strictly up to and including the as-of date."""
    return s[s.index <= pd.Timestamp(as_of)]


def momentum(s: pd.Series, as_of: str, lookback: int) -> Optional[float]:
    """Total return over the trailing `lookback` trading days (12-1 style if used)."""
    h = _hist(s, as_of)
    if len(h) < lookback + 1:
        return None
    p_now, p_then = float(h.iloc[-1]), float(h.iloc[-1 - lookback])
    return p_now / p_then - 1.0 if p_then > 0 else None


def dist_from_ma(s: pd.Series, as_of: str, window: int) -> Optional[float]:
    """(price / N-day moving average) - 1. Positive = above trend."""
    h = _hist(s, as_of)
    if len(h) < window:
        return None
    ma = float(h.iloc[-window:].mean())
    p = float(h.iloc[-1])
    return p / ma - 1.0 if ma > 0 else None


def compute_all(s: pd.Series, as_of: str, cfg: dict) -> dict:
    """All point-in-time signals for one name at one as-of date."""
    sg = cfg["signals"]
    return {
        "mom_12m": momentum(s, as_of, sg["momentum_12m_lookback"]),
        "mom_6m": momentum(s, as_of, sg["momentum_6m_lookback"]),
        "dist_200dma": dist_from_ma(s, as_of, sg["ma_long"]),
    }


SIGNAL_NAMES = ["mom_12m", "mom_6m", "dist_200dma"]
