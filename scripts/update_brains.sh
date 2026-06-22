#!/usr/bin/env bash
# update_brains.sh — refresh the Jensen Brain and Leopold Brain corpora + rebuild
# their BM25 indexes, in one command. Idempotent and safe to re-run.
#
#   Jensen Brain  = what Jensen *said* (YouTube transcripts) + what NVIDIA *did*
#                   (press + blog RSS — the time-stamped "news/actions" lane).
#   Leopold Brain = what Leopold *wrote* (Situational Awareness essay) + *said*
#                   (long-form interview transcripts) + how he's *positioned*
#                   (Situational Awareness LP 13F holdings from SEC EDGAR — long/short).
#   Jordi Brain   = what Jordi Visser *said* (every @JordiVisserLabs YouTube video) +
#                   a keyless news lane. Single owned channel, so no purity filter needed.
#   Gavin Brain   = what Gavin Baker *said* (long-form guest appearances — BG2, Invest
#                   Like the Best, Aleph, a16z… via STRICT search+purity) + a news lane.
#   X Brain       = what FinTwit/AI *posts* (curated accounts via keyless Nitter RSS) +
#                   a Google-News proxy lane; also recomputes research.json (trending AI
#                   topics + most-bullish names) for the dashboard's Research tab.
#
# The TradingAgents bridges (scripts/jensen_brain.py / leopold_brain.py) read each
# brain's index/chunks.jsonl directly, so rebuilding the index is all that's needed
# for fresh material to show up in /trading-analysis and /jensen-brain /leopold-brain.
#
# Usage:
#   scripts/update_brains.sh            # FULLY AUTOMATIC: refresh + discover new YouTube
#                                       #   videos since the watermark, purity-filter them,
#                                       #   auto-ingest the approved ones, and rebuild
#   scripts/update_brains.sh jensen     # only the Jensen Brain
#   scripts/update_brains.sh leopold    # only the Leopold Brain
#   scripts/update_brains.sh jordi      # only the Jordi Brain
#   scripts/update_brains.sh ingest     # transcribe the human-REVIEWED pending_*.tsv tier
#                                       #   (only needed for the 'review' uncertain bucket)
#
# Incremental YouTube discovery (key-free, via yt-dlp): each normal run discovers videos
# published since the corpus date watermark (floor DISCOVER_SINCE) and the purity filter
# (work/purity.py) sorts each into three tiers:
#   accept -> auto_<brain>.tsv  -> auto-ingested + indexed THIS run (no human needed)
#   review -> pending_<brain>.tsv -> parked for an optional human glance (run `ingest`)
#   reject -> work/discover_rejects.log -> dropped, but logged for audit/recovery
# This keeps the pipeline hands-off while protecting corpus purity (Jensen/Leopold must
# contain the subject SPEAKING, not third-party commentary / reaction / clickbait).
#
# Env overrides (default to the standard sibling-project paths):
#   JENSEN_HOME=/path/to/jensen-brain
#   LEOPOLD_HOME=/path/to/leopold-brain
#   DISCOVER_SINCE=YYYYMMDD   discovery floor (default 20260101 = Jan 2026 forward)
set -uo pipefail

JENSEN_HOME="${JENSEN_HOME:-/home/ewexler/projects/jensen-brain}"
LEOPOLD_HOME="${LEOPOLD_HOME:-/home/ewexler/projects/leopold-brain}"
JORDI_HOME="${JORDI_HOME:-/home/ewexler/projects/jordi-brain}"
GAVIN_HOME="${GAVIN_HOME:-/home/ewexler/projects/gavin-brain}"
X_HOME="${X_HOME:-/home/ewexler/projects/x-brain}"
PY="${PYTHON:-python3}"
WHICH="${1:-both}"

chunks() { [ -f "$1/index/chunks.jsonl" ] && wc -l < "$1/index/chunks.jsonl" | tr -d ' ' || echo 0; }

update_jensen() {
  echo "================ JENSEN BRAIN ($JENSEN_HOME) ================"
  if [ ! -d "$JENSEN_HOME" ]; then echo "  [skip] not found"; return; fi
  local before; before=$(chunks "$JENSEN_HOME")
  echo "-- fetch latest NVIDIA news (press + blog RSS, idempotent) --"
  ( cd "$JENSEN_HOME" && "$PY" work/fetch_nvidia.py ) || echo "  [warn] fetch_nvidia.py failed (offline?) — rebuilding with what's on disk"
  echo "-- discover new Jensen YouTube videos since watermark + purity-filter them --"
  ( cd "$JENSEN_HOME" && "$PY" work/discover_new.py ) || echo "  [warn] discovery skipped (yt-dlp missing / offline?)"
  echo "-- auto-ingest purity-approved videos (auto_jensen.tsv) --"
  ( cd "$JENSEN_HOME" && "$PY" work/ingest_pending.py ) || echo "  [warn] auto-ingest failed"
  echo "-- rebuild index --"
  ( cd "$JENSEN_HOME" && "$PY" index/build_index.py )
  echo "   chunks: $before -> $(chunks "$JENSEN_HOME")"
}

update_leopold() {
  echo "================ LEOPOLD BRAIN ($LEOPOLD_HOME) ================"
  if [ ! -d "$LEOPOLD_HOME" ]; then echo "  [skip] not found"; return; fi
  local before; before=$(chunks "$LEOPOLD_HOME")
  echo "-- refresh Situational Awareness essay chapters (idempotent) --"
  ( cd "$LEOPOLD_HOME" && "$PY" work/fetch_situational_awareness.py ) || echo "  [warn] essay fetch failed (offline?)"
  echo "-- fetch interview transcripts from the whitelist (idempotent; needs yt-dlp) --"
  ( cd "$LEOPOLD_HOME" && "$PY" work/fetch_interviews.py ) || echo "  [warn] interview fetch failed (yt-dlp missing / offline?)"
  echo "-- discover new Leopold YouTube videos since watermark + purity-filter them --"
  ( cd "$LEOPOLD_HOME" && "$PY" work/discover_new.py ) || echo "  [warn] discovery skipped (yt-dlp missing / offline?)"
  echo "-- auto-ingest purity-approved videos (auto_leopold.tsv) --"
  ( cd "$LEOPOLD_HOME" && "$PY" work/ingest_pending.py ) || echo "  [warn] auto-ingest failed"
  echo "-- refresh Situational Awareness LP 13F holdings from SEC EDGAR (what Leopold is long/short; idempotent per quarter) --"
  ( cd "$LEOPOLD_HOME" && "$PY" work/fetch_13f.py ) || echo "  [warn] 13F fetch failed (offline / SEC throttle?)"
  echo "-- rebuild index --"
  ( cd "$LEOPOLD_HOME" && "$PY" index/build_index.py )
  echo "   chunks: $before -> $(chunks "$LEOPOLD_HOME")"
}

update_jordi() {
  echo "================ JORDI BRAIN ($JORDI_HOME) ================"
  if [ ! -d "$JORDI_HOME" ]; then echo "  [skip] not found"; return; fi
  local before; before=$(chunks "$JORDI_HOME")
  echo "-- fetch new @JordiVisserLabs videos (idempotent; bootstrap on first run) --"
  ( cd "$JORDI_HOME" && "$PY" work/fetch_channel.py ) || echo "  [warn] channel fetch failed (yt-dlp missing / offline?)"
  echo "-- fetch latest Jordi news (keyless Google News RSS, idempotent) --"
  ( cd "$JORDI_HOME" && "$PY" work/fetch_news.py ) || echo "  [warn] news fetch failed (offline?)"
  echo "-- rebuild index --"
  ( cd "$JORDI_HOME" && "$PY" index/build_index.py )
  echo "   chunks: $before -> $(chunks "$JORDI_HOME")"
}

update_gavin() {
  echo "================ GAVIN BRAIN ($GAVIN_HOME) ================"
  if [ ! -d "$GAVIN_HOME" ]; then echo "  [skip] not found"; return; fi
  local before; before=$(chunks "$GAVIN_HOME")
  echo "-- discover new Gavin Baker appearances since watermark + STRICT purity-filter --"
  ( cd "$GAVIN_HOME" && "$PY" work/discover_new.py ) || echo "  [warn] discovery skipped (yt-dlp missing / offline?)"
  echo "-- auto-ingest purity-approved videos (auto_gavin.tsv) --"
  ( cd "$GAVIN_HOME" && "$PY" work/ingest_pending.py ) || echo "  [warn] auto-ingest failed"
  echo "-- fetch latest Gavin news (keyless Google News RSS, idempotent) --"
  ( cd "$GAVIN_HOME" && "$PY" work/fetch_news.py ) || echo "  [warn] news fetch failed (offline?)"
  echo "-- rebuild index --"
  ( cd "$GAVIN_HOME" && "$PY" index/build_index.py )
  echo "   chunks: $before -> $(chunks "$GAVIN_HOME")"
}

update_x() {
  echo "================ X BRAIN ($X_HOME) ================"
  if [ ! -d "$X_HOME" ]; then echo "  [skip] not found"; return; fi
  local before; before=$(chunks "$X_HOME")
  echo "-- fetch curated FinTwit/AI posts (keyless Nitter RSS, idempotent; best-effort) --"
  ( cd "$X_HOME" && "$PY" work/fetch_accounts.py ) || echo "  [warn] account fetch failed (no live Nitter?) — relying on the news lane"
  echo "-- fetch AI-trend + stock-chatter news lane (keyless Google News RSS, idempotent) --"
  ( cd "$X_HOME" && "$PY" work/fetch_trends.py ) || echo "  [warn] trend fetch failed (offline?)"
  echo "-- rebuild index --"
  ( cd "$X_HOME" && "$PY" index/build_index.py )
  echo "-- recompute research.json (trending AI topics + most-bullish names) --"
  ( cd "$X_HOME" && "$PY" work/analyze_corpus.py ) || echo "  [warn] analyze_corpus failed"
  echo "   chunks: $before -> $(chunks "$X_HOME")"
}

# Transcribe REVIEWED pending_<brain>.tsv rows (the human-review tier), then rebuild.
ingest_brain() {
  local home="$1" name="$2" pending="$3"
  echo "================ INGEST $name ($home) ================"
  if [ ! -d "$home" ]; then echo "  [skip] not found"; return; fi
  if [ ! -f "$home/work/ingest_pending.py" ]; then echo "  [skip] no ingest_pending.py"; return; fi
  local before; before=$(chunks "$home")
  ( cd "$home" && "$PY" work/ingest_pending.py "work/$pending" ) || echo "  [warn] ingest failed"
  echo "-- rebuild index --"
  ( cd "$home" && "$PY" index/build_index.py )
  echo "   chunks: $before -> $(chunks "$home")"
}

case "$WHICH" in
  jensen)  update_jensen ;;
  leopold) update_leopold ;;
  jordi)   update_jordi ;;
  gavin)   update_gavin ;;
  x)       update_x ;;
  both|all|"") update_jensen; echo; update_leopold; echo; update_jordi; echo; update_gavin; echo; update_x ;;
  ingest)  ingest_brain "$JENSEN_HOME" "JENSEN" "pending_jensen.tsv"; echo; ingest_brain "$LEOPOLD_HOME" "LEOPOLD" "pending_leopold.tsv"; echo; ingest_brain "$GAVIN_HOME" "GAVIN" "pending_gavin.tsv" ;;
  ingest-jensen)  ingest_brain "$JENSEN_HOME" "JENSEN" "pending_jensen.tsv" ;;
  ingest-leopold) ingest_brain "$LEOPOLD_HOME" "LEOPOLD" "pending_leopold.tsv" ;;
  ingest-gavin)   ingest_brain "$GAVIN_HOME" "GAVIN" "pending_gavin.tsv" ;;
  *) echo "usage: $0 [jensen|leopold|jordi|gavin|x|both|ingest|ingest-jensen|ingest-leopold|ingest-gavin]"; exit 2 ;;
esac

echo
case "$WHICH" in ingest|ingest-jensen|ingest-leopold|ingest-gavin) SKIP_REVIEW=1;; *) SKIP_REVIEW=0;; esac
if [ "$SKIP_REVIEW" = 0 ]; then
  echo "Approved videos were auto-ingested. OPTIONAL: review the 'uncertain' tier if any:"
  for f in "$JENSEN_HOME/work/pending_jensen.tsv" "$LEOPOLD_HOME/work/pending_leopold.tsv" "$GAVIN_HOME/work/pending_gavin.tsv"; do
    [ -f "$f" ] && echo "  \$EDITOR $f   ($(grep -vc '^#' "$f" 2>/dev/null) row(s))"
  done
  echo "  then: scripts/update_brains.sh ingest      # transcribe the ones you keep"
  echo "  rejects (audit): work/discover_rejects.log"
  echo
fi
echo "Done. Verify with:"
echo "  python3 $JENSEN_HOME/index/search.py  'AI factory power grid data center' --k 3"
echo "  python3 $LEOPOLD_HOME/index/search.py 'trillion dollar cluster power electricity' --k 3"
echo "  python3 $JORDI_HOME/index/search.py   'AI capex scarcity SaaS disruption bitcoin' --k 3"
echo "  python3 $GAVIN_HOME/index/search.py   'AI sustaining disruptive compute moat NVIDIA' --k 3"
echo "  python3 $X_HOME/index/search.py       'NVDA AI datacenter bullish' --k 3"
