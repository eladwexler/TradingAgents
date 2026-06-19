---
name: jensen-brain
description: Judge whether Jensen Huang / NVIDIA would strategically back a company (invest, partner, acquire, or champion it) — a qualitative NVIDIA-strategic-fit lens grounded only in what Jensen has actually said, sourced from a BM25 index over 100+ Jensen Huang interview/keynote transcripts. Returns a "Jensen Brain Verdict" (Likely back / Possible / Unlikely back / Insufficient evidence) with confidence, reasons, and cited quotes. Use when the user asks "would Jensen back X", "what would Jensen Huang think of X", whether a company sits with or against NVIDIA's platform, or wants the Jensen verdict on a name without running a full trading analysis.
---

# Jensen Brain (NVIDIA strategic-fit lens)

Answer one question about a company: **would Jensen Huang / NVIDIA strategically back it**
(invest, partner, acquire, or champion it), judged *only* from what Jensen has actually
said in public? This is a **qualitative** secular sanity-check on whether a name sits
*with* or *against* NVIDIA's platform — not a price forecast, not a BUY/HOLD/SELL.

> Research scaffold only. **Not** financial/investment advice. The verdict reflects
> NVIDIA-strategic-fit, not whether the stock is a good investment.

This is the same lens that `trading-analysis` surfaces as Stage 6.5, but standalone — run
it for any company without the full multi-agent forecast.

## Inputs

Ask for (or infer):
- **Company** — name, CEO, flagship products/tickers (good alias terms sharpen retrieval).
- Optional **sector / theses** — the NVIDIA theses the company touches (accelerated
  computing / AI factories / physical AI / robotics / autonomous vehicles / sovereign AI /
  digital biology / CUDA ecosystem). Infer from the company if not given.

## Run the bridge

The bridge queries the "Jensen brain" — a BM25 index over 100+ Jensen interview/keynote
transcripts in the companion `jensen` project. From the TradingAgents repo root, pass
alias terms plus the NVIDIA theses the company touches:

```
python3 .claude/skills/trading-analysis/scripts/jensen_brain.py \
    "<company> <CEO> <products/aliases>" \
    --sector "<NVIDIA theses it touches>" \
    --k 5
```

Example:

```
python3 .claude/skills/trading-analysis/scripts/jensen_brain.py \
    "Tesla Elon Musk autonomous robotaxi Optimus Dojo" \
    --sector "autonomous vehicles physical AI robotics humanoid" \
    --k 5
```

(Set `JENSEN_HOME` if the jensen project lives elsewhere; default
`/home/ewexler/projects/jensen-brain`. If the bridge reports the index is missing, tell
the user Jensen Brain is unavailable and stop — **do not fabricate** a verdict or quotes.)

### Refreshing NVIDIA's actions (optional)

The index covers two things: what **Jensen said** (interview/keynote transcripts) and
what **NVIDIA published** (press releases + blog — partnerships, investments,
announcements). To pull the latest NVIDIA materials before judging, run once in the
jensen project:

```
python3 work/fetch_nvidia.py && python3 index/build_index.py   # in $JENSEN_HOME
```

(Idempotent — skips items already on disk. Skip this if the corpus is fresh enough.)

## Read the output → verdict

The bridge returns these groups, each hit tagged `[JENSEN-SAID]` or
`[NVDA-ANNOUNCED]`:
- **DIRECT MENTIONS — JENSEN** — whether *he* talks about the company,
- **NVIDIA ACTIONS / ANNOUNCEMENTS** — whether *NVIDIA* has actually done something
  (partnered, invested, built with them) — the difference between rhetoric and action,
- sector/thesis fit, competition/substitution risk, partnership philosophy,

plus a two-part **coverage signal** (`jensen_top_score` = does he mention it;
`nvda_action_score` = has NVIDIA acted on it). Weigh a real NVIDIA action far more
heavily than praise. From these, decide one verdict, grounded in Jensen's recurring
theses:

- Companies that **consume/extend** the NVIDIA platform lean *Likely back*.
- Companies building **substitutes** (rival GPUs/ASICs/TPUs, competing stacks) lean
  *Unlikely back*.
- Distinguish *Jensen praising/using* a company from *NVIDIA actually backing* it.
- If `top_direct_score` is low, say the corpus is thin and lean on sector fit — don't
  overclaim from a tangential mention.

## Output

- **Jensen Brain Verdict:** Likely back / Possible / Unlikely back / Insufficient evidence
  — with confidence (low / med / high).
- **Why:** 2–4 bullets tying the company to specific Jensen theses + its NVIDIA
  relationship (customer / partner / supplier / competitor).
- **In his words:** 1–3 short quoted snippets, each cited `(<date> — <video title>, <url>)`.
  Quote only retrieved text; **never invent quotes**.
- **NVIDIA on record:** if the NVIDIA-actions lane has hits, name the actual
  partnership/investment/announcement with its date + url; if it's empty, say plainly
  that NVIDIA has published no such action (don't infer one from Jensen's praise).

Keep the verdict qualitative and self-contained — it is a strategic-fit read, not a
recommendation.
