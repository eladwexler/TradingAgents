# eval/ Backtest Benchmark — SPY hurdle

_Generated 2026-06-20 20:52 · window 2024-06-20 → 2025-06-20 · 60/61 names priced_

> Hindsight-free: no LLM judgment, no forward knowledge in any signal. This is the **bar the platform must beat**, plus whether its price/trend factors had cross-sectional edge this window.

## 1. The bar (12-month buy-and-hold)

| Strategy | Return | Alpha vs SPY |
|---|---|---|
| SPY (the hurdle) | +10.4% | — |
| Equal-weight basket — raw mean | +55.5% | +45.2% |
| Equal-weight basket — **median name** | +28.9% | +18.5% |
| Equal-weight basket — winsorized mean (cap +300%) | +46.0% | +35.7% |

- **Hit-rate**: +58.6% of 58 names beat SPY over the year (coin-flip Brier null = 0.250).
- ⚠️ **Data-quality flag**: 1 name(s) show >+500% 12m returns — likely penny-stock / reverse-split / ticker-reuse artifacts, not investable outcomes. They inflate the raw mean; use the **median** and **winsorized** rows as the honest bar. Suspect: OKLO +520.4%.

## 2. Did the platform's factor families have edge? (12m horizon)

| Signal (point-in-time at entry) | IC (rank corr) | Top−Bottom quintile | Brier vs 0.5 null |
|---|---|---|---|
| mom_12m | -0.291 | -63.8% | 0.337 ❌ |
| mom_6m | -0.466 | -128.1% | 0.366 ❌ |
| dist_200dma | -0.420 | -130.2% | 0.355 ❌ |

_IC>0 = signal ranked winners above losers. Brier below the 0.5 null (✅) = the factor added information; ❌ = no better than a coin flip._

## 3. Robustness — monthly IC (63-day forward, 15 anchors)

| Signal | Mean IC | Std IC | % anchors IC>0 |
|---|---|---|---|
| mom_12m | -0.018 | 0.141 | +36.4% |
| mom_6m | 0.062 | 0.139 | +66.7% |
| dist_200dma | 0.029 | 0.149 | +69.2% |

_A factor with real edge shows a consistently positive mean IC and a high share of positive anchors. Near-zero / sign-flipping mean = no robust edge._

## 4. Per-name 12m return (extremes)

Best: OKLO +520.4%, IONQ +493.5%, PLTR +437.2%, AMPX +212.2%, CRDO +201.4%

Worst: AXTI -50.1%, SMCI -50.6%, OTLK -77.5%, CRML -78.5%, SLNH -90.4%

---
*Benchmark only. Establishes a baseline; it does not itself predict. Not financial advice.*