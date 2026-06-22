#!/usr/bin/env python3
"""Print the short "re-run these today" list — the daily *what's due* report.

The whole point of the /daily routine is NOT to re-forecast everything; it's to tell
you the handful of names that have a real reason to be re-analyzed. This reads only
caches the daily refresh already produced (no per-ticker network), and flags an open
call when:

  * DRIFT     — flagged by `ta_memory.py watch` (in under_pressure.json): the call is
                moving hard against its thesis.
  * MOVE      — |price move since the analysis entry| ≥ MOVE_PCT (default 20%): the
                thesis may be broken or validated; the multiple has re-rated.
  * CHECKPOINT— the 3 / 6 / 9 / 12-month review points have elapsed since the last
                analysis without a refresh (interim at 3/9, full at 6, resolve at 12).

It also separates out MATURED calls (horizon elapsed) which should be *resolved*
(graded), not re-run. Earnings-since-last-analysis is NOT detected here (no earnings
feed on the free stack) — that one you watch manually around report dates.

Usage:  python3 scripts/reanalysis_triggers.py [--move-pct 20] [--json]
Reads:  analyzed-stocks/<T>/<DATE>_decision.md (latest per ticker),
        ~/.tradingagents/memory/metrics.json (live price),
        ~/.tradingagents/memory/under_pressure.json (drift flags).
"""
import os, re, glob, json, argparse, datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STOCKS = os.path.join(ROOT, "analyzed-stocks")
MEMDIR = os.path.expanduser("~/.tradingagents/memory")
METRICS = os.path.join(MEMDIR, "metrics.json")
UNDER = os.path.join(MEMDIR, "under_pressure.json")

CHECKPOINTS = [(90, "3mo"), (183, "6mo"), (274, "9mo"), (365, "12mo")]


def latest_decisions():
    """Latest decision file per ticker → (ticker, date, entry_price, rating, horizon_m)."""
    out = {}
    for d in sorted(glob.glob(os.path.join(STOCKS, "*", "*_decision.md"))):
        tk = os.path.basename(os.path.dirname(d))
        m = re.search(r"(\d{4}-\d{2}-\d{2})_decision\.md$", d)
        if not m:
            continue
        date = m.group(1)
        if tk in out and date <= out[tk]["date"]:
            continue
        txt = open(d, encoding="utf-8", errors="replace").read()
        pm = re.search(r"Price at analysis:\s*\$([0-9][0-9,]*\.?[0-9]*)", txt)
        rm = re.search(r"FINAL TRANSACTION PROPOSAL \(MACRO-ADJUSTED\):.*?\b(Buy|Overweight|Hold|Underweight|Sell)\b",
                       txt, re.I) or re.search(r"\b(Buy|Overweight|Hold|Underweight|Sell)\b", txt)
        hm = re.search(r"H=?\s*(\d+)\s*mo|horizon[^0-9]*(\d+)\s*month", txt, re.I)
        out[tk] = {"ticker": tk, "date": date,
                   "entry": float(pm.group(1).replace(",", "")) if pm else None,
                   "rating": (rm.group(1).title() if rm else "—"),
                   "horizon_m": int(next((g for g in (hm.groups() if hm else []) if g), 24))}
    return out


def load_live_prices():
    try:
        return json.load(open(METRICS)).get("metrics", {})
    except Exception:
        return {}


def load_drift():
    try:
        return {f["ticker"] for f in json.load(open(UNDER)).get("flagged", [])}
    except Exception:
        return set()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--move-pct", type=float, default=20.0)
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    today = datetime.date.today()
    decs = latest_decisions()
    prices = load_live_prices()
    drift = load_drift()

    due, matured = [], []
    for tk, d in decs.items():
        try:
            dd = datetime.date.fromisoformat(d["date"])
        except ValueError:
            continue
        days = (today - dd).days
        hz_days = round(d["horizon_m"] * 30.44)
        live = (prices.get(tk) or {}).get("price")
        move = ((live - d["entry"]) / d["entry"] * 100) if (live and d["entry"]) else None

        if days >= hz_days * 0.95:
            matured.append({**d, "days": days, "move": move})
            continue

        reasons, pr = [], 0
        if tk in drift:
            reasons.append("DRIFT (under pressure vs thesis)"); pr = max(pr, 3)
        if move is not None and abs(move) >= a.move_pct:
            reasons.append(f"MOVE {move:+.0f}% since entry"); pr = max(pr, 2)
        cp = [name for days_thr, name in CHECKPOINTS if days >= days_thr]
        if cp:
            reasons.append(f"CHECKPOINT {cp[-1]} elapsed (analyzed {days}d ago)"); pr = max(pr, 1)
        if reasons:
            due.append({**d, "days": days, "move": move, "reasons": reasons, "prio": pr})

    due.sort(key=lambda x: (-x["prio"], -(abs(x["move"]) if x["move"] is not None else 0)))

    if a.json:
        print(json.dumps({"due": due, "matured": matured}, indent=1)); return

    print(f"=== Re-analysis triggers — {today} ===")
    print(f"{len(decs)} tracked names · {len(due)} due to RE-RUN · {len(matured)} MATURED (resolve, don't re-run)\n")
    if due:
        print("RE-RUN these (event-driven — not the whole book):")
        for x in due:
            tag = {3: "🔴", 2: "🟠", 1: "🟡"}[x["prio"]]
            mv = f"{x['move']:+.0f}%" if x["move"] is not None else "n/a"
            print(f"  {tag} {x['ticker']:6} [{x['rating']}]  {mv} since {x['date']}  — " + "; ".join(x["reasons"]))
    else:
        print("No open call has a re-run trigger today. Nothing to re-forecast. ✅")
    if matured:
        print("\nMATURED — resolve & Brier-score (ta_memory.py resolve), do NOT re-run:")
        for x in matured:
            print(f"  ✓ {x['ticker']:6} [{x['rating']}] analyzed {x['date']} ({x['days']}d, {x['horizon_m']}mo horizon)")
    print("\nNote: earnings-since-last-analysis isn't auto-detected (no earnings feed) — watch report dates manually.")


if __name__ == "__main__":
    main()
