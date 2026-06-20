#!/usr/bin/env python3
"""Persistent decision log for the trading-analysis skill — no LLM, no API key.

Writes a markdown log **byte-compatible** with TradingAgents'
``~/.tradingagents/memory/trading_memory.md`` (see
``tradingagents/agents/utils/memory.py``). It is vendored standalone here —
same separator, tag format, DECISION/REFLECTION sections, and 5-tier rating
heuristic — so it stays stdlib-only (plus yfinance for return math) instead of
dragging in the project's langchain package via ``tradingagents.agents``.

Round trip:
  1. recall   TICKER                      -> past same-ticker + cross-ticker lessons
                                              (inject at the START of an analysis)
  2. log      TICKER DATE [--file f]       -> append a pending decision entry
                                              (run at the END, decision via stdin/file)
  3. pending  [TICKER]                     -> list entries awaiting an outcome
  4. returns  TICKER DATE [--holding-days N]-> compute raw/alpha return from prices
  5. resolve  TICKER DATE --reflection-file f [--holding-days N]
                                            -> attach realised return + Claude's
                                               one-paragraph reflection to a
                                               pending entry (atomic rewrite)

Path resolution matches the project: $TRADINGAGENTS_MEMORY_LOG_PATH, else
~/.tradingagents/memory/trading_memory.md. Override per-call with --path.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Optional

# --- format constants (must match tradingagents/agents/utils/memory.py) ----
_SEPARATOR = "\n\n<!-- ENTRY_END -->\n\n"
_DECISION_RE = re.compile(r"DECISION:\n(.*?)(?=\nREFLECTION:|\Z)", re.DOTALL)
_REFLECTION_RE = re.compile(r"REFLECTION:\n(.*?)$", re.DOTALL)

# --- post-mortem error taxonomy (separates a flawed PROCESS from bad luck) ---
# Stored on a resolved entry as the `E=` token so misses can be aggregated by cause.
#   luck        - unforecastable shock; the process was sound -> do NOT learn from it
#   thesis      - mis-judged fundamentals / valuation / moat   -> fix the analysis
#   calibration - right direction but over-confident P / sizing -> fix the numbers
#   timing      - right thesis, wrong entry                     -> entry/Shay lesson
#   none        - call was correct / no error to record
ERROR_CLASSES = ("luck", "thesis", "calibration", "timing", "none")

# --- 5-tier rating heuristic (mirrors tradingagents/agents/utils/rating.py) -
RATINGS_5_TIER = ("Buy", "Overweight", "Hold", "Underweight", "Sell")
_RATING_SET = {r.lower() for r in RATINGS_5_TIER}
_RATING_LABEL_RE = re.compile(r"rating.*?[:\-][\s*]*(\w+)", re.IGNORECASE)

# --- benchmark map (mirrors tradingagents/default_config.py) ----------------
_BENCHMARK_MAP = {
    ".NS": "^NSEI", ".BO": "^BSESN", ".T": "^N225", ".HK": "^HSI",
    ".L": "^FTSE", ".TO": "^GSPTSE", ".AX": "^AXJO",
    ".SS": "000001.SS", ".SZ": "399001.SZ", "": "SPY",
}


def parse_rating(text: str, default: str = "Hold") -> str:
    """Extract a 5-tier rating: explicit 'Rating: X' label, else first rating word."""
    for line in text.splitlines():
        m = _RATING_LABEL_RE.search(line)
        if m and m.group(1).lower() in _RATING_SET:
            return m.group(1).title()
    for word in re.findall(r"[A-Za-z]+", text):
        if word.lower() in _RATING_SET:
            return word.title()
    return default


def resolve_benchmark(ticker: str) -> str:
    env = os.environ.get("TRADINGAGENTS_BENCHMARK_TICKER")
    if env:
        return env
    up = ticker.upper()
    for suffix, bench in _BENCHMARK_MAP.items():
        if suffix and up.endswith(suffix.upper()):
            return bench
    return _BENCHMARK_MAP[""]


def _default_path() -> Path:
    p = os.environ.get("TRADINGAGENTS_MEMORY_LOG_PATH")
    if p:
        return Path(p).expanduser()
    return Path(os.path.expanduser("~")) / ".tradingagents" / "memory" / "trading_memory.md"


class DecisionLog:
    """Append-only markdown log of trading decisions and reflections."""

    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    # --- write ---
    def store_decision(self, ticker: str, trade_date: str, decision: str,
                       prob: Optional[float] = None,
                       horizon_months: Optional[int] = None) -> bool:
        """Append a pending entry. Idempotent on (date, ticker). Returns False if dup.

        ``prob`` is P(beats benchmark over the horizon) and ``horizon_months`` is
        the forecast horizon — both stored as ``key=value`` tokens so the
        prediction can be scored for calibration once it resolves.
        """
        prefix = f"[{trade_date} | {ticker} |"
        if self.path.exists():
            for line in self.path.read_text(encoding="utf-8").splitlines():
                if line.startswith(prefix) and "| pending" in line:
                    return False
        rating = parse_rating(decision)
        tag = f"[{trade_date} | {ticker} | {rating} | pending"
        if prob is not None:
            tag += f" | P={prob:.2f}"
        if horizon_months:
            tag += f" | H={horizon_months}mo"
        tag += "]"
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(f"{tag}\n\nDECISION:\n{decision}{_SEPARATOR}")
        return True

    # --- read ---
    def load_entries(self) -> List[dict]:
        if not self.path.exists():
            return []
        text = self.path.read_text(encoding="utf-8")
        out = []
        for raw in (e.strip() for e in text.split(_SEPARATOR) if e.strip()):
            parsed = self._parse_entry(raw)
            if parsed:
                out.append(parsed)
        return out

    def get_pending(self, ticker: Optional[str] = None) -> List[dict]:
        return [e for e in self.load_entries()
                if e["pending"] and (ticker is None or e["ticker"] == ticker)]

    def get_past_context(self, ticker: str, n_same: int = 5, n_cross: int = 3) -> str:
        entries = [e for e in self.load_entries() if not e["pending"]]
        if not entries:
            return ""
        same, cross = [], []
        for e in reversed(entries):
            if len(same) >= n_same and len(cross) >= n_cross:
                break
            if e["ticker"] == ticker and len(same) < n_same:
                same.append(e)
            elif e["ticker"] != ticker and len(cross) < n_cross:
                cross.append(e)
        parts = []
        if same:
            parts.append(f"Past analyses of {ticker} (most recent first):")
            parts.extend(self._format_full(e) for e in same)
        if cross:
            parts.append("Recent cross-ticker lessons:")
            parts.extend(self._format_reflection_only(e) for e in cross)
        return "\n\n".join(parts)

    # --- update (Phase B) ---
    def update_with_outcome(self, ticker, trade_date, raw_return, alpha_return,
                            holding_days, reflection, cagr=None, error_class=None) -> bool:
        if not self.path.exists():
            return False
        blocks = self.path.read_text(encoding="utf-8").split(_SEPARATOR)
        prefix = f"[{trade_date} | {ticker} |"
        raw_pct, alpha_pct = f"{raw_return:+.1%}", f"{alpha_return:+.1%}"
        updated, new_blocks = False, []
        for block in blocks:
            s = block.strip()
            if not s:
                new_blocks.append(block); continue
            lines = s.splitlines()
            tag = lines[0].strip()
            if not updated and tag.startswith(prefix) and "| pending" in tag:
                # Preserve the forecast tokens (P=, H=) carried on the pending tag.
                pos, kv = [], {}
                for f in (x.strip() for x in tag[1:-1].split("|")):
                    if "=" in f:
                        k, _, v = f.partition("=")
                        kv[k.strip()] = v.strip()
                    else:
                        pos.append(f)
                rating = pos[2]
                new_tag = f"[{trade_date} | {ticker} | {rating} | {raw_pct} | {alpha_pct} | {holding_days}d"
                if kv.get("P"):
                    new_tag += f" | P={kv['P']}"
                if kv.get("H"):
                    new_tag += f" | H={kv['H']}"
                if cagr is not None:
                    new_tag += f" | CAGR={cagr:+.1%}"
                if error_class:
                    new_tag += f" | E={error_class}"
                new_tag += "]"
                rest = "\n".join(lines[1:])
                new_blocks.append(f"{new_tag}\n\n{rest.lstrip()}\n\nREFLECTION:\n{reflection}")
                updated = True
            else:
                new_blocks.append(block)
        if not updated:
            return False
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(_SEPARATOR.join(new_blocks), encoding="utf-8")
        tmp.replace(self.path)
        return True

    # --- helpers ---
    def _parse_entry(self, raw: str) -> Optional[dict]:
        lines = raw.strip().splitlines()
        if not lines:
            return None
        tag = lines[0].strip()
        if not (tag.startswith("[") and tag.endswith("]")):
            return None
        # Split tag into positional fields and key=value tokens (P=, H=, CAGR=).
        pos, kv = [], {}
        for f in (x.strip() for x in tag[1:-1].split("|")):
            if "=" in f:
                k, _, v = f.partition("=")
                kv[k.strip()] = v.strip()
            else:
                pos.append(f)
        if len(pos) < 4:
            return None
        pending = pos[3] == "pending"
        body = "\n".join(lines[1:]).strip()
        dm, rm = _DECISION_RE.search(body), _REFLECTION_RE.search(body)
        return {
            "date": pos[0], "ticker": pos[1], "rating": pos[2],
            "pending": pending,
            "raw": None if pending else pos[3],
            "alpha": None if pending else (pos[4] if len(pos) > 4 else None),
            "holding": None if pending else (pos[5] if len(pos) > 5 else None),
            "prob": kv.get("P"), "horizon": kv.get("H"), "cagr": kv.get("CAGR"),
            "error": kv.get("E"),
            "decision": dm.group(1).strip() if dm else "",
            "reflection": rm.group(1).strip() if rm else "",
        }

    def _format_full(self, e: dict) -> str:
        raw, alpha, holding = e["raw"] or "n/a", e["alpha"] or "n/a", e["holding"] or "n/a"
        tag = f"[{e['date']} | {e['ticker']} | {e['rating']} | {raw} | {alpha} | {holding}]"
        parts = [tag, f"DECISION:\n{e['decision']}"]
        if e["reflection"]:
            parts.append(f"REFLECTION:\n{e['reflection']}")
        return "\n\n".join(parts)

    def _format_reflection_only(self, e: dict) -> str:
        tag = f"[{e['date']} | {e['ticker']} | {e['rating']} | {e['raw'] or 'n/a'}]"
        if e["reflection"]:
            return f"{tag}\n{e['reflection']}"
        text = e["decision"][:300]
        return f"{tag}\n{text}{'...' if len(e['decision']) > 300 else ''}"


_DAYS_PER_MONTH = 30.44


def months_to_days(months: float) -> int:
    return int(round(months * _DAYS_PER_MONTH))


class ReturnResult:
    """Realised return over a calendar window, with CAGR for multi-year horizons."""

    def __init__(self, raw, alpha, elapsed_days, benchmark, cagr, target_days, reached):
        self.raw = raw
        self.alpha = alpha
        self.elapsed_days = elapsed_days
        self.benchmark = benchmark
        self.cagr = cagr
        self.target_days = target_days
        self.reached = reached  # has the full target horizon elapsed yet?


def fetch_returns(ticker: str, trade_date: str, horizon_days: int = 5) -> Optional[ReturnResult]:
    """Realised raw/alpha/CAGR from trade_date to trade_date+horizon_days (calendar).

    Uses the last available close at or before the target date, so it works for
    both short windows and multi-year horizons. Returns None if there is not yet
    at least one trading row after the entry. ``reached`` is False when the
    target horizon has not fully elapsed (i.e. this is an interim mark-to-market,
    not a final outcome).
    """
    import yfinance as yf

    benchmark = resolve_benchmark(ticker)
    try:
        start = datetime.strptime(trade_date, "%Y-%m-%d")
        target = start + timedelta(days=horizon_days)
        # Fetch a little past the target so the target date itself is covered.
        end_str = (target + timedelta(days=7)).strftime("%Y-%m-%d")
        stock = yf.Ticker(ticker).history(start=trade_date, end=end_str)
        bench = yf.Ticker(benchmark).history(start=trade_date, end=end_str)
        if len(stock) < 2 or len(bench) < 2:
            return None

        def _at_target(df):
            # Last row dated on/before the target; falls back to the final row.
            idx = df.index
            tz = idx.tz
            cutoff = target if tz is None else target.replace(tzinfo=tz) if hasattr(target, "replace") else target
            try:
                mask = idx <= cutoff
                pos = int(mask.sum()) - 1
            except TypeError:
                pos = len(df) - 1
            return max(1, min(pos, len(df) - 1))

        s_pos, b_pos = _at_target(stock), _at_target(bench)
        s0, s1 = float(stock["Close"].iloc[0]), float(stock["Close"].iloc[s_pos])
        b0, b1 = float(bench["Close"].iloc[0]), float(bench["Close"].iloc[b_pos])
        raw = s1 / s0 - 1.0
        bench_ret = b1 / b0 - 1.0
        elapsed = (stock.index[s_pos].to_pydatetime().replace(tzinfo=None) - start).days or 1
        cagr = (1.0 + raw) ** (365.25 / elapsed) - 1.0 if elapsed > 0 and raw > -1 else None
        reached = elapsed >= horizon_days * 0.95
        return ReturnResult(raw, raw - bench_ret, elapsed, benchmark, cagr, horizon_days, reached)
    except Exception as exc:  # noqa: BLE001
        print(f"WARN: could not compute returns for {ticker} @ {trade_date}: {exc}", file=sys.stderr)
        return None


# --- subcommands ----------------------------------------------------------


def cmd_recall(args, log: DecisionLog) -> None:
    ctx = log.get_past_context(args.ticker)
    print(ctx if ctx else f"(no resolved past decisions for {args.ticker} yet)")


def cmd_log(args, log: DecisionLog) -> None:
    if args.file:
        decision = Path(args.file).read_text(encoding="utf-8")
    elif args.text:
        decision = args.text
    else:
        decision = sys.stdin.read()
    if not decision.strip():
        print("ERROR: empty decision text (provide --file, --text, or pipe via stdin)", file=sys.stderr)
        raise SystemExit(2)
    if args.prob is not None and not (0.0 <= args.prob <= 1.0):
        print("ERROR: --prob must be a probability in [0,1]", file=sys.stderr)
        raise SystemExit(2)
    rating = parse_rating(decision)
    wrote = log.store_decision(args.ticker, args.trade_date, decision,
                               prob=args.prob, horizon_months=args.horizon_months)
    extra = ""
    if args.prob is not None:
        extra += f" | P={args.prob:.2f}"
    if args.horizon_months:
        extra += f" | H={args.horizon_months}mo"
    if wrote:
        print(f"Logged [{args.trade_date} | {args.ticker} | {rating} | pending{extra}] -> {log.path}")
    else:
        print(f"Already logged (pending) for {args.trade_date} | {args.ticker}; left unchanged.")


def cmd_log_cycle(args, log: DecisionLog) -> None:
    import csv
    csv_path = log.path.parent / "ai_cycle_history.csv"
    file_exists = csv_path.exists()
    row = [args.date, args.phase, args.score] + args.indicators
    with open(csv_path, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        if not file_exists:
            headers = ["Date", "Phase", "Risk_Score", "Ind1_Capex", "Ind2_GPU", "Ind3_NVDA", "Ind4_LeadTimes",
                       "Ind5_Financing", "Ind6_Concentration", "Ind7_Credibility", "Ind8_Depreciation", 
                       "Ind9_Macro", "Ind10_Valuation", "Ind11_Insider", "Ind12_SoftwareCanary"]
            writer.writerow(headers)
        writer.writerow(row)
    print(f"Logged AI Cycle state to {csv_path}")


def cmd_pending(args, log: DecisionLog) -> None:
    pend = log.get_pending(args.ticker)
    if not pend:
        print("(no pending entries)")
        return
    for e in pend:
        print(f"[{e['date']} | {e['ticker']} | {e['rating']} | pending]")


def _horizon_days(args) -> int:
    """Resolve the return window: --horizon-months takes precedence over --holding-days."""
    if getattr(args, "horizon_months", None):
        return months_to_days(args.horizon_months)
    return args.holding_days


def cmd_returns(args, log: DecisionLog) -> None:
    r = fetch_returns(args.ticker, args.trade_date, _horizon_days(args))
    if r is None:
        print(f"NO_DATA: not enough price history yet for {args.ticker} since {args.trade_date}. "
              f"Try again after more trading days.")
        raise SystemExit(1)
    print(f"Ticker: {args.ticker}  Trade date: {args.trade_date}  Benchmark: {r.benchmark}")
    print(f"Raw return: {r.raw:+.1%}")
    print(f"Alpha vs {r.benchmark}: {r.alpha:+.1%}")
    print(f"Elapsed: {r.elapsed_days} calendar days" + ("" if r.reached else "  (horizon NOT yet reached — interim mark-to-market)"))
    if r.cagr is not None:
        print(f"CAGR: {r.cagr:+.1%}")


def cmd_resolve(args, log: DecisionLog) -> None:
    reflection = Path(args.reflection_file).read_text(encoding="utf-8").strip() if args.reflection_file else (args.reflection or "")
    if not reflection:
        print("ERROR: provide --reflection-file or --reflection (Claude's one-paragraph reflection)", file=sys.stderr)
        raise SystemExit(2)
    r = fetch_returns(args.ticker, args.trade_date, _horizon_days(args))
    if r is None:
        print(f"NO_DATA: not enough price history yet to resolve {args.ticker} @ {args.trade_date}.")
        raise SystemExit(1)
    if not r.reached and not args.force:
        print(f"Horizon NOT yet reached for {args.ticker} @ {args.trade_date} "
              f"({r.elapsed_days}d of {r.target_days}d elapsed). "
              f"Use 'returns' for an interim mark, or pass --force to resolve early.")
        raise SystemExit(1)
    ec = getattr(args, "error_class", None)
    if ec and ec not in ERROR_CLASSES:
        print(f"ERROR: --error-class must be one of {', '.join(ERROR_CLASSES)}", file=sys.stderr)
        raise SystemExit(2)
    ok = log.update_with_outcome(args.ticker, args.trade_date, r.raw, r.alpha,
                                 f"{r.elapsed_days}", reflection, cagr=r.cagr, error_class=ec)
    if ok:
        cagr_s = f" / CAGR {r.cagr:+.1%}" if r.cagr is not None else ""
        ec_s = f" / error={ec}" if ec else ""
        if r.alpha <= 0 and not ec:
            ec_s = " / error=UNCLASSIFIED (pass --error-class luck|thesis|calibration|timing)"
        print(f"Resolved [{args.trade_date} | {args.ticker}] raw {r.raw:+.1%} / "
              f"alpha vs {r.benchmark} {r.alpha:+.1%}{cagr_s}{ec_s} / {r.elapsed_days}d.")
    else:
        print(f"No matching pending entry for {args.trade_date} | {args.ticker} (already resolved?).")


def _pct_to_float(s) -> Optional[float]:
    if not s:
        return None
    try:
        return float(str(s).replace("%", "").replace("+", "").strip()) / 100.0
    except ValueError:
        return None


def cmd_score(args, log: DecisionLog) -> None:
    """Calibration & skill scorecard over resolved predictions.

    Reports hit-rate (beat benchmark), mean alpha/CAGR, and — when forecast
    probabilities were logged — a Brier score plus Brier Skill Score vs the
    base-rate baseline. This is how you tell whether the framework has *edge*
    rather than just direction.
    """
    entries = [e for e in log.load_entries()
               if not e["pending"] and (args.ticker is None or e["ticker"] == args.ticker)]
    resolved = [e for e in entries if _pct_to_float(e["alpha"]) is not None]
    if not resolved:
        print("(no resolved predictions to score yet)")
        return

    alphas = [_pct_to_float(e["alpha"]) for e in resolved]
    raws = [_pct_to_float(e["raw"]) for e in resolved if _pct_to_float(e["raw"]) is not None]
    cagrs = [_pct_to_float(e["cagr"]) for e in resolved if _pct_to_float(e["cagr"]) is not None]
    wins = [a for a in alphas if a > 0]
    hit_rate = len(wins) / len(alphas)

    print(f"=== Prediction scorecard{(' — ' + args.ticker) if args.ticker else ''} ===")
    print(f"Resolved predictions: {len(resolved)}")
    print(f"Hit-rate (beat benchmark): {hit_rate:.0%} ({len(wins)}/{len(alphas)})")
    print(f"Mean alpha: {sum(alphas)/len(alphas):+.1%}  |  median alpha: {sorted(alphas)[len(alphas)//2]:+.1%}")
    if raws:
        print(f"Mean raw return: {sum(raws)/len(raws):+.1%}")
    if cagrs:
        print(f"Mean CAGR: {sum(cagrs)/len(cagrs):+.1%}")

    # --- Brier calibration over entries that carried a forecast probability ---
    probbed = [(float(e["prob"]), 1.0 if _pct_to_float(e["alpha"]) > 0 else 0.0)
               for e in resolved if e["prob"]]
    if probbed:
        brier = sum((p - o) ** 2 for p, o in probbed) / len(probbed)
        base = sum(o for _, o in probbed) / len(probbed)
        base_brier = sum((base - o) ** 2 for _, o in probbed) / len(probbed)
        bss = 1 - brier / base_brier if base_brier > 0 else float("nan")
        print(f"\nCalibration (n={len(probbed)} with forecast P):")
        print(f"  Brier score: {brier:.3f}  (lower is better; 0=perfect, 0.25=coin-flip)")
        print(f"  Base-rate Brier: {base_brier:.3f}  |  Brier Skill Score: {bss:+.2f} (>0 = beats base rate)")
    else:
        print("\n(no forecast probabilities logged yet — log with --prob to enable Brier calibration)")

    # --- rating monotonicity: do bullish ratings earn more alpha? ---
    bull = [a for e, a in zip(resolved, alphas) if e["rating"] in ("Buy", "Overweight")]
    flat = [a for e, a in zip(resolved, alphas) if e["rating"] == "Hold"]
    bear = [a for e, a in zip(resolved, alphas) if e["rating"] in ("Underweight", "Sell")]
    print("\nMean alpha by rating tier (want bullish > Hold > bearish):")
    for label, grp in (("Buy/Overweight", bull), ("Hold", flat), ("Underweight/Sell", bear)):
        if grp:
            print(f"  {label:18} {sum(grp)/len(grp):+.1%}  (n={len(grp)})")

    # --- why misses missed: post-mortem error taxonomy among losers ----------
    misses = [e for e in resolved if (_pct_to_float(e["alpha"]) or 0) <= 0]
    if misses:
        from collections import Counter
        classes = Counter((e.get("error") or "unclassified") for e in misses)
        print(f"\nMiss post-mortems (n={len(misses)} below-benchmark) — by cause:")
        for cls, n in classes.most_common():
            note = " (process sound — don't over-learn)" if cls == "luck" else ""
            print(f"  {cls:13} {n}{note}")
        unclf = classes.get("unclassified", 0)
        if unclf:
            print(f"  -> {unclf} miss(es) UNCLASSIFIED: re-resolve with --error-class to learn from them")

    # --- small-sample honesty: don't read calibration into a handful of calls -
    if len(resolved) < 20:
        print(f"\n⚠ SMALL SAMPLE (n={len(resolved)}): hit-rate/Brier are not yet statistically")
        print("  meaningful (a handful of outcomes ≈ coin-flip noise). Treat these as")
        print("  hypotheses, not validated lessons, until ~20–30+ resolved forecasts.")


def _rating_stance(rating: str) -> int:
    r = (rating or "").lower()
    if r in ("buy", "overweight"):
        return 1
    if r in ("sell", "underweight"):
        return -1
    return 0


def cmd_watch(args, log: DecisionLog) -> None:
    """Flag OPEN (pending) calls whose interim mark has drifted against the thesis.

    A bullish call lagging its benchmark, a bearish call being run over, or a Hold
    that moved a lot — i.e. positions worth re-analysing before the horizon matures.
    Writes ``under_pressure.json`` next to the memory log so the dashboard can show
    a ⚠ flag without doing any network I/O at build time.
    """
    import json
    pend = log.get_pending(args.ticker)
    flagged, checked, skipped = [], 0, 0
    for e in pend:
        horizon_m = None
        if e.get("horizon"):
            m = re.search(r"\d+", e["horizon"])
            if m:
                horizon_m = int(m.group(0))
        hd = months_to_days(horizon_m or args.horizon_months)
        r = fetch_returns(e["ticker"], e["date"], hd)
        if r is None:
            skipped += 1
            continue
        checked += 1
        if r.elapsed_days < args.min_days:
            continue  # too soon — day-1 noise isn't a broken thesis
        stance = _rating_stance(e["rating"])
        reason = None
        if stance > 0 and (r.alpha <= -args.alpha_threshold or r.raw <= -args.raw_threshold):
            reason = f"bullish ({e['rating']}) but {r.raw:+.0%} raw / {r.alpha:+.0%} α — thesis under pressure"
        elif stance < 0 and r.alpha >= args.alpha_threshold:
            reason = f"bearish ({e['rating']}) but {r.raw:+.0%} raw / {r.alpha:+.0%} α — running against the call"
        elif stance == 0 and abs(r.raw) >= args.big_move:
            reason = f"Hold but moved {r.raw:+.0%} since the call — revisit"
        if reason:
            flagged.append({"ticker": e["ticker"], "date": e["date"], "rating": e["rating"],
                            "raw": round(r.raw, 4), "alpha": round(r.alpha, 4),
                            "cagr": (round(r.cagr, 4) if r.cagr is not None else None),
                            "elapsed_days": r.elapsed_days, "benchmark": r.benchmark,
                            "reason": reason})
    flagged.sort(key=lambda x: x["alpha"])  # worst alpha first
    cache = log.path.parent / "under_pressure.json"
    payload = {"generated": datetime.now().strftime("%Y-%m-%d %H:%M"), "checked": checked,
               "flagged": flagged,
               "params": {"alpha_threshold": args.alpha_threshold, "raw_threshold": args.raw_threshold,
                          "min_days": args.min_days}}
    try:
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as exc:  # noqa: BLE001
        print(f"WARN: could not write {cache}: {exc}", file=sys.stderr)
    if not flagged:
        print(f"No open calls under pressure ({checked} checked, ≥{args.min_days}d elapsed). Cache -> {cache}")
        return
    print(f"⚠ {len(flagged)} open call(s) under pressure (of {checked} checked):")
    for x in flagged:
        cg = f" / CAGR {x['cagr']:+.0%}" if x["cagr"] is not None else ""
        print(f"  {x['ticker']:6} {x['date']}  {x['raw']:+.0%} raw / {x['alpha']:+.0%} α{cg}  "
              f"{x['elapsed_days']}d — {x['reason']}")
    print(f"\nConsider re-running /trading-analysis on these. Cache -> {cache}")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="ta_memory.py", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--path", default=None, help="override log path (default: $TRADINGAGENTS_MEMORY_LOG_PATH or ~/.tradingagents/memory/trading_memory.md)")
    sub = p.add_subparsers(dest="command", required=True)

    s = sub.add_parser("recall", help="print past lessons for a ticker (inject at start of analysis)")
    s.add_argument("ticker"); s.set_defaults(func=cmd_recall)

    s = sub.add_parser("log", help="append a pending decision entry (with forecast P + horizon)")
    s.add_argument("ticker"); s.add_argument("trade_date")
    s.add_argument("--file", help="read decision markdown from this file")
    s.add_argument("--text", help="decision text inline (else read stdin)")
    s.add_argument("--prob", type=float, default=None,
                   help="forecast P(beats benchmark over horizon), 0..1 — enables Brier scoring")
    s.add_argument("--horizon-months", type=int, default=None,
                   help="forecast horizon in months (e.g. 24); used when resolving")
    s.set_defaults(func=cmd_log)

    s = sub.add_parser("log_cycle", help="log the 12 AI cycle indicators to a CSV database")
    s.add_argument("date", help="As-of date of the cycle report")
    s.add_argument("--phase", required=True, help="Current macro phase")
    s.add_argument("--score", required=True, help="Risk per AI Cake score 0-100")
    s.add_argument("--indicators", nargs=12, required=True, help="The 12 indicator colors (Green/Amber/Red)")
    s.set_defaults(func=cmd_log_cycle)

    s = sub.add_parser("pending", help="list entries awaiting an outcome")
    s.add_argument("ticker", nargs="?", default=None); s.set_defaults(func=cmd_pending)

    s = sub.add_parser("returns", help="compute realised raw/alpha/CAGR return from prices")
    s.add_argument("ticker"); s.add_argument("trade_date")
    s.add_argument("--holding-days", type=int, default=5, help="window in calendar days (short-horizon)")
    s.add_argument("--horizon-months", type=int, default=None, help="window in months (preferred; overrides --holding-days)")
    s.set_defaults(func=cmd_returns)

    s = sub.add_parser("resolve", help="attach realised return + reflection to a pending entry")
    s.add_argument("ticker"); s.add_argument("trade_date")
    s.add_argument("--reflection-file", help="file with Claude's one-paragraph reflection")
    s.add_argument("--reflection", help="reflection text inline")
    s.add_argument("--holding-days", type=int, default=5)
    s.add_argument("--horizon-months", type=int, default=None, help="forecast horizon in months (preferred)")
    s.add_argument("--force", action="store_true", help="resolve even if the full horizon has not elapsed")
    s.add_argument("--error-class", choices=ERROR_CLASSES, default=None,
                   help="post-mortem cause of a miss: luck|thesis|calibration|timing|none "
                        "(separates a flawed process from bad luck — required to learn from a miss)")
    s.set_defaults(func=cmd_resolve)

    s = sub.add_parser("watch", help="flag OPEN calls whose interim mark has drifted against the thesis")
    s.add_argument("ticker", nargs="?", default=None)
    s.add_argument("--alpha-threshold", type=float, default=0.10,
                   help="flag when |interim alpha| exceeds this against the call (default 0.10)")
    s.add_argument("--raw-threshold", type=float, default=0.20,
                   help="also flag a bullish call down more than this raw (default 0.20)")
    s.add_argument("--big-move", type=float, default=0.30,
                   help="flag a Hold that moved more than this raw (default 0.30)")
    s.add_argument("--min-days", type=int, default=21,
                   help="ignore calls younger than this many calendar days (default 21)")
    s.add_argument("--horizon-months", type=int, default=24,
                   help="horizon to mark against when an entry has none (default 24)")
    s.set_defaults(func=cmd_watch)

    s = sub.add_parser("score", help="calibration & skill scorecard over resolved predictions")
    s.add_argument("ticker", nargs="?", default=None)
    s.set_defaults(func=cmd_score)

    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    log = DecisionLog(Path(args.path).expanduser() if args.path else _default_path())
    args.func(args, log)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
