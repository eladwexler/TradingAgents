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
    def store_decision(self, ticker: str, trade_date: str, decision: str) -> bool:
        """Append a pending entry. Idempotent on (date, ticker). Returns False if dup."""
        if self.path.exists():
            for line in self.path.read_text(encoding="utf-8").splitlines():
                if line.startswith(f"[{trade_date} | {ticker} |") and line.endswith("| pending]"):
                    return False
        rating = parse_rating(decision)
        tag = f"[{trade_date} | {ticker} | {rating} | pending]"
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
                            holding_days, reflection) -> bool:
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
            if not updated and tag.startswith(prefix) and tag.endswith("| pending]"):
                fields = [f.strip() for f in tag[1:-1].split("|")]
                rating = fields[2]
                new_tag = f"[{trade_date} | {ticker} | {rating} | {raw_pct} | {alpha_pct} | {holding_days}d]"
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
        fields = [f.strip() for f in tag[1:-1].split("|")]
        if len(fields) < 4:
            return None
        body = "\n".join(lines[1:]).strip()
        dm, rm = _DECISION_RE.search(body), _REFLECTION_RE.search(body)
        return {
            "date": fields[0], "ticker": fields[1], "rating": fields[2],
            "pending": fields[3] == "pending",
            "raw": fields[3] if fields[3] != "pending" else None,
            "alpha": fields[4] if len(fields) > 4 else None,
            "holding": fields[5] if len(fields) > 5 else None,
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


def fetch_returns(ticker: str, trade_date: str, holding_days: int = 5):
    """Return (raw, alpha, actual_days) over holding_days from trade_date, or (None,)*3."""
    import yfinance as yf

    benchmark = resolve_benchmark(ticker)
    try:
        start = datetime.strptime(trade_date, "%Y-%m-%d")
        end_str = (start + timedelta(days=holding_days + 7)).strftime("%Y-%m-%d")
        stock = yf.Ticker(ticker).history(start=trade_date, end=end_str)
        bench = yf.Ticker(benchmark).history(start=trade_date, end=end_str)
        if len(stock) < 2 or len(bench) < 2:
            return None, None, None, benchmark
        actual = min(holding_days, len(stock) - 1, len(bench) - 1)
        raw = float((stock["Close"].iloc[actual] - stock["Close"].iloc[0]) / stock["Close"].iloc[0])
        bench_ret = float((bench["Close"].iloc[actual] - bench["Close"].iloc[0]) / bench["Close"].iloc[0])
        return raw, raw - bench_ret, actual, benchmark
    except Exception as exc:  # noqa: BLE001
        print(f"WARN: could not compute returns for {ticker} @ {trade_date}: {exc}", file=sys.stderr)
        return None, None, None, benchmark


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
    rating = parse_rating(decision)
    wrote = log.store_decision(args.ticker, args.trade_date, decision)
    if wrote:
        print(f"Logged [{args.trade_date} | {args.ticker} | {rating} | pending] -> {log.path}")
    else:
        print(f"Already logged (pending) for {args.trade_date} | {args.ticker}; left unchanged.")


def cmd_pending(args, log: DecisionLog) -> None:
    pend = log.get_pending(args.ticker)
    if not pend:
        print("(no pending entries)")
        return
    for e in pend:
        print(f"[{e['date']} | {e['ticker']} | {e['rating']} | pending]")


def cmd_returns(args, log: DecisionLog) -> None:
    raw, alpha, days, bench = fetch_returns(args.ticker, args.trade_date, args.holding_days)
    if raw is None:
        print(f"NO_DATA: not enough price history yet for {args.ticker} since {args.trade_date} "
              f"(benchmark {bench}). Try again after more trading days.")
        raise SystemExit(1)
    print(f"Ticker: {args.ticker}  Trade date: {args.trade_date}  Benchmark: {bench}")
    print(f"Raw return: {raw:+.1%}")
    print(f"Alpha vs {bench}: {alpha:+.1%}")
    print(f"Holding days: {days}")


def cmd_resolve(args, log: DecisionLog) -> None:
    reflection = Path(args.reflection_file).read_text(encoding="utf-8").strip() if args.reflection_file else (args.reflection or "")
    if not reflection:
        print("ERROR: provide --reflection-file or --reflection (Claude's one-paragraph reflection)", file=sys.stderr)
        raise SystemExit(2)
    raw, alpha, days, bench = fetch_returns(args.ticker, args.trade_date, args.holding_days)
    if raw is None:
        print(f"NO_DATA: not enough price history yet to resolve {args.ticker} @ {args.trade_date}.")
        raise SystemExit(1)
    ok = log.update_with_outcome(args.ticker, args.trade_date, raw, alpha, f"{days}", reflection)
    if ok:
        print(f"Resolved [{args.trade_date} | {args.ticker}] raw {raw:+.1%} / alpha vs {bench} {alpha:+.1%} / {days}d.")
    else:
        print(f"No matching pending entry for {args.trade_date} | {args.ticker} (already resolved?).")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="ta_memory.py", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--path", default=None, help="override log path (default: $TRADINGAGENTS_MEMORY_LOG_PATH or ~/.tradingagents/memory/trading_memory.md)")
    sub = p.add_subparsers(dest="command", required=True)

    s = sub.add_parser("recall", help="print past lessons for a ticker (inject at start of analysis)")
    s.add_argument("ticker"); s.set_defaults(func=cmd_recall)

    s = sub.add_parser("log", help="append a pending decision entry")
    s.add_argument("ticker"); s.add_argument("trade_date")
    s.add_argument("--file", help="read decision markdown from this file")
    s.add_argument("--text", help="decision text inline (else read stdin)")
    s.set_defaults(func=cmd_log)

    s = sub.add_parser("pending", help="list entries awaiting an outcome")
    s.add_argument("ticker", nargs="?", default=None); s.set_defaults(func=cmd_pending)

    s = sub.add_parser("returns", help="compute realised raw/alpha return from prices")
    s.add_argument("ticker"); s.add_argument("trade_date")
    s.add_argument("--holding-days", type=int, default=5)
    s.set_defaults(func=cmd_returns)

    s = sub.add_parser("resolve", help="attach realised return + reflection to a pending entry")
    s.add_argument("ticker"); s.add_argument("trade_date")
    s.add_argument("--reflection-file", help="file with Claude's one-paragraph reflection")
    s.add_argument("--reflection", help="reflection text inline")
    s.add_argument("--holding-days", type=int, default=5)
    s.set_defaults(func=cmd_resolve)

    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    log = DecisionLog(Path(args.path).expanduser() if args.path else _default_path())
    args.func(args, log)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
