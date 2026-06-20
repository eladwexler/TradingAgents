# eval/ Backtest Benchmark — SPY hurdle

_Generated 2026-06-20 20:41 · window 2025-06-20 → 2026-06-20 · 60/61 names priced_

> Hindsight-free: no LLM judgment, no forward knowledge in any signal. This is the **bar the platform must beat**, plus whether its price/trend factors had cross-sectional edge this window.

## 1. The bar (12-month buy-and-hold)

| Strategy | Return | Alpha vs SPY |
|---|---|---|
| SPY (the hurdle) | +27.0% | — |
| Equal-weight basket — raw mean | +286.0% | +259.0% |
| Equal-weight basket — **median name** | +112.2% | +85.2% |
| Equal-weight basket — winsorized mean (cap +300%) | +140.7% | +113.7% |

- **Hit-rate**: +70.0% of 60 names beat SPY over the year (coin-flip Brier null = 0.250).
- ⚠️ **Data-quality flag**: 8 name(s) show >+500% 12m returns — likely penny-stock / reverse-split / ticker-reuse artifacts, not investable outcomes. They inflate the raw mean; use the **median** and **winsorized** rows as the honest bar. Suspect: AXTI +4496.2%, BE +1412.2%, AEHR +934.1%, LITE +848.0%, MU +819.7%, CIFR +669.9%, AAOI +590.2%, HYLN +504.5%.

## 2. Did the platform's factor families have edge? (12m horizon)

| Signal (point-in-time at entry) | IC (rank corr) | Top−Bottom quintile | Brier vs 0.5 null |
|---|---|---|---|
| mom_12m | -0.150 | -449.4% | 0.321 ❌ |
| mom_6m | -0.329 | -158.7% | 0.345 ❌ |
| dist_200dma | -0.170 | -99.8% | 0.323 ❌ |

_IC>0 = signal ranked winners above losers. Brier below the 0.5 null (✅) = the factor added information; ❌ = no better than a coin flip._

## 3. Robustness — monthly IC (63-day forward, 15 anchors)

| Signal | Mean IC | Std IC | % anchors IC>0 |
|---|---|---|---|
| mom_12m | 0.109 | 0.147 | +90.9% |
| mom_6m | 0.097 | 0.209 | +66.7% |
| dist_200dma | 0.138 | 0.199 | +76.9% |

_A factor with real edge shows a consistently positive mean IC and a high share of positive anchors. Near-zero / sign-flipping mean = no robust edge._

## 4. Per-name 12m return (extremes)

Best: AXTI +4496.2%, BE +1412.2%, AEHR +934.1%, LITE +848.0%, MU +819.7%

Worst: SMCI -32.3%, CRWV -35.8%, IBIT -39.3%, NOW -51.1%, ZS -58.8%

---
*Benchmark only. Establishes a baseline; it does not itself predict. Not financial advice.*