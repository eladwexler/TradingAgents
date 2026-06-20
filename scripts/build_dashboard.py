#!/usr/bin/env python3
"""Render every /trading-analysis verdict into HTML: one page per decision (from
scripts/templates/decision.html), plus an index + best-call dashboards
(scripts/templates/index.html). Pure stdlib, no deps.

Sources of truth:
  - the persistent decision log (~/.tradingagents/memory/trading_memory.md, or
    $TRADINGAGENTS_MEMORY_LOG_PATH) — the uniform spine: rating, pending/resolved
    status, P(beat) probability, horizon, and realized raw/alpha once matured.
  - analyzed-stocks/<TICKER>/<DATE>_decision.md — the richer per-decision detail
    (BASE/MACRO proposals, forecast table, Jensen/Leopold/Combined verdicts).

Output -> dashboard/ (open dashboard/index.html).
Rebuild:  python3 scripts/build_dashboard.py
"""
import os, re, glob, html, json, datetime, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(os.path.join(ROOT, ".claude", "skills", "trading-analysis", "scripts"))
try:
    from ta_memory import fetch_returns, fetch_last_price
except ImportError:
    fetch_returns = None
    fetch_last_price = None

TPL = os.path.join(ROOT, "scripts", "templates")
OUT = os.path.join(ROOT, "dashboard")
STOCKS = os.path.join(ROOT, "analyzed-stocks")
MEM = os.environ.get("TRADINGAGENTS_MEMORY_LOG_PATH",
                     os.path.expanduser("~/.tradingagents/memory/trading_memory.md"))
# X Brain research artifact (trending AI topics + most-bullish names); optional.
X_HOME = os.environ.get("X_HOME", "/home/ewexler/projects/x-brain")
X_RESEARCH = os.path.join(X_HOME, "index", "research.json")
X_HIST = os.path.join(X_HOME, "index", "research_history")
NOW = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")


def load_x_research(path):
    """X-brain research.json (trends + bullish stocks), or {} if unavailable."""
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


UNDER_PRESSURE = os.path.join(os.path.dirname(MEM), "under_pressure.json")
METRICS = os.path.join(os.path.dirname(MEM), "metrics.json")


def load_under_pressure(path):
    """ta_memory watch cache (open calls drifting against the thesis), or {} if absent."""
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


METRICS_HIST = os.path.join(os.path.dirname(MEM), "metrics_history")


def load_metrics(path):
    """fetch_metrics.py cache: {TICKER: {market_cap, forward_pe, …}} or {} if absent.

    Network-free here — the fetcher does the yfinance work and writes this JSON;
    the dashboard only reads it (offline → last cache)."""
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f).get("metrics", {})
    except Exception:
        return {}


def load_prev_metrics(hist_dir=METRICS_HIST):
    """Most recent dated metrics snapshot strictly older than today's — for the
    week-over-week Financials-moves diff. {} if none yet (first run = baseline)."""
    today = datetime.date.today().isoformat()
    try:
        snaps = sorted(f for f in os.listdir(hist_dir) if f.endswith(".json"))
    except Exception:
        return {}
    older = [f for f in snaps if f[:10] < today]
    if not older:
        return {}
    try:
        with open(os.path.join(hist_dir, older[-1]), encoding="utf-8") as f:
            return json.load(f).get("metrics", {})
    except Exception:
        return {}


def load_prev_research(cur):
    """Most recent dated research snapshot strictly older than the current one (for diffing)."""
    cur_date = (cur.get("generated", "") or "")[:10]
    try:
        snaps = sorted(f for f in os.listdir(X_HIST) if f.endswith(".json"))
    except Exception:
        return {}
    prev = [f for f in snaps if f[:10] < cur_date]
    if not prev:
        return {}
    try:
        with open(os.path.join(X_HIST, prev[-1]), encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

# ---------- parsing ----------------------------------------------------------

def parse_memory(path):
    """(date,ticker) -> {rating,status,raw,alpha,holding,prob,horizon}."""
    out = {}
    if not os.path.exists(path):
        return out
    hdr = re.compile(r"^\[(\d{4}-\d{2}-\d{2}) \| ([A-Z0-9.\-]+) \| ([^|\]]+?) \| (.+?)\]\s*$")
    for line in open(path, encoding="utf-8"):
        m = hdr.match(line)
        if not m:
            continue
        date, tk, rating, rest = m.group(1), m.group(2), m.group(3).strip(), m.group(4).strip()
        rec = {"rating": rating, "status": "pending", "raw": "", "alpha": "",
               "holding": "", "prob": "", "horizon": ""}
        parts = [p.strip() for p in rest.split("|")]
        if parts and parts[0].lower().startswith("pending"):
            rec["status"] = "pending"
            for p in parts[1:]:
                if p.startswith("P="):
                    rec["prob"] = p[2:]
                elif p.startswith("H="):
                    rec["horizon"] = p[2:]
        elif parts and re.match(r"^[+\-]?\d", parts[0]):
            rec["status"] = "resolved"
            rec["raw"] = parts[0]
            if len(parts) > 1: rec["alpha"] = parts[1]
            if len(parts) > 2: rec["holding"] = parts[2]
        out[(date, tk)] = rec
    return out


def grab(pat, text, grp=1, flags=re.I):
    m = re.search(pat, text, flags)
    return m.group(grp).strip() if m else ""


def parse_forecast(md):
    """Return {'12mo':{...},'24mo':{...},'36mo':{...}} from the markdown table."""
    rows = {}
    lines = md.splitlines()
    header, cols = None, []
    for ln in lines:
        if "|" not in ln:
            continue
        cells = [c.strip() for c in ln.strip().strip("|").split("|")]
        low = [c.lower() for c in cells]
        if any("horizon" in c for c in low):
            header = low
            def idx(*keys):
                for i, c in enumerate(header):
                    if any(k in c for k in keys):
                        return i
                return -1
            cols = {"bear": idx("bear"), "base": idx("base"), "bull": idx("bull"),
                    "exp": idx("expected", "exp."), "target": idx("target"),
                    "cagr": idx("cagr"), "pbeat": idx("p(beat", "beat")}
            continue
        if header and re.match(r"^(12|24|36)\s*mo", cells[0].lower().replace(" ", "")):
            hz = re.match(r"^(12|24|36)", cells[0]).group(1) + "mo"
            def cell(key):
                i = cols.get(key, -1)
                return cells[i] if 0 <= i < len(cells) else ""
            rows[hz] = {k: cell(k) for k in
                        ("bear", "base", "bull", "exp", "target", "cagr", "pbeat")}
    return rows


def parse_decision(path):
    md = open(path, encoding="utf-8").read()
    base = os.path.basename(path)
    date = base.split("_")[0]
    ticker = os.path.basename(os.path.dirname(path))
    d = {"ticker": ticker, "date": date, "src": os.path.relpath(path, ROOT), "md": md}
    # company name from a title line "# TKR — Name — ..."
    title = grab(r"^#\s+" + re.escape(ticker) + r"\s+[—-]\s+(.+?)\s+[—-]", md, flags=re.M)
    d["name"] = title or ""
    # proposals
    d["base_action"] = grab(r"FINAL TRANSACTION PROPOSAL \(BASE\):\s*\*{0,2}([A-Za-z]+)", md)
    d["base_rating"] = grab(r"FINAL TRANSACTION PROPOSAL \(BASE\):.*?rating[:\s]+\**([A-Za-z→\- ]+?)\**[\s\*]*[(\n]", md)
    d["macro_action"] = grab(r"FINAL TRANSACTION PROPOSAL \(MACRO-ADJUSTED\):\s*\*{0,2}([A-Za-z]+)", md)
    d["macro_rating"] = grab(r"FINAL TRANSACTION PROPOSAL \(MACRO-ADJUSTED\):.*?rating[:\s]+\**([A-Za-z→\- ]+?)\**[\s\*]*[(\n]", md)
    if not d["base_action"]:  # older single-proposal format
        d["base_action"] = grab(r"FINAL TRANSACTION PROPOSAL:\s*\*{0,2}([A-Za-z]+)", md)
        d["base_rating"] = grab(r"^Rating:\s*([A-Za-z→\- ]+)", md, flags=re.M) or d["base_action"].title()
    d["verdict_new"] = grab(r"VERDICT FOR NEW INVESTORS:\**\s*(.+?)(?:\n\n|\n#|\n\*\*FINAL|\Z)", md, flags=re.I | re.S)
    d["jensen"] = grab(r"Jensen Brain Verdict:\s*\**\s*([A-Za-z ]+?)\**\s*[(\-—\n]", md)
    d["leopold"] = grab(r"Leopold Brain Verdict:\s*\**\s*([A-Za-z ]+?)\**\s*[(\-—\n]", md)
    d["jordi"] = grab(r"Jordi Brain Verdict:\s*\**\s*([A-Za-z ]+?)\**\s*[(\-—\n]", md)
    d["gavin"] = grab(r"Gavin Brain Verdict:\s*\**\s*([A-Za-z ]+?)\**\s*[(\-—\n]", md)
    d["x"] = grab(r"X Brain Verdict:\s*\**\s*([A-Za-z ]+?)\**\s*[(\-—\n]", md)
    d["combined"] = grab(r"Combined Strategic Verdict:\s*\**\s*([A-Z ]+?)\**\s*[(\-—\.\n]", md)
    # price recorded at analysis time (entry reference) — "Price at analysis: $123.45 …"
    d["price_at"] = grab(r"Price at analysis[:\s]*\**\s*\$?\s*([\d,]+(?:\.\d+)?)", md)
    d["forecast"] = parse_forecast(md)
    return d

# ---------- AI build-out domain (where each name sits in the stack) ----------
# One layer of the AI build-out per ticker, hardware-up the stack to applications.
AI_DOMAIN = {
    "NVDA": "Compute — GPU accelerators",
    "AMD":  "Compute — GPU accelerators",
    "AVGO": "Custom AI silicon & networking (ASIC)",
    "MRVL": "Custom AI silicon & optical DSP (ASIC)",
    "ARM":  "Compute IP / CPU architecture",
    "ALAB": "AI connectivity silicon (retimers/PCIe)",
    "CRDO": "AI connectivity silicon (active cables)",
    "COHR": "Optical interconnect & networking",
    "LITE": "Optical interconnect & networking",
    "CIEN": "Optical interconnect & networking",
    "AAOI": "Optical interconnect & networking",
    "MU":   "Memory / HBM",
    "Q":    "Semiconductor materials / fab supply",
    "DELL": "AI servers & systems (OEM)",
    "PENG": "AI infrastructure / HPC integration",
    "CEG":  "Power generation (nuclear)",
    "BE":   "Power generation (fuel cells)",
    "ATKR": "Electrical / grid infrastructure",
    "VRT":  "Datacenter power & cooling",
    "CRWV": "Neocloud / GPU cloud capacity",
    "NBIS": "Neocloud / GPU cloud capacity",
    "APLD": "Neocloud / datacenter capacity",
    "IREN": "Neocloud / GPU capacity (ex-bitcoin miner)",
    "BRUN": "Neocloud / AI compute (micro-cap)",
    "MSFT": "Hyperscaler / cloud platform",
    "GOOGL":"Hyperscaler / cloud platform",
    "AMZN": "Hyperscaler / cloud platform",
    "META": "Hyperscaler / cloud platform",
    "PLTR": "AI application software & agents",
    "NOW":  "AI application software (enterprise SaaS)",
    "SNOW": "AI application software (data cloud)",
    "PATH": "AI application software (automation/agents)",
    "ZETA": "AI application software (marketing)",
    "PANW": "Cybersecurity",
    "ZS":   "Cybersecurity",
    "IBIT": "Bitcoin / crypto (AI-macro)",
    "TSLA": "Physical AI / robotics & autonomy",
    "SOFI": "Fintech / consumer finance",
    "OTLK": "Outside the AI build-out (biotech)",
    # --- 2026-06-20 batch ---
    "IQE":  "Semiconductor materials / fab supply",
    "AEHR": "Semiconductor test equipment",
    "GLW":  "Optical interconnect & networking",
    "NVTS": "Power semiconductors (GaN/SiC)",
    "QCOM": "Compute — edge / mobile AI",
    "ANET": "AI networking (datacenter switching)",
    "SMCI": "AI servers & systems (OEM)",
    "CORZ": "Neocloud / datacenter capacity",
    "ETN":  "Datacenter power & electrical",
    "PWR":  "Electrical / grid infrastructure",
    "GEV":  "Power generation (grid / turbines)",
    "ALB":  "Battery materials (lithium)",
    "OKLO": "Power generation (nuclear SMR)",
    "MP":   "Rare earths / critical minerals",
    "CRML": "Rare earths / critical minerals",
    "USAR": "Rare earths / critical minerals",
    "TMRC": "Rare earths / critical minerals",
    "IONQ": "Quantum computing",
    "AXTI": "Semiconductor materials / fab supply",
    "OSS":  "Edge AI compute",
    "HYLN": "Power generation (distributed)",
    "AMPX": "Battery / energy storage",
    "CIFR": "Neocloud / datacenter capacity",
    "KEEL": "AI infrastructure / datacenter",
    "SLNH": "Neocloud / renewable datacenter",
    "TE":   "Power / clean energy",
    "WYFI": "Unverified / AI-adjacent",
    "SIVE": "Unverified",
}

# How each AI-trend domain behaves in general — the secular character of the layer.
DOMAIN_NOTE = {
    "Compute — GPU accelerators": "The engine of the build-out — demand outruns supply; NVDA the scarce toll-booth, AMD the contested #2.",
    "Custom AI silicon & networking (ASIC)": "Hyperscaler custom-silicon & switching — scarce, high-moat supplier layer all three lenses favor.",
    "Custom AI silicon & optical DSP (ASIC)": "Custom silicon + optical DSP — picks-and-shovels of rack-scale compute; consensus tailwind.",
    "Compute IP / CPU architecture": "Architecture IP beneath every chip — thesis-adjacent, thinner direct coverage.",
    "AI connectivity silicon (retimers/PCIe)": "Scale-up interconnect plumbing — small but necessary part of rack-scale compute.",
    "AI connectivity silicon (active cables)": "Active-cable connectivity — picks-and-shovels of dense GPU racks.",
    "Optical interconnect & networking": "The scale-out backbone — Jensen's 'copper wall → optics'; a consensus scarce-supplier tailwind, partly NVDA-funded.",
    "Memory / HBM": "Memory is the co-bottleneck with compute — HBM reprices up in the shortage.",
    "Semiconductor materials / fab supply": "Upstream fab/materials — enables every leading-edge wafer; quiet picks-and-shovels.",
    "AI servers & systems (OEM)": "Box-builders turning capex into systems — 'your capex is my opportunity.'",
    "AI infrastructure / HPC integration": "Compute+memory integrator — thinner, deal-dependent exposure.",
    "Power generation (nuclear)": "Electricity is the binding constraint — gated, must-build base-load power.",
    "Power generation (fuel cells)": "On-site power for datacenters — the electricity-scarcity theme.",
    "Electrical / grid infrastructure": "Grid/electrical real-economy build — picks-and-shovels of datacenter power.",
    "Datacenter power & cooling": "Thermal/power inside the datacenter — direct capex beneficiary.",
    "Neocloud / GPU cloud capacity": "Debt-funded GPU capacity — CONTESTED: build-out tailwind vs Visser's ROIC-gap / private-credit warning.",
    "Neocloud / datacenter capacity": "Debt-funded datacenter capacity — contested on financing structure (ROIC gap / leverage).",
    "Neocloud / GPU capacity (ex-bitcoin miner)": "Bitcoin-miner pivoting to GPU cloud — mixed: crypto optionality vs neocloud leverage risk.",
    "Neocloud / AI compute (micro-cap)": "Speculative micro-cap compute — casualty-profile if financing tightens.",
    "Hyperscaler / cloud platform": "The spenders — CONTESTED: Leopold says they build the trillion-dollar cluster (tailwind); Visser says underweight them on the ROIC gap / negative FCF.",
    "AI application software & agents": "The software WINNER (PLTR) — ontology/agents survive and win the SaaS shift.",
    "AI application software (enterprise SaaS)": "The 'SaaS-pocalypse' layer — seat-priced software agents commoditize; a headwind.",
    "AI application software (data cloud)": "Consumption SaaS repriced as a technology-risk asset — disruption headwind.",
    "AI application software (automation/agents)": "Legacy RPA in the agents' cross-hairs — abundance-side casualty.",
    "AI application software (marketing)": "Marketing SaaS — application software AI compresses; headwind.",
    "Cybersecurity": "Necessary spend Visser likes, but still a SaaS multiple at risk — net mixed.",
    "Bitcoin / crypto (AI-macro)": "Visser's purest AI-macro / abundance-deflation trade; sits outside the Jensen/Leopold lens.",
    "Physical AI / robotics & autonomy": "The next leg — 'AI to the physical world'; robotaxi/humanoid optionality.",
    "Fintech / consumer finance": "Credit-cycle exposed with crypto optionality — mixed.",
    "Outside the AI build-out (biotech)": "Not an AI-build-out name — judged on its own merits.",
}

# ---------- buckets: generic categories that group the micro-domains ---------
# Each fine-grained AI_DOMAIN rolls up into one broad bucket (compute, networking,
# photonics, power…) so names can be grouped & sorted by category, with the
# specific domain kept underneath.
BUCKET = {
    # Compute
    "Compute — GPU accelerators": "Compute",
    "Compute IP / CPU architecture": "Compute",
    "Compute — edge / mobile AI": "Compute",
    "Edge AI compute": "Compute",
    # Custom silicon
    "Custom AI silicon & networking (ASIC)": "Custom silicon (ASIC)",
    "Custom AI silicon & optical DSP (ASIC)": "Custom silicon (ASIC)",
    # Networking & connectivity
    "AI connectivity silicon (retimers/PCIe)": "Networking & connectivity",
    "AI connectivity silicon (active cables)": "Networking & connectivity",
    "AI networking (datacenter switching)": "Networking & connectivity",
    # Photonics / optical
    "Optical interconnect & networking": "Photonics / optical",
    # Memory
    "Memory / HBM": "Memory",
    # Semiconductor supply chain
    "Semiconductor materials / fab supply": "Semiconductor supply chain",
    "Semiconductor test equipment": "Semiconductor supply chain",
    # Systems & servers
    "AI servers & systems (OEM)": "Systems & servers",
    "AI infrastructure / HPC integration": "Systems & servers",
    "AI infrastructure / datacenter": "Systems & servers",
    # Cloud & datacenter capacity
    "Neocloud / GPU cloud capacity": "Cloud & datacenter capacity",
    "Neocloud / datacenter capacity": "Cloud & datacenter capacity",
    "Neocloud / GPU capacity (ex-bitcoin miner)": "Cloud & datacenter capacity",
    "Neocloud / AI compute (micro-cap)": "Cloud & datacenter capacity",
    "Neocloud / renewable datacenter": "Cloud & datacenter capacity",
    # Hyperscalers
    "Hyperscaler / cloud platform": "Hyperscalers",
    # Power & energy
    "Power generation (nuclear)": "Power & energy",
    "Power generation (nuclear SMR)": "Power & energy",
    "Power generation (fuel cells)": "Power & energy",
    "Power generation (grid / turbines)": "Power & energy",
    "Power generation (distributed)": "Power & energy",
    "Power / clean energy": "Power & energy",
    "Electrical / grid infrastructure": "Power & energy",
    "Datacenter power & cooling": "Power & energy",
    "Datacenter power & electrical": "Power & energy",
    "Power semiconductors (GaN/SiC)": "Power & energy",
    # Materials & storage
    "Battery materials (lithium)": "Materials & storage",
    "Battery / energy storage": "Materials & storage",
    "Rare earths / critical minerals": "Materials & storage",
    # Software & applications
    "AI application software & agents": "Software & applications",
    "AI application software (enterprise SaaS)": "Software & applications",
    "AI application software (data cloud)": "Software & applications",
    "AI application software (automation/agents)": "Software & applications",
    "AI application software (marketing)": "Software & applications",
    # Cybersecurity
    "Cybersecurity": "Cybersecurity",
    # Physical AI
    "Physical AI / robotics & autonomy": "Physical AI & robotics",
    # Quantum
    "Quantum computing": "Quantum computing",
    # Crypto / AI-macro
    "Bitcoin / crypto (AI-macro)": "Crypto / AI-macro",
    # Other / outside AI
    "Fintech / consumer finance": "Other / outside AI",
    "Outside the AI build-out (biotech)": "Other / outside AI",
    "Unverified / AI-adjacent": "Other / outside AI",
    "Unverified": "Other / outside AI",
}

# bucket display order — roughly hardware-up the stack, then off-thesis
BUCKET_ORDER = ["Compute", "Custom silicon (ASIC)", "Networking & connectivity",
                "Photonics / optical", "Memory", "Semiconductor supply chain",
                "Systems & servers", "Cloud & datacenter capacity", "Hyperscalers",
                "Power & energy", "Materials & storage", "Software & applications",
                "Cybersecurity", "Physical AI & robotics", "Quantum computing",
                "Crypto / AI-macro", "Other / outside AI"]

def bucket_for_domain(dom):
    return BUCKET.get(dom, "Other / outside AI")

def bucket_for(ticker):
    return bucket_for_domain(AI_DOMAIN.get(ticker, "—"))

def bucket_rank(b):
    return BUCKET_ORDER.index(b) if b in BUCKET_ORDER else len(BUCKET_ORDER)

# ---------- classification helpers ------------------------------------------

def cls_action(a):
    a = (a or "").upper()
    return "b-buy" if a == "BUY" else "b-sell" if a == "SELL" else "b-hold" if a == "HOLD" else "b-neu"

def cls_rating(r):
    r = (r or "").lower()
    if any(k in r for k in ("buy", "overweight")): return "b-buy"
    if any(k in r for k in ("underweight", "sell")): return "b-sell"
    if "hold" in r: return "b-hold"
    return "b-neu"

def cls_combined(c):
    c = (c or "").upper()
    return {"CONVICTION ALIGNED": "v-conviction", "ALIGNED": "v-aligned",
            "NEUTRAL": "v-neutral", "CONTESTED": "v-contested",
            "EXPOSED": "v-exposed", "OFFSIDE": "v-offside",
            "INSUFFICIENT": "v-insufficient"}.get(c, "v-neutral")

def cls_brain(v):
    v = (v or "").lower()
    if "tailwind" in v or "likely" in v or "constructive" in v or "conviction" in v: return "b-buy"
    if "headwind" in v or "unlikely" in v or "cautious" in v or "avoid" in v: return "b-sell"
    if "possible" in v: return "b-hold"
    return "b-neu"

def cls_x(v):
    """X Brain crowd-sentiment verdict → badge class."""
    v = (v or "").lower()
    if "bullish" in v: return "b-buy"
    if "bearish" in v: return "b-sell"
    if "mixed" in v: return "b-hold"
    return "b-neu"


def x_verdict_score(v):
    """X Brain verdict → ordinal so we can tell which way the crowd moved."""
    v = (v or "").lower()
    if "bullish" in v: return 1
    if "bearish" in v: return -1
    return 0  # Mixed / Insufficient chatter — neutral


def x_trend_cell(runs):
    """Inline trend for a ticker's X Brain verdict: latest vs its previous analysis.

    `runs` = that ticker's records (any order). Compares the two most recent runs that
    actually carry an X verdict. Returns (html, sort_value):
      ⇄  verdict changed (colored toward/away from bullish) · tooltip shows old→new
      →  unchanged since the prior run
      ·  only one X reading on record (no history yet)
    """
    xs = [r for r in sorted(runs, key=lambda r: r["date"]) if r.get("x")]
    if len(xs) < 2:
        return ('<span class="muted" title="only one X Brain reading on record — '
                're-run the analysis over time to build a trend">·</span>', 0)
    cur, prev = xs[-1], xs[-2]
    if cur["x"] == prev["x"]:
        return (f'<span class="muted" title="X Brain unchanged since {html.escape(prev["date"])} '
                f'({html.escape(prev["x"])})">→</span>', 0)
    d = x_verdict_score(cur["x"]) - x_verdict_score(prev["x"])
    cls = "b-pos" if d > 0 else "b-neg" if d < 0 else "muted"
    tip = (f'X Brain crowd shifted: {html.escape(prev["x"])} ({html.escape(prev["date"])}) → '
           f'{html.escape(cur["x"])} ({html.escape(cur["date"])})')
    return (f'<span class="{cls}" title="{tip}">⇄</span>', d)

# combined-verdict -> numeric secular tilt (used by the by-domain rollup + priority)
COMBINED_SCORE = {"CONVICTION ALIGNED": 2, "ALIGNED": 1, "NEUTRAL": 0,
                  "CONTESTED": 0, "EXPOSED": -1, "OFFSIDE": -2, "INSUFFICIENT": 0}

def combined_score(c):
    return COMBINED_SCORE.get((c or "").upper(), 0)

def _stance_pts(r):
    s = (r.get("rating") or r.get("base_action") or "").lower()
    if "overweight" in s: return 1
    if "underweight" in s: return -1
    if "buy" in s: return 2
    if "sell" in s: return -2
    return 0

def priority_raw(r):
    """Signed actionability: conviction + P(beat) edge + expected return + secular tilt.
    Range ~ -6..+6. High = strong, corroborated long; low = avoid/short."""
    pts = float(_stance_pts(r))
    if r.get("pbeat_n") is not None:
        pts += (r["pbeat_n"] - 0.5) * 4.0           # ±2 for P(beat) 0..1
    if r.get("exp24_n") is not None:
        pts += max(-1.0, min(1.0, r["exp24_n"] / 25.0))  # ±1 for ±25% exp 24mo
    pts += combined_score(r.get("combined")) * 0.5   # ±1 secular tilt
    return pts

def priority_100(r):
    return round((priority_raw(r) + 6) / 12 * 100)   # 0..100, 50 = neutral

def cls_priority(p):
    return "b-pos" if p >= 60 else "b-neg" if p <= 40 else "muted"

def num(s):
    m = re.search(r"[+\-]?\d+(?:\.\d+)?", s or "")
    return float(m.group(0)) if m else None

def fmt_price(v):
    return f"${v:,.2f}" if isinstance(v, (int, float)) else "—"

def price_cell(r):
    """Latest price (live close) + % change since the analysis-date entry price."""
    lp = r.get("last_price_n")
    ep = r.get("price_at_n")
    if lp is None:
        return ('—' if ep is None else
                f'<span class="muted" title="price at analysis ({r["date"]})">{fmt_price(ep)}</span>')
    chg = ""
    if ep:
        pct = (lp / ep - 1.0) * 100
        chg = (f' <span class="{"b-pos" if pct >= 0 else "b-neg"}" '
               f'title="vs ${ep:,.2f} at analysis ({r["date"]})">{pct:+.1f}%</span>')
    return f'<b>{fmt_price(lp)}</b>{chg}'

def action_from_rating(r):
    c = cls_rating(r)
    return "BUY" if c == "b-buy" else "SELL" if c == "b-sell" else "HOLD"

# rating -> numeric stance (-2 sell .. +2 buy), most-specific match first
_RATING_ORDER = [("overweight", 1), ("underweight", -1), ("buy", 2),
                 ("sell", -2), ("hold", 0)]
_RATING_LABEL = {2: "Buy", 1: "OW", 0: "Hold", -1: "UW", -2: "Sell"}
_RATING_HEX = {2: "#2ea043", 1: "#2ea043", 0: "#d29922", -1: "#f85149", -2: "#f85149"}

def rating_score(r):
    r = (r or "").lower()
    for k, v in _RATING_ORDER:
        if k in r:
            return v
    return None

def trend_chart(points):
    """points: [{date,score,rating,pbeat_n}] asc. Returns (svg_html, n_breaks, path_text)."""
    pts = [p for p in points if p["score"] is not None]
    if len(pts) < 2:
        return "", 0, ""
    W, H, padx, ptop, pbot = 360, 124, 30, 14, 28
    x0, x1 = padx, W - 12
    span = H - ptop - pbot
    X = lambda i: x0 + (x1 - x0) * (i / (len(pts) - 1))
    Y = lambda s: ptop + (2 - s) / 4 * span          # score 2->top, -2->bottom
    Yp = lambda p: ptop + (1 - p) * span             # prob 1->top, 0->bottom
    e = []
    # gridlines + y labels for the five stance levels
    for s in (2, 1, 0, -1, -2):
        y = Y(s)
        dash = "" if s == 0 else ' stroke-dasharray="2,3"'
        e.append(f'<line x1="{x0}" y1="{y:.1f}" x2="{x1}" y2="{y:.1f}" stroke="#2d3643"{dash}/>')
        e.append(f'<text x="{x0-6:.0f}" y="{y+3:.0f}" fill="#6b7681" font-size="9" text-anchor="end">{_RATING_LABEL[s]}</text>')
    # P(beat) faint line (0..1 on the same band)
    probpts = [(i, p["pbeat_n"]) for i, p in enumerate(pts) if p["pbeat_n"] is not None]
    if len(probpts) >= 2:
        poly = " ".join(f"{X(i):.1f},{Yp(v):.1f}" for i, v in probpts)
        e.append(f'<polyline points="{poly}" fill="none" stroke="#58a6ff" stroke-width="1.4" stroke-dasharray="4,3" opacity="0.85"/>')
    # rating segments, colored green(up)/red(down)/grey(flat)
    n_breaks = 0
    for i in range(1, len(pts)):
        ds = pts[i]["score"] - pts[i-1]["score"]
        col = "#6b7681" if ds == 0 else ("#2ea043" if ds > 0 else "#f85149")
        if ds != 0:
            n_breaks += 1
        e.append(f'<line x1="{X(i-1):.1f}" y1="{Y(pts[i-1]["score"]):.1f}" x2="{X(i):.1f}" y2="{Y(pts[i]["score"]):.1f}" stroke="{col}" stroke-width="2.2"/>')
    # dots (ringed where the stance changed) + date labels
    for i, p in enumerate(pts):
        x, y = X(i), Y(p["score"])
        changed = i > 0 and p["score"] != pts[i-1]["score"]
        if changed:
            e.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="6" fill="none" stroke="#e6edf3" stroke-width="1.5"/>')
        e.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3.6" fill="{_RATING_HEX[p["score"]]}"/>')
        e.append(f'<text x="{x:.1f}" y="{H-9:.0f}" fill="#6b7681" font-size="8.5" text-anchor="middle">{p["date"][5:]}</text>')
    svg = f'<svg viewBox="0 0 {W} {H}" width="100%" preserveAspectRatio="xMidYMid meet" role="img">{"".join(e)}</svg>'
    path = " → ".join(_RATING_LABEL[p["score"]] for p in pts)
    return svg, n_breaks, path

def trend_conclusion(points):
    """Plain-words read of the engine's stance across runs.
    Returns (signal, badge_class, sentence)."""
    pts = [p for p in points if p["score"] is not None]
    n = len(pts)
    if n < 2:
        return "Single run", "b-neu", "Only one analysis on record — no trend yet."
    ups = sum(1 for i in range(1, n) if pts[i]["score"] > pts[i-1]["score"])
    downs = sum(1 for i in range(1, n) if pts[i]["score"] < pts[i-1]["score"])
    net = pts[-1]["score"] - pts[0]["score"]
    first, last = _RATING_LABEL[pts[0]["score"]], _RATING_LABEL[pts[-1]["score"]]
    # P(beat) drift, if available
    probs = [p["pbeat_n"] for p in pts if p["pbeat_n"] is not None]
    pdrift = ""
    if len(probs) >= 2:
        dp = probs[-1] - probs[0]
        arrow = "↑" if dp > 0.02 else "↓" if dp < -0.02 else "→"
        pdrift = f" P(beat) {probs[0]:.2f}{arrow}{probs[-1]:.2f}."
    if ups and downs:
        return ("Whipsaw", "b-hold",
                f"Stance whipsawed across {n} runs ({first}→{last}) — low conviction / unsettled read; treat the latest call as tentative.{pdrift}")
    if net > 0:
        return ("Strengthening", "b-buy",
                f"Engine upgraded {first}→{last} over {n} runs — conviction improving; the latest bullish read is corroborated, not a one-off.{pdrift}")
    if net < 0:
        return ("Weakening", "b-sell",
                f"Engine downgraded {first}→{last} over {n} runs — conviction deteriorating; discount the bullish case.{pdrift}")
    return ("Stable", "b-neu",
            f"Held {last} across {n} runs — consistent read; the call is stable, not reactive noise.{pdrift}")

# ---------- minimal markdown -> html ----------------------------------------

def inline(s):
    s = html.escape(s, quote=False)
    s = re.sub(r"\[([^\]]+)\]\((https?://[^)]+)\)", r'<a href="\2" target="_blank">\1</a>', s)
    s = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", s)
    s = re.sub(r"`([^`]+)`", r"<code>\1</code>", s)
    return s

def md_to_html(md):
    out, i, lines = [], 0, md.splitlines()
    while i < len(lines):
        ln = lines[i]
        if not ln.strip():
            i += 1; continue
        if re.match(r"^\s*-{3,}\s*$", ln):
            out.append("<hr>"); i += 1; continue
        h = re.match(r"^(#{1,6})\s+(.*)$", ln)
        if h:
            lvl = len(h.group(1)); out.append(f"<h{lvl}>{inline(h.group(2))}</h{lvl}>"); i += 1; continue
        if ln.lstrip().startswith("|") and i + 1 < len(lines) and re.search(r"\|?\s*:?-{2,}", lines[i+1]):
            tbl = []
            while i < len(lines) and lines[i].lstrip().startswith("|"):
                tbl.append(lines[i]); i += 1
            out.append(render_table(tbl)); continue
        if re.match(r"^\s*[-*]\s+", ln):
            out.append("<ul>")
            while i < len(lines) and re.match(r"^\s*[-*]\s+", lines[i]):
                out.append("<li>" + inline(re.sub(r"^\s*[-*]\s+", "", lines[i])) + "</li>"); i += 1
            out.append("</ul>"); continue
        para = [ln]; i += 1
        while i < len(lines) and lines[i].strip() and not re.match(r"^(#{1,6}\s|\s*[-*]\s|\s*\|)", lines[i]):
            para.append(lines[i]); i += 1
        out.append("<p>" + inline(" ".join(para)) + "</p>")
    return "\n".join(out)

def render_table(rows):
    cells = [[c.strip() for c in r.strip().strip("|").split("|")] for r in rows]
    head, body = cells[0], cells[2:]
    h = "".join(f"<th>{inline(c)}</th>" for c in head)
    b = "".join("<tr>" + "".join(f"<td>{inline(c)}</td>" for c in r) + "</tr>" for r in body)
    return f"<table><thead><tr>{h}</tr></thead><tbody>{b}</tbody></table>"

# ---------- forecast table (decision page) ----------------------------------

def forecast_html(fc):
    if not fc:
        return '<p class="muted">No structured forecast table in this decision (older format).</p>'
    head = ["Horizon", "Bear", "Base", "Bull", "Exp. return", "Target", "CAGR", "P(beat)"]
    keys = ["bear", "base", "bull", "exp", "target", "cagr", "pbeat"]
    rows = ""
    for hz in ("12mo", "24mo", "36mo"):
        r = fc.get(hz)
        if not r:
            continue
        tds = f'<td><b>{hz}</b></td>' + "".join(f'<td class="num">{html.escape(r.get(k,"") or "—")}</td>' for k in keys)
        rows += f"<tr>{tds}</tr>"
    th = "".join(f"<th>{c}</th>" for c in head)
    return f'<table><thead><tr>{th}</tr></thead><tbody>{rows}</tbody></table>'

# ---------- Financials tab (yfinance metrics cache) --------------------------

def _m_money(n):
    """1.96e12 -> $1.96T ; 575e6 -> $575M."""
    if n is None:
        return "—"
    a = abs(n)
    for div, suf in ((1e12, "T"), (1e9, "B"), (1e6, "M"), (1e3, "K")):
        if a >= div:
            return f"${n/div:.2f}{suf}".replace(".00", "")
    return f"${n:.0f}"


def _m_pct(f, signed=False):
    """0.476 -> 47.6% ; fraction in, percent out."""
    if f is None:
        return "—"
    return f"{f*100:+.1f}%" if signed else f"{f*100:.1f}%"


def _m_x(n, suffix="×"):
    return f"{n:.1f}{suffix}" if n is not None else "—"


def _m_cell(val, disp, num=True, cls=""):
    """A <td> carrying data-s for the JS sorter (raw number, or text)."""
    c = f' class="{cls}"' if cls else ""
    if num:
        s = "" if val is None else f"{val}"
        return f'<td{c} data-s="{s if s else -1e9}">{disp}</td>'
    return f'<td{c} data-s="{html.escape(str(val or ""))}">{disp}</td>'


def _rule40_cls(v):
    return "b-pos" if (v is not None and v >= 40) else ("b-neg" if v is not None else "")


# Per-metric tooltips — what it is + how to read it (good ▲ / bad ▼). Shared by the
# detail-page Key-metrics box and the Financials-tab headers.
METRIC_TIP = {
    "market_cap": "Total equity value (price × shares). Size, not quality — bigger = more established & liquid, smaller = more room to run but riskier.",
    "price": "Latest price from the market-data feed (yfinance).",
    "forward_pe": "Price ÷ next-12mo expected EPS. LOWER = cheaper. Rough read: <15 cheap · 15–30 fair · >40 expensive (priced for high growth). 'n/a' = no positive forward earnings.",
    "peg": "Forward P/E ÷ expected growth. <1 = growth not fully priced in (GOOD value) · ~1–2 = fair · >2 = expensive vs its growth (CAUTION).",
    "ev_sales": "Enterprise value ÷ revenue. LOWER = cheaper. <5 modest · >15 rich. Best valuation gauge for fast-growing or unprofitable names that have no P/E.",
    "ev_ebitda": "Enterprise value ÷ EBITDA. LOWER = cheaper. <15 reasonable · >30 expensive. Negative = EBITDA-unprofitable (interpret with care).",
    "fcf_yield": "Free cash flow ÷ market cap. HIGHER = more cash generated per $ invested (GOOD). Positive = self-funding · negative = cash-burning (BAD, relies on raising money).",
    "gross_margin": "Revenue left after cost of goods. HIGHER = stronger pricing power / moat. >60% excellent · 30–60% solid · <30% commodity-like (BAD pricing power).",
    "operating_margin": "Profit from core operations as % of revenue. HIGHER = more efficient. Negative = operating at a loss.",
    "profit_margin": "Bottom-line net income as % of revenue. HIGHER = more profitable. Negative = losing money on a GAAP basis.",
    "rev_growth": "Year-over-year revenue growth. HIGHER = faster-growing (GOOD). Negative = shrinking (BAD).",
    "rule_of_40": "Revenue growth + FCF margin (software health rule). ≥40 = healthy growth/profit balance (GOOD, green) · <40 = paying too much growth for too little profit, or vice-versa.",
    "beta": "Volatility vs the market. ~1 = moves with the market · >1.5 = high-beta (amplifies both gains AND losses, RISKIER) · <1 = defensive/calmer.",
    "short_pct_float": "Shares sold short ÷ float. HIGHER = more bearish bets / squeeze potential. <5% normal · >10% heavily shorted (a two-edged RISK — crowded bearish but squeeze-prone).",
    "avg_dollar_vol": "Average daily dollar volume traded. HIGHER = more liquid, easy to enter/exit (GOOD). Low = wide spreads, hard to exit a position (RISK).",
    "dividend_yield": "Annual dividend ÷ price. Income return; growth names are often 0. Higher = more income but can signal lower growth — not good/bad on its own.",
    "implied_upside": "Analyst mean target ÷ price − 1. POSITIVE = analysts see upside (GOOD) · large NEGATIVE = price already above targets (CAUTION, stretched).",
    "pct_52w_range": "Where the price sits in its 1-year low→high band. ~100% = near highs (momentum, but extended) · ~0% = near lows (value, or a broken chart).",
    "next_earnings": "Next scheduled earnings date — a known volatility catalyst. Size positions so a gap move around it is survivable.",
}


def metrics_box(m):
    """Compact 'Key metrics' grid for a detail page (or '' if none cached)."""
    if not m:
        return ""
    def vb(field, label, v, cls=""):
        c = f' class="{cls}"' if cls else ""
        tip = METRIC_TIP.get(field, "")
        t = f' title="{html.escape(tip)}"' if tip else ""
        cue = ' <span class="muted" style="cursor:help">ⓘ</span>' if tip else ""
        return (f'<div class="vbox"{t}><div class="k">{label}{cue}</div>'
                f'<div{c}>{v}</div></div>')
    rows = [
        vb("market_cap", "Market cap", _m_money(m.get("market_cap"))),
        vb("forward_pe", "Forward P/E", _m_x(m.get("forward_pe"), "")),
        vb("peg", "PEG", _m_x(m.get("peg"), "")),
        vb("ev_sales", "EV / Sales", _m_x(m.get("ev_sales"))),
        vb("ev_ebitda", "EV / EBITDA", _m_x(m.get("ev_ebitda"))),
        vb("fcf_yield", "FCF yield", _m_pct(m.get("fcf_yield")),
           "b-pos" if (m.get("fcf_yield") or 0) > 0 else "b-neg" if m.get("fcf_yield") is not None else ""),
        vb("gross_margin", "Gross margin", _m_pct(m.get("gross_margin"))),
        vb("rev_growth", "Rev growth (YoY)", _m_pct(m.get("rev_growth"), signed=True)),
        vb("rule_of_40", "Rule of 40", (f'{m["rule_of_40"]:.0f}' if m.get("rule_of_40") is not None else "—"),
           _rule40_cls(m.get("rule_of_40"))),
        vb("beta", "Beta", _m_x(m.get("beta"), "")),
        vb("short_pct_float", "Short % float", _m_pct(m.get("short_pct_float"))),
        vb("avg_dollar_vol", "Avg $ vol", _m_money(m.get("avg_dollar_vol"))),
        vb("implied_upside", "Analyst upside", _m_pct(m.get("implied_upside"), signed=True),
           "b-pos" if (m.get("implied_upside") or 0) > 0 else "b-neg" if m.get("implied_upside") is not None else ""),
        vb("dividend_yield", "Div yield", (_m_pct((m.get("dividend_yield") or 0)/100) if m.get("dividend_yield") else "—")),
        vb("next_earnings", "Next earnings", m.get("next_earnings", "—")),
    ]
    fa = m.get("fetched_at", "")
    note = f'<p class="sub" style="margin:6px 0 0">Market data via yfinance · fetched {fa}.</p>' if fa else ""
    return ('<h2>Key metrics <span class="muted" style="text-transform:none;font-weight:400">'
            '· valuation, profitability, balance-sheet &amp; liquidity</span></h2>'
            f'<div class="verdict-grid">{"".join(rows)}</div>{note}')


def build_financials(metrics, latest):
    """Sortable financial-metrics table over the latest decision per ticker."""
    if not metrics:
        return ('<p class="muted">No metrics cached yet. Generate them with '
                '<code>python3 scripts/fetch_metrics.py</code> (network; writes '
                '<code>metrics.json</code> next to the decision log), then rebuild.</p>')
    cols = [
        ("Ticker", False, None), ("Mkt cap", True, "market_cap"), ("Price", True, "price"),
        ("Fwd P/E", True, "forward_pe"), ("PEG", True, "peg"), ("EV/Sales", True, "ev_sales"),
        ("EV/EBITDA", True, "ev_ebitda"), ("FCF yld", True, "fcf_yield"),
        ("Gross marg", True, "gross_margin"), ("Rev gr", True, "rev_growth"),
        ("Rule40", True, "rule_of_40"), ("Beta", True, "beta"),
        ("Short%", True, "short_pct_float"), ("Avg $vol", True, "avg_dollar_vol"),
        ("Div yld", True, "dividend_yield"), ("52w range", True, "pct_52w_range"),
        ("Upside", True, "implied_upside"), ("Next ER", False, "next_earnings"),
    ]
    def _th(i, name, num, field):
        tip = METRIC_TIP.get(field, "")
        t = f' title="{html.escape(tip)}"' if tip else ""
        cue = " ⓘ" if tip else ""
        return f'<th onclick="sortBy({i},this{",1" if num else ""})"{t}>{html.escape(name)}{cue}</th>'
    th = "".join(_th(i, name, num, field) for i, (name, num, field) in enumerate(cols))
    rows = []
    for tk in sorted(latest):
        m = metrics.get(tk)
        page = latest[tk].get("page")
        tklink = f'<a href="{page}">{tk}</a>' if page else tk
        if not m:
            rows.append(f'<tr><td data-s="{tk}">{tklink}</td>'
                        + '<td data-s="-1e9" class="muted" colspan="17">—</td></tr>')
            continue
        rng = m.get("pct_52w_range")
        rng_disp = (f'{rng*100:.0f}%' if rng is not None else "—")
        cells = [
            f'<td data-s="{tk}">{tklink}</td>',
            _m_cell(m.get("market_cap"), _m_money(m.get("market_cap"))),
            _m_cell(m.get("price"), f'${m["price"]:.2f}' if m.get("price") else "—"),
            _m_cell(m.get("forward_pe"), _m_x(m.get("forward_pe"), "")),
            _m_cell(m.get("peg"), _m_x(m.get("peg"), "")),
            _m_cell(m.get("ev_sales"), _m_x(m.get("ev_sales"))),
            _m_cell(m.get("ev_ebitda"), _m_x(m.get("ev_ebitda"))),
            _m_cell(m.get("fcf_yield"), _m_pct(m.get("fcf_yield")),
                    cls="b-pos" if (m.get("fcf_yield") or 0) > 0 else "b-neg" if m.get("fcf_yield") is not None else ""),
            _m_cell(m.get("gross_margin"), _m_pct(m.get("gross_margin"))),
            _m_cell(m.get("rev_growth"), _m_pct(m.get("rev_growth"), signed=True)),
            _m_cell(m.get("rule_of_40"), (f'{m["rule_of_40"]:.0f}' if m.get("rule_of_40") is not None else "—"),
                    cls=_rule40_cls(m.get("rule_of_40"))),
            _m_cell(m.get("beta"), _m_x(m.get("beta"), "")),
            _m_cell(m.get("short_pct_float"), _m_pct(m.get("short_pct_float"))),
            _m_cell(m.get("avg_dollar_vol"), _m_money(m.get("avg_dollar_vol"))),
            _m_cell(m.get("dividend_yield"), (_m_pct((m.get("dividend_yield") or 0)/100) if m.get("dividend_yield") else "—")),
            _m_cell(rng, rng_disp),
            _m_cell(m.get("implied_upside"), _m_pct(m.get("implied_upside"), signed=True),
                    cls="b-pos" if (m.get("implied_upside") or 0) > 0 else "b-neg" if m.get("implied_upside") is not None else ""),
            _m_cell(m.get("next_earnings", ""), m.get("next_earnings", "—"), num=False),
        ]
        rows.append("<tr>" + "".join(cells) + "</tr>")
    n_cov = sum(1 for tk in latest if metrics.get(tk))
    intro = (f'<p class="sub" style="margin:-4px 0 10px">{n_cov} of {len(latest)} names have cached '
             'metrics · click any header to re-sort · ticker → full decision. '
             '<b>Rule40</b> = rev-growth + FCF-margin (software health, ≥40 green); '
             '<b>FCF yld</b> = free cash flow ÷ market cap; <b>EV/Sales</b> &amp; '
             '<b>EV/EBITDA</b> are enterprise-value multiples; <b>Short%</b> = short interest '
             'as % of float; <b>52w range</b> = where price sits in its 1-yr band.</p>')
    return (intro + '<div style="overflow-x:auto"><table id="fin"><thead><tr>' + th
            + '</tr></thead><tbody>' + "".join(rows) + '</tbody></table></div>')


def build_metric_moves(cur, prev, latest):
    """Week-over-week financial-metric diff for the Changes tab. Returns (html, count).

    Diffs the current metrics.json against the most recent older snapshot
    (metrics_history/). Surfaces valuation re-rating (forward P/E, EV/Sales),
    short-interest spikes, FCF-yield shifts, and analyst-upside changes — only when
    the move clears a noise threshold. First run (no prior snapshot) = baseline note."""
    title = ('<h2>📐 Financials moves <span class="muted" style="font-weight:400;'
             'text-transform:none">· valuation re-rating, short-interest &amp; FCF-yield '
             'shifts vs. the previous metrics snapshot</span></h2>')
    if not prev:
        return (title + '<p class="muted">Baseline metrics snapshot saved — valuation / '
                'short-interest moves will appear here after the next refresh.</p>', 0)

    arrow = {"up": '<span class="muted">▲</span>', "down": '<span class="muted">▼</span>'}
    # (field, label, getter, formatter, abs-threshold, rel-threshold, want-abs-points)
    def fp(v):  # forward P/E style
        return _m_x(v, "")
    specs = [
        ("forward_pe", "Fwd P/E", fp, 1.5, 0.12),
        ("ev_sales", "EV/Sales", lambda v: _m_x(v), 0.6, 0.15),
        ("short_pct_float", "Short % float", lambda v: _m_pct(v), 0.02, None),
        ("fcf_yield", "FCF yield", lambda v: _m_pct(v), 0.01, None),
        ("implied_upside", "Analyst upside", lambda v: _m_pct(v, signed=True), 0.05, None),
    ]
    events = []
    for tk in sorted(latest):
        c, p = cur.get(tk), prev.get(tk)
        if not c or not p:
            continue
        for field, label, fmt, abs_thr, rel_thr in specs:
            a, b = p.get(field), c.get(field)
            if a is None or b is None:
                continue
            d = b - a
            if abs(d) < abs_thr:
                continue
            if rel_thr is not None and abs(a) > 1e-9 and abs(d) / abs(a) < rel_thr:
                continue
            events.append({"tk": tk, "label": label, "old": fmt(a), "new": fmt(b),
                           "dir": "up" if d > 0 else "down", "mag": abs(d) / (abs(a) + 1e-9)})
    if not events:
        return (title + '<p class="muted">No material valuation / short-interest moves vs. the '
                'previous snapshot.</p>', 0)
    events.sort(key=lambda e: e["mag"], reverse=True)
    rows = "".join(
        f'<li><b>{e["tk"]}</b> <span class="cf">{e["label"]}</span> '
        f'{html.escape(e["old"])} → {html.escape(e["new"])} {arrow[e["dir"]]}</li>'
        for e in events)
    head = title.replace('📐 Financials moves <span', f'📐 Financials moves <span class="muted">({len(events)})</span> <span')
    return (head + f'<ul class="chg">{rows}</ul>', len(events))


# ---------- Research tab (X-brain trends + bullish names) --------------------

def _x_lean_cls(lean):
    return {"Bullish": "b-pos", "Bearish": "b-neg"}.get(lean, "muted")

def build_research(rx, rx_prev=None):
    """Render the X-brain research.json (trends + bullish stocks) into the Research tab.
    If rx_prev (a prior snapshot) is given, annotate inline ▲/▼/NEW deltas."""
    if not rx:
        return ('<p class="muted">No X-brain research found. Generate it with '
                '<code>python3 work/fetch_trends.py &amp;&amp; python3 index/build_index.py &amp;&amp; '
                'python3 work/analyze_corpus.py</code> in the x-brain project '
                '(or run <code>/update-all</code>), then rebuild this dashboard.</p>')
    trends = rx.get("trends", [])
    bullish = rx.get("bullish", [])
    meta = (f'<p class="sub" style="margin:-4px 0 12px">From the X Brain corpus — '
            f'{rx.get("n_posts",0)} curated-account posts + {rx.get("n_news",0)} news-lane items '
            f'({rx.get("n_chunks",0)} chunks) · generated {html.escape(str(rx.get("generated","")))}. '
            f'Keyless FinTwit/AI signal — coarse lexicon sentiment, <b>not</b> advice.</p>')

    # trending AI topics — horizontal bars scaled to the top topic (+ rank delta vs prev)
    prev_rank = {t["topic"]: i for i, t in enumerate((rx_prev or {}).get("trends", []))}
    tmax = max((t["mentions"] for t in trends), default=1) or 1
    trows = ""
    for i, t in enumerate(trends):
        w = max(3, round(100 * t["mentions"] / tmax))
        delta = ""
        if rx_prev:
            if t["topic"] not in prev_rank:
                delta = ' <span class="b-pos" title="new on the board">NEW</span>'
            else:
                d = prev_rank[t["topic"]] - i
                if d >= 1:
                    delta = f' <span class="b-pos" title="up {d}">▲{d}</span>'
                elif d <= -1:
                    delta = f' <span class="b-neg" title="down {-d}">▼{-d}</span>'
        trows += (f'<li><span class="tk" style="min-width:210px">{html.escape(t["topic"])}{delta}</span>'
                  f'<span class="bar" style="width:{w}%"></span>'
                  f'<span class="muted">{t["mentions"]}</span></li>')
    trends_html = (f'<ol class="xbars">{trows}</ol>' if trows else
                   '<p class="muted">No trend signal in the corpus yet.</p>')

    # most-bullish names — sortable table (with inline Δ vs the previous snapshot)
    def _b(v, c):
        return f'<span class="badge {c}">{html.escape(str(v))}</span>'
    prev_b = {b["ticker"]: b for b in (rx_prev or {}).get("bullish", [])}
    pdate = ((rx_prev or {}).get("generated", "") or "")[:10]
    brows = ""
    for r in bullish:
        # clicking the name opens the live X cashtag search — see the actual FinTwit chatter
        tk = html.escape(r["ticker"])
        xurl = f'https://x.com/search?q=%24{tk}&f=live'
        tkcell = (f'<a href="{xurl}" target="_blank" rel="noopener" '
                  f'title="live X chatter for ${tk}">{tk}</a>')
        # Δ vs last run: net-sentiment move, lean flips, or NEW since the prior snapshot
        if not rx_prev:
            dcell, dval = '<span class="muted" title="no prior snapshot yet — refresh to start the trend">·</span>', 0
        elif r["ticker"] not in prev_b:
            dcell, dval = ('<span class="b-pos" title="not on the board in the previous snapshot">NEW</span>',
                           10 ** 6)
        else:
            p = prev_b[r["ticker"]]
            dn = r["net"] - p.get("net", 0)
            dval = dn
            if dn > 0:
                bits = [f'<span class="b-pos" title="X net sentiment up {dn} vs {pdate}">▲{dn}</span>']
            elif dn < 0:
                bits = [f'<span class="b-neg" title="X net sentiment down {-dn} vs {pdate}">▼{-dn}</span>']
            else:
                bits = ['<span class="muted" title="no net-sentiment change">→0</span>']
            if r["lean"] != p.get("lean"):
                bits.append(f'<span class="muted" title="lean flipped: {html.escape(p.get("lean",""))} → '
                            f'{html.escape(r["lean"])}">⇄</span>')
            dcell = " ".join(bits)
        brows += (
            f'<tr>'
            f'<td><b>{tkcell}</b></td>'
            f'<td class="num" data-s="{r["mentions"]}">{r["mentions"]}</td>'
            f'<td>{_b(r["lean"], _x_lean_cls(r["lean"]))}</td>'
            f'<td class="num b-pos" data-s="{r["bull"]}">{r["bull"]}</td>'
            f'<td class="num b-neg" data-s="{r["bear"]}">{r["bear"]}</td>'
            f'<td class="num" data-s="{r["net"]}">{r["net"]:+d}</td>'
            f'<td class="num" data-s="{r["ratio"]}">{r["ratio"]:.2f}</td>'
            f'<td class="muted" data-s="{html.escape(r.get("date",""))}" style="white-space:nowrap">{html.escape(r.get("date",""))}</td>'
            f'<td class="num" data-s="{dval}">{dcell}</td>'
            f'</tr>')
    bullish_html = (
        '<table id="xbull"><thead><tr>'
        '<th onclick="sortBy(0,this)" title="Stock symbol — click to open live X chatter for its $cashtag.">Ticker</th>'
        '<th onclick="sortBy(1,this,1)" title="How many posts in the corpus mention this name — raw attention/buzz volume.">Buzz (mentions)</th>'
        '<th onclick="sortBy(2,this)" title="Net crowd lean from the bull-vs-bear lexicon: Bullish, Bearish, or neutral.">Lean</th>'
        '<th onclick="sortBy(3,this,1)" title="Count of bullish lexicon hits in posts about this name.">Bull words</th>'
        '<th onclick="sortBy(4,this,1)" title="Count of bearish lexicon hits in posts about this name.">Bear words</th>'
        '<th onclick="sortBy(5,this,1)" title="Bull words minus bear words — the signed sentiment balance.">Net</th>'
        '<th onclick="sortBy(6,this,1)" title="Bull words ÷ bear words — how lopsided the chatter is (higher = more one-sidedly bullish).">Bull ratio</th>'
        '<th onclick="sortBy(7,this)" title="Date of the most recent post about this name in the corpus.">Latest</th>'
        f'<th onclick="sortBy(8,this,1)" title="Trend since the previous X Brain run ({html.escape(pdate) if pdate else "no prior snapshot yet"}): change in net sentiment (▲/▼), a lean flip (⇄), or NEW on the board. Populates once a second snapshot exists.">Δ vs last</th>'
        f'</tr></thead><tbody>{brows}</tbody></table>') if brows else \
        '<p class="muted">No per-name sentiment in the corpus yet.</p>'

    return (
        f'{meta}'
        f'<h2>🔥 Most-talked AI trends on X <span class="muted" style="text-transform:none;font-weight:400">· by mention volume in the corpus</span></h2>'
        f'{trends_html}'
        f'<h2>🐂 Most-bullish stocks on X <span class="muted" style="text-transform:none;font-weight:400">· buzz (mentions) + bull-vs-bear lexicon lean · click a ticker for live X chatter ($cashtag), a header to sort</span></h2>'
        f'{bullish_html}')

# ---------- Changes tab (week-over-week / latest-run diff) -------------------

def _dparse(s):
    try:
        return datetime.datetime.strptime(s[:10], "%Y-%m-%d")
    except Exception:
        return None

def compute_changes(recs, by_ticker, rx_cur, rx_prev):
    """Return (events, count). events = list of dicts grouped by 'group'."""
    ev = []
    dates = [r["date"] for r in recs if r.get("date")]
    latest_dt = _dparse(max(dates)) if dates else None
    def recent(d):  # within the latest run batch (≤3 days of newest date) — daily or weekly
        dt = _dparse(d)
        return dt is not None and latest_dt is not None and (latest_dt - dt).days <= 3

    BRAINS = [("jensen", "Jensen"), ("leopold", "Leopold"), ("jordi", "Jordi"),
              ("gavin", "Gavin"), ("x", "X")]
    for tk, rs in (by_ticker or {}).items():
        runs = sorted(rs, key=lambda r: r["date"])
        cur = runs[-1]
        if not recent(cur["date"]):
            continue                              # only flag the just-completed run
        if len(runs) < 2:
            ev.append({"group": "new", "ticker": tk, "date": cur["date"],
                       "text": f'first analysis on record'})
            continue
        prev = runs[-2]
        sub = f'{prev["date"]} → {cur["date"]}'
        # rating flip (both sides must be present — ignore newly-added fields)
        ps, cs = rating_score(prev["rating"]), rating_score(cur["rating"])
        if cur["rating"] and prev["rating"] and ps != cs:
            e = {"group": "flip", "ticker": tk, "date": cur["date"], "field": "Rating",
                 "old": prev["rating"] or "—", "new": cur["rating"] or "—",
                 "ocls": cls_rating(prev["rating"]), "ncls": cls_rating(cur["rating"]), "sub": sub}
            # a REVERSAL = stance crossed the neutral line (bullish <-> bearish) — actionable
            if ps is not None and cs is not None and ps * cs < 0:
                e["reversal"] = "to-bull" if cs > 0 else "to-bear"
            ev.append(e)
        # combined verdict flip
        if cur["combined"] and prev["combined"] and (cur["combined"]).upper() != (prev["combined"]).upper():
            ev.append({"group": "flip", "ticker": tk, "date": cur["date"], "field": "Combined",
                       "old": prev["combined"] or "—", "new": cur["combined"] or "—",
                       "ocls": cls_combined(prev["combined"]), "ncls": cls_combined(cur["combined"]), "sub": sub})
        # brain flips (only when a real before AND after exist — not newly-added coverage)
        for key, label in BRAINS:
            if cur.get(key) and prev.get(key) and cur.get(key) != prev.get(key):
                ocls = cls_x(prev.get(key)) if key == "x" else cls_brain(prev.get(key))
                ncls = cls_x(cur.get(key)) if key == "x" else cls_brain(cur.get(key))
                ev.append({"group": "flip", "ticker": tk, "date": cur["date"], "field": f'{label} Brain',
                           "old": prev.get(key) or "—", "new": cur.get(key) or "—",
                           "ocls": ocls, "ncls": ncls, "sub": sub})
        # metric moves (with thresholds so noise doesn't spam)
        def move(field, o, n, thr, fmt, pct=False):
            if o is None or n is None or abs(n - o) < thr:
                return
            d = "up" if n > o else "down"
            ev.append({"group": "metric", "ticker": tk, "date": cur["date"], "field": field,
                       "old": fmt(o), "new": fmt(n), "dir": d, "sub": sub})
        move("P(beat)", prev["pbeat_n"], cur["pbeat_n"], 0.03, lambda v: f"{v:.2f}")
        move("Exp 24mo", prev["exp24_n"], cur["exp24_n"], 3.0, lambda v: f"{v:+.0f}%")
        move("Priority", float(priority_100(prev)), float(priority_100(cur)), 5.0, lambda v: f"{v:.0f}")

    # ---- X research diff (trends + bullish), if we have a prior snapshot ----
    if rx_cur and rx_prev:
        pdate = (rx_prev.get("generated", "") or "")[:10]
        # trends: rank movement
        cur_t = [t["topic"] for t in rx_cur.get("trends", [])]
        prev_t = {t["topic"]: i for i, t in enumerate(rx_prev.get("trends", []))}
        for i, topic in enumerate(cur_t):
            if topic not in prev_t:
                ev.append({"group": "x", "kind": "trend", "date": pdate, "dir": "new",
                           "text": f'trend <b>{html.escape(topic)}</b> entered the board (#{i+1})'})
            else:
                d = prev_t[topic] - i  # positive = moved up
                if abs(d) >= 2:
                    ev.append({"group": "x", "kind": "trend", "date": pdate,
                               "dir": "up" if d > 0 else "down",
                               "text": f'trend <b>{html.escape(topic)}</b> #{prev_t[topic]+1} → #{i+1}'})
        # bullish: lean flips, new names, big net moves
        prev_b = {b["ticker"]: b for b in rx_prev.get("bullish", [])}
        for b in rx_cur.get("bullish", []):
            tk = b["ticker"]; p = prev_b.get(tk)
            if not p:
                continue
            if b.get("lean") != p.get("lean"):
                ev.append({"group": "x", "kind": "lean", "ticker": tk, "date": pdate, "dir": "flip",
                           "text": f'<b>{tk}</b> X sentiment {html.escape(p.get("lean",""))} → '
                                   f'{html.escape(b.get("lean",""))}'})
            elif abs(b.get("net", 0) - p.get("net", 0)) >= 25:
                d = b["net"] - p["net"]
                ev.append({"group": "x", "kind": "net", "ticker": tk, "date": pdate,
                           "dir": "up" if d > 0 else "down",
                           "text": f'<b>{tk}</b> X net sentiment {p["net"]:+d} → {b["net"]:+d}'})
    return ev, len(ev)


def build_changes(ev, rx_prev):
    if not ev:
        return ('<p class="muted">No changes detected in the latest run yet. Re-run the analysis '
                '(or <code>/update-all</code>); this view diffs the newest run against the previous one.</p>')
    arrow = {"up": '<span class="b-pos">▲</span>', "down": '<span class="b-neg">▼</span>',
             "flip": '<span class="muted">⇄</span>', "new": '<span class="b-pos">＋</span>'}
    def tklink(tk):
        return f'<a href="{tk}_*">{tk}</a>' if False else f'<b>{tk}</b>'
    groups = {"new": [], "flip": [], "metric": [], "x": []}
    for e in ev:
        groups.get(e["group"], groups["flip"]).append(e)
    out = []
    if groups["new"]:
        items = "".join(f'<li>{arrow["new"]} <b>{e["ticker"]}</b> <span class="muted">{e["text"]} · {e["date"]}</span></li>'
                        for e in sorted(groups["new"], key=lambda e: e["ticker"]))
        out.append(f'<h2>🆕 New names analyzed <span class="muted">({len(groups["new"])})</span></h2><ul class="chg">{items}</ul>')
    if groups["flip"]:
        rows = ""
        for e in sorted(groups["flip"], key=lambda e: (e["date"], e["ticker"]), reverse=True):
            mark = ' <span class="b-pos" title="reversal">🔄</span>' if e.get("reversal") else ""
            rows += (f'<li><b>{e["ticker"]}</b>{mark} <span class="cf">{e["field"]}</span> '
                     f'<span class="badge {e["ocls"]}">{html.escape(e["old"])}</span> → '
                     f'<span class="badge {e["ncls"]}">{html.escape(e["new"])}</span> '
                     f'<span class="muted">{e["sub"]}</span></li>')
        out.append(f'<h2>🔀 Rating &amp; verdict flips <span class="muted">({len(groups["flip"])})</span></h2><ul class="chg">{rows}</ul>')
    if groups["metric"]:
        rows = ""
        for e in sorted(groups["metric"], key=lambda e: (e["date"], e["ticker"]), reverse=True):
            rows += (f'<li><b>{e["ticker"]}</b> <span class="cf">{e["field"]}</span> '
                     f'{html.escape(e["old"])} → {html.escape(e["new"])} {arrow.get(e["dir"],"")} '
                     f'<span class="muted">{e["sub"]}</span></li>')
        out.append(f'<h2>📈 Forecast metric moves <span class="muted">({len(groups["metric"])})</span></h2><ul class="chg">{rows}</ul>')
    if groups["x"]:
        rows = "".join(f'<li>{arrow.get(e["dir"],"")} {e["text"]} <span class="muted">· vs {e["date"]}</span></li>'
                       for e in groups["x"])
        out.append(f'<h2>🔬 X research shifts <span class="muted">({len(groups["x"])})</span></h2><ul class="chg">{rows}</ul>')
    elif not rx_prev:
        out.append('<h2>🔬 X research shifts</h2><p class="muted">Baseline snapshot saved — '
                   'trend &amp; sentiment changes will appear here after the next refresh.</p>')
    return "\n".join(out)


def build_reversals(ev):
    """Directional reversals only — the rating crossed the bullish/bearish line (the
    'flip your position' signal). Returns (html, count)."""
    revs = [e for e in ev if e.get("reversal")]
    if not revs:
        return ('<p class="muted">No directional reversals in the latest run — no name crossed '
                'between bullish (Buy/Overweight) and bearish (Sell/Underweight) since the '
                'previous run. Milder rating changes (e.g. Hold→Buy) are in the 🔔 Changes tab.</p>', 0)

    def rows(items):
        items = sorted(items, key=lambda e: (e["date"], e["ticker"]), reverse=True)
        if not items:
            return '<li class="muted">none this run</li>'
        return "".join(
            f'<li><a href="{e["ticker"]}_{e["date"]}.html"><b>{e["ticker"]}</b></a> '
            f'<span class="badge {e["ocls"]}">{html.escape(e["old"])}</span> → '
            f'<span class="badge {e["ncls"]}">{html.escape(e["new"])}</span> '
            f'<span class="muted">{e["sub"]}</span></li>' for e in items)

    bull = [e for e in revs if e["reversal"] == "to-bull"]
    bear = [e for e in revs if e["reversal"] == "to-bear"]
    html_out = (
        '<p class="sub" style="margin:-4px 0 12px">A <b>reversal</b> = the rating crossed the '
        'neutral line between <b>bullish</b> (Buy/Overweight) and <b>bearish</b> '
        '(Sell/Underweight) vs. the previous run — the strongest "flip the position" signal. '
        'Click a ticker for its decision page.</p>'
        f'<h2>🟢 Turned bullish <span class="muted">({len(bull)})</span> '
        '<span class="muted" style="font-weight:400;text-transform:none">· was bearish → now '
        'bullish · open / add candidates</span></h2>'
        f'<ul class="chg">{rows(bull)}</ul>'
        f'<h2>🔴 Turned bearish <span class="muted">({len(bear)})</span> '
        '<span class="muted" style="font-weight:400;text-transform:none">· was bullish → now '
        'bearish · trim / exit candidates</span></h2>'
        f'<ul class="chg">{rows(bear)}</ul>')
    return html_out, len(revs)

def build_under_pressure(up):
    """Render the ta_memory watch cache — open calls drifting against the thesis."""
    flagged = (up or {}).get("flagged", [])
    if not flagged:
        return "", 0
    gen = html.escape(str(up.get("generated", "")))
    rows = ""
    for x in flagged:
        page = f'{x["ticker"]}_{x["date"]}.html'
        raw = x.get("raw"); alpha = x.get("alpha")
        rows += (f'<li><a href="{page}"><b>{html.escape(x["ticker"])}</b></a> '
                 f'<span class="badge {cls_rating(x.get("rating",""))}">{html.escape(x.get("rating","") or "—")}</span> '
                 f'<span class="b-neg">{raw:+.0%} raw / {alpha:+.0%} α</span> '
                 f'<span class="muted">{x.get("elapsed_days","?")}d · {html.escape(x.get("reason",""))}</span></li>')
    return (f'<h2>⚠️ Open calls under pressure <span class="muted">({len(flagged)})</span> '
            f'<span class="muted" style="font-weight:400;text-transform:none">· interim mark vs the call '
            f'(as of {gen}) — candidates to re-analyze before the horizon matures</span></h2>'
            f'<ul class="chg">{rows}</ul>'), len(flagged)

# ---------- build ------------------------------------------------------------

def main():
    os.makedirs(OUT, exist_ok=True)
    mem = parse_memory(MEM)
    metrics = load_metrics(METRICS)
    decisions = {}
    for p in glob.glob(os.path.join(STOCKS, "*", "*_decision.md")):
        d = parse_decision(p)
        decisions[(d["date"], d["ticker"])] = d

    # union of keys (decision files + logged entries)
    keys = set(decisions) | set(mem)
    recs = []
    for (date, tk) in keys:
        d = decisions.get((date, tk), {"ticker": tk, "date": date, "name": "", "md": "",
                                       "src": "", "forecast": {}, "verdict_new": "",
                                       "jensen": "", "leopold": "", "jordi": "", "gavin": "", "x": "", "combined": "",
                                       "base_action": "", "base_rating": "",
                                       "macro_action": "", "macro_rating": "", "price_at": ""})
        m = mem.get((date, tk), {})
        rating = d.get("base_rating") or m.get("rating", "")
        base_action = d.get("base_action") or action_from_rating(rating)
        macro_action = d.get("macro_action") or base_action
        # P(beat): prefer logged prob, else 24mo table cell
        prob = m.get("prob", "")
        fc24 = d["forecast"].get("24mo", {})
        if not prob and fc24.get("pbeat"):
            prob = re.sub(r"[^\d.]", "", fc24["pbeat"])
        exp24 = fc24.get("exp", "")
        status = m.get("status", "pending")
        raw_val = m.get("raw", "")
        alpha_val = m.get("alpha", "")
        holding_val = m.get("holding", "")
        # price at analysis (entry reference) recorded in the decision file, if any
        price_at_n = num(d.get("price_at", ""))
        last_price_n = None  # latest live close (most recent trading day)

        if status == "pending" and fetch_returns:
            try:
                days_elapsed = (datetime.datetime.now() - datetime.datetime.strptime(date, "%Y-%m-%d")).days
                if days_elapsed > 0:
                    r_res = fetch_returns(tk, date, days_elapsed)
                    if r_res:
                        raw_val = f"{r_res.raw:+.1%}"
                        alpha_val = f"{r_res.alpha:+.1%}"
                        holding_val = f"{r_res.elapsed_days}d (Live)"
                        if r_res.last_price is not None:
                            last_price_n = r_res.last_price
                        if price_at_n is None and r_res.entry_price is not None:
                            price_at_n = r_res.entry_price  # backfill entry from prices
            except Exception:
                pass

        recs.append({**d, "rating": rating, "base_action": base_action,
                     "macro_action": macro_action,
                     "macro_rating": d.get("macro_rating") or "",
                     "status": status, "raw": raw_val,
                     "alpha": alpha_val, "holding": holding_val,
                     "prob": prob, "horizon": m.get("horizon", "") or "24mo",
                     "exp24": exp24, "target24": fc24.get("target", ""),
                     "price_at_n": price_at_n, "last_price_n": last_price_n,
                     "pbeat_n": num(prob), "exp24_n": num(exp24), "alpha_n": num(alpha_val)})
    recs.sort(key=lambda r: (r["date"], r["ticker"]), reverse=True)

    # ---- per-ticker decision trend (chart + plain-words conclusion) ----
    by_ticker = {}
    for r in recs:
        by_ticker.setdefault(r["ticker"], []).append(r)
    trend = {}   # ticker -> {svg,breaks,path,signal,sig_cls,sentence,n,points}
    for tk, rs in by_ticker.items():
        pts = [{"date": r["date"], "score": rating_score(r["rating"]),
                "rating": r["rating"], "pbeat_n": r["pbeat_n"]}
               for r in sorted(rs, key=lambda r: r["date"])]
        svg, brk, path = trend_chart(pts)
        sig, sig_cls, sentence = trend_conclusion(pts)
        trend[tk] = {"svg": svg, "breaks": brk, "path": path, "signal": sig,
                     "sig_cls": sig_cls, "sentence": sentence, "n": len(rs)}

    def trend_block(tk):
        t = trend[tk]
        if t["n"] < 2:
            return ('<p class="muted">Only one analysis on record for ' + tk +
                    ' — no decision trend yet. Re-run <code>/trading-analysis ' + tk +
                    '</code> over time to build one.</p>')
        brkbadge = (f'<span class="badge b-sell">⚡ stance changed {t["breaks"]}×</span>'
                    if t["breaks"] else '<span class="badge b-neu">stable · no breaks</span>')
        return (f'<div class="trend-detail">'
                f'<div class="trend-head"><span class="badge {t["sig_cls"]}">{t["signal"]}</span> '
                f'{brkbadge} <span class="muted">{t["n"]} runs · {t["path"]}</span></div>'
                f'<div class="chart">{t["svg"]}</div>'
                f'<p class="trend-read">{t["sentence"]}</p>'
                f'<p class="muted" style="font-size:11px">Dots = engine rating per run (green=bullish tilt, '
                f'amber=Hold, red=bearish tilt); ring = stance change. Blue dashed = P(beat) trend (0–1). '
                f'This trend is a consistency check on the call below — it does not override the forecast.</p>'
                f'</div>')

    # ---- latest decision per ticker (computed before pages so they can show the live price) ----
    latest = {}
    for r in recs:
        if r["ticker"] not in latest:  # recs already sorted date desc
            latest[r["ticker"]] = r
    L = list(latest.values())

    # Backfill a live latest price for the headline (latest-per-ticker) rows that
    # didn't get one from fetch_returns (e.g. resolved calls, or analyses too recent
    # to have a 2nd trading row yet, skip that path).
    if fetch_last_price:
        for r in latest.values():
            if r.get("last_price_n") is None:
                try:
                    lp = fetch_last_price(r["ticker"])
                    if lp is not None:
                        r["last_price_n"] = lp
                except Exception:
                    pass

    # per-decision pages (only where we have the markdown body)
    dtpl = open(os.path.join(TPL, "decision.html"), encoding="utf-8").read()
    for r in recs:
        if not r["md"]:
            continue
        r["page"] = f'{r["ticker"]}_{r["date"]}.html'
        pb = f'{float(r["prob"]):.2f}' if r["pbeat_n"] is not None else "—"
        status = (f'Resolved · {r["raw"]} raw / {r["alpha"]} alpha ({r["holding"]})'
                  if r["status"] == "resolved" else
                  (f'Pending · P={pb} · H={r["horizon"]}' if pb != "—" else "Pending"))
        page = dtpl
        repl = {
            "{{TICKER}}": r["ticker"], "{{NAME}}": html.escape(r["name"]), "{{DATE}}": r["date"],
            "{{HORIZON}}": r["horizon"], "{{STATUS}}": status,
            "{{BASE_ACTION}}": r["base_action"] or "—", "{{BASE_RATING}}": r["rating"] or "—",
            "{{MACRO_ACTION}}": r["macro_action"] or "—", "{{MACRO_RATING}}": r["macro_rating"] or r["rating"] or "—",
            "{{BASE_CLS}}": cls_action(r["base_action"]), "{{MACRO_CLS}}": cls_action(r["macro_action"]),
            "{{PBEAT}}": pb, "{{EXP24}}": r["exp24"] or "—",
            "{{EXP_CLS}}": ("b-pos" if (r["exp24_n"] or 0) > 0 else "b-neg" if r["exp24_n"] is not None else ""),
            "{{PRICE}}": price_cell(r),
            "{{DOMAIN}}": AI_DOMAIN.get(r["ticker"], "—"),
            "{{JENSEN}}": r["jensen"] or "n/a", "{{JENSEN_CLS}}": cls_brain(r["jensen"]),
            "{{LEOPOLD}}": r["leopold"] or "n/a", "{{LEOPOLD_CLS}}": cls_brain(r["leopold"]),
            "{{JORDI}}": r["jordi"] or "n/a", "{{JORDI_CLS}}": cls_brain(r["jordi"]),
            "{{GAVIN}}": r["gavin"] or "n/a", "{{GAVIN_CLS}}": cls_brain(r["gavin"]),
            "{{X}}": r["x"] or "n/a", "{{X_CLS}}": cls_x(r["x"]),
            "{{COMBINED}}": r["combined"] or "n/a", "{{COMBINED_CLS}}": cls_combined(r["combined"]),
            "{{VERDICT_NEW}}": inline(r["verdict_new"]) if r["verdict_new"] else '<span class="muted">—</span>',
            "{{FORECAST_TABLE}}": forecast_html(r["forecast"]),
            "{{METRICS_BOX}}": metrics_box(metrics.get(r["ticker"])),
            "{{TREND}}": trend_block(r["ticker"]),
            "{{BODY}}": md_to_html(r["md"]),
            "{{SRCPATH}}": r["src"], "{{GENERATED}}": NOW,
        }
        for k, v in repl.items():
            page = page.replace(k, v)
        open(os.path.join(OUT, r["page"]), "w", encoding="utf-8").write(page)

    def li(r, metric):
        tk = (f'<a href="{r["page"]}">{r["ticker"]}</a>' if r.get("page") else r["ticker"])
        return f'<li><span class="tk">{tk}</span><span class="muted">{r["date"]}</span><span class="mt">{metric}</span></li>'

    def board(title, items, fmt, empty="—"):
        body = "".join(li(r, fmt(r)) for r in items) or f'<li class="muted">{empty}</li>'
        return f'<div class="board"><h3>{title}</h3><ol>{body}</ol></div>'

    longs = sorted([r for r in L if cls_rating(r["rating"]) == "b-buy" and r["pbeat_n"] is not None],
                   key=lambda r: r["pbeat_n"], reverse=True)[:8]
    byexp = sorted([r for r in L if r["exp24_n"] is not None],
                   key=lambda r: r["exp24_n"], reverse=True)[:8]
    bypb = sorted([r for r in L if r["pbeat_n"] is not None],
                  key=lambda r: r["pbeat_n"], reverse=True)[:8]
    secular = sorted([r for r in L if cls_combined(r["combined"]) in ("v-conviction", "v-aligned")],
                     key=lambda r: 0 if r["combined"].upper() == "CONVICTION ALIGNED" else 1)[:8]
    resolved = sorted([r for r in recs if r["status"] == "resolved" and r["alpha_n"] is not None],
                      key=lambda r: r["alpha_n"], reverse=True)[:8]

    dashboards = "".join([
        board("Highest-conviction longs <span class='muted'>(Buy/OW · P↓)</span>", longs,
              lambda r: f'<span class="b-pos">P {r["pbeat_n"]:.2f}</span>'),
        board("Highest expected 24mo return", byexp,
              lambda r: f'<span class="b-pos">{r["exp24"]}</span>'),
        board("Highest P(beat benchmark)", bypb, lambda r: f'P {r["pbeat_n"]:.2f}'),
        board("Strongest secular fit <span class='muted'>(combined verdict)</span>", secular,
              lambda r: f'<span class="badge {cls_combined(r["combined"])}">{r["combined"]}</span>'),
        board("Resolved — realized alpha", resolved,
              lambda r: f'<span class="{"b-pos" if r["alpha_n"]>0 else "b-neg"}">{r["alpha"]}</span>'),
    ])

    # ---- by-domain rollup: secular tilt per layer of the AI build-out ----
    _cscore = combined_score

    def _tilt_label(avg, n_contested, n):
        lab = ("Strong tailwind" if avg >= 1.5 else "Tailwind" if avg >= 0.5
               else "Mixed" if avg > -0.5 else "Headwind" if avg > -1.5 else "Strong headwind")
        if n_contested and n_contested * 2 >= n:
            lab += " · contested"
        return lab

    def _chip(r):
        badge_html = f'<span class="badge {cls_combined(r["combined"])}">{r["ticker"]}</span>'
        return f'<a href="{r["page"]}">{badge_html}</a>' if r.get("page") else badge_html

    dom_groups = {}
    for r in L:
        dom_groups.setdefault(AI_DOMAIN.get(r["ticker"], "—"), []).append(r)
    def _bdg(text, cls):
        return f'<span class="badge {cls}">{html.escape(str(text))}</span>' if text else ""

    def _dom_member_li(m):
        tk = f'<a href="{m["page"]}">{m["ticker"]}</a>' if m.get("page") else m["ticker"]
        call = _bdg(m["base_action"], cls_action(m["base_action"]))
        cb = _bdg(m["combined"], cls_combined(m["combined"]))
        p = priority_100(m)
        return (f'<li><span class="tk">{tk}</span> {call} {cb} '
                f'<span class="badge {cls_priority(p)}" title="priority">P{p}</span></li>')

    # precompute per-domain stats once (reused by the summary table + cards)
    dom_stats = {}
    for dom, members in dom_groups.items():
        n = len(members)
        avg = sum(_cscore(m["combined"]) for m in members) / n
        n_contested = sum(1 for m in members if (m["combined"] or "").upper() == "CONTESTED")
        ordered = sorted(members, key=lambda m: (-_cscore(m["combined"]), -priority_100(m)))
        dom_stats[dom] = {"n": n, "avg": avg, "nc": n_contested, "ordered": ordered}

    # summary table rows — sorted by tilt desc, with the bucket as the first column
    dom_rows = ""
    for dom in sorted(dom_groups, key=lambda d: (-dom_stats[d]["avg"], d)):
        s = dom_stats[dom]; n, avg, n_contested, ordered = s["n"], s["avg"], s["nc"], s["ordered"]
        b = bucket_for_domain(dom)
        chips = " ".join(_chip(m) for m in ordered)
        cls_tilt = "b-pos" if avg > 0.4 else "b-neg" if avg < -0.4 else "muted"
        tilt_lab = _tilt_label(avg, n_contested, n)
        dom_rows += (f'<tr><td class="muted" data-s="{bucket_rank(b):02d}" style="white-space:nowrap">{html.escape(b)}</td>'
                     f'<td><b>{html.escape(dom)}</b></td>'
                     f'<td class="num" data-s="{n}">{n}</td>'
                     f'<td>{chips}</td>'
                     f'<td data-s="{avg:.2f}"><span class="{cls_tilt}">{tilt_lab}</span> '
                     f'<span class="muted">({avg:+.1f})</span></td></tr>')

    def _dom_card(dom):
        s = dom_stats[dom]; n, avg, n_contested, ordered = s["n"], s["avg"], s["nc"], s["ordered"]
        note = DOMAIN_NOTE.get(dom, "")
        avg_p = round(sum(priority_100(m) for m in ordered) / n)
        tilt_lab = _tilt_label(avg, n_contested, n)
        b = bucket_for_domain(dom)
        return (
            f'<div class="domcard" data-domain="{html.escape(dom)}" data-bucket="{html.escape(b)}" data-tilt="{avg:.2f}">'
            f'<div class="domcard-head"><b>{html.escape(dom)}</b>'
            f'<span class="badge {cls_combined("CONVICTION ALIGNED" if avg>=1.5 else "ALIGNED" if avg>=0.5 else "EXPOSED" if avg<=-0.5 else "CONTESTED" if n_contested else "NEUTRAL")}">{tilt_lab}</span></div>'
            f'<div class="domcard-meta"><span class="muted">{n} name{"s" if n>1 else ""} · tilt {avg:+.1f} · avg priority {avg_p}</span></div>'
            f'<p class="domcard-read">{html.escape(note)}</p>'
            f'<ul class="domlist">{"".join(_dom_member_li(m) for m in ordered)}</ul>'
            f'</div>')

    # cards grouped under bucket section headers (the generic category), domains
    # within each bucket ordered by tilt desc
    buckets_present = {}
    for dom in dom_groups:
        buckets_present.setdefault(bucket_for_domain(dom), []).append(dom)
    dom_cards = ""
    for b in sorted(buckets_present, key=bucket_rank):
        doms = sorted(buckets_present[b], key=lambda d: (-dom_stats[d]["avg"], d))
        nstocks = sum(dom_stats[d]["n"] for d in doms)
        b_avg = sum(_cscore(m["combined"]) for d in doms for m in dom_stats[d]["ordered"]) / nstocks
        cards = "".join(_dom_card(d) for d in doms)
        dom_cards += (
            f'<section class="bucketsec" data-bucket="{html.escape(b)}">'
            f'<h3 class="buckethead">{html.escape(b)} '
            f'<span class="muted">· {len(doms)} domain{"s" if len(doms)>1 else ""} · '
            f'{nstocks} name{"s" if nstocks>1 else ""} · tilt {b_avg:+.1f}</span></h3>'
            f'<div class="domcards">{cards}</div></section>')

    # ---- track-record cards ----
    res = [r for r in recs if r["status"] == "resolved" and r["alpha_n"] is not None]
    hit = sum(1 for r in res if r["alpha_n"] > 0)
    pend = sum(1 for r in recs if r["status"] == "pending")
    mean_alpha = (sum(r["alpha_n"] for r in res) / len(res)) if res else None
    _tt_verdicts = ("Total number of logged trading-analysis forecasts across all runs. "
                    "The smaller number is how many unique tickers those cover (a ticker re-analyzed "
                    "later counts once here, but adds another verdict).")
    _tt_pending = ("Forecasts whose target horizon (12–36 months) hasn't matured yet, so the real "
                   "outcome can't be graded against the benchmark. They flip to Resolved once the "
                   "horizon passes and the actual return + alpha are recorded.")
    _tt_hit = ("Of the forecasts whose horizon has matured (Resolved), the share that beat their "
               "benchmark — i.e. realized total return exceeded the benchmark over the same window.")
    _tt_alpha = ("Average out-performance across all Resolved calls: realized return minus the "
                 "benchmark's return over the same horizon. Positive = beat the benchmark on average.")
    cards = "".join([
        f'<div class="card" title="{html.escape(_tt_verdicts)}"><div class="k">Verdicts</div><div class="v">{len(recs)}<small> · {len(latest)} tickers</small></div></div>',
        f'<div class="card" title="{html.escape(_tt_pending)}"><div class="k">Pending</div><div class="v">{pend}<small> awaiting horizon</small></div></div>',
        f'<div class="card" title="{html.escape(_tt_hit)}"><div class="k">Resolved hit-rate</div><div class="v">{(100*hit/len(res)):.0f}%<small> {hit}/{len(res)} beat bench</small></div></div>' if res else
        f'<div class="card" title="{html.escape(_tt_hit)}"><div class="k">Resolved hit-rate</div><div class="v">—<small> none matured</small></div></div>',
        f'<div class="card" title="{html.escape(_tt_alpha)}"><div class="k">Mean realized alpha</div><div class="v {"b-pos" if (mean_alpha or 0)>0 else "b-neg"}">{mean_alpha:+.1f}%</div></div>' if mean_alpha is not None else
        f'<div class="card" title="{html.escape(_tt_alpha)}"><div class="k">Mean realized alpha</div><div class="v">—</div></div>',
    ])

    # ---- full table ----
    def badge(txt, c):
        return f'<span class="badge {c}">{html.escape(txt or "—")}</span>'
    rows_html = ""
    for r in recs:
        tk = f'<a href="{r["page"]}">{r["ticker"]}</a>' if r.get("page") else r["ticker"]
        pb_n = r["pbeat_n"]
        pb_disp = f"{pb_n:.2f}" if pb_n is not None else "—"
        pb_sort = pb_n if pb_n is not None else -1
        if r["status"] == "resolved":
            outcome = f'{r["alpha"]} α'
            ocls = "b-pos" if (r["alpha_n"] or 0) > 0 else "b-neg"
        elif r["alpha"]:
            outcome = f'<span style="color:#58a6ff">Live: {r["alpha"]} α</span>'
            ocls = "b-pos" if (r["alpha_n"] or 0) > 0 else "b-neg"
        else:
            outcome = f'P {pb_disp}' if pb_n is not None else "pending"
            ocls = "muted"
        osort = r["alpha_n"] if r["alpha_n"] is not None else (pb_n or 0)
        exp_sort = r["exp24_n"] if r["exp24_n"] is not None else -999
        exp_disp = html.escape(r["exp24"] or "—")
        comb = badge(r["combined"], cls_combined(r["combined"])) if r["combined"] else "—"
        jen = badge(r["jensen"], cls_brain(r["jensen"])) if r["jensen"] else "—"
        leo = badge(r["leopold"], cls_brain(r["leopold"])) if r["leopold"] else "—"
        jor = badge(r["jordi"], cls_brain(r["jordi"])) if r["jordi"] else "—"
        gav = badge(r["gavin"], cls_brain(r["gavin"])) if r["gavin"] else "—"
        xb = badge(r["x"], cls_x(r["x"])) if r["x"] else "—"
        base_b = badge(r["base_action"], cls_action(r["base_action"]))
        macro_b = badge(r["macro_action"], cls_action(r["macro_action"]))
        prio = priority_100(r); prio_raw = priority_raw(r)
        dom_cell = html.escape(AI_DOMAIN.get(r["ticker"], "—"))
        bkt = bucket_for(r["ticker"])
        prio_word = ("high-conviction long" if prio >= 60 else
                     "avoid / short" if prio <= 40 else "neutral")
        dom_full = AI_DOMAIN.get(r["ticker"], "—")
        name_part = (" — " + r["name"]) if r.get("name") else ""
        exp_part = (" · expected 24mo " + r["exp24"]) if r.get("exp24") else ""
        if r["last_price_n"] is not None:
            price_part = f'Latest ${r["last_price_n"]:,.2f}'
            if r["price_at_n"]:
                price_part += f' (vs ${r["price_at_n"]:,.2f} at analysis, {(r["last_price_n"]/r["price_at_n"]-1)*100:+.1f}%)'
            price_part += '. '
        elif r["price_at_n"]:
            price_part = f'Price at analysis ${r["price_at_n"]:,.2f}. '
        else:
            price_part = ''
        row_tip = html.escape(
            f'{r["ticker"]}{name_part} · {dom_full} · analyzed {r["date"]}. '
            f'{price_part}'
            f'Call: Base {r["base_action"] or "—"} / Macro {r["macro_action"] or "—"}. '
            f'P(beat benchmark) {pb_disp}{exp_part}. '
            f'Secular fit (4 lenses fused): {r["combined"] or "n/a"}. '
            f'Priority {prio}/100 — {prio_word}. '
            f'Hover a column header for what each field means.')
        rows_html += (
            f'<tr title="{row_tip}" data-domain="{dom_cell}" data-bucket="{html.escape(bkt)}">'
            f'<td data-s="{r["date"]}">{r["date"]}</td>'
            f'<td><b>{tk}</b></td>'
            f'<td class="num" data-s="{r["last_price_n"] if r["last_price_n"] is not None else (r["price_at_n"] or -1)}">{price_cell(r)}</td>'
            f'<td class="num" data-s="{prio_raw:.3f}"><span class="badge {cls_priority(prio)}">{prio}</span></td>'
            f'<td>{base_b}</td>'
            f'<td>{macro_b}</td>'
            f'<td class="num" data-s="{pb_sort}">{pb_disp}</td>'
            f'<td class="num" data-s="{exp_sort}">{exp_disp}</td>'
            f'<td>{comb}</td>'
            f'<td>{jen}</td>'
            f'<td>{leo}</td>'
            f'<td>{jor}</td>'
            f'<td>{gav}</td>'
            f'<td>{xb}</td>'
            f'<td class="num {ocls}" data-s="{osort}">{outcome}</td>'
            f'<td class="muted" data-s="{bucket_rank(bkt):02d}" style="white-space:nowrap">{html.escape(bkt)}</td>'
            f'</tr>')

    # ---- by-stock rollup: times analyzed + latest secular read ----
    counts = {}
    for r in recs:
        counts[r["ticker"]] = counts.get(r["ticker"], 0) + 1
    bystock = sorted(latest.values(), key=lambda r: (-counts[r["ticker"]], r["ticker"]))
    stk_rows = ""
    for r in bystock:
        n = counts[r["ticker"]]
        tk = f'<a href="{r["page"]}">{r["ticker"]}</a>' if r.get("page") else r["ticker"]
        pb_n = r["pbeat_n"]
        pb_disp = f"{pb_n:.2f}" if pb_n is not None else "—"
        call = badge(r["base_action"], cls_action(r["base_action"]))
        if r["rating"]:
            call += " " + badge(r["rating"], cls_rating(r["rating"]))
        jen = badge(r["jensen"], cls_brain(r["jensen"])) if r["jensen"] else "—"
        leo = badge(r["leopold"], cls_brain(r["leopold"])) if r["leopold"] else "—"
        jor = badge(r["jordi"], cls_brain(r["jordi"])) if r["jordi"] else "—"
        gav = badge(r["gavin"], cls_brain(r["gavin"])) if r["gavin"] else "—"
        xb = badge(r["x"], cls_x(r["x"])) if r["x"] else "—"
        xtrend_html, xtrend_s = x_trend_cell(by_ticker.get(r["ticker"], []))
        comb = badge(r["combined"], cls_combined(r["combined"])) if r["combined"] else "—"
        dom = html.escape(AI_DOMAIN.get(r["ticker"], "—"))
        bkt = bucket_for(r["ticker"])
        stk_name_part = (" — " + r["name"]) if r.get("name") else ""
        stk_rating_part = (" (" + r["rating"] + ")") if r.get("rating") else ""
        stk_tip = html.escape(
            f'{r["ticker"]}{stk_name_part} · {AI_DOMAIN.get(r["ticker"], "—")}. '
            f'Analyzed {n}× · latest {r["date"]}: {r["base_action"] or "—"}{stk_rating_part}. '
            f'P(beat) {pb_disp} · combined {r["combined"] or "n/a"}. '
            f'Hover a column header for what each field means.')
        stk_rows += (
            f'<tr title="{stk_tip}" data-domain="{dom}" data-bucket="{html.escape(bkt)}">'
            f'<td><b>{tk}</b></td>'
            f'<td class="muted" data-s="{bucket_rank(bkt):02d}" style="white-space:nowrap">{html.escape(bkt)}</td>'
            f'<td class="muted" style="white-space:nowrap">{dom}</td>'
            f'<td class="num" data-s="{n}">{n}×</td>'
            f'<td data-s="{r["date"]}">{r["date"]}</td>'
            f'<td>{call}</td>'
            f'<td class="num" data-s="{pb_n if pb_n is not None else -1}">{pb_disp}</td>'
            f'<td>{jen}</td>'
            f'<td>{leo}</td>'
            f'<td>{jor}</td>'
            f'<td>{gav}</td>'
            f'<td>{xb}</td>'
            f'<td class="num" data-s="{xtrend_s}">{xtrend_html}</td>'
            f'<td>{comb}</td>'
            f'</tr>')

    # ---- decision-trend cards (multiply-analyzed tickers) ----
    multi = [tk for tk in trend if trend[tk]["n"] >= 2]
    multi.sort(key=lambda tk: (trend[tk]["breaks"], trend[tk]["n"]), reverse=True)
    changed = sum(1 for tk in multi if trend[tk]["breaks"])
    trend_cards = ""
    for tk in multi:
        t = trend[tk]
        r = latest[tk]
        link = f'<a href="{r["page"]}">{tk}</a>' if r.get("page") else tk
        brk = (f'<span class="badge b-sell">⚡ {t["breaks"]}×</span>' if t["breaks"]
               else '<span class="badge b-neu">stable</span>')
        sig_slug = t["signal"].lower().split()[0]  # strengthening/weakening/stable/whipsaw
        trend_cards += (
            f'<div class="trend-card" data-signal="{sig_slug}"><div class="trend-head"><span class="tk">{link}</span>'
            f'<span class="badge {t["sig_cls"]}">{t["signal"]}</span>{brk}'
            f'<span class="muted" style="margin-left:auto">{t["n"]} runs</span></div>'
            f'<div class="chart">{t["svg"]}</div>'
            f'<p class="trend-read">{t["sentence"]}</p></div>')
    if not trend_cards:
        trend_cards = '<p class="muted">No stock has been analyzed more than once yet.</p>'
    trend_intro = (f'<p class="muted" style="margin:-4px 0 14px">{len(multi)} stocks analyzed '
                   f'2+ times · <b class="b-neg">{changed}</b> changed the engine\'s stance at least once · '
                   f'{len(multi)-changed} held a stable read.</p>')

    # stance-change track-record card
    _tt_stance = ("Among tickers analyzed more than once, how many had their verdict/stance change "
                  "between the earliest and latest run (e.g. ALIGNED → EXPOSED). A measure of how "
                  "often the view flipped as new data arrived.")
    cards += (f'<div class="card" title="{html.escape(_tt_stance)}"><div class="k">Stance changes</div>'
              f'<div class="v">{changed}<small> of {len(multi)} multi-run names</small></div></div>')

    # domain filter dropdown — grouped under bucket optgroups, each with an
    # "All <bucket>" entry (value bucket:<name>) plus the specific domains within.
    domain_options = f'<option value="">All buckets &amp; domains ({len(L)})</option>'
    for b in sorted(buckets_present, key=bucket_rank):
        doms = sorted(buckets_present[b])
        nstocks = sum(len(dom_groups[d]) for d in doms)
        domain_options += f'<optgroup label="{html.escape(b)}">'
        domain_options += f'<option value="bucket:{html.escape(b)}">▸ All {html.escape(b)} ({nstocks})</option>'
        for d in doms:
            domain_options += f'<option value="{html.escape(d)}">{html.escape(d)} ({len(dom_groups[d])})</option>'
        domain_options += '</optgroup>'

    # ---- Financials tab (cached yfinance metrics) ----
    financials_html = build_financials(metrics, latest)

    # ---- Research tab + weekly Changes diff ----
    rx_cur = load_x_research(X_RESEARCH)
    rx_prev = load_prev_research(rx_cur)
    research_html = build_research(rx_cur, rx_prev)
    changes_ev, changes_n = compute_changes(recs, by_ticker, rx_cur, rx_prev)
    up_html, up_n = build_under_pressure(load_under_pressure(UNDER_PRESSURE))
    moves_html, moves_n = build_metric_moves(metrics, load_prev_metrics(), latest)
    changes_n += moves_n
    changes_html = up_html + build_changes(changes_ev, rx_prev) + moves_html
    reversals_html, reversals_n = build_reversals(changes_ev)
    badges = ''
    if up_n:
        badges += f'<span class="chgbadge upbadge">⚠️ {up_n} under pressure</span>'
    if changes_n:
        badges += f'<span class="chgbadge">🔔 {changes_n} change{"s" if changes_n != 1 else ""}</span>'
    if reversals_n:
        badges += f'<span class="chgbadge revbadge">🔄 {reversals_n} reversal{"s" if reversals_n != 1 else ""}</span>'
    changes_badge = badges
    changes_tab = f'🔔 Changes{f" ({changes_n + up_n})" if (changes_n + up_n) else ""}'
    reversals_tab = f'🔄 Reversals{f" ({reversals_n})" if reversals_n else ""}'

    itpl = open(os.path.join(TPL, "index.html"), encoding="utf-8").read()
    idx = itpl
    for k, v in {"{{GENERATED}}": NOW, "{{COUNT}}": str(len(recs)),
                 "{{TICKERS}}": str(len(latest)), "{{SUMMARY_CARDS}}": cards,
                 "{{DASHBOARDS}}": dashboards, "{{BY_STOCK}}": stk_rows,
                 "{{BY_DOMAIN}}": dom_rows, "{{DOMAIN_OPTIONS}}": domain_options,
                 "{{DOMAIN_CARDS}}": dom_cards, "{{RESEARCH}}": research_html,
                 "{{FINANCIALS}}": financials_html,
                 "{{CHANGES}}": changes_html, "{{CHANGES_BADGE}}": changes_badge,
                 "{{CHANGES_TAB}}": changes_tab, "{{REVERSALS}}": reversals_html,
                 "{{REVERSALS_TAB}}": reversals_tab,
                 "{{TREND_INTRO}}": trend_intro, "{{TREND_CARDS}}": trend_cards,
                 "{{TABLE_ROWS}}": rows_html}.items():
        idx = idx.replace(k, v)
    open(os.path.join(OUT, "index.html"), "w", encoding="utf-8").write(idx)

    # copy stylesheet
    css = open(os.path.join(TPL, "style.css"), encoding="utf-8").read()
    open(os.path.join(OUT, "style.css"), "w", encoding="utf-8").write(css)

    pages = sum(1 for r in recs if r.get("page"))
    print(f"built {OUT}/index.html  ·  {len(recs)} verdicts ({pages} detail pages, "
          f"{len(latest)} tickers)  ·  {len(res)} resolved")


if __name__ == "__main__":
    main()
