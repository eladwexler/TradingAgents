# Trading-Analysis Verdict Dashboard

Renders every `/trading-analysis` verdict into a browsable HTML site: one detail page
per decision + an index with best-call dashboards.

## Build / refresh

```bash
python3 scripts/build_dashboard.py      # regenerate everything into dashboard/
```

Pure stdlib, no deps, idempotent. Then open **`dashboard/index.html`** in a browser.
Re-run it after every new verdict (the `/trading-analysis` skill does this in Stage 7).

## What it reads

| Source | Provides |
|---|---|
| `~/.tradingagents/memory/trading_memory.md` (`$TRADINGAGENTS_MEMORY_LOG_PATH`) | the uniform spine — rating, pending/resolved status, `P=`(beat) probability, horizon, realized raw/alpha once matured |
| `analyzed-stocks/<TICKER>/<DATE>_decision.md` | richer detail — BASE/MACRO proposals, forecast table (12/24/36mo), verdict-for-new-investors, Jensen / Leopold / Combined verdicts, full body |
| `metrics.json` (next to the decision log, written by `scripts/fetch_metrics.py`) | per-ticker market metrics — valuation (fwd P/E, PEG, EV/Sales, EV/EBITDA), profitability (FCF yield, margins, Rule-of-40), liquidity/risk (beta, short %, avg $ vol), next-earnings + analyst upside (powers the **Financials** tab + the detail **Key metrics** box) |

A decision in either source shows up; missing fields degrade gracefully (older
freeform decision files still render — they just have fewer badges).

## What it produces (into `dashboard/`)

- **`index.html`** — a collapsible plain-words **legend**; track-record cards (count,
  pending, resolved hit-rate, mean alpha, stance-changes); five **best-decision
  leaderboards** (highest-conviction longs by P, highest expected 24mo return, highest
  P(beat), strongest secular fit, resolved realized-alpha); a **Decision trends** grid
  (per multiply-analyzed stock: an inline-SVG sparkline of the rating trajectory + P(beat)
  with a Strengthening/Stable/Weakening/Whipsaw read); a **By stock** rollup (times
  analyzed + latest Jensen/Leopold/Combined); and a **sortable/filterable table** of all
  verdicts. Click any ticker for its detail page.
- **`<TICKER>_<DATE>.html`** — one page per decision: verdict badges, the forecast
  table, the **Decision-trend chart + conclusion** for that ticker, the new-investor
  callout, and the full rendered decision markdown.
- **`style.css`** — shared dark theme.

### Buckets (generic categories)
Each ticker's fine-grained `AI_DOMAIN` (e.g. "Optical interconnect & networking")
rolls up into a broad **bucket** (`BUCKET` / `BUCKET_ORDER` in `build_dashboard.py`):
Compute, Custom silicon (ASIC), Networking & connectivity, Photonics / optical,
Memory, Semiconductor supply chain, Systems & servers, Cloud & datacenter capacity,
Hyperscalers, Power & energy, Materials & storage, Software & applications,
Cybersecurity, Physical AI & robotics, Quantum computing, Crypto / AI-macro,
Other / outside AI. The **AI-trend domains** tab groups the domain cards under
bucket headers; the filter dropdown is bucket-grouped with an "▸ All <bucket>"
entry per group; and the By-domain, By-stock and All-verdicts tables each carry a
sortable **Bucket** column. To add/retag a name: set its `AI_DOMAIN`, and (if it's a
new micro-domain) map that micro-domain in `BUCKET`.

### Financials tab (per-ticker market metrics)
The **📐 Financials** tab is a sortable table of the financial data the per-decision
markdown only carried in prose: valuation (forward P/E, PEG, **EV/Sales**, **EV/EBITDA**,
P/S), profitability (**FCF yield**, gross margin, **Rule-of-40** = rev-growth + FCF-margin),
risk/liquidity (beta, **short % of float**, avg $ volume, 52-week range position) and the
next-earnings date + analyst implied upside. The same fields render as a **Key metrics**
grid on every detail page (`{{METRICS_BOX}}` in `decision.html`).

Source: a cache `metrics.json` next to the decision log
(`$TRADINGAGENTS_MEMORY_LOG_PATH` dir), produced by **`scripts/fetch_metrics.py`** (yfinance;
one row per tracked ticker, derived fields computed). This mirrors the `watch →
under_pressure.json → dashboard reads it` pattern: the **fetcher** does the network work and
the **dashboard build stays offline-free** (reads the cache only; absent → the tab explains
how to generate it; a per-ticker fetch error keeps the prior cached row). `update_all.sh`
runs `fetch_metrics.py` right before the build. Data quality is yfinance's — an occasional
bad field for a thin/foreign-resolving ticker is isolated to that row.

### LLM export (briefing for an external model)
**`scripts/export_llm.py`** writes a self-contained briefing another LLM can read to
recommend a portfolio strategy: `dashboard/export/portfolio_llm.md` (primary) +
`portfolio.json` (machine-precise). It reuses this builder's parsers, and bundles a TASK
preamble, the macro phase (latest `ai-cycle-reports`), the calibration track-record, bucket
**concentration**, a watchlist table, and per-name notes. `update_all.sh` runs it right after
the dashboard build. Flags: `--full` (every dated decision), `--format md|json|both`,
`--stdout`.

### Research tab (X Brain)
The **Research** tab reads `$X_HOME/index/research.json` (default
`/home/ewexler/projects/x-brain/index/research.json`, produced by the x-brain project's
`work/analyze_corpus.py`) and renders two keyless FinTwit/AI views: **most-talked AI
trends** (mention-volume bars) and **most-bullish stocks** (buzz + a bull-vs-bear lexicon
lean, sortable). If the file is absent the tab shows how to generate it. Each verdict table
also carries an **X** column (the per-ticker `X Brain Verdict:` crowd-sentiment overlay,
parsed from the decision files); it is a sentiment overlay and is **not** part of the
Combined verdict.

### Changes tab (week-over-week / latest-run diff)
The **🔔 Changes** tab (with a header count badge) flags what moved in the **newest run vs.
the previous one** — built for a weekly (or daily) cadence so you don't re-read every row:
- **🆕 New names** — tickers analyzed in the latest batch with no prior decision on record.
- **🔀 Rating & verdict flips** — rating, Combined Strategic Verdict, or any of the 5 brain
  verdicts (Jensen/Leopold/Jordi/Gavin/X) changing, shown old→new. Only counts when *both*
  sides exist (newly-added coverage isn't a "flip").
- **📈 Forecast metric moves** — P(beat) (±0.03), Exp 24mo (±3pp), Priority (±5) with ▲/▼.
- **📐 Financials moves** — week-over-week shifts in the market metrics: valuation re-rating
  (forward P/E ±12%/±1.5pts, EV/Sales ±15%), **short-interest** spikes (±2pp of float),
  **FCF-yield** shifts (±1pp), and analyst-upside changes (±5pp), sorted by magnitude with ▲/▼.
- **🔬 X research shifts** — trends rising/falling/new in the ranking, and names flipping
  Bullish↔Mixed↔Bearish or moving most in net sentiment.

"Latest run" = the most recent decision date (±3 days for weekend spillover). Decision diffs
come from the dated `analyzed-stocks/` history (no extra storage); the **X-research** and
**Financials** diffs need a prior snapshot, so `analyze_corpus.py` archives
`index/research_history/<date>.json` and `fetch_metrics.py` archives
`metrics_history/<date>.json` (next to the decision log) each run, and the dashboard diffs
current vs the most recent older snapshot. On the first run after enabling each, the section
just says "baseline saved — appears after the next refresh."

### Under-pressure flag (open calls going wrong, interim)
The 🔔 Changes tab leads with an **⚠️ Open calls under pressure** section (+ a header badge)
listing *pending* forecasts whose interim mark has drifted against the thesis — a BUY lagging
its benchmark, a bearish call being run over, or a Hold that moved a lot. It's a re-analyze
worklist, surfaced *before* the horizon matures. Source: `ta_memory.py watch` computes the
marks (yfinance) and writes `under_pressure.json` next to the memory log; the dashboard only
*reads* that cache, so the build stays network-free. `update_all.sh` runs `watch` right before
the dashboard build; thresholds are tunable (`--alpha-threshold`, `--raw-threshold`,
`--min-days`).

### Reversals tab (act-on-it signals)
The **🔄 Reversals** tab isolates the subset of rating flips that **crossed the neutral line**
between bullish (Buy/Overweight) and bearish (Sell/Underweight) since the previous run — the
"flip your position" calls — split into **🟢 Turned bullish** (open/add candidates) and
**🔴 Turned bearish** (trim/exit candidates). Detection: `rating_score(prev)*rating_score(cur) < 0`
(both nonzero, opposite sign), so e.g. Underweight→Overweight or Sell→Buy qualify, but
Hold→Buy (mild upgrade) does not — those stay in the 🔔 Changes tab (where reversals are also
marked with a 🔄). A purple **🔄 N reversals** badge appears in the header.

### Decision trends (consistency check)
For any stock analyzed 2+ times, the engine's rating is scored (Buy +2 … Sell −2) and
plotted across runs. A change between consecutive runs is a **break** (ring on the chart);
the trajectory is summarized as **Strengthening** (net upgrade — bullish read corroborated),
**Weakening** (net downgrade — discount the bull case), **Whipsaw** (up *and* down — low
conviction, treat the latest call as tentative), or **Stable** (held — consistent, not
noise). This is surfaced on the dashboard and each detail page and is meant as a
*consistency check on the call* — it does not override the forecast numbers.

## Templates (editable)

The HTML lives in `scripts/templates/` and is filled by the generator with `{{TOKENS}}`:

- `decision.html` — the single-verdict page template (the canonical "verdict → HTML").
- `index.html` — the index + dashboards shell (with vanilla-JS sort/filter).
- `style.css` — styling, copied into `dashboard/` verbatim.

Edit a template, re-run the builder — no Python changes needed for layout tweaks.

## Notes

- `dashboard/` is generated output (git-ignored). Treat it as a build artifact; rebuild
  rather than hand-editing.
- P(beat) prefers the logged `P=` (the Brier-scored number); falls back to the 24mo
  forecast-table cell. Expected-return / target come from the 24mo forecast row.
- Best-call leaderboards use the **latest** decision per ticker; the full table shows
  every dated verdict.
