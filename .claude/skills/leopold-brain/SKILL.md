---
name: leopold-brain
description: Judge whether a company sits with or against Leopold Aschenbrenner's "Situational Awareness" thesis — AGI by ~2027 via straight-line compute scaling, the intelligence explosion, the trillion-dollar cluster, power/electricity as the binding constraint, chips/fabs, locking down the labs, and the US-China superintelligence race. A qualitative thesis-fit lens grounded only in what Leopold has actually written or said, sourced from a BM25 index over his Situational Awareness essay + long-form interviews. Returns a "Leopold Brain Verdict" (Thesis tailwind / Possible / Thesis headwind / Insufficient evidence) with confidence, reasons, and cited quotes. Use when the user asks "what would Leopold Aschenbrenner think of X", whether a company is an AGI-buildout beneficiary, whether a name fits the Situational Awareness / 2027-AGI thesis, or wants the Leopold verdict on a ticker without a full trading analysis.
---

# Leopold Brain (Situational Awareness thesis-fit lens)

Answer one question about a company: **does it sit *with* or *against* Leopold
Aschenbrenner's "Situational Awareness" thesis** — is it a beneficiary/enabler of the
AGI build-out (a thesis *tailwind*) or orthogonal / likely to be disrupted (a thesis
*headwind*), judged *only* from what Leopold has actually written or said in public?
This is a **qualitative** secular sanity-check on whether a name rides the build-out
Leopold describes — not a price forecast, not a BUY/HOLD/SELL.

> Research scaffold only. **Not** financial/investment advice. The verdict reflects
> fit-with-Leopold's-worldview, not whether the stock is a good investment.

This is the Situational-Awareness counterpart to `jensen-brain`'s NVIDIA-strategic-fit
lens. Where Jensen Brain asks "would Jensen/NVIDIA back it", Leopold Brain asks "does
the Situational Awareness build-out thesis lift it or pass it by".

## The thesis in one breath

Leopold's worldview (from the essay + interviews): AGI is plausibly ~2027, driven by
straight-line **OOMs** of compute scale-up + algorithmic efficiency + "unhobbling";
AGI then bootstraps an **intelligence explosion** to superintelligence. That forces an
**industrial mobilization** — the **trillion-dollar cluster**, with **power/electricity
the single biggest binding constraint** (natural gas, nuclear, SMRs, gigawatts→100GW),
plus **chips / fabs / HBM / CoWoS / TSMC** bottlenecks. National security takes over:
**lock down the labs** (security, espionage, the CCP threat), **the free world must
prevail**, and ultimately a government-led **"Project."** Beneficiaries: compute,
power, grid, chips/fabs, the leading labs. At risk: anything the build-out commoditizes
or AGI itself disrupts.

## Inputs

Ask for (or infer):
- **Company** — name, CEO, flagship products/tickers (good alias terms sharpen retrieval).
- Optional **theses** — the Situational Awareness theses the company touches (compute
  scaling / trillion-dollar cluster / power & electricity / chips & fabs & HBM /
  AGI labs / security / US-China race). Infer from the company if not given.

## Run the bridge

The bridge queries the "Leopold brain" — a BM25 index over Leopold's *Situational
Awareness* essay + his long-form interviews in the companion `leopold-brain` project.
From the TradingAgents repo root, pass alias terms plus the theses the company touches:

```
python3 .claude/skills/trading-analysis/scripts/leopold_brain.py \
    "<company> <CEO> <products/aliases>" \
    --thesis "<Situational Awareness theses it touches>" \
    --k 5
```

Example:

```
python3 .claude/skills/trading-analysis/scripts/leopold_brain.py \
    "Constellation Vistra nuclear utility electricity power generation" \
    --thesis "power electricity gigawatt natural gas energy constraint datacenter buildout" \
    --k 5
```

(Set `LEOPOLD_HOME` if the leopold-brain project lives elsewhere; default
`/home/ewexler/projects/leopold-brain`. If the bridge reports the index is missing,
tell the user Leopold Brain is unavailable and stop — **do not fabricate** a verdict
or quotes.)

### Refreshing / extending the corpus (optional)

The corpus is Leopold's own words: the canonical essay + interview transcripts. To
refresh or extend it, run in the leopold-brain project:

```
python3 work/fetch_situational_awareness.py   # essay chapters (idempotent)
python3 work/fetch_interviews.py              # interview transcripts (idempotent)
python3 index/build_index.py                  # rebuild the BM25 index
```

Add new interview video IDs to the `INTERVIEWS` list in `work/fetch_interviews.py`.
Keep the corpus to **Leopold speaking/writing** — not third-party commentary,
audiobook reads, or essay summaries.

## Read the output → verdict

The bridge returns these groups, each hit tagged `[ESSAY]` or `[INTERVIEW (...)]`:
- **DIRECT MENTIONS** — does Leopold name the company at all,
- **THESIS FIT** — how squarely it sits in the Situational Awareness build-out,
- **BENEFICIARY / BOTTLENECK LENS** — who the build-out enriches and what gates it
  (compute, power, chips),
- **SKEPTICISM / WHAT-BREAKS-THE-TRADE LENS** — where Leopold is wary (bubble,
  overbuild, commoditization, export controls, scaling stalls),

plus a **coverage signal** (`leopold_direct_score` = does he name it). Note Leopold is
an essayist/investor, **not** a company — there is no "announcements" lane, and a name
absent from the corpus is normal. Judge by thesis fit, not by whether he happened to
mention it. From these, decide one verdict, grounded in his recurring theses:

- Names squarely in the **build-out** — compute, **power/grid/utilities**, **chips /
  fabs / HBM / TSMC**, the leading **AGI labs** — lean *Thesis tailwind*.
- Names the build-out **commoditizes or AGI disrupts** (e.g. labor-arbitrage services,
  legacy software moats AGI erodes), or that are simply orthogonal, lean *Thesis headwind*.
- Distinguish *Leopold naming a sector* (power, chips) from *naming the specific company* —
  most tickers he never names; reason from sector fit and say so.
- Weigh the **skepticism lane**: if the build-out makes a thing cheap/commoditized, that
  cuts against a name whose margins depend on scarcity.

## Output

- **Leopold Brain Verdict:** Thesis tailwind / Possible / Thesis headwind / Insufficient
  evidence — with confidence (low / med / high).
- **Why:** 2–4 bullets tying the company to specific Situational Awareness theses
  (compute / power / chips / labs / security / US-China) and where it sits in the
  build-out (enabler / beneficiary / commoditized / disrupted / orthogonal).
- **In his words:** 1–3 short quoted snippets, each cited `(<date> — <title>, <url>)`.
  Quote only retrieved text; **never invent quotes**.
- **Thesis caveat:** if `leopold_direct_score` is low, say plainly the corpus does not
  name the company and the read rests on sector fit — don't overclaim from a tangential
  hit. Note the corpus window (essay = mid-2024; interviews through their dates).

Keep the verdict qualitative and self-contained — it is a thesis-fit read, not a
recommendation.
