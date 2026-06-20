---
name: jordi-brain
description: Judge whether a company sits with or against Jordi Visser's macro / AI investment thesis — the AI capex super-cycle, compute scarcity vs. abundance, the deflationary AI productivity boom ("the new QE is AI and crypto"), bitcoin as the purest AI-macro trade, physical AI / robotics / robotaxis, and creative destruction (the "SaaS-pocalypse", ROIC gaps, labor disruption). A qualitative thesis-fit lens grounded only in what Jordi has actually said, sourced from a BM25 index over every video on his @JordiVisserLabs YouTube channel plus a news lane. Returns a "Jordi Brain Verdict" (Constructive / Possible / Cautious / Insufficient evidence) with confidence, reasons, and cited quotes. Use when the user asks "what would Jordi Visser think of X", whether a company is an AI-capex / productivity-boom beneficiary or a creative-destruction casualty, whether a name fits Jordi's macro framework, or wants the Jordi verdict on a ticker without a full trading analysis.
---

# Jordi Brain (macro / AI thesis-fit lens)

Answer one question about a company: **does it sit with or against Jordi Visser's macro /
AI thesis** — is it a *beneficiary* of the AI capex super-cycle, compute scarcity, the
deflationary productivity boom and bitcoin/physical-AI build-out (a thesis *tailwind*), or
on the wrong side of the creative destruction he warns about — the "SaaS-pocalypse", ROIC
gaps, hyperscaler leverage, labor disruption (a thesis *headwind*)? Judged **only** from
what Jordi has actually said. This is a **qualitative** secular lens — not a price
forecast, not a BUY/HOLD/SELL.

> Research scaffold only. **Not** financial/investment advice. The verdict reflects
> Jordi-thesis-fit, not whether the stock is a good investment.

This is the same lens that `trading-analysis` surfaces as Stage 6.65, but standalone — run
it for any company without the full multi-agent forecast.

## Inputs

Ask for (or infer):
- **Company** — name, CEO, ticker, flagship products (good alias terms sharpen retrieval).
- Optional **thesis terms** — the Jordi theses the company touches (AI capex cycle / compute
  scarcity / deflation & productivity / bitcoin / physical AI / robotics / SaaS disruption /
  ROIC gap / agents). Infer from the company if not given.

## Run the bridge

The bridge queries the "Jordi brain" — a BM25 index over every @JordiVisserLabs video
(what Jordi *said*) plus a news lane (third-party coverage). From the TradingAgents repo
root, pass alias terms plus the Jordi theses the company touches:

```
python3 .claude/skills/trading-analysis/scripts/jordi_brain.py \
    "<company> <CEO> <ticker/aliases>" \
    --thesis "<Jordi theses it touches>" \
    --k 5
```

Example:

```
python3 .claude/skills/trading-analysis/scripts/jordi_brain.py \
    "Palantir PLTR Karp" \
    --thesis "SaaS disruption agents software ontology AI productivity" \
    --k 5
```

(Set `JORDI_HOME` if the jordi-brain project lives elsewhere; default
`/home/ewexler/projects/jordi-brain`. If the bridge reports the index is missing, tell the
user Jordi Brain is unavailable and stop — **do not fabricate** a verdict or quotes.)

### Refreshing the corpus (optional)

The index covers what **Jordi said** (his channel transcripts) and **news** about him. To
pull the latest before judging, run once in the jordi-brain project:

```
python3 work/fetch_channel.py && python3 work/fetch_news.py && python3 index/build_index.py
```

(Idempotent — skips videos/news already on disk. The `/update` command does this for you.)

## Read the output → verdict

The bridge returns these groups, each hit tagged `[JORDI-SAID]` or `[NEWS]`:
- **DIRECT MENTIONS — JORDI** — whether *he* talks about the company,
- **NEWS MENTIONS** — third-party coverage in the corpus,
- **THESIS FIT** — the Jordi macro/AI framework the name touches,
- **TAILWIND LENS** — his constructive themes (who wins the AI-capex / productivity boom),
- **SKEPTICISM / CREATIVE-DESTRUCTION LENS** — what he warns gets disrupted,

plus a **coverage signal** (`jordi_direct_score`, `news_score`). From these decide one
verdict, grounded in Jordi's recurring framework:

- Names squarely in the **AI-capex beneficiaries / compute & power scarcity / physical-AI /
  bitcoin-macro** build-out, or genuine **productivity / disruption winners**, lean
  *Constructive*.
- Names his thesis says get **commoditized or disrupted** (legacy seat-priced SaaS an agent
  replicates, businesses with a widening **ROIC gap**, over-levered hyperscalers,
  labor-arbitrage services) lean *Cautious*.
- If `jordi_direct_score` is low, say the corpus doesn't name it and lean on thesis fit —
  don't overclaim from a tangential mention.

## Output

- **Jordi Brain Verdict:** Constructive / Possible / Cautious / Insufficient evidence —
  with confidence (low / med / high).
- **Why:** 2–4 bullets tying the company to specific Jordi theses + where it sits in his
  framework (capex beneficiary / scarcity winner / productivity winner / commoditized /
  disrupted / orthogonal).
- **In his words:** 1–3 short quoted snippets, each cited `(<date> — <video title>, <url>)`.
  Quote only retrieved text; **never invent quotes**.

Keep the verdict qualitative and self-contained — it is a thesis-fit read, not a
recommendation.
