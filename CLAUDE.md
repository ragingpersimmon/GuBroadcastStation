# Gu Broadcasting Station: agent guide

## Start of every session
1. Read **`TASKS.md`**. It is the backlog. If Ric's request doesn't name something else, offer to continue with the first open **[agent]** task whose blockers are met, and list any **[ric]** tasks that are blocking progress.
2. When you finish or learn something, update `TASKS.md` in the same change: tick boxes, add new tasks, add dated notes to the Findings log.

## What this is
AI-anchored news site. Pipeline: `gbs ingest` (world feeds through 5protocol's `news_ingest`, submodule `vendor/5protocol`) → `gbs rundown` (cluster, assignment desk, persona scripts, sponsor reads, static site) → `gbs studio` (local ComfyUI on the 5090: OmniVoice TTS + InfiniteTalk, then ffmpeg). Docs: `docs/ARCHITECTURE.md`, `docs/NEWSROOM.md`, `gbs/anchors/workflows/README.md`.

## Rules
- **Never modify `vendor/5protocol`.** It's a live trading bot. Only bump the submodule pin.
- The bridge must keep its own state dir (`$GBS_DATA_DIR/fiveprotocol/`) and never write 5protocol's `data/news_*.json`.
- Editorial standards in `gbs/editorial/standards.py` are non-negotiable: rewrite in your own words, credit and link sources, no invented facts, no humour on serious stories, sponsor reads always labelled, every on-air character disclosed as AI.
- Only use TTS/video models with commercial-use licences (no XTTS-v2).
- Clone only invented voices or Ric's own.
- Run `FIVEPROTOCOL_PATH=<5protocol checkout> pytest -q` before committing. Add tests for new behaviour.
- Ric's style: terse, direct, actionable.
