# Investing Plan — Index

Actionable positioning hub. Status as of **2026-06-12**. Starting point: **no existing holdings** in these names (initiation plans).

This folder holds the *actionable plans*. The full multi-agent analyses (evidence) live in `analyzed-stocks/<TICKER>/<date>_decision.md`; the macro backdrop lives in `ai-cycle-reports/`. The machine-readable decision log is `~/.tradingagents/memory/trading_memory.md` (pending entries resolve with realized return).

> Research scaffold only — not financial, investment, or trading advice.

## Active plans

| Plan | Names | Stance | Doc |
|---|---|---|---|
| AI-interconnect sleeve | MRVL, CRDO | Initiate, staged; treat as ONE correlated bet (don't chase spikes) | [mrvl-crdo-sleeve.md](mrvl-crdo-sleeve.md) |
| AI-neocloud satellite | NBIS | Small speculative starter; keep separate from & smaller than the sleeve | [nbis-starter.md](nbis-starter.md) |

## Quick entry reference (levels from verified 2026-06-12 snapshots)

| Name | Last close | Starter zone | Core add | Value add | Stop / invalidation |
|---|---:|---|---|---|---|
| MRVL | $280.71 | $255–265 (or small now) | — | $225–235 | < $179.5 (50-SMA) |
| CRDO | $264.76 | $225–232 (or small now) | — | $208–215 | < $182.3 (50-SMA) |
| NBIS | $222.24 | $215–225 | $200–210 | $182–190 | < $180 (50-SMA) |

## Portfolio rules
- **MRVL + CRDO = one sleeve.** Same interconnect-capex driver, high beta (2.28 / 3.23), moved together. Size the combined sleeve to ~1.3–1.5× a single-name conviction position, NOT 2×. Intra-sleeve tilt ~55% CRDO / 45% MRVL.
- **NBIS is a separate, smaller satellite.** Neocloud (capex *spender*/GPU buyer, peer to CRWV); correlated to AI-capex broadly but a distinct factor and the highest-risk name (cash-burn, dilution). No leverage — pre-accept a secondary/dilution gap.
- **Shared tripwire:** any hyperscaler capex guide-down → trim the whole AI-capex complex.

## Open items
- Convert tranche %s → exact share/dollar counts once a sleeve target (% of portfolio or $) is provided.
- Decide **starter-now vs pullback-only** for MRVL/CRDO.
- MRVL & NBIS both have a **June 22** index-inclusion catalyst (S&P 500 / Nasdaq-100) — don't rush adds before it; sell-the-news risk.

## Underlying analyses
- MRVL: [`analyzed-stocks/MRVL/2026-06-12_decision.md`](../analyzed-stocks/MRVL/2026-06-12_decision.md) (prior: 2026-06-06)
- CRDO: [`analyzed-stocks/CRDO/2026-06-12_decision.md`](../analyzed-stocks/CRDO/2026-06-12_decision.md) (prior: 2026-06-06, 2026-06-08)
- NBIS: [`analyzed-stocks/NBIS/2026-06-12_decision.md`](../analyzed-stocks/NBIS/2026-06-12_decision.md) (prior 2026-06-06 — not yet reconciled)
- Macro: [`ai-cycle-reports/2026-06-08_cycle.md`](../ai-cycle-reports/2026-06-08_cycle.md)
