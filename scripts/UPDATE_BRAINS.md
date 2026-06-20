# Updating the Jensen, Leopold & Jordi Brains

The three secular-lens brains used by `/trading-analysis` (Stages 6.5–6.65),
`/jensen-brain`, `/leopold-brain`, and `/jordi-brain` are **corpus + BM25 index** projects
that live *outside* this repo:

| Brain | Default path (env override) | Corpus = |
|---|---|---|
| Jensen | `/home/ewexler/projects/jensen-brain` (`$JENSEN_HOME`) | what Jensen **said** (`transcripts/`) + what NVIDIA **did** (`materials/`) |
| Leopold | `/home/ewexler/projects/leopold-brain` (`$LEOPOLD_HOME`) | what Leopold **wrote** (essay) + **said** (interviews), in `writings/` |
| Jordi | `/home/ewexler/projects/jordi-brain` (`$JORDI_HOME`) | what Jordi **said** (`transcripts/` = @JordiVisserLabs) + **news** (`materials/`) |
| Gavin | `/home/ewexler/projects/gavin-brain` (`$GAVIN_HOME`) | what Gavin **said** (guest appearances, search+purity) + **news** (`materials/`) |
| X | `/home/ewexler/projects/x-brain` (`$X_HOME`) | what FinTwit **posts** (`posts/` via keyless Nitter RSS) + **news proxy** (`materials/`); `work/analyze_corpus.py` → `index/research.json` for the dashboard Research tab. Crowd-sentiment overlay (Stage 6.67) — **not** in the Combined verdict. |

The TradingAgents bridges (`.claude/skills/trading-analysis/scripts/jensen_brain.py`,
`leopold_brain.py`) read each brain's `index/chunks.jsonl` directly. **So the only
thing that has to happen for new material to take effect is a rebuild of that index** —
no change inside TradingAgents.

## The one command

```bash
scripts/update_brains.sh            # FULLY AUTOMATIC: refresh + discover + auto-ingest + rebuild
scripts/update_brains.sh jensen     # just Jensen
scripts/update_brains.sh leopold    # just Leopold
scripts/update_brains.sh ingest     # transcribe the human-REVIEWED pending tier only
```

It is **idempotent** — fetchers/discovery skip anything already on disk (matched by URL /
video id), so it is safe to run after every news cycle. It prints the before→after chunk
count for each brain and the verify commands. If you are offline, it warns and still
rebuilds from whatever is on disk.

After it runs, the new passages are immediately live in `/trading-analysis`,
`/jensen-brain`, and `/leopold-brain`.

## What the command does, brain by brain

### Jensen
1. `work/fetch_nvidia.py` — pulls NVIDIA's **press + corporate-blog RSS** (the
   time-stamped *"what NVIDIA did"* news lane) into `materials/`.
2. `work/discover_new.py` — **key-free incremental YouTube discovery** (yt-dlp search)
   of new Jensen videos published since the corpus date watermark, then `work/purity.py`
   sorts each candidate `accept`/`review`/`reject` (see next section).
3. `work/ingest_pending.py` — auto-transcribes the `accept` tier (`auto_jensen.tsv`) into
   `transcripts/` with the metadata header.
4. `index/build_index.py` — re-chunks `transcripts/` + `materials/` → `chunks.jsonl`.

### Leopold
1. `work/fetch_situational_awareness.py` — re-fetches the 8 essay chapters (idempotent).
2. `work/fetch_interviews.py` — downloads any **whitelisted** Leopold interview not yet
   on disk (needs `yt-dlp`).
3. `work/discover_new.py` + `work/purity.py` — same incremental discovery + filter as
   Jensen, but **stricter** (auto-accept requires an allowlisted long-form host).
4. `work/ingest_pending.py` — auto-transcribes the `accept` tier (`auto_leopold.tsv`) into
   `writings/`.
5. `index/build_index.py` — re-chunks `writings/` → `chunks.jsonl`.

### Jordi
1. `work/fetch_channel.py` — enumerates the **@JordiVisserLabs** channel and transcribes
   any video not yet on disk (idempotent: bootstraps the whole back catalogue on the first
   run, then picks up only new uploads). **No purity filter** — it's his own channel, so
   every upload is him speaking. Optional `DISCOVER_SINCE` floor.
2. `work/fetch_news.py` — keyless **Google News RSS** for "Jordi Visser" into `materials/`.
3. `index/build_index.py` — re-chunks `transcripts/` + `materials/` → `chunks.jsonl`.

## Incremental discovery + the purity filter (the automation)

Discovery watermark = the latest `Upload date` already in the corpus, floored at
`DISCOVER_SINCE` (default `20260101` = Jan 2026 forward); the search window is
`max(watermark, floor)` → today. `work/purity.py` classifies each discovered video by
title/channel/duration heuristics into three tiers:

| Tier | File | What happens |
|---|---|---|
| **accept** | `work/auto_<brain>.tsv` | auto-transcribed + indexed that run (no human) |
| **review** | `work/pending_<brain>.tsv` | parked; ingest the ones you keep with `update_brains.sh ingest` |
| **reject** | `work/discover_rejects.log` | dropped, but logged for audit/recovery |

Tuned for **precision on `accept`** — a wrong accept pollutes the brain, so borderline
cases fall to `review`, never silently into the corpus. **Leopold is stricter than Jensen**
(`REQUIRE_ALLOWLIST = True`): he is *talked about* far more than he speaks, so only known
long-form host channels (Dwarkesh, a16z, Lex, …) auto-accept; everything else is review/reject.

**Tuning knobs:** edit the `CHANNEL_ALLOW` / `DENY_TITLE` / `DENY_CHANNEL` / duration floors
in each brain's `work/purity.py`; set env `DISCOVER_SINCE`, `DISCOVER_QUERIES` (`;`-separated),
`DISCOVER_N` (results per query) to change the window/queries/breadth.

## Adding NEW source material by hand (still supported)

Discovery covers new YouTube automatically. To add a source manually anyway, add it then
run the command (which rebuilds):

### Add a Jensen *interview/keynote* transcript
Append a row to `$JENSEN_HOME/work/ranked_filtered.tsv` — tab-separated
`YYYYMMDD ⇥ video_id ⇥ duration_sec ⇥ channel ⇥ title` — then:
```bash
cd "$JENSEN_HOME" && TARGET=$(( $(ls transcripts/*.txt | wc -l) + 5 )) python3 work/download_transcripts.py
```
(`TARGET` = total transcripts to reach. It downloads English captions, de-dupes rolling
captions, and drops anything < 500 chars.) Then `scripts/update_brains.sh jensen`.

### Add a Leopold *interview*
Add a `(video_id, "YYYYMMDD", "Channel", "Title")` tuple to the `INTERVIEWS` list in
`$LEOPOLD_HOME/work/fetch_interviews.py`, then `scripts/update_brains.sh leopold`.

### Add any doc by hand
Drop a `.txt` with the standard header (and the 70-`=` separator line) into the right
dir — `transcripts/` (Jensen, defaults to `source: jensen`) or `materials/` (Jensen,
add a `Source: nvda-blog`/`nvda-press` line) or `writings/` (Leopold, `Source:
essay`/`interview`) — then run the command.

```
Title: ...
Channel: ...
Upload date: 2026-06-19
Duration: 0 min
Source: nvda-blog          # materials/ & writings/ only; transcripts/ omit it
URL: https://...
======================================================================

<body text>
```

## Corpus purity rules (do not break these)

These are *qualitative-lens* brains — polluting them with the wrong voice degrades every
verdict. When adding sources by hand:

- **Jensen `transcripts/` = Jensen speaking.** No third-party commentary, dubbed/translated
  re-uploads, or clip compilations. `materials/` = NVIDIA's *own* publications only.
- **Leopold `writings/` = Leopold writing or speaking.** No commentary *about* him, no
  audiobook reads of the essay (the text is already in the corpus), no AI-generated
  summaries. Example of the distinction seen in practice: a podcast titled *"Leopold
  Aschenbrenner says No More Stocks!"* whose description says *"We discuss Leopold's
  portfolio"* is **commentary about him → excluded**; a *"Leopold chats with <host>"*
  where he is the long-form guest is **included**.

## Last refresh (2026-06-19)

- **Added incremental YouTube discovery + auto-ingest** (`discover_new.py`, `purity.py`,
  `ingest_pending.py` in each brain). First auto-discovery pulled 2 new Jensen videos
  since the watermark — AP exclusive (2026-06-16) auto-accepted, a Fox clip routed to
  review — taking Jensen to **102 transcripts + 21 materials, 5,230 chunks**.
- Leopold: **8 essay chapters + 3 interviews**; discovery's stricter filter auto-rejected
  all 5 commentary candidates ("$14B Fund", "Best AI Investor", an 89-sec reaction).
