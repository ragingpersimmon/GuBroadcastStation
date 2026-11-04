# Gu Broadcasting Station — architecture & parts list

Cast, shows and desk assignments: **[NEWSROOM.md](NEWSROOM.md)**.

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
| 3a | **HeyGen Avatar III anchors** (optional, paid) — anchor video + voice from script, parallel render, lower third + ticker burned in | droplet → api.heygen.com | `gbs/anchors/heygen_client.py`, `cli.render_rundown` | **working**; needs API key + avatar/voice ids |
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

## Local anchors on the 5090 (default — no HeyGen bill)

`ANCHOR_ENGINE=comfy`. For each clip: voice from the `tts` workflow (OmniVoice / Chatterbox) → InfiniteTalk talking head (`anchor_talking`, Wan2.1 fp8/GGUF via Kijai WanVideoWrapper) → ffmpeg lower third and ticker. Faces and voices are designed once and then locked, so every character looks and sounds the same in every clip.

One-time setup on kwon9000:
1. Install ComfyUI-WanVideoWrapper (Kijai), ComfyUI-VideoHelperSuite and ComfyUI-OmniVoice-TTS. Download the InfiniteTalk and Wan2.1 I2V 480p weights in **fp8 or GGUF** from `Kijai/WanVideo_comfy`.
2. Build and test four workflows in ComfyUI, export each as API format, then convert them: `python -m gbs comfy-tokenize export.json --kind anchor_talking|tts|tts_design|anchor_portrait`. Details are in `gbs/anchors/workflows/README.md`.
3. `python -m gbs comfy-portraits` designs the 14 faces into `assets/anchors/`. Re-roll any you don't like with `--force`, after changing that character's seed or `look_prompt`, then commit the ones you keep.
4. `python -m gbs comfy-voices` has each character read their signature line with a voice built from `voice_prompt`. The clip is saved to `assets/voices/` and reused as the cloning reference from then on. Commit those too.
5. `python -m gbs newsroom` lists anything still missing.

**GPU handoff.** The 27B and InfiniteTalk don't fit in 32 GB together. Set `GBS_GPU_HANDOFF`: `ollama` unloads the model with keep_alive=0, and `command` runs your own unload/reload commands, for example over ssh. Each render pass then goes: LLM out → render → ComfyUI `/free` → LLM back in.

**Scheduling.** `gubroadcast-pipeline.timer` publishes a text edition every 15 minutes and never waits on the GPU. `gubroadcast-studio.timer` renders the latest edition's top clips in the background, with a lock so passes never overlap. It skips clips that are already done and republishes the page with players. If renders fall behind, editions simply go out with fewer videos. Tune `render_top` and `render_quarters` per show to match what one GPU can do, after timing a real 40-second clip.

## HeyGen Avatar III setup (optional, paid)

1. HeyGen account with API access → API key → `HEYGEN_API_KEY` in `.env`.
2. Pick the anchor look, one of:
   - **Public / Instant Avatar** → `character_type: "avatar"`, `avatar_id`.
   - **Your own face from ComfyUI** → generate the anchor portrait on kwon9000, upload it in HeyGen as a Photo Avatar → `character_type: "talking_photo"`, `talking_photo_id`.
3. `python -m gbs heygen-list` → copy `avatar_id` / `voice_id` into each on-air talent's `heygen` block in `config/newsroom.json` (14 characters).
4. Keep `HEYGEN_TEST=1` (watermarked, no credits) until the output looks right, then set `HEYGEN_TEST=0`.
5. `GBS_RENDER=1` renders inside every `gbs run`; per-show `render_top` / `render_quarters` set how much gets video (`GBS_RENDER_TOP` overrides). HeyGen API bills by minute of video. With the default show clock (newsroom.json `render_top` / `render_quarters`), a weekday is about 87 clips × ~40 s ≈ 58 min of video. Check this against your plan before raising either number.
6. `ANCHOR_ENGINE=heygen` switches to HeyGen; `comfy` switches back.

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
