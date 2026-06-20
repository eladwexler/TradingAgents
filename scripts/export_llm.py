#!/usr/bin/env python3
"""Export the dashboard's decision data as an LLM-ingestible briefing.

Produces a single self-contained package another model can read to recommend a
portfolio strategy (what to buy / add / hold / trim / exit, and sizing) WITHOUT
needing the repo, the HTML, or any tool:

  dashboard/export/portfolio_llm.md   — human+LLM readable digest (primary)
  dashboard/export/portfolio.json     — same data, machine-precise

It reuses build_dashboard.py's parsers (parse_memory / parse_decision /
parse_forecast / buckets) so it can never drift from the dashboard's data model.

What goes in (so a reviewing LLM can reason, not just read):
  1. TASK preamble  — explicit instruction for the consuming model + disclaimer.
  2. Macro context  — the latest /ai-cycle-watch phase/stance (the regime).
  3. Track record   — calibration: resolved hit-rate + mean alpha, so the model
                      knows how much to trust these calls.
  4. Concentration  — exposure by AI-build-out bucket (the real portfolio risk:
                      almost everything is one correlated AI bet).
  5. Holdings table — one row per name: rating, P(beat), exp 24mo, target,
                      scenarios, the 4-lens Combined verdict + 5 brains + X, flags.
  6. Per-name notes — the new-investor verdict + forecast + key fundamentals.

Usage:
  python3 scripts/export_llm.py                 # both files, latest decision/ticker
  python3 scripts/export_llm.py --full          # every dated decision, not just latest
  python3 scripts/export_llm.py --format md     # md | json | both (default both)
  python3 scripts/export_llm.py --stdout        # also print the md to stdout
  python3 scripts/export_llm.py --out DIR       # output dir (default dashboard/export)
"""
import os, re, glob, json, argparse, datetime, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import build_dashboard as bd  # reuse the canonical parsers / maps

ROOT = bd.ROOT
STOCKS = bd.STOCKS
MEM = bd.MEM
CYCLE_DIR = os.path.join(ROOT, "ai-cycle-reports")
DEFAULT_OUT = os.path.join(ROOT, "dashboard", "export")
TODAY = datetime.date.today().isoformat()

DISCLAIMER = ("Research scaffold only — NOT financial, investment, or trading "
              "advice. Forecasts carry wide error bars; data may be stale.")

TASK_PREAMBLE = """\
# AI / Semiconductor Watchlist — Strategy Briefing for an LLM Reviewer

You are an investment analyst. Below is a structured snapshot of a multi-agent
research process that scores AI-build-out equities. Each name carries a rating, a
calibrated 12-36mo return forecast (bear/base/bull + P(beat-benchmark)), four
secular "brain" lenses fused into one Combined Strategic Verdict, and an X/FinTwit
sentiment overlay.

YOUR TASK — produce a concise portfolio strategy:
  1. BUY / ADD, HOLD, and TRIM / EXIT lists, each with a one-line rationale that
     cites the data below (rating, P(beat), expected return, Combined verdict, any
     under-pressure flag, the macro phase).
  2. Suggested position sizing tilt per name (conviction x volatility), and the
     TOP RISK you see — pay special attention to the bucket-concentration section:
     these names are highly correlated, so treat them as one AI factor bet, not N
     independent ideas.
  3. State the assumptions and what single data point would most change your view.
Calibrate your confidence to the track-record section (how good past calls were).
Do NOT invent numbers not present below. End with the disclaimer.
"""

# ------------------------------------------------------------------ helpers ---
def _pct(s):
    """'+12.5%' / '-3%' -> float 12.5 / -3.0 ; None if unparseable."""
    if not s:
        return None
    m = re.search(r"[+\-]?\d+(?:\.\d+)?", s.replace(",", ""))
    return float(m.group()) if m else None


def latest_cycle():
    """(date, stance-line, path) of the newest ai-cycle report, or (None, '', None)."""
    files = sorted(glob.glob(os.path.join(CYCLE_DIR, "*_cycle.md")))
    if not files:
        return None, "", None
    path = files[-1]
    date = os.path.basename(path)[:10]
    stance = ""
    with open(path, encoding="utf-8") as f:
        for ln in f:
            ln = ln.strip()
            if ln.upper().startswith("STANCE:"):
                stance = ln
                break
            if ln and not stance:
                stance = ln  # fall back to first non-empty line
    return date, stance, path


def collect_decisions(full=False):
    """List of parsed decisions. Latest per ticker unless full=True."""
    paths = sorted(glob.glob(os.path.join(STOCKS, "*", "*_decision.md")))
    parsed = [bd.parse_decision(p) for p in paths]
    if full:
        return sorted(parsed, key=lambda d: (d["ticker"], d["date"]))
    latest = {}
    for d in parsed:
        cur = latest.get(d["ticker"])
        if cur is None or d["date"] > cur["date"]:
            latest[d["ticker"]] = d
    return sorted(latest.values(), key=lambda d: d["ticker"])


def track_record(mem):
    """Resolved hit-rate (alpha>0) + mean alpha from the memory spine."""
    resolved = [e for e in mem.values() if e.get("status") != "pending" and e.get("alpha")]
    pending = [e for e in mem.values() if e.get("status") == "pending"]
    alphas = [a for a in (_pct(e.get("alpha")) for e in resolved) if a is not None]
    hits = sum(1 for a in alphas if a > 0)
    return {
        "decisions_logged": len(mem),
        "pending": len(pending),
        "resolved": len(resolved),
        "hit_rate": (hits / len(alphas)) if alphas else None,
        "mean_alpha_pct": (sum(alphas) / len(alphas)) if alphas else None,
    }


def brain_sign(v):
    """Collapse any brain verdict to a signed glance token (+/~/-/·)."""
    t = (v or "").strip().lower()
    if not t:
        return "·"
    if any(k in t for k in ("insufficient", "n/a", "mixed")):
        return "·"
    # negatives first — "unlikely back" contains the substring "likely"
    if any(k in t for k in ("unlikely", "headwind", "cautious", "bearish")):
        return "−"
    if any(k in t for k in ("likely", "tailwind", "constructive", "conviction", "bullish")):
        return "+"
    if "possible" in t:
        return "~"
    return "~"


def fc24(d):
    return (d.get("forecast") or {}).get("24mo", {}) or {}


def mem_for(mem, d):
    return mem.get((d["date"], d["ticker"]), {})


def rec(d, mem):
    """One flat record per decision for JSON + table rendering."""
    f = fc24(d)
    m = mem_for(mem, d)
    dom = bd.AI_DOMAIN.get(d["ticker"], "")
    return {
        "ticker": d["ticker"], "name": d.get("name", ""), "date": d["date"],
        "bucket": bd.bucket_for(d["ticker"]), "domain": dom,
        "rating": d.get("macro_rating") or d.get("base_rating") or d.get("base_action"),
        "action": d.get("macro_action") or d.get("base_action"),
        "status": m.get("status", ""),
        "pbeat": m.get("prob") or f.get("pbeat"),
        "horizon": m.get("horizon", ""),
        "exp_return_24mo": f.get("exp"), "target_24mo": f.get("target"),
        "cagr_24mo": f.get("cagr"),
        "scenarios_24mo": {"bear": f.get("bear"), "base": f.get("base"), "bull": f.get("bull")},
        "price_at_analysis": d.get("price_at"),
        "realized_raw": m.get("raw"), "realized_alpha": m.get("alpha"),
        "combined_verdict": d.get("combined"),
        "brains": {"jensen": d.get("jensen"), "leopold": d.get("leopold"),
                   "jordi": d.get("jordi"), "gavin": d.get("gavin"), "x": d.get("x")},
        "verdict_for_new_investors": (d.get("verdict_new") or "").strip(),
        "source": d.get("src", ""),
    }


# -------------------------------------------------------------- rendering -----
def render_md(records, mem, full):
    cyc_date, stance, _ = latest_cycle()
    tr = track_record(mem)
    out = [TASK_PREAMBLE.rstrip(),
           "",
           f"- **As-of:** {TODAY}",
           f"- **Names covered:** {len({r['ticker'] for r in records})}"
           f" ({len(records)} decisions{' — full dated history' if full else ', latest per ticker'})",
           f"- **Benchmark for alpha:** SPY (per the logging convention).",
           ""]

    # --- macro regime ---
    out += ["## 1. Macro regime (AI capex cycle)"]
    if stance:
        out += [f"- **Cycle report:** {cyc_date}", f"- {stance}", ""]
    else:
        out += ["- (no ai-cycle report found)", ""]

    # --- track record ---
    out += ["## 2. Track record (how much to trust these calls)"]
    hr = f"{tr['hit_rate']*100:.0f}%" if tr["hit_rate"] is not None else "n/a"
    ma = f"{tr['mean_alpha_pct']:+.1f}pp" if tr["mean_alpha_pct"] is not None else "n/a"
    out += [f"- Decisions logged: **{tr['decisions_logged']}** "
            f"(resolved **{tr['resolved']}**, pending **{tr['pending']}**).",
            f"- Resolved hit-rate (positive alpha vs SPY): **{hr}**; "
            f"mean realized alpha: **{ma}**.",
            "- Treat pending forecasts as unproven; weight the resolved hit-rate when "
            "deciding how literally to take P(beat).", ""]

    # --- concentration ---
    out += ["## 3. Exposure concentration (the real risk — correlated bets)"]
    by_bucket = {}
    for r in records:
        by_bucket.setdefault(r["bucket"], []).append(r["ticker"])
    for b in sorted(by_bucket, key=lambda x: (-len(by_bucket[x]), x)):
        names = sorted(set(by_bucket[b]))
        out += [f"- **{b}** ({len(names)}): {', '.join(names)}"]
    out += ["", "> These buckets are AI-build-out layers; most move together with "
            "hyperscaler capex and rates. Size the *theme*, not just each name.", ""]

    # --- holdings table ---
    out += ["## 4. Watchlist table",
            "",
            "Brains column = secular fit per lens, signed: **+** with-thesis "
            "(Likely back / Thesis tailwind / Constructive / Conviction pick), "
            "**~** Possible, **−** against (Unlikely / Thesis headwind / Cautious), "
            "**·** insufficient/absent. Order = Jensen / Leopold / Jordi / Gavin.",
            "",
            "| Ticker | Bucket | Rating | P(beat) | Exp 24mo | Target | "
            "Bear/Base/Bull | Combined | Jen/Leo/Jor/Gav | X | Status |",
            "|---|---|---|---|---|---|---|---|---|---|---|"]
    def s(x):
        return (x or "—").replace("|", "/").strip()
    for r in sorted(records, key=lambda x: x["ticker"]):
        sc = r["scenarios_24mo"]
        bbb = f"{s(sc['bear'])} / {s(sc['base'])} / {s(sc['bull'])}"
        br = r["brains"]
        brains = "".join(brain_sign(br[k]) for k in ("jensen", "leopold", "jordi", "gavin"))
        out += ["| " + " | ".join([
            f"**{r['ticker']}**", s(r["bucket"]), s(r["rating"]), s(r["pbeat"]),
            s(r["exp_return_24mo"]), s(r["target_24mo"]), bbb,
            s(r["combined_verdict"]), brains, brain_sign(br["x"]), s(r["status"]),
        ]) + " |"]
    out += [""]

    # --- per-name notes ---
    out += ["## 5. Per-name notes"]
    for r in sorted(records, key=lambda x: x["ticker"]):
        head = f"### {r['ticker']}"
        if r["name"]:
            head += f" — {r['name']}"
        head += f"  ({r['date']})"
        out += [head]
        line = (f"- Rating **{s(r['rating'])}** · P(beat) {s(r['pbeat'])} · "
                f"Exp 24mo {s(r['exp_return_24mo'])} · Target {s(r['target_24mo'])} · "
                f"CAGR {s(r['cagr_24mo'])} · Combined {s(r['combined_verdict'])}")
        out += [line]
        if r["price_at_analysis"]:
            out += [f"- Price at analysis: ${r['price_at_analysis']}"]
        if r["realized_alpha"]:
            out += [f"- Realized: raw {s(r['realized_raw'])} / alpha {s(r['realized_alpha'])}"]
        if r["verdict_for_new_investors"]:
            v = re.sub(r"\s+", " ", r["verdict_for_new_investors"])[:600]
            out += [f"- New-investor verdict: {v}"]
        out += [""]

    out += ["---", f"_{DISCLAIMER}_"]
    return "\n".join(out) + "\n"


def build_json(records, mem):
    cyc_date, stance, _ = latest_cycle()
    return {
        "as_of": TODAY,
        "disclaimer": DISCLAIMER,
        "task": TASK_PREAMBLE.strip(),
        "macro_cycle": {"date": cyc_date, "stance": stance},
        "track_record": track_record(mem),
        "benchmark": "SPY",
        "records": records,
    }


def main():
    ap = argparse.ArgumentParser(description="Export dashboard decisions for an LLM reviewer.")
    ap.add_argument("--format", choices=["md", "json", "both"], default="both")
    ap.add_argument("--full", action="store_true", help="every dated decision (default: latest/ticker)")
    ap.add_argument("--out", default=DEFAULT_OUT, help="output directory")
    ap.add_argument("--stdout", action="store_true", help="also print the markdown")
    args = ap.parse_args()

    mem = bd.parse_memory(MEM)
    decisions = collect_decisions(full=args.full)
    records = [rec(d, mem) for d in decisions]

    os.makedirs(args.out, exist_ok=True)
    md = render_md(records, mem, args.full)

    if args.format in ("md", "both"):
        p = os.path.join(args.out, "portfolio_llm.md")
        with open(p, "w", encoding="utf-8") as f:
            f.write(md)
        print(f"wrote {os.path.relpath(p, ROOT)}  ({len(records)} decisions)")
    if args.format in ("json", "both"):
        p = os.path.join(args.out, "portfolio.json")
        with open(p, "w", encoding="utf-8") as f:
            json.dump(build_json(records, mem), f, indent=2, ensure_ascii=False)
        print(f"wrote {os.path.relpath(p, ROOT)}  ({len(records)} decisions)")
    if args.stdout:
        print("\n" + md)


if __name__ == "__main__":
    main()
