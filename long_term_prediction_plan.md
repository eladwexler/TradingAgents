# Making TradingAgents Actually Predict: 12-Month+ Implementation Plan

> The system today is a **narrative machine** that produces institutional-sounding reports.
> This plan turns it into a **prediction machine** that constrains narrative with empirical base rates,
> forces the LLM to be honest about what it doesn't know, and — critically — builds a
> self-correcting feedback loop that gets better with each resolved forecast.

---

## The Core Problem (Why It Can't Predict Today)

The LLM picks numbers that "sound right." When Claude writes "base case +22% over 24 months,"
it's not computing — it's *narrating*. The three structural fixes:

1. **Anchor on base rates** — what *actually happens* to stocks with these metrics over 12 months?
2. **Track what changes** — earnings revision velocity is the #1 12-month predictor; the system ignores it
3. **Constrain the LLM** — hard quantitative rails that the narrative cannot override

---

## Layer 1: Quantitative Base-Rate Anchoring (The Foundation)

### What empirically predicts 12-month returns?

| Factor | 12-Month Predictive Power | Currently in System? |
|---|---|---|
| **Forward P/E percentile** (vs own history) | Strong — top decile underperforms by ~5%/yr | ❌ No history |
| **Earnings revision velocity** (3-month EPS estimate change) | Strongest single factor | ❌ Not tracked |
| **PEG ratio** | Moderate | ✅ Yes, but no base rate |
| **FCF yield** | Strong for profitable names | ✅ Yes, but no base rate |
| **Insider buying clusters** | Moderate-strong (buying > selling signal) | ✅ Raw data only |
| **Short interest / short ratio** | Weak alone, strong at extremes | ✅ In metrics.json |
| **Analyst target consensus** | Weak (lagging) | ✅ Yes |
| **Revenue growth rate** | Moderate (already priced in at high multiples) | ✅ Yes |
| **Macro regime** (rates + credit) | Moderate for multiples | ✅ Yes |

### Build: `scripts/base_rates.py`

A new script that answers: **"historically, what happens to stocks like this one?"**

```python
# scripts/base_rates.py
# For a given ticker, compute the empirical base-rate expected return
# based on its current factor profile vs historical distributions.
#
# Uses yfinance for current metrics + a static empirical lookup table
# derived from published academic research (Fama-French, AQR, etc.)
#
# Key outputs:
#   - P/E percentile vs own 5-year history → historical median reversion rate
#   - PEG bucket → base-rate 12mo return for that PEG range  
#   - Revenue growth + margin profile → which growth bucket it falls in
#   - Sector + market-cap → base-rate for similar names
#   - COMPOSITE BASE RATE: the empirical "what usually happens" anchor
```

**What it produces** (injected into Stage 6 before the LLM forecasts):

```
## BASE RATE ANCHOR — NVDA
Forward P/E: 16.4x → percentile 23 of own 5yr range (cheap vs self)
PEG: 0.65 → base rate: stocks with PEG 0.5-1.0 return +18-25% over 12mo (median +21%)
FCF yield: 3.2% → base rate: positive, top quartile for growth
Revenue growth: +81% → base rate: names growing >50% mean-revert to +25-35% within 2yr
Sector P/E rank: 2nd cheapest of AI-infra basket (AVGO 24x, MRVL 42x, AMD 28x)
COMPOSITE BASE RATE: +15-25% (12mo), anchored on PEG + growth deceleration
⚠ BASE RATE CEILING: at this revenue scale ($130B+), >30% growth sustained >2yr = top 1% historically
```

### How it wires in:

Add to `trading-analysis/SKILL.md` Stage 6:

> **Before emitting the forecast, consult the base-rate anchor.** Your bear/base/bull
> scenarios must be *consistent* with the base rate — if the base rate says +15-25% and
> your base case says +45%, you must explicitly justify the deviation with a named catalyst
> that isn't already in consensus. **The base rate is the gravitational center; your forecast
> is an argued deviation from it.**

### Implementation:

```
scripts/base_rates.py TICKER
  → reads metrics.json + yfinance history
  → outputs a structured BASE_RATE block
  → saved to analyzed-stocks/TICKER/base_rate.json (for dashboard)
```

> [!IMPORTANT]
> This is the single highest-impact change. It turns the LLM from "pick a number" to "deviate from the empirical anchor and explain why." Most forecasting accuracy gains come from better anchoring, not better analysis.

---

## Layer 2: Earnings Revision Velocity Tracker

### Why this matters most

Academic research (Hawkins & Bernstein, Rendleman, Chan et al.) consistently shows:
- **Stocks with rising EPS estimates outperform by 4-8% over the next 6 months**
- **Stocks with falling EPS estimates underperform by 3-6%**
- This is the single strongest freely-available alpha signal for 3-12 month horizons
- The current system fetches consensus but **never tracks how consensus is changing**

### Build: `scripts/revision_tracker.py`

```python
# scripts/revision_tracker.py
# Tracks consensus EPS estimate changes over time.
# Runs daily/weekly via update-all, snapshots the consensus,
# and computes revision velocity.
#
# Schema per ticker per date:
#   { ticker, date, fwd_eps, fwd_rev, target_mean, n_analysts,
#     eps_1mo_chg, eps_3mo_chg, rev_1mo_chg, rev_3mo_chg,
#     target_1mo_chg, revision_signal }
#
# Revision signal:
#   ACCELERATING  = EPS estimates rising >2% in 3 months
#   STABLE        = EPS estimates flat (±2%)
#   DECELERATING  = EPS estimates falling >2% in 3 months
#   COLLAPSING    = EPS estimates falling >10% in 3 months (red flag)
```

### Data source:

Already available in `ta_data.py forward TICKER`:
```
EPS: trailing 6.53 | forward 12.73 (implied +94.9% fwd EPS growth)
Consensus EPS growth: current FY +87.9% | next FY +42.0%
```

**The trick:** snapshot this weekly so you can compute the *delta*. Forward EPS of 12.73 today
vs 12.50 four weeks ago = **+1.8% revision** = mild positive. Forward EPS of 12.73 today vs
14.00 four weeks ago = **-9.1% revision** = warning signal.

### Storage:

```
~/.tradingagents/memory/revisions/
  NVDA.csv    # date, fwd_eps, fwd_rev, target_mean, n_analysts
  AVGO.csv
  ...
```

### Wire into `update-all`:

Add as step 1.5 (after brains, before cycle):

```bash
# In update_all.sh, after brain refresh:
echo "── Revision tracker ──"
python3 scripts/revision_tracker.py        # snapshots all tracked tickers
python3 scripts/revision_tracker.py --report  # prints movers (>5% revision in 3mo)
```

### Wire into `trading-analysis` Stage 1.4 (Fundamentals):

> **Consult the revision tracker.** Run `python3 scripts/revision_tracker.py TICKER --signal`.
> The revision velocity (ACCELERATING / STABLE / DECELERATING / COLLAPSING) is a **hard input**
> to the Expected-Return Model:
> - COLLAPSING → **force bear-case probability up by 10%**, cap P(beats benchmark) at 0.40
> - DECELERATING → carry as a named risk; do not assign P(beat) > 0.60 without explicit justification
> - ACCELERATING → may raise P(beat) by up to 0.10, but only if valuation isn't already extreme

> [!TIP]
> This is the only signal that gives you a genuine near-term informational edge over "buy the consensus." The market underreacts to revision velocity for ~3 months.

---

## Layer 3: Valuation Regime Detector (Hard Kill Switches)

### The problem:

The system can report Mag7 at 42x forward P/E and still produce "Buy" for individual names
because the macro-adjusted downgrade is a soft LLM judgment, not a hard constraint.

### Build: `scripts/valuation_regime.py`

Hard, deterministic rules that **cannot** be overridden by the LLM:

```python
# scripts/valuation_regime.py
# Deterministic valuation guardrails for the PM stage.
# These are NOT inputs to the debate — they are POST-DEBATE constraints.

HARD_RULES = {
    # Rule 1: P/E vs own history
    "pe_ceiling": {
        "condition": "forward_pe > 95th percentile of own 5yr range",
        "action": "CAP rating at Hold. Cannot issue Buy/Overweight.",
        "reason": "Priced for perfection — historically this percentile underperforms"
    },
    
    # Rule 2: PEG extreme
    "peg_extreme": {
        "condition": "PEG > 3.0 AND revenue_growth < 30%",
        "action": "CAP rating at Hold. Flag 'growth premium unjustified'",
        "reason": "Paying 3x for sub-30% growth = paying for a miracle"
    },
    
    # Rule 3: Macro override
    "macro_kill": {
        "condition": "ai_cycle risk_score >= 80 AND ticker valuation == 'extreme'",
        "action": "FORCE Underweight/Sell. No Buy/Overweight/Hold possible.",
        "reason": "Late-cycle + extreme valuation = the setup that destroys capital"
    },
    
    # Rule 4: Revision collapse + expensive
    "revision_collapse": {
        "condition": "revision_signal == 'COLLAPSING' AND forward_pe > sector_median",
        "action": "FORCE Underweight. Flag 'deteriorating fundamentals at premium valuation'",
        "reason": "Falling estimates + premium valuation = the fastest way to lose money"
    },
    
    # Rule 5: Base rate override
    "base_rate_conflict": {
        "condition": "LLM base-case return > base_rate_ceiling + 15%",
        "action": "REJECT forecast. Force LLM to re-derive with explicit justification.",
        "reason": "Forecast deviates too far from what empirically happens to similar stocks"
    }
}
```

### Wire into `trading-analysis` Stage 6:

After the PM produces the forecast, run `valuation_regime.py TICKER` and apply any triggered
rules as **post-decision constraints** — the LLM states the constraint, explains why it's
binding, and adjusts. The decision file records "VALUATION CONSTRAINT APPLIED: [rule]".

---

## Layer 4: The Anti-Brain (Contrarian Secular Lens)

### The problem:

Jensen, Leopold, Jordi, Gavin are all AI bulls. The Combined Strategic Verdict structurally
leans ALIGNED for any AI stock. During a bubble, this is the worst possible bias.

### Build: A "Contrarian Brain" or "Bear Brain"

Two options (ranked by effort):

#### Option A: Historical Bubble Parallels (Low effort, high value)

Create a static corpus of **bust post-mortems** — the Cisco 2000 case study, the Nortel
collapse, the 2015 energy MLP blowup, the 2021 SPAC/ARK/Cathie Wood drawdown, the telecom
overbuilding bust. Index them with BM25 just like the other brains.

```
python3 .claude/skills/trading-analysis/scripts/bubble_brain.py \
    "<company> <products> <thesis>" \
    --parallel "which historical bust does this most resemble?" \
    --k 5
```

**Verdict options:** Repeating history / Possible parallel / No parallel / Insufficient evidence

This forces the system to ask: *"Is this Cisco in 1999?"* every time it's bullish on an
expensive AI name. The parallels are uncomfortable and useful.

#### Option B: Structural Bear Case Generator (Medium effort)

Instead of another BM25 brain, add a **mandatory bear scenario** that the LLM must write
*before* seeing any bullish inputs. Force it to answer:

> 1. What is the closest historical analogy to this stock at this valuation?
> 2. In that analogy, what was the drawdown from the peak?
> 3. What would have to go wrong for this name to be worth 50% less in 12 months?
> 4. Is the answer "literally nothing" — meaning you're pricing in perfection?

Wire this as **Stage 1.5** (after data gathering, before the analyst reports). The bear
case sets the floor; the bull case must then exceed it by enough to justify the risk.

---

## Layer 5: Portfolio-Level Risk and Position Sizing

### The problem:

Each ticker analysis is independent. There's no concept of "I'm already 40% in AI-infra
names and adding more is correlated risk, not diversification."

### Build: `scripts/portfolio_risk.py`

```python
# scripts/portfolio_risk.py
# Reads all current Buy/Overweight decisions from the memory log
# and computes portfolio-level statistics:
#
# 1. Sector concentration: % of active Buys in AI-infra vs other sectors
# 2. Correlation matrix: realized 90-day correlation between active names
# 3. Beta exposure: portfolio-weighted beta (are you 2x levered to SOXX?)
# 4. Drawdown exposure: if SOXX drops 30%, what's the modeled portfolio impact?
# 5. Valuation distribution: what % of active Buys are "extreme" valuation?
#
# Outputs a PORTFOLIO RISK CONTEXT block injected into every new analysis.
```

### Wire into `trading-analysis` Stage 0:

> **Before analyzing a new ticker, consult portfolio risk.** Run
> `python3 scripts/portfolio_risk.py --context`. If the portfolio is already >60%
> concentrated in AI-infra with an average beta >1.5, **the PM must size any new
> AI-infra Buy at 50% of normal** and state the concentration risk.

### Wire into `trading-analysis` Stage 6:

> **Position sizing must reflect portfolio context.** A name that would be a full Buy
> in isolation may only be an Overweight in the portfolio context due to correlation
> and concentration. The PM must state the portfolio-adjusted size.

---

## Layer 6: Forced Re-Analysis Cadence + Drift Detection

### The problem:

190 decisions, most never revisited. A 12-month prediction is useless if you don't check
whether the thesis is still intact at month 3, 6, and 9.

### Build: Scheduled re-analysis triggers in `update-all`

```python
# In update_all.sh, add after calibration:
echo "── Re-analysis triggers ──"
python3 scripts/reanalysis_triggers.py
```

```python
# scripts/reanalysis_triggers.py
# Identifies names that MUST be re-analyzed:
#
# MANDATORY triggers:
#   1. Earnings reported since last analysis → fundamentals changed
#   2. >20% price move since analysis → thesis may be broken/validated
#   3. Revision signal flipped (e.g., ACCELERATING → DECELERATING)
#   4. >90 days since last analysis → stale
#   5. Macro cycle risk score changed by >15 points
#
# Outputs a prioritized re-analysis queue.
```

### The 3-6-9-12 checkpoint system:

For every logged 12-month prediction, auto-schedule checkpoints:

| Month | Action |
|---|---|
| 3 | Interim mark + revision check. If thesis broken → early resolve |
| 6 | Full re-analysis. Update bear/base/bull. Adjust P(beat) |
| 9 | Interim mark. Flag for resolution prep |
| 12 | Resolve with realized returns + reflection + error-class |

This is partially built (`ta_memory.py watch`) but not systematic. Make it a hard
requirement in `update-all`: any call that has passed a checkpoint date without a
re-analysis gets flagged in the morning report.

---

## Layer 7: Universe Expansion (Escape the Echo Chamber)

### The problem:

90 tickers, nearly all AI/semi/infra. This isn't prediction — it's a thematic bet.

### The fix:

Add **10-15 non-AI names** across sectors as a **control group**:

| Sector | Names | Why |
|---|---|---|
| Consumer staples | PG, KO, COST | Low-beta, steady compounders — tests if the system can identify "hold" |
| Healthcare | UNH, LLY, ISRG | Different growth drivers — tests sector-agnostic analysis |
| Financials | JPM, V, MA | Rate-sensitive — tests macro integration |
| Energy | XOM, NEE | Cyclical — tests valuation discipline |
| Non-AI tech | ORCL, ADBE | Software with AI optionality — tests nuance |

**Why this matters:** If the system says "Buy" for 85% of names, it's not predicting — it's
expressing a bias. Adding names where the correct answer is often "Hold" or "Underweight"
tests whether the system can actually discriminate.

---

## Implementation Priority (What to Build First)

| Priority | Layer | Effort | Impact on 12mo Prediction |
|---|---|---|---|
| 🔴 **1** | Layer 2: Revision tracker | 1-2 days | **Highest** — the only freely-available alpha signal |
| 🔴 **2** | Layer 1: Base-rate anchoring | 2-3 days | **Very high** — prevents LLM fantasy numbers |
| 🟡 **3** | Layer 3: Valuation hard rails | 1 day | **High** — prevents buying tops |
| 🟡 **4** | Layer 6: Re-analysis cadence | 1 day | **High** — makes predictions living documents |
| 🟢 **5** | Layer 4: Anti-brain / bubble parallels | 2-3 days | **Medium** — counterbalances the AI-bull bias |
| 🟢 **6** | Layer 5: Portfolio risk | 1-2 days | **Medium** — prevents correlated blowups |
| 🟢 **7** | Layer 7: Universe expansion | Ongoing | **Medium** — tests the system's discrimination ability |

---

## What Success Looks Like (12 Months From Now)

If implemented, you should be able to answer these questions in June 2027:

1. **Brier score < 0.20?** — better than coin-flip calibration
2. **Bullish ratings outperform bearish ratings?** — the rating ladder works monotonically  
3. **Base-rate-constrained forecasts more accurate than unconstrained?** — the anchor helps
4. **Revision velocity signal adds alpha?** — ACCELERATING names beat DECELERATING by >5%
5. **Hard rails prevented any "buy at the top" disasters?** — valuation regime detector worked
6. **Hit rate >55% with mean alpha >3% (annualized)?** — genuine edge, not luck

> [!WARNING]
> Even with all of this, the honest expectation is **modest edge at best** — maybe 55-60%
> hit rate, 2-4% annualized alpha, with wide confidence intervals. That's what good
> quantitative shops achieve with vastly more data and compute. But it would be *real* edge,
> not narrative. The current system has a 67% hit rate over n=3 resolved calls — statistically
> indistinguishable from random. Getting to n=30+ with systematic factor tracking is the only
> path to knowing whether the framework works.

---

## The Honest Bottom Line

No amount of engineering turns an LLM into a crystal ball. But you can turn it from a
**narrative machine** (picks numbers that sound good) into a **constrained analyst**
(deviates from base rates only when it has a named, testable reason). The difference:

| Today | After Implementation |
|---|---|
| "Base case +22%" (from vibes) | "Base case +22% vs base rate of +15%, deviation justified by revision velocity +8% and PEG 0.65" |
| No revisiting | 3-6-9-12 month checkpoints with drift detection |
| All brains agree → confident | All brains agree → check if that's a bubble signal |
| Rating reflects the LLM's narrative | Rating constrained by valuation regime + portfolio risk |
| N=3 resolved, no Brier score | N=30+ resolved, Brier < 0.20 is the goal |

*The system doesn't need to predict the future. It needs to predict the future slightly better than "buy SPY and forget it." That's the bar, and it's much harder than it sounds.*
