"""Deterministic market-data verification snapshot.

The market analyst is an LLM that can confabulate exact numbers — citing a
Bollinger band or a "historically validated bounce" that the underlying data
doesn't support (#830). This module computes a ground-truth snapshot (latest
OHLCV row on or before the analysis date, common indicators, recent closes)
the analyst is told to treat as the source of truth for any exact numeric
claim. Deterministic, no LLM involved.
"""

from __future__ import annotations

from typing import Iterable, Optional

import pandas as pd
from stockstats import wrap

from tradingagents.dataflows.stockstats_utils import load_ohlcv

# A fixed, common indicator set so the snapshot is the same shape every run.
DEFAULT_SNAPSHOT_INDICATORS: tuple[str, ...] = (
    "close_9_ema", "close_21_ema", "close_10_ema", "close_50_sma", "close_200_sma",
    "rsi", "boll", "boll_ub", "boll_lb",
    "macd", "macds", "macdh", "atr",
)


def _verified_rows(symbol: str, curr_date: str) -> pd.DataFrame:
    """OHLCV on or before curr_date, date-sorted. Raises if nothing usable.

    ``load_ohlcv`` already normalizes the Date column and filters out
    look-ahead rows, but we re-apply the cutoff defensively — this is a
    verification path, so it must not trust its input to be pre-filtered.
    """
    data = load_ohlcv(symbol, curr_date)
    if data is None or data.empty:
        raise ValueError(f"No OHLCV data available for {symbol}.")

    df = data.copy()
    df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
    df = df.dropna(subset=["Date"])
    df = df[df["Date"] <= pd.to_datetime(curr_date)].sort_values("Date")
    if df.empty:
        raise ValueError(f"No OHLCV rows on or before {curr_date} for {symbol}.")
    return df


def _fmt(value) -> str:
    if value is None or pd.isna(value):
        return "N/A"
    if isinstance(value, pd.Timestamp):
        return value.strftime("%Y-%m-%d")
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, (int,)):
        return str(value)
    if isinstance(value, float):
        return f"{value:.2f}"
    return str(value)


def build_verified_market_snapshot(
    symbol: str,
    curr_date: str,
    look_back_days: int = 30,
    indicators: Optional[Iterable[str]] = None,
) -> str:
    """Render a ground-truth snapshot: latest OHLCV row, indicators, recent closes."""
    # `df` keeps the original capitalized OHLCV columns (Open/High/Low/Close/
    # Volume); stockstats `wrap()` lowercases columns and adds indicator
    # columns, so read raw prices from `df` and indicators from `stock_df`.
    df = _verified_rows(symbol, curr_date)
    stock_df = wrap(df.copy())

    selected = tuple(indicators or DEFAULT_SNAPSHOT_INDICATORS)
    indicator_values: dict[str, str] = {}
    for name in selected:
        try:
            stock_df[name]  # triggers stockstats calculation
            indicator_values[name] = _fmt(stock_df.iloc[-1][name])
        except Exception as exc:  # noqa: BLE001 — one bad indicator shouldn't sink the snapshot
            indicator_values[name] = f"N/A ({type(exc).__name__})"

    latest = df.iloc[-1]
    latest_date = _fmt(latest["Date"])
    window = max(1, min(int(look_back_days), 30))
    recent = df.tail(window)

    lines = [
        f"## Verified market data snapshot for {symbol.upper()}",
        "",
        f"- Requested analysis date: {curr_date}",
        f"- Latest trading row used: {latest_date}",
        "- Rows after the requested analysis date are excluded before verification.",
        "",
        "### Latest verified OHLCV row",
        "",
        "| Field | Value |",
        "|---|---:|",
    ]
    for field in ("Open", "High", "Low", "Close", "Volume"):
        lines.append(f"| {field} | {_fmt(latest.get(field))} |")

    lines += ["", "### Verified technical indicators (latest row)", "",
              "| Indicator | Value |", "|---|---:|"]
    for name, value in indicator_values.items():
        lines.append(f"| {name} | {value} |")

    lines += ["", f"### Recent verified closes (last {len(recent)} rows)", "",
              "| Date | Close |", "|---|---:|"]
    for _, row in recent.iterrows():
        lines.append(f"| {_fmt(row['Date'])} | {_fmt(row.get('Close'))} |")

    lines += [
        "",
        "Use this snapshot as the source of truth for exact OHLCV, price-level, "
        "and indicator-value claims. If another tool output conflicts with it, "
        "flag the discrepancy rather than inventing a reconciled number. Do not "
        "claim historical validation, support/resistance bounces, or exact "
        "percentage moves unless directly supported by tool output with concrete "
        "dates and prices.",
    ]

    # --- Shay Boloor Verdict (trend-structure classification) ---
    trend_block = _classify_trend_structure(
        latest.get("Close"), indicator_values, stock_df, df,
    )
    lines += ["", trend_block]

    return "\n".join(lines)


# Number of trading days to look back when measuring SMA slope direction.
_SLOPE_LOOKBACK = 10

# Extension threshold: price this far above the 21 EMA flags stretched
# risk/reward (especially relevant for AI-infra momentum names).
_EXTENSION_WARN_PCT = 15.0   # %
_EXTENSION_DANGER_PCT = 25.0  # %


def _classify_trend_structure(
    close: Optional[float],
    indicator_values: dict[str, str],
    stock_df: pd.DataFrame,
    df: pd.DataFrame,
) -> str:
    """Classify the stock into Bullish / Hold / Bearish using the
    9-EMA / 21-EMA / 50-SMA / 200-SMA trend-structure algorithm, with
    three additional quality checks:

    1. **SMA slope** — a rising 50 SMA + 200 SMA strengthens the signal;
       a flat or declining 200 SMA weakens it.
    2. **Volume confirmation** — a breakout with above-average volume is
       stronger than one on thin volume.
    3. **Extension warning** — even in a bullish structure, price stretched
       far above the 21 EMA means risk/reward is worse for new entries.
       Critical for AI-infra momentum names with huge run-ups.

    Core rules
    ----------
    * **BULLISH** — 9-EMA > 21-EMA AND price ≥ 50-SMA AND price ≥ 200-SMA.
    * **HOLD** — price ≥ 200-SMA but the bullish conditions are not fully met.
    * **BEARISH** — price < 200-SMA.
    """
    def _parse(key: str) -> Optional[float]:
        raw = indicator_values.get(key)
        if raw is None or raw.startswith("N/A"):
            return None
        try:
            return float(raw)
        except (ValueError, TypeError):
            return None

    ema9  = _parse("close_9_ema")
    ema21 = _parse("close_21_ema")
    sma50 = _parse("close_50_sma")
    sma200 = _parse("close_200_sma")

    lines = ["### Shay Boloor Verdict (Daily Timeframe: 9 EMA / 21 EMA / 50 SMA / 200 SMA)"]

    # ---- Table of levels ----
    lines += ["", "| Level | Value | Price vs Level |", "|---|---:|---|"]
    for label, val in (("9 EMA", ema9), ("21 EMA", ema21),
                        ("50 SMA", sma50), ("200 SMA", sma200)):
        if val is not None and close is not None and not pd.isna(close):
            pct = (close - val) / val * 100
            status = "ABOVE" if close >= val else "BELOW"
            lines.append(f"| {label} | {val:.2f} | {status} ({pct:+.1f}%) |")
        elif val is not None:
            lines.append(f"| {label} | {val:.2f} | (price N/A) |")
        else:
            lines.append(f"| {label} | N/A | N/A |")

    # ---- Momentum check ----
    if ema9 is not None and ema21 is not None:
        if ema9 > ema21:
            momentum = "🟢 9 EMA > 21 EMA → short-term momentum is bullish"
        else:
            momentum = "🟡 9 EMA ≤ 21 EMA → short-term momentum has faded"
        lines.append(f"\n**Momentum:** {momentum}")

    # ---- Qualifier 1: SMA slope direction ----
    slope_notes: list[str] = []
    try:
        if len(stock_df) > _SLOPE_LOOKBACK:
            prev_idx = -1 - _SLOPE_LOOKBACK
            for col, label in (("close_50_sma", "50 SMA"), ("close_200_sma", "200 SMA")):
                if col in stock_df.columns:
                    curr_val = stock_df.iloc[-1][col]
                    prev_val = stock_df.iloc[prev_idx][col]
                    if pd.notna(curr_val) and pd.notna(prev_val) and prev_val != 0:
                        chg = (curr_val - prev_val) / prev_val * 100
                        if chg > 0.1:
                            slope_notes.append(f"{label} ↑ rising ({chg:+.2f}% over {_SLOPE_LOOKBACK}d)")
                        elif chg < -0.1:
                            slope_notes.append(f"{label} ↓ declining ({chg:+.2f}% over {_SLOPE_LOOKBACK}d)")
                        else:
                            slope_notes.append(f"{label} → flat ({chg:+.2f}% over {_SLOPE_LOOKBACK}d)")
    except Exception:  # noqa: BLE001
        pass

    if slope_notes:
        quality_icon = "🟢" if all("↑" in n for n in slope_notes) else (
            "🔴" if all("↓" in n for n in slope_notes) else "🟡"
        )
        lines.append(f"\n**SMA Slope Quality:** {quality_icon} {' · '.join(slope_notes)}")

    # ---- Qualifier 2: Volume confirmation ----
    try:
        vol_col = "Volume" if "Volume" in df.columns else "volume"
        if vol_col in df.columns and len(df) >= 20:
            latest_vol = df.iloc[-1][vol_col]
            avg_vol_20 = df[vol_col].tail(20).mean()
            if pd.notna(latest_vol) and pd.notna(avg_vol_20) and avg_vol_20 > 0:
                vol_ratio = latest_vol / avg_vol_20
                if vol_ratio >= 1.5:
                    vol_note = f"🟢 Latest volume {vol_ratio:.1f}× the 20-day average — strong confirmation"
                elif vol_ratio >= 1.0:
                    vol_note = f"🟢 Latest volume {vol_ratio:.1f}× the 20-day average — adequate"
                elif vol_ratio >= 0.7:
                    vol_note = f"🟡 Latest volume {vol_ratio:.1f}× the 20-day average — thin, less conviction"
                else:
                    vol_note = f"🔴 Latest volume {vol_ratio:.1f}× the 20-day average — very low participation"
                lines.append(f"\n**Volume:** {vol_note}")
    except Exception:  # noqa: BLE001
        pass

    # ---- Qualifier 3: Extension warning ----
    extension_note = ""
    if close is not None and ema21 is not None and not pd.isna(close) and ema21 > 0:
        ext_pct = (close - ema21) / ema21 * 100
        if ext_pct >= _EXTENSION_DANGER_PCT:
            extension_note = (
                f"🔴 **EXTENDED — price is {ext_pct:+.1f}% above the 21 EMA.** "
                "Momentum is strong but risk/reward for *new* entries is poor. "
                "The 9/21 EMA gap is stretched — common trap in AI-infra momentum "
                "names after explosive moves. Wait for a pullback toward the 21 EMA."
            )
        elif ext_pct >= _EXTENSION_WARN_PCT:
            extension_note = (
                f"🟡 **Caution — price is {ext_pct:+.1f}% above the 21 EMA.** "
                "Trend is bullish but getting stretched. Size smaller on new entries "
                "and be aware the gap between price and the 21 EMA needs to compress."
            )
    if extension_note:
        lines.append(f"\n**Extension Check:** {extension_note}")

    # ---- Core classification ----
    if close is None or pd.isna(close):
        verdict = "⚠️ **SHAY BOLOOR VERDICT: UNKNOWN** (price unavailable)"
    elif any(v is None for v in (ema9, ema21, sma50, sma200)):
        verdict = "⚠️ **SHAY BOLOOR VERDICT: INCOMPLETE** (one or more indicator values unavailable)"
    elif ema9 > ema21 and close >= sma50 and close >= sma200:
        verdict = (
            "🟢 **SHAY BOLOOR VERDICT: BULLISH** — 9 EMA > 21 EMA and price is holding "
            "both the 50 SMA and 200 SMA. Momentum + structure aligned upward."
        )
    elif close >= sma200:
        verdict = (
            "🟡 **SHAY BOLOOR VERDICT: HOLD** — price is holding the 200 SMA (long-term "
            "trend intact) but momentum conditions are not fully bullish. "
            "Wait for the 9 EMA to recross above the 21 EMA with price reclaiming the 50 SMA."
        )
    else:
        verdict = (
            "🔴 **SHAY BOLOOR VERDICT: BEARISH** — price has broken below the 200 SMA; "
            "short- and intermediate-term momentum is down. Timing signal only: this "
            "argues for waiting on a *new* entry, not selling — for a durable-growth "
            "thesis a sub-200-SMA price can be an accumulation zone, not a sell."
        )
    lines.append(f"\n{verdict}")
    return "\n".join(lines)
