# eval/ Cycle-Timing Backtest — does the AI-cycle risk score lead?

_Generated 2026-06-20 21:03 · basket history 2019-11-29 → 2026-06-18 · 60 names_

> Tests ONLY the measurable canaries (extension, breadth_risk, momentum_heat, rates, credit_stress). Qualitative canaries + the narrative brains are NOT in this score and are untestable here. ~one cycle of data = low power: suggestive, not proof.

## 1. Does a high risk score precede weak forward returns?

| Forward window | Rank corr (risk → return) | Reads |
|---|---|---|
| 63 trading days | -0.496 | predictive ✅ |
| 126 trading days | -0.488 | predictive ✅ |

_Negative = the score was high before the basket fell (the canary led). Near-zero / positive = no predictive lead._

> ⚠️ **Power caveat:** forward windows overlap heavily (63-/126-day), so the effective independent sample is a handful of episodes — chiefly the 2022 rate-shock drawdown. A strong IC here can rest on **one or two events**; do not read it as a stable, repeatable edge.

## 2. Forward 63-day return by regime (point-in-time)

| Regime | N days | Mean fwd-63 return | % of windows negative |
|---|---|---|---|
| 🔴 Red (risk in top 20%) | 397 | -1.3% | +48.9% |
| 🟢 Green (risk in bottom 50%) | 610 | +22.0% | — |
| All days (base rate) | — | +12.2% | +27.7% |

_If the score leads, Red-regime forward returns are clearly worse than the base rate and negative more often._

## 3. Risk-managed timing vs buy-and-hold (the practical test)

| Strategy | CAGR | Vol | Sharpe | Max drawdown | % time invested |
|---|---|---|---|---|---|
| Risk-off when Red | +38.8% | +27.0% | 1.35 | -36.0% | +55.8% |
| Buy & hold basket | +64.2% | +36.8% | 1.53 | -45.8% | 100.0% |

_Timing 'works' only if it cuts max drawdown / lifts Sharpe WITHOUT giving back most of the CAGR. Most market-timing signals fail this — they exit late and miss the rebound._

---
*Benchmark only. Establishes whether the timing engine has any historical lead; it is not itself a forecast. Not financial advice.*