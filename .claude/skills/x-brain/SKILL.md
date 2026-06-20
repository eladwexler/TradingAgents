---
name: x-brain
description: Judge the X (Twitter) FinTwit/AI crowd's read on a company — is the crowd net bullish or bearish on the name, and does it sit on a currently-hot AI trend? A qualitative crowd-sentiment + trend-alignment lens grounded only in what was actually posted, sourced from a keyless BM25 index over curated FinTwit/AI accounts (via Nitter RSS) plus a Google-News proxy lane. Returns an "X Brain Verdict" (Bullish buzz / Mixed / Bearish / Insufficient chatter) with confidence, the bull-vs-bear balance, the trend it rides, and cited posts. Use when the user asks "what is X / Twitter / FinTwit saying about <ticker>", whether the crowd is bullish on a name, what AI trends are hot on X, or wants the X sentiment read on a ticker without a full trading analysis.
---

# X Brain (FinTwit / AI crowd-sentiment + trend lens)

Answer one question about a company: **what does X (Twitter) FinTwit think** — is the
crowd *net bullish or bearish* on the name, and does it ride a *currently-hot AI trend*?
Judged **only** from what was actually posted. This is a **qualitative crowd-sentiment**
read — not a price forecast, not a BUY/HOLD/SELL, and (unlike the four secular brains) it
is a *sentiment overlay*, **not** a thesis and **not** part of the Combined Strategic
Verdict.

> Research scaffold only. **Not** financial/investment advice. The verdict reflects crowd
> sentiment + trend buzz (a coarse lexicon signal), not whether the stock is a good
> investment. Crowd sentiment is often a contrarian/late signal — treat accordingly.

This is the same lens that `trading-analysis` surfaces as Stage 6.67, but standalone — run
it for any company without the full multi-agent forecast.

## Inputs

Ask for (or infer):
- **Company** — name, CEO, ticker, **$cashtag** (good alias terms sharpen retrieval).
- Optional **trend terms** — the hot AI trends the company touches (AI capex / inference /
  custom silicon / HBM / networking-optics / power / nuclear / robotics / agents /
  neocloud / sovereign AI). Infer from the company if not given.

## Run the bridge

The bridge queries the "X brain" — a keyless BM25 index over a curated-account lane
(FinTwit/AI posts via Nitter RSS, source `x`) plus a Google-News proxy lane (source
`x-news`) in the companion `x-brain` project. From the TradingAgents repo root, pass alias
terms plus the AI trends the company touches:

```
python3 .claude/skills/trading-analysis/scripts/x_brain.py \
    "<company> <CEO> <$cashtag/aliases>" \
    --trend "<hot AI trends it touches>" \
    --k 5
```

Example:

```
python3 .claude/skills/trading-analysis/scripts/x_brain.py \
    "NVDA Nvidia Jensen" \
    --trend "AI capex datacenter inference custom silicon networking" \
    --k 5
```

(Set `X_HOME` if the x-brain project lives elsewhere; default `/home/ewexler/projects/x-brain`.
 If the bridge reports the index is missing, tell the user X Brain is unavailable and stop
 — **do not fabricate** a verdict or posts.)

### Refreshing the corpus (optional)

The index covers curated-account **posts** (Nitter) and the **news proxy lane** (Google
News). To pull the latest before judging, run once in the x-brain project:

```
python3 work/fetch_accounts.py && python3 work/fetch_trends.py && \
  python3 index/build_index.py && python3 work/analyze_corpus.py
```

(Idempotent — skips posts/news already on disk. `/update-all` does this for you. If no
Nitter instance answers, the account lane is empty and the verdict leans on the news lane
— say so.)

## Read the output → verdict

The bridge returns these groups, each hit tagged `[X-POST]` or `[X-NEWS]`:
- **DIRECT MENTIONS — CURATED ACCOUNTS** — what FinTwit/AI accounts actually posted,
- **DIRECT MENTIONS — NEWS PROXY LANE** — coverage of the chatter (the reliable backbone),
- **BULLISH LENS** / **BEARISH LENS** — the name intersected with bullish vs bearish chatter,
- **TREND LENS** — the hot AI trends it touches,

plus a two-part **coverage signal** (`x_post_score`, `x_news_score`). From these decide one
verdict by weighing the **bull-vs-bear balance** and **trend alignment**:

- Heavier, more convincing **bullish** lens + rides a hot trend → *Bullish buzz*.
- Bull and bear both substantial, or off-trend → *Mixed*.
- Heavier **bearish** lens (crash/bubble/downgrade chatter dominates) → *Bearish*.
- Both coverage scores thin → *Insufficient chatter* — say the crowd isn't discussing it.

Distinguish a **curated post** (someone actually said it) from **news-lane** coverage
(reporting about the name). If `x_post_score` is ~0, note the account lane was empty
(Nitter down) and lean on the news lane.

## Output

- **X Brain Verdict:** Bullish buzz / Mixed / Bearish / Insufficient chatter — with
  confidence (low / med / high).
- **Why:** 2–4 bullets on the bull-vs-bear balance, the trend it rides (or doesn't), and
  whether the signal is account-driven or news-lane-only.
- **In their words:** 1–3 short quoted snippets, each cited `(<date> — @account or source, <url>)`.
  Quote only retrieved text; **never invent posts**.
- Optionally point to the aggregate **Research** view (trending AI topics + most-bullish
  names) from `index/research.json`, surfaced on the dashboard's Research tab.

Keep the verdict qualitative and self-contained — it is a crowd-sentiment read, not a
recommendation, and it does not move any forecast or rating.
