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
import os, re, glob, html, datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TPL = os.path.join(ROOT, "scripts", "templates")
OUT = os.path.join(ROOT, "dashboard")
STOCKS = os.path.join(ROOT, "analyzed-stocks")
MEM = os.environ.get("TRADINGAGENTS_MEMORY_LOG_PATH",
                     os.path.expanduser("~/.tradingagents/memory/trading_memory.md"))
NOW = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")

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
    d["combined"] = grab(r"Combined Strategic Verdict:\s*\**\s*([A-Z ]+?)\**\s*[(\-—\.\n]", md)
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

# ---------- build ------------------------------------------------------------

def main():
    os.makedirs(OUT, exist_ok=True)
    mem = parse_memory(MEM)
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
                                       "jensen": "", "leopold": "", "jordi": "", "gavin": "", "combined": "",
                                       "base_action": "", "base_rating": "",
                                       "macro_action": "", "macro_rating": ""})
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
        recs.append({**d, "rating": rating, "base_action": base_action,
                     "macro_action": macro_action,
                     "macro_rating": d.get("macro_rating") or "",
                     "status": m.get("status", "pending"), "raw": m.get("raw", ""),
                     "alpha": m.get("alpha", ""), "holding": m.get("holding", ""),
                     "prob": prob, "horizon": m.get("horizon", "") or "24mo",
                     "exp24": exp24, "target24": fc24.get("target", ""),
                     "pbeat_n": num(prob), "exp24_n": num(exp24), "alpha_n": num(m.get("alpha", ""))})
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
            "{{DOMAIN}}": AI_DOMAIN.get(r["ticker"], "—"),
            "{{JENSEN}}": r["jensen"] or "n/a", "{{JENSEN_CLS}}": cls_brain(r["jensen"]),
            "{{LEOPOLD}}": r["leopold"] or "n/a", "{{LEOPOLD_CLS}}": cls_brain(r["leopold"]),
            "{{JORDI}}": r["jordi"] or "n/a", "{{JORDI_CLS}}": cls_brain(r["jordi"]),
            "{{GAVIN}}": r["gavin"] or "n/a", "{{GAVIN_CLS}}": cls_brain(r["gavin"]),
            "{{COMBINED}}": r["combined"] or "n/a", "{{COMBINED_CLS}}": cls_combined(r["combined"]),
            "{{VERDICT_NEW}}": inline(r["verdict_new"]) if r["verdict_new"] else '<span class="muted">—</span>',
            "{{FORECAST_TABLE}}": forecast_html(r["forecast"]),
            "{{TREND}}": trend_block(r["ticker"]),
            "{{BODY}}": md_to_html(r["md"]),
            "{{SRCPATH}}": r["src"], "{{GENERATED}}": NOW,
        }
        for k, v in repl.items():
            page = page.replace(k, v)
        open(os.path.join(OUT, r["page"]), "w", encoding="utf-8").write(page)

    # ---- dashboards (latest decision per ticker) ----
    latest = {}
    for r in recs:
        if r["ticker"] not in latest:  # recs already sorted date desc
            latest[r["ticker"]] = r
    L = list(latest.values())

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

    dom_rows = ""
    dom_cards = ""
    for dom, members in sorted(dom_groups.items(),
                               key=lambda kv: (-sum(_cscore(m["combined"]) for m in kv[1]) / len(kv[1]), kv[0])):
        n = len(members)
        avg = sum(_cscore(m["combined"]) for m in members) / n
        n_contested = sum(1 for m in members if (m["combined"] or "").upper() == "CONTESTED")
        ordered = sorted(members, key=lambda m: (-_cscore(m["combined"]), -priority_100(m)))
        chips = " ".join(_chip(m) for m in ordered)
        cls_tilt = "b-pos" if avg > 0.4 else "b-neg" if avg < -0.4 else "muted"
        tilt_lab = _tilt_label(avg, n_contested, n)
        dom_rows += (f'<tr><td><b>{html.escape(dom)}</b></td>'
                     f'<td class="num" data-s="{n}">{n}</td>'
                     f'<td>{chips}</td>'
                     f'<td data-s="{avg:.2f}"><span class="{cls_tilt}">{tilt_lab}</span> '
                     f'<span class="muted">({avg:+.1f})</span></td></tr>')
        # per-domain dashboard card: how the AI-trend behaves + its companies
        note = DOMAIN_NOTE.get(dom, "")
        avg_p = round(sum(priority_100(m) for m in members) / n)
        dom_cards += (
            f'<div class="domcard" data-domain="{html.escape(dom)}" data-tilt="{avg:.2f}">'
            f'<div class="domcard-head"><b>{html.escape(dom)}</b>'
            f'<span class="badge {cls_combined("CONVICTION ALIGNED" if avg>=1.5 else "ALIGNED" if avg>=0.5 else "EXPOSED" if avg<=-0.5 else "CONTESTED" if n_contested else "NEUTRAL")}">{tilt_lab}</span></div>'
            f'<div class="domcard-meta"><span class="muted">{n} name{"s" if n>1 else ""} · tilt {avg:+.1f} · avg priority {avg_p}</span></div>'
            f'<p class="domcard-read">{html.escape(note)}</p>'
            f'<ul class="domlist">{"".join(_dom_member_li(m) for m in ordered)}</ul>'
            f'</div>')

    # ---- track-record cards ----
    res = [r for r in recs if r["status"] == "resolved" and r["alpha_n"] is not None]
    hit = sum(1 for r in res if r["alpha_n"] > 0)
    pend = sum(1 for r in recs if r["status"] == "pending")
    mean_alpha = (sum(r["alpha_n"] for r in res) / len(res)) if res else None
    cards = "".join([
        f'<div class="card"><div class="k">Verdicts</div><div class="v">{len(recs)}<small> · {len(latest)} tickers</small></div></div>',
        f'<div class="card"><div class="k">Pending</div><div class="v">{pend}<small> awaiting horizon</small></div></div>',
        f'<div class="card"><div class="k">Resolved hit-rate</div><div class="v">{(100*hit/len(res)):.0f}%<small> {hit}/{len(res)} beat bench</small></div></div>' if res else
        '<div class="card"><div class="k">Resolved hit-rate</div><div class="v">—<small> none matured</small></div></div>',
        f'<div class="card"><div class="k">Mean realized alpha</div><div class="v {"b-pos" if (mean_alpha or 0)>0 else "b-neg"}">{mean_alpha:+.1f}%</div></div>' if mean_alpha is not None else
        '<div class="card"><div class="k">Mean realized alpha</div><div class="v">—</div></div>',
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
        outcome = (f'{r["alpha"]} α' if r["status"] == "resolved" else
                   (f'P {pb_disp}' if pb_n is not None else "pending"))
        osort = r["alpha_n"] if r["status"] == "resolved" and r["alpha_n"] is not None else (pb_n or 0)
        ocls = "b-pos" if (r["status"] == "resolved" and (r["alpha_n"] or 0) > 0) else ("b-neg" if r["status"] == "resolved" else "muted")
        exp_sort = r["exp24_n"] if r["exp24_n"] is not None else -999
        exp_disp = html.escape(r["exp24"] or "—")
        comb = badge(r["combined"], cls_combined(r["combined"])) if r["combined"] else "—"
        jen = badge(r["jensen"], cls_brain(r["jensen"])) if r["jensen"] else "—"
        leo = badge(r["leopold"], cls_brain(r["leopold"])) if r["leopold"] else "—"
        jor = badge(r["jordi"], cls_brain(r["jordi"])) if r["jordi"] else "—"
        gav = badge(r["gavin"], cls_brain(r["gavin"])) if r["gavin"] else "—"
        base_b = badge(r["base_action"], cls_action(r["base_action"]))
        macro_b = badge(r["macro_action"], cls_action(r["macro_action"]))
        prio = priority_100(r); prio_raw = priority_raw(r)
        dom_cell = html.escape(AI_DOMAIN.get(r["ticker"], "—"))
        rows_html += (
            f'<tr data-domain="{dom_cell}">'
            f'<td data-s="{r["date"]}">{r["date"]}</td>'
            f'<td><b>{tk}</b></td>'
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
            f'<td class="num {ocls}" data-s="{osort}">{outcome}</td>'
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
        comb = badge(r["combined"], cls_combined(r["combined"])) if r["combined"] else "—"
        dom = html.escape(AI_DOMAIN.get(r["ticker"], "—"))
        stk_rows += (
            f'<tr data-domain="{dom}">'
            f'<td><b>{tk}</b></td>'
            f'<td class="muted" style="white-space:nowrap">{dom}</td>'
            f'<td class="num" data-s="{n}">{n}×</td>'
            f'<td data-s="{r["date"]}">{r["date"]}</td>'
            f'<td>{call}</td>'
            f'<td class="num" data-s="{pb_n if pb_n is not None else -1}">{pb_disp}</td>'
            f'<td>{jen}</td>'
            f'<td>{leo}</td>'
            f'<td>{jor}</td>'
            f'<td>{gav}</td>'
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
    cards += (f'<div class="card"><div class="k">Stance changes</div>'
              f'<div class="v">{changed}<small> of {len(multi)} multi-run names</small></div></div>')

    # domain filter dropdown options (with per-domain counts) for the By-stock table
    domain_options = f'<option value="">All domains ({len(L)})</option>'
    for dom in sorted(dom_groups):
        domain_options += f'<option value="{html.escape(dom)}">{html.escape(dom)} ({len(dom_groups[dom])})</option>'

    itpl = open(os.path.join(TPL, "index.html"), encoding="utf-8").read()
    idx = itpl
    for k, v in {"{{GENERATED}}": NOW, "{{COUNT}}": str(len(recs)),
                 "{{TICKERS}}": str(len(latest)), "{{SUMMARY_CARDS}}": cards,
                 "{{DASHBOARDS}}": dashboards, "{{BY_STOCK}}": stk_rows,
                 "{{BY_DOMAIN}}": dom_rows, "{{DOMAIN_OPTIONS}}": domain_options,
                 "{{DOMAIN_CARDS}}": dom_cards,
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
