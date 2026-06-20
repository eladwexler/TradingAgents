# `eval/` — Backtest Benchmark (isolated)

A self-contained baseline that answers the question the live platform **cannot yet
answer**: over the trailing 12 months, *what was the bar*, and did the price/trend
factor families the agents rely on have any cross-sectional edge?

It exists because every live forecast is a 24-month call logged in June 2026 — none
have matured, so there is nothing to score yet. This harness gives a real number
**now**, against history, instead of waiting until 2028.

## What it is NOT

- **Not a re-run of the agents.** Re-judging a stock as of 12 months ago is
  contaminated by hindsight — I already know how it played out. That number would be
  worthless. So this harness uses only **mechanical, deterministic, point-in-time
  signals** and naive baselines.
- **Not a predictor.** It establishes a baseline/bar. It does not itself forecast.

## Lookahead-bias guardrails (the whole point)

1. **Signals see only the past.** Every signal in `signals.py` is computed from
   closes *up to and including* its as-of date. Nothing reads a future price.
2. **No live fundamentals.** Valuation factors are deliberately omitted — keyless
   point-in-time fundamentals don't exist, and using *today's* P/E as of a past date
   would be lookahead. Only price/trend signals (momentum, distance-from-200dma) are
   scored.
3. **Names only from the live tree.** `universe.py` reads the *subdirectory names*
   under `analyzed-stocks/` — never the decision content (which encodes current
   theses and would leak).
4. **Robustness over one lucky date.** Headline = a single 12-month hold; section 3
   re-measures signal IC at ~12 monthly anchors with a fixed short forward horizon.

## Isolation (does not pollute the live analysis)

- Everything lives under `eval/`. Output goes **only** to `eval/results/`.
- It **never** writes to `~/.tradingagents/`, `analyzed-stocks/`, `dashboard/`, or
  `metrics.json`, and no live script imports from `eval/`.
- `data.py` is a standalone keyless yfinance wrapper with **zero** imports from the
  `tradingagents` package or the skill scripts. Prices cache to `eval/.price_cache/`
  (gitignored).

## How the metrics read

| Metric | Meaning | Good looks like |
|---|---|---|
| Hit-rate | % of names that beat SPY over the year | n/a — descriptive |
| **IC** (rank corr) | did the signal rank winners above losers? | consistently > 0 |
| Top−bottom quintile | spread between best- and worst-signal names | large & positive |
| **Brier vs 0.5 null** | is signal→P(beat) better than a coin flip? | **below** the null |
| Mean IC (monthly) | robustness across start dates | positive, high % positive |

A factor only has *edge* if IC is consistently positive **and** its Brier beats the
0.5 null. A negative/sign-flipping IC means the factor anti-predicted in this window.

## Run

```bash
python3 eval/run_backtest.py                 # uses eval/config.yaml
python3 eval/run_backtest.py --config <path>
```

Outputs: `eval/results/scorecard.md` (human) and `scorecard.json` (machine).

## Reading the current result (caveats)

- The universe is ~60 AI-capex names in a single, strong AI-bull regime — so the
  basket and hit-rate are **regime-specific**, not a general edge.
- A handful of names show >+500% returns (penny-stock / reverse-split / ticker-reuse
  artifacts). They inflate the raw mean; the **median** and **winsorized** rows are
  the honest bar. The data-quality flag in the scorecard lists them.
- Over this particular 12m window the 12m-momentum/trend signals **anti-predicted**
  (negative IC) because the biggest winners were beaten-down mean-reverters — yet the
  shorter-horizon monthly IC was positive. That tension is a real finding, not a bug:
  it shows how horizon- and regime-dependent these factors are.

## Extending

- Add signals in `signals.py` (keep them strictly point-in-time) and list them in
  `SIGNAL_NAMES`.
- Tune the window / anchors / cap in `config.yaml`.
- To benchmark a *real* point-in-time fundamental factor, add a vendor with
  historical fundamentals to `data.py` — do **not** use current snapshots.
