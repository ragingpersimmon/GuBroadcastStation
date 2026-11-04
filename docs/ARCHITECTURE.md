# Gu Broadcast Station — architecture & parts list

```
                      ┌─────────────── StarNet (Tailscale) ───────────────┐
  RSS / GDELT ──► [1] NEWSDESK ── 5protocol news_ingest (library) ──┐     │
                      │          5protocol /news.json (regime) ─────┤     │
                      │                                             ▼     │
                      │   [2] EDITORIAL  rundown → scripts (Strata LLM)   │
                      │                    │                              │
                      │   [4] MONETIZATION sponsor reads / web slots      │
                      │                    ▼                              │
  droplet ◄──────── [5] SITE  static HTML, RSS, sitemap, ads.txt          │
     ▲                     rundown.json ───────────────┐                  │
     │                                                 ▼                  │
     ├── public/v/*.mp4 ◄──── [3a] HeyGen Avatar III (default, cloud API)  │
     │                          script+voice → anchor video → ffmpeg      │
     └── rsync public/v/*.mp4 ◄── [3b] ComfyUI studio on kwon9000 (5090)  │
                                   faces for HeyGen photo avatars,        │
                                   fallback talking heads, b-roll         │
                      └───────────────────────────────────────────────────┘
```

## The parts

| # | Part | Where it runs | Code | Status |
|---|---|---|---|---|
| 1 | **Newsdesk** — world feed ingest, dedupe, urgency score | droplet | `gbs/newsdesk/` → imports `vendor/5protocol/news_ingest.py` | **working** |
| 1b | **Market Pulse** — live 5protocol regime for the markets banner | droplet → nebulizer:8699 | `fiveprotocol_bridge.market_pulse` | working (needs `PHONE_PUSH_KEY`) |
| 2 | **Editorial** — cluster same-event coverage, rank, desk-balance, write anchor reads | droplet (LLM on kwon9000) | `gbs/editorial/` | working (template fallback w/o LLM) |
| 3a | **HeyGen Avatar III anchors** (default) — anchor video + voice from script, parallel render, lower third + ticker burned in | droplet → api.heygen.com | `gbs/anchors/heygen_client.py`, `cli.render_rundown` | **working**; needs API key + avatar/voice ids |
| 3b | **ComfyUI studio** — design anchor faces (upload as HeyGen Photo Avatars), fallback talking heads, b-roll | kwon9000 | `gbs/anchors/comfy_client.py`, `gbs/studio/` | client done; workflows to build |
| 4 | **Monetization** — on-air sponsor reads, pre-roll, web ad slots, ads.txt | droplet | `gbs/monetization/`, `config/sponsors.json` | working (house ad); network off |
| 5 | **Site** — static edition pages, RSS, sitemap, about/AI disclosure, advertise | droplet nginx | `gbs/site/`, `deploy/` | working |
| 6 | **Ops** — systemd timer, provisioning, nginx | droplet | `deploy/` | ready |

## Repos you need

**Yours**
- `ragingpersimmon/GuBroadcastStation` — this repo (orchestrator, site, config).
- `ragingpersimmon/5protocol` — pinned as git submodule `vendor/5protocol`. Supplies `news_ingest.NewsFeedPoller` and `news_signal_engine`. Private repo ⇒ the droplet needs a read-only deploy key.

**Third-party, on kwon9000 (studio)**
- `comfyanonymous/ComfyUI` — the render engine, exposed on `:8188` to the tailnet only.
- `ltdrdata/ComfyUI-Manager` — install/update nodes.
- Face consistency: `cubiq/ComfyUI_IPAdapter_plus` (FaceID) or a per-anchor LoRA (train with `ostris/ai-toolkit` or kohya `sd-scripts`).
- Lip-sync (pick one): a LatentSync wrapper node (search "LatentSync" in ComfyUI-Manager; best quality), SadTalker or Wav2Lip node packs (lighter).
- Video helpers: `Kosinkadink/ComfyUI-VideoHelperSuite` (load/save video + audio).
- TTS (pick one): Piper (`OHF-Voice/piper1-gpl`, formerly `rhasspy/piper`; fast CPU, default in `studio/render.py`), or XTTS-v2 / F5-TTS node packs for more natural voices.
- `ffmpeg` (system package) for compositing.

**Optional later**
- Ad network: Google AdSense / Ezoic / Raptive (apply once you have traffic + original-content history).
- Video ad serving (VAST pre-roll): Google IMA SDK or Video.js + `videojs-ima`.
- Distribution: YouTube Data API uploader for each edition (second revenue line).

## HeyGen Avatar III setup

1. HeyGen account with API access → API key → `HEYGEN_API_KEY` in `.env`.
2. Pick the anchor look, one of:
   - **Public / Instant Avatar** → `character_type: "avatar"`, `avatar_id`.
   - **Your own face from ComfyUI** → generate the anchor portrait on kwon9000, upload it in HeyGen as a Photo Avatar → `character_type: "talking_photo"`, `talking_photo_id`.
3. `python -m gbs heygen-list` → copy `avatar_id` / `voice_id` into each anchor's `heygen` block in `config/anchors.json`.
4. Keep `HEYGEN_TEST=1` (watermarked, no credits) until the output looks right, then set `HEYGEN_TEST=0`.
5. `GBS_RENDER=1` renders inside every `gbs run`; `GBS_RENDER_TOP` limits video to the top N segments. HeyGen API bills by minute of video: ~40 s per read × 3 segments × 48 editions/day ≈ 96 min/day. Check this against your plan before raising either number.
6. `ANCHOR_ENGINE=comfy` switches back to the ComfyUI path at any time.

## 5protocol hook — what was reused, what wasn't

- Reused as a library (no copies): concurrent fetch with hard timeouts, HTML scrubbing, sha256 dedupe with persisted seen-set, `news_signal_engine` risk score (used as an urgency signal for ranking).
- Isolated: GBS passes its own feed map and state paths (`$GBS_DATA_DIR/fiveprotocol/`), so it never touches the trading bot's `data/news_*.json`, and the explicit feed list switches off 5protocol's market-tuned GDELT/crypto add-ons.
- `/news.json` drops `link`/`summary`, so it is **only** used for the regime banner, never for publishable stories.
- 5protocol is untouched by this repo. To bump: `git -C vendor/5protocol pull && git add vendor/5protocol`.

## Editorial guardrails (keep these — they're what makes it monetizable)

- Rewrite in original words; credit outlets on air and link them on the page. Never republish article text.
- Anchors are disclosed as AI on every page footer and `/about.html`.
- B-roll must be illustrative, never synthetic "photos" of real events.
- Sponsor reads are labelled "Sponsored by" on air and on page; web placements use `rel="sponsored"`.
- Ad networks penalise thin auto-generated content: the value-add is the curation, multi-source merge, and anchor presentation. Add human review for the top story before turning the network on.

## Next build steps

1. HeyGen: API key, fill avatar/voice ids (`heygen-list`), test renders with `HEYGEN_TEST=1 python -m gbs studio`.
2. Optional custom faces: ComfyUI on kwon9000 → `anchor_portrait` → upload to HeyGen as Photo Avatars.
3. Turn on `GBS_RENDER=1` once a test edition looks right.
4. Point a domain at the droplet, `deploy/provision_droplet.sh`, certbot.
5. Sell first direct sponsor; enable ad network after ~30 days of editions.
