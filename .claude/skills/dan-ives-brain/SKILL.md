---
name: dan-ives-brain
description: Judge whether Dan Ives (Wedbush Securities) would rate a company a top pick in his "4th industrial revolution" / "Golden Age of AI" framework — is this a direct AI monetization beneficiary with Big Tech / cloud / cybersecurity / EV tailwinds? A qualitative sell-side analyst lens grounded only in what Dan Ives has actually said, sourced from a BM25 index over his media appearances (CNBC, Bloomberg, Fox Business, Yahoo Finance…) plus a news lane. Returns a "Dan Ives Brain Verdict" (Top Pick / Constructive / Cautious / Insufficient evidence) with confidence, reasons, and cited quotes. Use when the user asks "what would Dan Ives think of X", whether a name is in Dan Ives's coverage universe, or wants the Dan Ives / Wedbush verdict on a ticker without a full trading analysis.
---

# Dan Ives Brain (sell-side tech analyst conviction lens)

Answer one question about a company: **would Dan Ives (Wedbush Securities) rate it a
top pick** — judged through his "4th industrial revolution" / "Golden Age of AI" framework.
His central question: *is this a direct AI monetization beneficiary with strong Big Tech /
cloud / cybersecurity / EV tailwinds?* He covers primarily US large-cap tech (AAPL, MSFT,
GOOGL, META, AMZN), enterprise software (CRM, NOW, PLTR), cybersecurity (CRWD, PANW, ZS),
and EV / autonomous (TSLA). Judged **only** from what Dan Ives has actually said. This is
a **qualitative** lens — not a price forecast, not a BUY/HOLD/SELL.

> Research scaffold only. **Not** financial/investment advice. The verdict reflects
> Dan Ives's AI-tech-bull conviction, not whether the stock is a good investment.

This is the same lens that `trading-analysis` surfaces as Stage 6.663, but standalone.

## Inputs

Ask for (or infer):
- **Company** — name, CEO, ticker, flagship products (good alias terms sharpen retrieval).
- Optional **thesis terms** — the Dan Ives theses it touches (AI monetization / 4th industrial
  revolution / golden age of AI / cloud / cybersecurity / enterprise software / EV / Tesla /
  Apple ecosystem / Microsoft-OpenAI / digital transformation).

## Run the bridge

```
python3 .claude/skills/trading-analysis/scripts/dan_ives_brain.py \
    "<company> <CEO> <ticker/aliases>" \
    --thesis "<Dan Ives theses it touches>" \
    --k 5
```

Example:

```
python3 .claude/skills/trading-analysis/scripts/dan_ives_brain.py \
    "Microsoft MSFT Satya Nadella Azure OpenAI Copilot" \
    --thesis "AI monetization cloud enterprise golden age 4th industrial revolution" \
    --k 5
```

(Set `DAN_IVES_HOME` if the dan-ives-brain project lives elsewhere; default
`/home/ewexler/projects/dan-ives-brain`. If the bridge reports the index is missing, tell
the user Dan Ives Brain is unavailable and stop — **do not fabricate** a verdict or quotes.)

### Refreshing the corpus (optional)

```
python3 work/discover_new.py && python3 work/ingest_pending.py && \
  python3 work/fetch_news.py && python3 index/build_index.py     # in $DAN_IVES_HOME
```

(Idempotent. Discovery is STRICT — title must name Dan Ives; allowlisted financial-media
venues auto-ingest. The `/update-all` command does this for you.)

## Read the output → verdict

The bridge returns these groups, each hit tagged `[DAN-SAID]` or `[NEWS]`:
- **DIRECT MENTIONS — DAN IVES** — whether *he* names and rates the company,
- **NEWS MENTIONS** — third-party coverage,
- **THESIS FIT** — the Dan Ives framework the name touches,
- **BULL LENS** — his constructive AI-tech themes / who wins,
- **SKEPTICISM LENS** — what he flags as risk or avoids,

plus a **coverage signal** (`dan_direct_score`, `news_score`). Decide one verdict:

- **Top Pick** — Dan Ives explicitly names it as a Buy / Outperform / top pick in his AI
  monetization universe; strong, direct, repeated endorsement.
- **Constructive** — fits his framework (clear AI monetization angle, Big Tech / cloud /
  cybersecurity / EV tailwind) but no explicit top-pick call on this specific name.
- **Cautious** — he flags regulatory risk, China exposure, commoditization, or calls it
  an underperform / avoid.
- **Insufficient evidence** — outside his coverage universe or he doesn't mention it; do
  not infer a Top Pick from generic AI-bull passages.

If `dan_direct_score` is low, default to **Constructive or Insufficient**, not Top Pick.

## Output

- **Dan Ives Brain Verdict:** Top Pick / Constructive / Cautious / Insufficient evidence —
  with confidence (low / med / high).
- **Why:** 2–4 bullets tying the company to Dan's AI-monetization / 4th-industrial-revolution
  framework + whether it's in his explicit coverage universe.
- **In his words:** 1–3 short quoted snippets, each cited `(<date> — <venue/title>, <url>)`.
  Quote only retrieved text; **never invent quotes**.

Keep it qualitative and self-contained — a sell-side AI-tech-bull read, not a recommendation.
