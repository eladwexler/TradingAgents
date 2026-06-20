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
- **🔬 X research shifts** — trends rising/falling/new in the ranking, and names flipping
  Bullish↔Mixed↔Bearish or moving most in net sentiment.

"Latest run" = the most recent decision date (±3 days for weekend spillover). Decision diffs
come from the dated `analyzed-stocks/` history (no extra storage); X-research diffs need a
prior snapshot, so `analyze_corpus.py` archives `index/research_history/<date>.json` each run
and the dashboard diffs current vs the most recent older snapshot (the Research tab also gets
inline ▲/▼/NEW trend deltas). On the first changes-enabled build the X section just says
"baseline saved — appears after the next refresh."

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
