# Proposal — Learning, Admitting Mistakes & Telling Signal from Coincidence

> **Status: PROPOSAL ONLY — not implemented.** A design for how `/trading-analysis` should
> recognise when it was wrong, learn from it *without* overfitting to luck, and display that
> honestly. Scoped to the existing pieces: `ta_memory.py` (`recall` / `log` / `pending` /
> `returns` / `resolve` / `score`), `build_dashboard.py`, the decision files in
> `analyzed-stocks/`, and the macro phase from `/ai-cycle-watch`.

## 0. The one-paragraph thesis
The loop already *can* learn — forecasts are pre-registered with `P(beat)` + horizon, `resolve`
records realized alpha + a reflection, `score` measures Brier/hit-rate, and `recall` feeds
lessons forward. The gaps: it only reckons with a call **at maturity**, the "admission" is
**unstructured prose**, measured bias isn't **fed back as a number**, and the dashboard never
makes wrongness **accountable**. The deeper risk is **mistaking a coincidence for a lesson** —
so the core of this proposal is a *lesson lifecycle* that keeps unproven lessons out of the
forecast math until they earn their place.

---

## 1. A call can be "wrong" at three moments — catch each
1. **At maturity** (horizon elapsed): resolved with negative alpha / wrong direction → a true
   Brier miss. *Handled today, but quietly.*
2. **Interim** (before maturity): e.g. a BUY down 30% on a thesis-invalidating event. Today
   `ta_memory returns` can mark-to-market, but nothing **flags** "this open call is going wrong."
3. **Self-contradiction**: the engine reverses itself (the 🔄 Reversals tab) — implying the
   *prior* call was likely wrong, but we never say so or explain why.

---

## 2. ADMIT — a structured post-mortem, not free text
Capture, at `resolve` (and on reversal), an **error taxonomy** alongside the prose:

| Class | Meaning | What to change |
|---|---|---|
| **Bad luck** | unforecastable shock; process was sound | nothing — *do not learn from this one* |
| **Thesis error** | mis-judged fundamentals / valuation / moat | the analysis |
| **Calibration error** | right direction, over-confident `P` / sizing | the numbers |
| **Timing error** | right thesis, wrong entry | the entry / Shay lens |

**Principle — judge process, not outcome.** A BUY logged at `P=0.55` that loses is *not* a
mistake; it's the 45% happening. The "Bad luck" class exists precisely to stop the system from
turning an unlucky-but-sound call into a false lesson. This single classification is the
highest-leverage anti-coincidence move available.

---

## 3. KNOW IT'S REAL, NOT A COINCIDENCE — the lesson lifecycle
From a single resolved trade you **cannot** know a lesson is real (one outcome = one draw from
a distribution). So every lesson is a **registered hypothesis with a status**, never ground
truth, and only *validated* lessons may move forecasts.

```
🧪 LESSON  "High-multiple name >2σ above the upper Bollinger band into a binary
            earnings event (<48h) → don't initiate; mean-reversion risk."
   created 2026-06-04 (regime: Phase 2→3)   ·   mechanism: ✔ stated
   forward tests: 2 / 5 needed              ·   forward hit-rate: — (n<5)
   status: 🧪 CANDIDATE   (logged but INERT — not feeding recall, not moving P)
        → ✅ VALIDATED    (≥N forward tests, beats the null, CI excludes 0.5)
        → ❌ REFUTED      (forward record contradicts it → retire it)
        → ⏸ STALE         (macro regime changed → re-test before trusting)
```

The five tests a candidate must pass to be promoted:

1. **Pre-registration** — the rule is stated *before* the trades that test it (anti-hindsight).
   The forecast log already does this for `P`; extend it to lessons.
2. **Out-of-sample / forward-only scoring** — a lesson that only explains the cases it came from
   is worthless; it must improve calibration on **new** forecasts. Score its forward record
   separately from its originating cases.
3. **Calibration vs. a null** — compare Brier to dumb baselines (always 0.5, always
   "benchmark"); run a **bootstrap / permutation** test for "could this record arise by chance?"
4. **Mechanism, not just correlation** — require a plausible causal story; reject patterns
   without one (guards against p-hacking across many mined patterns).
5. **Regime-tagging** — tag the macro phase (`/ai-cycle-watch`) at creation; re-test on regime
   change, since e.g. "don't fade the uptrend on valuation" can invert in a drawdown.

**Statistical honesty everywhere:** every stat shows a **confidence interval + small-N
warning**. With **3 resolved** forecasts today, a "67% hit-rate" has a 95% CI of roughly
**20%–94%** — indistinguishable from a coin flip. Nothing below the bar is allowed to *look*
authoritative. Realistic threshold: **~20–30+ resolved forecasts** before any lesson earns the
right to move a number; today's data buys *hypotheses, not lessons*.

---

## 4. LEARN — make validated bias actually bend the next forecast
- **Calibration feedback (transparent):** `score` already measures bias (e.g. "Buys average
  −X% alpha", "P>0.7 calls hit 55%"). Turn it into an explicit, shown **shrink factor** the next
  run applies (pull `P(beat)` toward 0.5 by N when over-confident). Surface it in **Stage 0** so
  the analysis *states* the adjustment.
- **Lessons ledger → recall:** only **✅ VALIDATED** lessons are injected by `recall`
  (candidates stay inert). Aggregate taxonomy tags into recurring patterns rather than
  per-ticker prose.
- **In-line admission in the verdict:** when `recall` surfaces a validated lesson against the
  current setup, the analysis says so plainly ("the last two Holds on this name were too
  cautious — nudging conviction up"). *That* is the skill admitting it, in context.

---

## 5. DISPLAY — accountability as a first-class view
A new **📒 Track Record / Accountability** tab (extends today's track-record cards):

```
📒 Track Record                    Brier 0.21 · hit-rate 67% (2/3) · ⚠ N=3 — NOT YET MEANINGFUL (CI 20–94%)

Reliability (predicted P vs realized)      Open calls under pressure (interim)
  P 0.7+  ▏ hit 50%  (overconfident ▼)       ⚠ APLD BUY  -28% / -19% α · thesis under pressure → re-analyze
  P 0.5–0.7 ▏ hit 70%                         ⚠ NBIS OW   -15% / -11% α
  P <0.5  ▏ hit 80%

❌ Resolved misses (post-mortems)          🔁 Self-corrections          🧪 Lessons (status)
  AVGO Hold -13.8% [thesis ✗]               APLD OW→UW: prior bullish     "no-fade AI uptrend"  ✅ validated
       "stretched into binary print"             call corrected (link)     ">2σ into earnings"   🧪 candidate 2/5
```

Plus:
- **Badges** on existing tables: `❌ missed`, `⚠️ under pressure`, `🔁 corrected`.
- **Per-decision page → "Accountability" section:** original forecast vs realized, Brier
  contribution, taxonomy tag + lesson. For a reversed call, a banner: *"⚠️ Superseded by the
  2026-06-20 call (Sell→Buy). What the prior call got wrong: …"* linking both pages.
- **Reliability curve over time** with error bands, so you can watch calibration improve (or not).

---

## 6. Data-model & command sketch (for later)
- `ta_memory resolve …`: add structured fields `error_class`, `direction_correct`,
  `brier_contribution`, `lesson_id` (keep the prose too).
- **Lessons store** (`lessons.md`/`.jsonl`): `{id, rule, mechanism, created, regime,
  status, originating_cases[], forward_cases[]}`.
- New commands: `ta_memory mistakes` (resolved misses + recurring tags), `ta_memory watch`
  (pending calls whose interim mark is materially off → the ⚠️ feed), `ta_memory lessons`
  (lifecycle status + forward scorecard + CIs / null comparison).
- `build_dashboard.py`: render the Accountability tab + badges from those fields.

---

## 7. Phasing & recommendation
1. **Cheap, do first (no schema change):** interim **⚠️ "under pressure" flag** from existing
   `returns`, plus surfacing today's `score` bias as a one-line **Stage-0 calibration note**.
2. **Medium:** the **error taxonomy** at resolve + the **Accountability tab** (post-mortems,
   reversal "what it got wrong" banner) + **CIs/small-N warnings on every stat**.
3. **Deeper (needs the data to mature):** the **lesson lifecycle** (candidate→validated,
   forward-only scoring, null/bootstrap test) and the mechanical **shrink factor** feeding
   `P(beat)`.

## 8. Caveats (the whole point)
- **Tiny N today (3 resolved).** Treat all calibration/reliability output as noise until
  ~20–30+ resolved; the UI must *say so*.
- **Overfitting is the failure mode.** Promoting one unlucky trade to a confident rule is worse
  than having no rule. The candidate→validated gate exists to prevent exactly that.
- **Outcome ≠ process; correlation ≠ mechanism; in-sample ≠ predictive.** Every step above is a
  defense of one of those three lines.
- **Don't let lessons fossilise.** Regimes change; a validated lesson can go STALE — re-test on
  macro-phase flips rather than trusting it forever.
