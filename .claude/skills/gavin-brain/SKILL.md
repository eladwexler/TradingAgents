---
name: gavin-brain
description: Judge — STRICTLY — whether Gavin Baker (Atreides Management) would back a company as an AI winner, through his central lens "is AI *sustaining* (helps the incumbent's moat — proprietary data, distribution, scale, compute) or *disruptive* (erodes it)?". A qualitative AI-stock-picker lens grounded only in what Gavin has actually said, sourced from a BM25 index over his long-form guest appearances (BG2, Invest Like the Best, Aleph, a16z, Sohn, TBPN…) plus a news lane. Returns a "Gavin Brain Verdict" (Conviction pick / Possible / Cautious / Insufficient evidence) with confidence, reasons, and cited quotes. Use when the user asks "what would Gavin Baker think of X", whether AI is sustaining or disruptive to a business, whether a name is a Gavin/Atreides-style AI winner, or wants the Gavin verdict on a ticker without a full trading analysis.
---

# Gavin Brain (AI-winner conviction lens — STRICT)

Answer one question about a company: **would Gavin Baker back it as an AI winner** —
judged through his central framework, *"is AI sustaining or disruptive to this business?"*
Sustaining innovation strengthens an incumbent's moat (proprietary data, distribution,
scale, compute access) → constructive. Disruptive innovation erodes the moat (commoditizes
the product, lets a new entrant in) → avoid. Judged **only** from what Gavin has actually
said. This is a **qualitative** lens — not a price forecast, not a BUY/HOLD/SELL.

> Research scaffold only. **Not** financial/investment advice. The verdict reflects
> Gavin-AI-conviction, not whether the stock is a good investment.

**Be strict.** Gavin is a concentrated, opinionated investor. Reserve the positive verdict
(*Conviction pick*) for **strong, direct, repeated** evidence — a known holding or an
emphatic endorsement of the *specific name*. Praise of a *theme* (e.g. "AI compute is
huge") is **not** backing a specific stock. When evidence is thin, say *Possible* or
*Insufficient* — do not inflate.

This is the same lens that `trading-analysis` surfaces as Stage 6.66, but standalone.

## Inputs

Ask for (or infer):
- **Company** — name, CEO, ticker, flagship products (good alias terms sharpen retrieval).
- Optional **thesis terms** — the Gavin theses it touches (compute / accelerators / inference
  vs training / custom silicon / proprietary data / distribution / power / sustaining-vs-disruptive).

## Run the bridge

```
python3 .claude/skills/trading-analysis/scripts/gavin_brain.py \
    "<company> <CEO> <ticker/aliases>" \
    --thesis "<Gavin theses it touches>" \
    --k 5
```

Example:

```
python3 .claude/skills/trading-analysis/scripts/gavin_brain.py \
    "Nvidia NVDA Jensen Huang" \
    --thesis "compute accelerator AI capex inference training moat custom silicon" \
    --k 5
```

(Set `GAVIN_HOME` if the gavin-brain project lives elsewhere; default
`/home/ewexler/projects/gavin-brain`. If the bridge reports the index is missing, tell the
user Gavin Brain is unavailable and stop — **do not fabricate** a verdict or quotes.)

### Refreshing the corpus (optional)

```
python3 work/discover_new.py && python3 work/ingest_pending.py && \
  python3 work/fetch_news.py && python3 index/build_index.py     # in $GAVIN_HOME
```

(Idempotent. Discovery is STRICT — only allowlisted long-form venues auto-ingest. The
`/update-all` command does this for you.)

## Read the output → verdict

The bridge returns these groups, each hit tagged `[GAVIN-SAID]` or `[NEWS]`:
- **DIRECT MENTIONS — GAVIN** — whether *he* talks about the company,
- **NEWS MENTIONS** — third-party coverage,
- **THESIS FIT** — the Gavin framework the name touches,
- **SUSTAINING-VS-DISRUPTIVE LENS** — does AI help or erode the moat,
- **SKEPTICISM LENS** — what he avoids,

plus a **coverage signal** (`gavin_direct_score`, `news_score`). Decide one verdict,
applying the strict bar:

- **Conviction pick** — strong, direct, repeated endorsement or a known holding; AI is
  clearly *sustaining* for its moat (compute/data/distribution/scale winner). High bar.
- **Possible** — fits his framework or he speaks well of the theme, but no direct,
  conviction-level call on the specific name.
- **Cautious** — he frames AI as *disruptive* to it, or flags commoditization / thin-wrapper
  / share-loss risk.
- **Insufficient evidence** — he doesn't mention it and framework fit isn't overwhelming.

If `gavin_direct_score` is low, do **not** issue a Conviction pick — lean Possible/Insufficient
and say the corpus is thin.

## Output

- **Gavin Brain Verdict:** Conviction pick / Possible / Cautious / Insufficient evidence —
  with confidence (low / med / high).
- **Why:** 2–4 bullets tying the company to Gavin's sustaining-vs-disruptive framework +
  whether it's a compute/data/distribution moat winner or a disruption casualty.
- **In his words:** 1–3 short quoted snippets, each cited `(<date> — <venue/title>, <url>)`.
  Quote only retrieved text; **never invent quotes**.

Keep it qualitative and self-contained — a strict AI-conviction read, not a recommendation.
