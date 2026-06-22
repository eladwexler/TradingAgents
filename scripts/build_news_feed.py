#!/usr/bin/env python3
"""Build the dashboard's 🗞️ News-tab data feed.

Scans the keyless news corpora already refreshed by /update-all and distils a
dated, human-readable news feed that the dashboard renders:

  1. X Brain news lane (x-brain/index/chunks.jsonl) — FinTwit/AI posts + a
     Google-News proxy lane, each with title/url/date/text. We extract the
     stock(s) each item references (reusing x-brain's own cashtag/alias/symbol
     rules + bull/bear lexicon) and keep the *bullish* ones.
  2. Industry desk (ai-news/<date>/optimized_llm_payload.json) — primary-source
     semiconductor/AI articles (SemiAnalysis, EE Times, Semiconductor Engineering…).

Output (dashboard/data/news_feed.json, + a dated snapshot under news_history/):
  - per-DATE recap: an optional agent-written prose recap (news-recaps/<DATE>.md)
    on top of a deterministic auto-digest, the day's bullish stock-referencing
    headlines, the day's "new on the radar" cashtags, hot themes, and the
    industry desk.
  - by_ticker rollup: tracked names with fresh bullish news (window), flagged
    analyzed vs not, each with its headlines.
  - new_candidates: $cashtags that are NOT in the tracked universe but show up in
    bullish news — inferred beneficiaries worth a /trading-analysis.

Pure stdlib. Reuses x-brain's lexicon by import (falls back to a local copy).
Deterministic and idempotent — safe to re-run; /update-all calls it before
build_dashboard.py.
"""
import os, re, sys, json, glob, html, datetime
from collections import defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
X_HOME = os.environ.get("X_HOME", os.path.expanduser("~/projects/x-brain"))
AINEWS_HOME = os.environ.get("AINEWS_HOME", os.path.expanduser("~/projects/ai-news"))
STOCKS = os.path.join(ROOT, "analyzed-stocks")
RECAP_DIR = os.path.join(ROOT, "news-recaps")            # optional agent-written prose recaps
OUT = os.path.join(ROOT, "dashboard", "data", "news_feed.json")
HIST = os.path.join(ROOT, "dashboard", "data", "news_history")

WINDOW_DAYS = int(os.environ.get("NEWS_WINDOW_DAYS", "21"))   # how far back counts as "news"
MAX_RECAP_DAYS = 12                                           # dated recap cards to render
MAX_HEADLINES_PER_TICKER = 6
MAX_ITEMS_PER_DAY = 30
MIN_CAND_MENTIONS = 2          # floor to keep one-off random cashtags out of "new candidates"

# ---- reuse x-brain's ticker universe + sentiment lexicon (keep in sync) ------
try:
    sys.path.insert(0, os.path.join(X_HOME, "work"))
    import analyze_corpus as _ac          # noqa: E402  (guarded by __main__ in the module)
    TICKERS, AMBIGUOUS = _ac.TICKERS, _ac.AMBIGUOUS
    BULL, BEAR, count_terms = _ac.BULL, _ac.BEAR, _ac.count_terms
except Exception as e:                     # pragma: no cover — fallback keeps us running offline
    print(f"  [news] could not import x-brain analyze_corpus ({e}); using a minimal local lexicon")
    TICKERS, AMBIGUOUS = {}, set()
    BULL = ["bullish", "buy", "long", "calls", "breakout", "accumulate", "undervalued",
            "rally", "surge", "soar", "beat", "upgrade", "record", "strong", "wins", "secures"]
    BEAR = ["bearish", "sell", "short", "puts", "dump", "overvalued", "crash", "plunge",
            "miss", "downgrade", "weak", "cut", "lawsuit", "probe", "halt"]
    def count_terms(text_l, terms):
        return sum(text_l.count(t) for t in terms)

# cashtags that aren't single-stock equities (indices / FX / crypto / rates) — never a "new candidate"
NOT_STOCKS = {"SPX", "SPY", "QQQ", "DJI", "DIA", "IWM", "VIX", "DXY", "ES", "NQ", "RTY",
              "BTC", "ETH", "SOL", "XRP", "DOGE", "USD", "EUR", "GBP", "JPY", "GLD", "SLV",
              "TLT", "HYG", "TNX", "WTI", "USO", "VOO", "VTI", "TQQQ", "SQQQ", "UVXY"}

CASHTAG = re.compile(r"\$([A-Za-z]{1,5})\b")


def analyzed_universe():
    """Tickers that already have a /trading-analysis decision on file."""
    if not os.path.isdir(STOCKS):
        return set()
    return {d for d in os.listdir(STOCKS) if os.path.isdir(os.path.join(STOCKS, d))}


def build_matchers():
    alias = {tk: [re.compile(rf"\b{re.escape(a)}\b", re.I) for a in al]
             for tk, al in TICKERS.items()}
    sym = {tk: re.compile(rf"\b{tk}\b") for tk in TICKERS if tk not in AMBIGUOUS}
    return alias, sym


def refs_in(text, alias, sym):
    """Return (tracked_tickers:set, new_cashtags:set) referenced by one item.

    Mirrors x-brain's detection: a $cashtag, a name alias (word-boundary), or the
    bare uppercase symbol (skipped for AMBIGUOUS dictionary-word tickers)."""
    tracked, cands = set(), set()
    for m in CASHTAG.findall(text):
        up = m.upper()
        if up in TICKERS:
            tracked.add(up)
        elif up not in NOT_STOCKS:
            cands.add(up)
    for tk in TICKERS:
        if tk in tracked:
            continue
        if any(p.search(text) for p in alias[tk]):
            tracked.add(tk); continue
        sp = sym.get(tk)
        if sp and sp.search(text):
            tracked.add(tk)
    return tracked, cands


def load_x_news():
    """Yield {title,url,date,source,text} for each X-corpus news/post item."""
    path = os.path.join(X_HOME, "index", "chunks.jsonl")
    if not os.path.exists(path):
        return
    seen = set()
    with open(path, encoding="utf-8") as f:
        for line in f:
            try:
                d = json.loads(line)
            except Exception:
                continue
            doc = d.get("doc")              # one item spans multiple chunks; keep the first
            if doc in seen:
                continue
            seen.add(doc)
            yield {
                "title": (d.get("title") or d.get("text") or "")[:240],
                "url": d.get("url", ""),
                "date": (d.get("date") or "")[:10],
                "source": d.get("source", "x"),
                "text": d.get("text") or d.get("title") or "",
            }


def load_industry(since):
    """Recent ai-news primary-source articles grouped by date (YYYY-MM-DD)."""
    by_date = defaultdict(list)
    for pf in sorted(glob.glob(os.path.join(AINEWS_HOME, "*", "optimized_llm_payload.json"))):
        day = os.path.basename(os.path.dirname(pf))
        if not re.match(r"\d{4}-\d{2}-\d{2}", day) or day < since:
            continue
        try:
            arts = json.load(open(pf, encoding="utf-8"))
        except Exception:
            continue
        for a in arts if isinstance(arts, list) else []:
            by_date[day].append({
                "title": a.get("title", ""),
                "source": (a.get("source", "") or "").replace("_", " "),
                "url": a.get("url", ""),
                "tags": a.get("tags", []) if isinstance(a.get("tags"), list) else [],
            })
    return by_date


def load_recap(day):
    """Optional agent-written prose recap for a date (news-recaps/<DATE>.md)."""
    p = os.path.join(RECAP_DIR, f"{day}.md")
    if os.path.exists(p):
        return open(p, encoding="utf-8").read().strip()
    return None


def auto_digest(day_names, day_cands, themes, n_items, n_industry):
    """Deterministic, human-readable one-paragraph digest for a date."""
    if not n_items and not n_industry:
        return "Quiet tape — no stock-referencing bullish chatter captured."
    parts = []
    if n_items:
        top = ", ".join(f"{t} (+{net})" for t, net, _ in day_names[:3])
        parts.append(f"{n_items} bullish stock-referencing item(s) across "
                     f"{len(day_names)} name(s)" + (f" — hottest: {top}." if top else "."))
    if day_cands:
        nc = ", ".join(f"${t} ×{c}" for t, c in day_cands[:4])
        parts.append(f"New on the radar: {nc}.")
    if themes:
        parts.append("Themes: " + ", ".join(themes[:3]) + ".")
    if n_industry:
        parts.append(f"Industry desk: {n_industry} primary-source article(s).")
    return " ".join(parts)


def main():
    today = datetime.date.today().isoformat()
    since = (datetime.date.today() - datetime.timedelta(days=WINDOW_DAYS)).isoformat()
    analyzed = analyzed_universe()
    alias, sym = build_matchers()

    # hot themes from the X research snapshot (if present)
    themes = []
    rp = os.path.join(X_HOME, "index", "research.json")
    if os.path.exists(rp):
        try:
            themes = [t["topic"] for t in json.load(open(rp)).get("trends", [])]
        except Exception:
            themes = []

    # ---- scan X news lane: keep bullish, stock-referencing items in the window ----
    by_ticker = defaultdict(lambda: {"net": 0, "mentions": 0, "headlines": []})
    cand_stat = defaultdict(lambda: {"mentions": 0, "first": "", "last": "", "sample": None})
    items_by_date = defaultdict(list)
    n_scanned = n_kept = 0

    for it in load_x_news():
        day = it["date"]
        if not day or day < since:
            continue
        n_scanned += 1
        text = it["text"]
        tracked, cands = refs_in(text, alias, sym)
        if not tracked and not cands:
            continue
        tl = text.lower()
        net = count_terms(tl, BULL) - count_terms(tl, BEAR)
        if net <= 0:                          # bullish only
            continue
        n_kept += 1
        rec = {"title": it["title"], "url": it["url"], "date": day,
               "source": it["source"], "net": net,
               "tickers": sorted(tracked), "cands": sorted(cands)}
        items_by_date[day].append(rec)
        for tk in tracked:
            s = by_ticker[tk]
            s["net"] += net
            s["mentions"] += 1
            s["headlines"].append({"title": it["title"], "url": it["url"],
                                   "date": day, "source": it["source"], "net": net})
        for c in cands:
            cs = cand_stat[c]
            cs["mentions"] += 1
            cs["last"] = max(cs["last"], day)
            cs["first"] = min(cs["first"] or day, day)
            if cs["sample"] is None or net > cs["sample"]["net"]:
                cs["sample"] = {"title": it["title"], "url": it["url"], "date": day, "net": net}

    industry = load_industry(since)

    # ---- per-date recap cards (newest first) ----
    all_dates = sorted(set(list(items_by_date) + list(industry)), reverse=True)[:MAX_RECAP_DAYS]
    dates_out = []
    for day in all_dates:
        items = sorted(items_by_date.get(day, []), key=lambda r: -r["net"])[:MAX_ITEMS_PER_DAY]
        # day-level top names + candidates
        dn = defaultdict(lambda: [0, 0])      # ticker -> [net, mentions]
        dc = defaultdict(int)
        for r in items:
            for tk in r["tickers"]:
                dn[tk][0] += r["net"]; dn[tk][1] += 1
            for c in r["cands"]:
                dc[c] += 1
        day_names = sorted(([t, v[0], v[1]] for t, v in dn.items()), key=lambda x: (-x[1], -x[2]))
        day_cands = sorted(dc.items(), key=lambda x: -x[1])
        ind = industry.get(day, [])
        dates_out.append({
            "date": day,
            "prose": load_recap(day),
            "digest": auto_digest(day_names, day_cands, themes, len(items), len(ind)),
            "n_items": len(items),
            "top_names": [{"ticker": t, "net": n, "mentions": m} for t, n, m in day_names[:8]],
            "new_candidates": [{"ticker": t, "mentions": c} for t, c in day_cands[:8]],
            "items": items,
            "industry": ind,
        })

    # ---- by-ticker rollup (tracked names, window) ----
    bt = []
    for tk, s in by_ticker.items():
        heads = sorted(s["headlines"], key=lambda h: (h["date"], h["net"]), reverse=True)[:MAX_HEADLINES_PER_TICKER]
        bt.append({"ticker": tk, "analyzed": tk in analyzed, "net": s["net"],
                   "mentions": s["mentions"], "headlines": heads})
    bt.sort(key=lambda x: (-x["net"], -x["mentions"]))

    # ---- new candidates (untracked $cashtags in bullish news) ----
    nc = [{"ticker": t, "mentions": v["mentions"], "first_seen": v["first"],
           "last_seen": v["last"], "sample": v["sample"]}
          for t, v in cand_stat.items()
          if t not in analyzed and v["mentions"] >= MIN_CAND_MENTIONS]
    nc.sort(key=lambda x: (-x["mentions"], x["ticker"]))

    feed = {
        "generated": datetime.datetime.now().isoformat(timespec="seconds"),
        "window_days": WINDOW_DAYS,
        "since": since,
        "n_scanned": n_scanned,
        "n_bullish_items": n_kept,
        "dates": dates_out,
        "by_ticker": bt,
        "new_candidates": nc,
    }

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    os.makedirs(HIST, exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(feed, f, ensure_ascii=False, indent=1)
    with open(os.path.join(HIST, f"{today}.json"), "w", encoding="utf-8") as f:
        json.dump(feed, f, ensure_ascii=False)
    print(f"wrote {OUT}: {n_kept} bullish stock-ref items / {n_scanned} scanned "
          f"(window {WINDOW_DAYS}d) · {len(bt)} tracked names · {len(nc)} new candidates · "
          f"{len(dates_out)} recap day(s) · snapshot -> news_history/{today}.json")


if __name__ == "__main__":
    main()
