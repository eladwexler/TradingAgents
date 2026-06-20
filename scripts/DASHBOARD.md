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
