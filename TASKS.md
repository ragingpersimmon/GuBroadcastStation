# TASKS — Gu Broadcasting Station

The working backlog. Agents: read this at the start of every session, pick up the
first open **[agent]** task whose blockers are met, and keep this file current
(tick boxes, add findings, add new tasks you discover). **[ric]** tasks need
Ric's hardware, accounts or decisions. Don't fake them; ask, or prepare
everything up to that point.

Status key: `[ ]` open · `[~]` in progress · `[x]` done · `(blocked: …)`

---

## 1. Local anchor studio (5090 / kwon9000)

- [ ] **T1 [ric]** Install on ComfyUI: Kijai `ComfyUI-WanVideoWrapper`, `ComfyUI-VideoHelperSuite`, `ComfyUI-OmniVoice-TTS`. Download InfiniteTalk + Wan2.1 I2V 480p weights in **fp8 or GGUF** from `Kijai/WanVideo_comfy`.
- [ ] **T2 [ric]** Build and run four workflows by hand, then export each as API format: InfiniteTalk talking head, OmniVoice clone, OmniVoice voice design, photoreal portrait. Drop the exports in `gbs/anchors/workflows/exports/`.
- [ ] **T3 [agent]** (blocked: T2) Run `python -m gbs comfy-tokenize <export> --kind anchor_talking|tts|tts_design|anchor_portrait` for each export. Fix any tokens it warns about by hand, and commit the templates. Done when `python -m gbs newsroom` no longer lists missing workflows.
- [ ] **T4 [ric]** Say how the 27B is served (Ollama / llama.cpp / LM Studio / vLLM), what OS kwon9000 runs, and whether the droplet can ssh to it.
- [ ] **T5 [agent]** (blocked: T4) Set up the GPU handoff: `GBS_GPU_HANDOFF` plus the exact `GBS_LLM_UNLOAD_CMD` / `GBS_LLM_RELOAD_CMD` in `.env.example` and docs, then test the unload → render → reload cycle.
- [ ] **T6 [agent+ric]** (blocked: T3) Run `python -m gbs comfy-portraits`. Ric picks the faces (15, including lead anchor Harold Yi) and the agent re-rolls rejects (`--force`, after a new seed or `look_prompt` in `config/newsroom.json`). Commit the locked `assets/anchors/*.png`.
- [ ] **T7 [agent+ric]** (blocked: T6) Run `python -m gbs comfy-voices`, Ric approves each voice, then commit `assets/voices/*`.
- [ ] **T8 [agent]** (blocked: T7) Time one 40 s clip end to end and record the number here. Then set `render_top` / `render_quarters` per show in `newsroom.json` so a day's clips fit in GPU time with headroom. Today's schedule asks for ~87 clips per weekday, which is probably too many.
- [ ] **T9 [agent]** (blocked: T8) Check the ffmpeg lower third and ticker on a real InfiniteTalk clip (fonts, safe areas, `drawtext` escaping of quotes and colons in headlines). Fix `gbs/studio/render.py` as needed.
- [ ] **T10 [agent]** Evaluate LongCat-Video-Avatar 1.5 against InfiniteTalk on English reads. Early reports say its lip-sync was trained mostly on Chinese. Record the verdict here.

## 2. Droplet + site

- [x] **T11 [ric]** Domain bought: **gubs.ca** (2026-11-04).
- [ ] **T11b [ric]** At the registrar, point DNS at the droplet: `A gubs.ca → <droplet IPv4>`, `A www → <droplet IPv4>` (plus `AAAA` if the droplet has IPv6). Check with `dig +short gubs.ca`.
- [ ] **T11c [ric]** Set up email for @gubs.ca: forwarding is enough to start (registrar forwarding, Cloudflare Email Routing or ImprovMX) for news@, tips@, corrections@, ads@ and privacy@, all to your inbox. The site publishes these addresses. Add SPF/DMARC records once a sender exists (needed for T32 newsletter).
- [x] **T12a [agent]** Domain wired in: nginx (apex canonical, www→apex, ACME path), `.env.example`, config defaults, site emails (done 2026-11-04).
- [ ] **T12b [ric/agent]** (blocked: T11b, T13) On the droplet: `sudo DOMAIN=gubs.ca CERT_EMAIL=<you> deploy/provision_droplet.sh`. It bootstraps HTTP, gets the Let's Encrypt cert for gubs.ca + www, installs the HTTPS config and enables both timers. Then check `curl -I https://gubs.ca`.
- [ ] **T13 [ric]** Add a read-only deploy key for the private `5protocol` submodule on the droplet. Put `PHONE_PUSH_KEY` in `/opt/gubroadcast/.env` for the market pulse.
- [ ] **T14 [agent]** (blocked: T12) On the droplet, run `python -m gbs ingest` and check every feed in `gbs/newsdesk/feeds.py` returns items. Fix or replace dead RSS URLs and log any changes here. (They couldn't be verified from the build sandbox.)
- [ ] **T15 [ric]** Set `GBS_LOCAL_NAME/LAT/LON` (Celeste's weather) and decide on traffic: the Open511 / DriveBC feed URL for `GBS_TRAFFIC_OPEN511_URL`.
- [ ] **T16 [agent]** (blocked: T15) Check that the weather and traffic segments render against live data. Confirm the DriveBC Open511 query parameters (area / bbox) for the chosen region.
- [ ] **T17 [agent]** Point `LLM_BASE_URL` at Strata or the 27B and review 10 real scripts for each beat (open, story, sponsor read, breaking, close). Tune the prompts in `gbs/editorial/scriptwriter.py` and `standards.py`. Persona humour must never appear on serious stories.

## 3. Editorial quality & trust

- [ ] **T18 [agent]** Add a human review queue: the lead story in each flagship show waits for Ric's approve/edit/kill before it renders (a simple web page or CLI `gbs review`). Needed before applying to ad networks.
- [ ] **T19 [agent]** Make the same-event clustering in `editorial/rundown.py` stronger, e.g. local embeddings with a Jaccard fallback. Add tests with real headline pairs.
- [x] **T20 [agent]** Per-story pages, section/sub-section pages, daily archive, people, shows, search, sitemaps (done 2026-11-04, see `gbs/site/build.py`).
- [ ] **T21 [agent]** Add illustrative B-roll stills per story (`broll_still` workflow). They must never look like a real photo of a real event. Label them "Illustration".

## 4. Money

- [ ] **T22 [ric]** Book the first direct sponsor and fill in `config/sponsors.json`, including the pre-roll video if any.
- [ ] **T23 [agent]** Add the sponsor pre-roll to composed clips (`compose_cmd(preroll=…)`) and make sure it carries a "Sponsored" label on screen.
- [ ] **T24 [agent]** Wire up the ad network once approved: AdSense/Ezoic client and slot IDs, `ads.txt`, consent banner (CMP) for EU/UK visitors.
- [ ] **T25 [agent]** Add privacy-friendly analytics (e.g. self-hosted Plausible/Umami on the droplet) so sponsor decks have real traffic numbers.

## 5. Distribution

- [ ] **T26 [agent]** Write a YouTube uploader for flagship-show clips (YouTube Data API, upload as unlisted for review first). The AI-content disclosure flag must be on.
- [ ] **T27 [agent]** Write a social posting helper for `public/social/*.mp4` (Mina Cho's desk): captions plus a source link in the description, with Ric approving each post.

## 5b. Site follow-ups

- [ ] **T31 [ric]** Get the legal templates (`/privacy/`, `/terms/`, `/cookies/`) reviewed for your jurisdiction (`config/site.json`). Confirm the operator name and the promises they make (log retention, response times) before launch.
- [ ] **T32 [agent]** Build The Gu Briefing sender. Pick a provider (Buttondown / Listmonk self-hosted), set `newsletter.action` in `config/site.json`, and add a weekday-morning job that emails the top stories with source links and an unsubscribe link. Until then, `/newsletter/` says "launching soon" and collects sign-ups by email.
- [ ] **T33 [agent]** Social share images: render a 1200x630 card per story (headline + Gu lower-third look, or a frame from the anchor clip) and add `og:image` / `twitter:image`.
- [ ] **T34 [agent]** Burn-in captions on anchor clips (the script is the transcript), then update `/accessibility/` to drop the "known gaps" line.
- [ ] **T35 [agent]** Self-host the two web fonts (Archivo, Source Serif 4) under `/assets/fonts/` so no request goes to Google, and update `/privacy/`.
- [ ] **T36 [agent]** Set `social` handles in `config/site.json` once accounts exist (footer shows only filled ones).

## 6. Housekeeping

- [x] **T28 [ric]** Review and merge PR #1 (`groundwork/news-bridge`) into `main`.
- [ ] **T29 [agent]** Add CI (GitHub Actions): checkout with the submodule, run `pytest -q`.
- [ ] **T30 [agent]** Bump the `vendor/5protocol` pin when 5protocol's news pipeline changes, and re-run tests.

---

## Done

- [x] 5protocol news bridge (library mode + market pulse), world and beat feeds, story store
- [x] Rundown, persona scripts, standards and sensitivity gate, sponsor reads
- [x] Newsroom: 21 staff, show clock, assignment desk, ECHO breaking
- [x] Local anchor engine (InfiniteTalk + OmniVoice via ComfyUI), GPU handoff hooks, background studio timer
- [x] HeyGen Avatar III engine (optional, paid)
- [x] Full news site: home, 15 section/sub-section pages + feeds, story pages (NewsArticle JSON-LD, sources, share), live edition, video, markets, shows, people, archive, search, newsletter, about/standards/AI/corrections/sources, contact/tips, advertise/guidelines, privacy/terms/cookies/accessibility, HTML + XML + news sitemaps, robots, manifest, 404. A link-crawl test means no internal link resolves to nothing.

## Findings log

_Agents: append dated notes here (render timings, dead feeds, prompt changes)._

- 2026-11-04: Domain is gubs.ca. Public emails derive from GBS_SITE_URL's host (config/site.json `emails`).

- 2026-11-04: Harold Yi added as lead anchor of Gu Morning and Gu Evening News, with a fixed signature open (see docs/NEWSROOM.md). Tessa Vale is now assistant anchor and Benji Powers morning co-anchor. When Harold's voice is designed in T7, check that it says the signature line straight.

- 2026-11-04: Site build verified on Python 3.11 and 3.13; screenshots checked at 1366 px and 390 px. Run `pytest tests/test_site.py` after any template change; it fails on any broken internal link.
