---
name: update-brains
description: Refresh and rebuild the Jensen Brain and Leopold Brain corpora + BM25 indexes used by trading-analysis, jensen-brain, and leopold-brain. Pulls the latest NVIDIA news (Jensen) and re-fetches the Situational Awareness essay + whitelisted interviews (Leopold), then rebuilds each index so new material goes live. Use when the user asks to "update the brains", refresh/rebuild the Jensen or Leopold corpus, pull the latest NVIDIA news into the brain, or add new transcripts/interviews/materials to a brain.
---

# Update Brains

One command to refresh and rebuild the two secular-lens brains
(`/jensen-brain`, `/leopold-brain`, and Stages 6.5–6.6 of `/trading-analysis`).
They are corpus + BM25 index projects in sibling repos; the TradingAgents bridges read
each brain's `index/chunks.jsonl` directly, so **a rebuild is all that's needed** for new
material to take effect.

## Run (agent path)

From the TradingAgents repo root:

```bash
scripts/update_brains.sh            # refresh + rebuild BOTH brains
scripts/update_brains.sh jensen     # only the Jensen Brain
scripts/update_brains.sh leopold    # only the Leopold Brain
```

Idempotent (fetchers skip anything already on disk by URL / video id), safe to re-run,
and it prints the before→after chunk count per brain. If offline it warns and rebuilds
from what's on disk. Honors `$JENSEN_HOME` / `$LEOPOLD_HOME` overrides (defaults:
`/home/ewexler/projects/{jensen,leopold}-brain`). Needs `yt-dlp` only when fetching new
Leopold interviews.

After it runs, report the chunk-count deltas and any new items fetched.

## What it does

Each normal run is **fully automatic** — refresh existing sources, discover new YouTube
videos published since the corpus date watermark, purity-filter them, auto-ingest the
approved ones, and rebuild:

- **Jensen** — `work/fetch_nvidia.py` (NVIDIA press + blog RSS) → `work/discover_new.py`
  (yt-dlp search since watermark, key-free) → `work/purity.py` (3-tier filter) →
  `work/ingest_pending.py` (auto-ingest approved) → `index/build_index.py`.
- **Leopold** — `work/fetch_situational_awareness.py` (essay) + `work/fetch_interviews.py`
  (whitelist) → `work/discover_new.py` → `work/purity.py` → `work/ingest_pending.py` →
  `index/build_index.py`.

### Incremental YouTube discovery + auto-ingest

Discovery watermark = latest `Upload date` already in the corpus, floored at
`DISCOVER_SINCE` (default `20260101` = Jan 2026 forward). New videos are sorted by
`purity.py` into three tiers to protect corpus purity (Jensen = Jensen *speaking* +
NVIDIA's own pubs; Leopold = Leopold's *own words* only — never third-party commentary,
reactions, audiobooks):

- **accept** → `work/auto_<brain>.tsv` → auto-transcribed + indexed that run (no human).
- **review** → `work/pending_<brain>.tsv` → parked for an *optional* glance; ingest the
  ones you keep with `scripts/update_brains.sh ingest`.
- **reject** → `work/discover_rejects.log` → dropped, but logged for audit/recovery.

## Growing a brain (new sources by hand — still supported)

Discovery handles new YouTube automatically. To add a source manually anyway (full
instructions + header format in [`scripts/UPDATE_BRAINS.md`](../../../scripts/UPDATE_BRAINS.md)):

- **Jensen transcript:** append a row to `$JENSEN_HOME/work/ranked_filtered.tsv`
  (`YYYYMMDD ⇥ video_id ⇥ duration_sec ⇥ channel ⇥ title`), run
  `download_transcripts.py`, then this skill.
- **Leopold interview:** add a `(video_id, "YYYYMMDD", "Channel", "Title")` tuple to the
  `INTERVIEWS` list in `$LEOPOLD_HOME/work/fetch_interviews.py`, then this skill.
- **Any doc by hand:** drop a `.txt` with the standard metadata header (+ the 70-`=`
  separator) into the right dir, then this skill.
- **Tune discovery:** edit the allowlists / deny patterns / duration floors in each
  brain's `work/purity.py`; set `DISCOVER_SINCE`, `DISCOVER_QUERIES`, `DISCOVER_N` to
  change the search window/queries/breadth.

## Verify

```bash
python3 $JENSEN_HOME/index/search.py  'AI factory power grid data center' --k 3
python3 $LEOPOLD_HOME/index/search.py 'trillion dollar cluster power electricity' --k 3
```
