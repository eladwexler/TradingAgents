"""Scoring metrics for the benchmark.

All metrics are computed cross-sectionally (across the universe) and compared to
the dumb nulls a real predictor must beat: buy-SPY, coin-flip P=0.5, and the
equal-weight basket.
"""
from __future__ import annotations

import math
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd


def hit_rate_vs_benchmark(name_rets: Dict[str, float], bench_ret: float) -> Tuple[float, int]:
    """Fraction of names that beat the benchmark over the window."""
    vals = [r for r in name_rets.values() if r is not None]
    if not vals:
        return float("nan"), 0
    wins = sum(1 for r in vals if r > bench_ret)
    return wins / len(vals), len(vals)


def spearman_ic(signal: Dict[str, float], fwd: Dict[str, float]) -> Optional[float]:
    """Rank correlation between a signal and forward returns across names."""
    pairs = [(signal[t], fwd[t]) for t in signal
             if t in fwd and signal[t] is not None and fwd[t] is not None]
    if len(pairs) < 5:
        return None
    # Spearman = Pearson on ranks. Computed directly to avoid a scipy dependency.
    s = pd.Series([p[0] for p in pairs]).rank()
    f = pd.Series([p[1] for p in pairs]).rank()
    if s.std(ddof=0) == 0 or f.std(ddof=0) == 0:
        return None
    ic = float(np.corrcoef(s.values, f.values)[0, 1])
    return None if math.isnan(ic) else ic


def quintile_spread(signal: Dict[str, float], fwd: Dict[str, float], q: int = 5
                    ) -> Optional[Dict[str, float]]:
    """Mean forward return of the top signal-quintile minus the bottom."""
    pairs = [(signal[t], fwd[t]) for t in signal
             if t in fwd and signal[t] is not None and fwd[t] is not None]
    if len(pairs) < q * 2:
        return None
    df = pd.DataFrame(pairs, columns=["sig", "fwd"]).sort_values("sig")
    n = len(df)
    k = max(1, n // q)
    bottom = df.head(k)["fwd"].mean()
    top = df.tail(k)["fwd"].mean()
    return {"top_mean": float(top), "bottom_mean": float(bottom),
            "spread": float(top - bottom), "bucket_n": int(k)}


def signal_to_prob(signal: Dict[str, float]) -> Dict[str, float]:
    """Map a cross-sectional signal to P(beat benchmark) via percentile rank.

    A higher-ranked name gets a higher probability. This is the most charitable
    way to turn a raw factor into a calibrated-style probability, so the Brier
    comparison against the 0.5 null is fair.
    """
    items = [(t, v) for t, v in signal.items() if v is not None]
    if len(items) < 2:
        return {}
    ser = pd.Series({t: v for t, v in items})
    ranks = ser.rank(pct=True)  # 0..1
    # squeeze toward [0.15, 0.85] so we never assert near-certainty from a factor
    return {t: float(0.15 + 0.70 * r) for t, r in ranks.items()}


def brier(probs: Dict[str, float], outcomes: Dict[str, int]) -> Optional[float]:
    """Mean squared error of P(beat) vs realized beat(1)/miss(0)."""
    pairs = [(probs[t], outcomes[t]) for t in probs if t in outcomes]
    if not pairs:
        return None
    return float(np.mean([(p - o) ** 2 for p, o in pairs]))


def basket_return(name_rets: Dict[str, float]) -> Optional[float]:
    vals = [r for r in name_rets.values() if r is not None]
    return float(np.mean(vals)) if vals else None


def basket_stats(name_rets: Dict[str, float], cap: float = 3.0) -> Optional[Dict[str, float]]:
    """Robust views of the equal-weight basket so a few outliers don't define the bar.

    `cap` winsorizes each name's return to [-0.9, +cap] before averaging — this is
    the honest "bar" when the universe contains microcaps/shells whose raw returns
    (e.g. +4000%) are likely data artifacts, not investable outcomes.
    """
    vals = [r for r in name_rets.values() if r is not None]
    if not vals:
        return None
    arr = np.array(vals)
    capped = np.clip(arr, -0.9, cap)
    return {
        "mean": float(arr.mean()),
        "median": float(np.median(arr)),
        "winsorized_mean": float(capped.mean()),
        "cap": cap,
    }


def outliers(name_rets: Dict[str, float], threshold: float = 5.0) -> Dict[str, float]:
    """Names whose 12m return exceeds `threshold` (e.g. +500%) — flag as suspect."""
    return {t: r for t, r in name_rets.items() if r is not None and r > threshold}
