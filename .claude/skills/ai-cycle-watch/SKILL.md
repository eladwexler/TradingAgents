---
name: ai-cycle-watch
description: Locate where we are in the AI build-out / capex cycle, score the leading indicators that precede a correction, estimate the timeline, and produce a survivor-vs-casualty watchlist with positioning implications. Use when the user asks about "the AI bubble", AI capex cycle, when the correction will happen, what survives it, or which companies benefit/suffer from the AI build-out.
---

# AI Cycle Watch (build-out → correction → aftermath)

A reusable macro-thesis skill: map the AI infrastructure cycle, read the canary indicators that flip *before* prices do, estimate where in the arc we are, and translate that into a survivor/casualty watchlist and positioning. It reuses this project's key-free data CLI (`ta_data.py`) for market data and `WebSearch`/`WebFetch` for the live qualitative readings (capex guidance, GPU rental prices, news).

> Research scaffold only. **Not** financial/investment advice. Cycles are *directionally* predictable and *precisely* unpredictable — never present a date as a forecast; present a window with its error bar and the evidence behind it. Always carry the disclaimer into the final output.

## Inputs

Ask for (or infer):
- **As-of date** — `YYYY-MM-DD`, defaults to today. Convert any relative dates ("now") to absolute in the report.
- Optional **focus** — e.g. "power names", "hyperscalers", "what to short", "where are we". Default: full sweep.
- Optional **watchlist tickers** to score individually (otherwise use the default baskets below).

## Data sources (no LLM key required)

1. **Market data** — reuse the trading-analysis CLI from the repo root:
   ```
   python3 .claude/skills/trading-analysis/scripts/ta_data.py <command> [args]
   ```
   Useful here: `gather TICKER DATE` (one-shot bundle), `global_news DATE`, `news TICKER START END`, `snapshot TICKER DATE`, `fundamentals TICKER DATE`. Same **data-integrity rule applies: never state a number that didn't come from tool output.** If a command prints `NO_DATA`/`ERROR`, say the data is unavailable.
2. **Macro data** — run the new macro CLI for hard, quantitative indicators:
   ```
   python3 .claude/skills/trading-analysis/scripts/ta_macro_data.py <command>
   ```
   Commands: `macro` (10yr Treasury & High Yield proxy), `valuation` (Mag7 Forward P/E), `software_canary` (Application/Software YoY revenue growth).
3. **Live qualitative readings** — `WebSearch`/`WebFetch` for the indicators a price feed won't give you: hyperscaler capex guidance language, GPU rental/spot prices, transformer/power lead times, financing structure (circular deals, SPV/debt-funded data centers), and depreciation commentary. Always date-stamp what you find and cite the source.

## The phase model (the map)

| Phase | What it is | Rough timing | Marker that it's ending |
|---|---|---|---|
| 1. Infrastructure land-grab | GPUs, data centers, power, training | 2023–2026 | Capex growth decelerates |
| 2. Model capability race | Frontier reasoning, multimodal, agents | 2024–2027 | Releases underwhelm / "exponential" narrative breaks |
| 3. Application / agent deployment | AI doing real enterprise work | 2025–2029 | ROI proven *or* disproven |
| 4. ROI reckoning | Monetization must justify capex; consolidation | 2027–2030 | The structural correction |
| 5. Diffusion / commoditization | AI as cheap embedded utility | 2029+ | — |

Phases overlap. The job is to locate the **center of gravity**, not pick one box.

## The leading indicators (the canaries)

Score each as **Green** (boom intact) / **Amber** (stress building) / **Red** (rolling over). These flip before price. Apply strict quantitative thresholds where specified.

1. **Hyperscaler capex guidance** *(highest weight)* — MSFT/GOOGL/AMZN/META. Raising + "we're supply-constrained" = Green. First quarter any of them *guides capex down* or says "more disciplined" = the starting gun → Red.
2. **GPU rental / spot prices** — H100/B200 hourly rates. Stable/rising = Green; **falling = supply outrunning demand = early glut** = Amber→Red. The canary.
3. **NVDA forward guidance & backlog quality** — clean backlog = Green; "lumpiness", cancellations, stretched customer financing = Amber/Red.
4. **Power / transformer / HVAC lead times** — long & lengthening = demand hot (Green for the theme, but late-cycle); *easing* lead times = cooling = Amber.
5. **Financing structure** — more **circularity** (chipmakers funding their own customers, debt/SPV-financed data centers) = later, more fragile stage = Amber/Red.
6. **Market concentration** — index returns leaning on fewer names = fragility high = Amber.
7. **Credibility events** — a flagship enterprise AI deployment publicly failing, or a marquee model release underwhelming = narrative crack = Red.
8. **Depreciation vs. revenue** — as 2024–2026 capex depreciates into income statements, is AI revenue showing up to cover it? Gap widening = Amber→Red.
9. **Macro/Cost of Capital** — Run `ta_macro_data.py macro`. 10-year Treasury > 4.5% or HYG dropping > 5% MoM = Red. Otherwise Amber if rising, Green if falling.
10. **Valuation Heatmap** — Run `ta_macro_data.py valuation`. Mag7 Avg Fwd P/E > 35 = Red (Euphoria). Mag7 Avg Fwd P/E 28-35 = Amber. < 28 = Green.
11. **Insider Selling & Smart Money** — C-suite/10% owner selling in the "survivors" basket (NVDA, MSFT, AVGO). Spikes > 2x trailing average = Red.
12. **Application Layer ROI Canary** — Run `ta_macro_data.py software_canary`. If average YoY revenue growth of the software basket drops below 20% while Infrastructure Capex (#1) is still growing, this is a structural fracture = Red.

## The Bottleneck Cascade (the mechanism of re-rating)

The AI buildout is a sequence of **binding constraints**. When a resource becomes scarce relative to a $700B+ annual spend, the company that owns it captures outsized pricing power, backlog visibility, and narrative dominance simultaneously — fundamentals look great *because of* the bottleneck, not independently of it. The stock re-rates to price in that rent. Then the bottleneck shifts, and so does the re-rating.

This is more important than any valuation multiple. A company AT the current bottleneck will always look expensive on trailing P/S — that is the point. A company PAST the bottleneck will look cheap while its rent disappears.

**The cascade so far and ahead:**

| Node | Status | Owners | Shift signal to watch |
|---|---|---|---|
| Training compute / GPUs | EASING — Blackwell supply ramping | NVDA | H100/B200 spot prices falling |
| HBM memory | ACTIVE | MU, SK Hynix | CXMT supply online; HBM spot softens |
| Networking / interconnect | ACTIVE | AVGO, ANET, CRDO | Lead times ease; merchant silicon catches up |
| Custom silicon / ASICs | ACTIVE | AVGO, MRVL | When hyperscalers buy commodity ASICs, not custom |
| Power / electricity | ACTIVE — lengthening | CEG, VRT, ETN, GEV | Transformer lead times drop below ~52 weeks |
| Data-center construction | ACTIVE — second-order | PWR, STRL, MTZ | When order books thin |
| Application / agent layer | **NOT A BOTTLENECK YET** | — | 88% of pilots fail; ROI unproven at scale |
| Inference / edge compute | Pre-bottleneck (2027+?) | TBD | When agents are in production and inference cost is the limit |

**Three positions — score every watchlist name into one:**

- **AT** — owns an active bottleneck node. Re-rating in progress. Pricing power + backlog + news flow aligned. The primary framework for evaluating these names is bottleneck duration and rent sustainability, NOT current P/S.
- **PRE** — positioned at the NEXT bottleneck but it has not activated. Optionality bet. Rich multiples here are pricing an arrival that may be 2–3 years out. Do not confuse "growing" with "bottleneck."
- **PAST** — owned a previous bottleneck now easing/commoditizing. Multiple compression risk as rent disappears. Requires a new catalyst or moat to hold the re-rating.

**Critical honesty rule:** The application layer is currently PRE — not AT. Software companies growing 30–80% YoY are benefiting from the buildout, not constraining it. The bottleneck shifts to the application layer only when: (a) agents are in wide production replacing real workflows, (b) the scarce resource is software/model capability rather than compute/power, and (c) enterprise ROI is publicly validated at scale. None of those are true yet.

## The baskets (default watchlist)

- **Structural beneficiaries:** NVDA (toll booth, but priced rich), TSMC (makes everyone's chips), power/electrical (VST, GEV, ETN, NEE, IPPs, nuclear/SMR), HBM/memory (MU, SK Hynix), networking/optical (AVGO, ANET, COHR), hyperscalers with distribution (MSFT, GOOGL, AMZN, META).
- **Second-order:** data-center REITs, construction, cooling/HVAC, industrial gases, copper.
- **Likely casualties:** pure capex-burners without monetization, leveraged "neocloud"/SPV data-center operators, thin-moat AI wrappers, labor-arbitrage services (BPO, call centers, low-end IT/content/translation), seat-priced legacy SaaS an agent can replicate, high-cost/stranded utilities, late infrastructure entrants building into a glut.

## The aftermath thesis (what a *real* correction sets up)

Carry this sequence — it's the durable, high-conviction part (railways → electricity → telecom/dark-fiber → dot-com all repeat it):

> **Build-out → glut → washout → cheap infrastructure → value captured downstream.**

Capex collapses fast; overbuilt compute/power sits idle and rental prices crater; bankruptcies + consolidation; then the *cheap leftover infrastructure subsidizes the next generation of applications* — and the eventual winners are often **deployers/consumers** of compute (incl. boring non-tech industries), not the builders. Cash-rich hyperscalers and TSMC usually consolidate their lead through the downturn.

## Pipeline

### Stage 0 — Set the frame
State the as-of date (absolute), the phase model, and that timing carries a wide error bar. Pull `ta_data.py global_news DATE` for macro context.

### Stage 1 — Read the indicators (live)
For each of the 12 canaries, gather the latest reading. Run `ta_macro_data.py` commands (`macro`, `valuation`, `software_canary`) for the hard data indicators. Use `WebSearch`/`WebFetch` for the qualitative ones (capex guidance, GPU spot prices, lead times, financing). Date-stamp and cite each. If a reading can't be found, mark it **Unknown** — don't guess.

### Stage 2 — Score the board
Produce a Green/Amber/Red table of all 12 indicators with the one-line evidence for each. You MUST respect the strict numerical thresholds defined above for the macro and valuation indicators. Weight #1 (hyperscaler capex) and #2 (GPU rentals) most heavily.

### Stage 2.5 — Map the Bottleneck Cascade
Using the cascade table above as the template, produce the current snapshot:
- For each node: update its status (EASING / ACTIVE / NOT YET) from the live indicator readings in Stage 1.
- Identify which node is the **primary active bottleneck** right now (the one with the tightest supply/demand and the clearest rent extraction).
- Identify which node is **next** — and be honest if it is not yet a bottleneck (do not promote PRE to AT).
- Score every ticker in the user's watchlist (or the default baskets) as **AT / PRE / PAST** with a one-line reason.
- Note any **shift signals** that are appearing in the data (e.g., GPU spot prices softening = GPU node moving from ACTIVE → EASING).

This section must appear in the written report before Survivor/Casualty. It is the primary context for interpreting every stock score.

### Stage 3 — Locate the phase + timeline
From the scored board, place the center of gravity on the phase map and give a **timeline window with its error bar**, distinguishing:
- a **sentiment correction** (sharp, ~15–35%, recoverable, can hit any quarter on a single bad print), from
- a **structural correction** (deep, prolonged, needs accumulated evidence — base case ~2027–2029, pushable to 2030+ if agent ROI lands, pull-able to 2026 on a shock).
State explicitly: position for the **sequence**, not the date.

### Stage 4 — Survivor vs. casualty
Score the baskets (and any user tickers) through the "what survives the correction" lens: balance-sheet strength, monetization vs. capex, moat vs. agent-replaceability, leverage/financing structure. Use `ta_data.py gather`/`fundamentals` for the hard numbers on named tickers.

### Stage 5 — Positioning implications
Translate into actionable, indicator-linked guidance (scale exposure to the canaries; the trap is being early/over-leveraged at a euphoric top). One rating per named ticker if asked: **Beneficiary / Neutral / At-risk**. Not a trade recommendation — a thesis map.

### Stage 6 — Persist
Write the report to `ai-cycle-reports/<DATE>_cycle.md` (repo-relative; create the dir if missing) so successive runs form a time series — capex guidance and GPU prices read across dates are themselves a signal. Start the file with a one-line **stance** (e.g. `STANCE: Phase 2→3, indicators mostly Amber, structural-correction base case 2027–2029`) so it parses at a glance.

Then, log the exact indicator colors and phase into the persistent CSV database by running:
```bash
python3 .claude/skills/trading-analysis/scripts/ta_memory.py log_cycle <DATE> \
  --phase "<CURRENT_PHASE>" \
  --score <RISK_SCORE_0_100> \
  --indicators <COLOR_1> <COLOR_2> ... <COLOR_12>
```
*(Pass exactly 12 `Green`, `Amber`, or `Red` values in order).*

## Output format

1. **Stance** up top: one line — current phase, net indicator color, correction window + error bar.
2. **Indicator scoreboard** — the 12-row Green/Amber/Red table with dated evidence.
3. **Bottleneck Cascade Map** — the cascade table (node / status / owners / shift signal) updated from live readings, followed by each watchlist ticker scored AT / PRE / PAST with one-line reason. This is the primary lens for infrastructure names — it supersedes P/S multiples as the re-rating frame.
4. **Phase + timeline** — where we are, sentiment-vs-structural distinction, the sequence to position for.
5. **Survivor / casualty** — two short lists (or scored watchlist), with the one-reason-each.
6. **Data caveat + disclaimer** — note any Unknown indicators / sources that returned nothing, and the standard not-financial-advice line.
7. **Idiot Investor Summary (Jensen's Take)** — A summary clause at the very end giving the true risk score 0-100 of the "current risk per AI cake". Explain the score in really simple, plain English (idiot-proof) but keep a SERIOUS and professional tone. Adopt Jensen Huang's perspective: frame the AI build-out as a massive "AI cake" (total addressable market/opportunity) where the shift to accelerated computing and "AI factories" is a mandatory industrial revolution. Do not use silly baking metaphors; simply explain the serious underlying infrastructure reality versus the macro noise.
8. **[HEDGE_CANDIDATES]** — A machine-readable JSON block containing 3-5 high-conviction short targets drawn from the Casualties list (e.g., leveraged neoclouds, over-valued wrappers). Format: ````json [ { "ticker": "...", "reason": "..." } ] ````. This will be ingested by the Portfolio Manager skill for pairs trades.

## Notes & failure modes
- Data deps for `ta_data.py`: `pip install -r .claude/skills/trading-analysis/scripts/requirements.txt` (no keys) if a `ModuleNotFoundError` appears.
- Web readings can be stale or paywalled — prefer primary sources (earnings calls/transcripts, IR capex slides) over secondary commentary, and always date-stamp. If you can't verify an indicator, mark it Unknown rather than inferring.
- The whole point is **repeatability**: same indicators, same baskets, every run, archived by date. Resist re-deriving the framework each time — read the latest `ai-cycle-reports/` entry first and report *what changed*.
