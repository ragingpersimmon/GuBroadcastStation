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
- [~] **T4 [ric]** Say how the 27B is served (Ollama / llama.cpp / LM Studio / vLLM), what OS kwon9000 runs, and whether the droplet can ssh to it. **Answered 2026-11-07:** llama.cpp `llama-server`, supervised by 5protocol `brain_server.py` (garden watchdog), on Windows 11. Endpoint `http://127.0.0.1:8080/v1` locally, `http://100.111.143.71:8081/v1` from the tailnet, model `qwen3.8-27b`, ctx 32768, no API key. Ollama is retired. Still open: can the droplet ssh to kwon9000?
- [ ] **T5 [agent]** (unblocked 2026-11-07 for the local commands; droplet part waits on T4 ssh) Set up the GPU handoff: `GBS_GPU_HANDOFF` plus the exact `GBS_LLM_UNLOAD_CMD` / `GBS_LLM_RELOAD_CMD` in `.env.example` and docs, then test the unload → render → reload cycle.
- [ ] **T6 [agent+ric]** (blocked: T3) Run `python -m gbs comfy-portraits`. Ric picks the faces (15, including lead anchor Harold Yi) and the agent re-rolls rejects (`--force`, after a new seed or `look_prompt` in `config/newsroom.json`). Commit the locked `assets/anchors/*.png`.
- [ ] **T7 [agent+ric]** (blocked: T6) Run `python -m gbs comfy-voices`, Ric approves each voice, then commit `assets/voices/*`.
- [ ] **T8 [agent]** (blocked: T7) Time one 40 s clip end to end and record the number here. Then set `render_top` / `render_quarters` per show in `newsroom.json` so a day's clips fit in GPU time with headroom. Today's schedule asks for ~87 clips per weekday, which is probably too many.
- [ ] **T9 [agent]** (blocked: T8) Check the ffmpeg lower third and ticker on a real InfiniteTalk clip (fonts, safe areas, `drawtext` escaping of quotes and colons in headlines). Fix `gbs/studio/render.py` as needed.
- [ ] **T10 [agent]** Evaluate LongCat-Video-Avatar 1.5 against InfiniteTalk on English reads. Early reports say its lip-sync was trained mostly on Chinese. Record the verdict here.

## 2. Droplet + site

- [x] **T11 [ric]** Domain bought: **gubs.ca** (2026-11-04).
- [x] **T11b [ric]** At the registrar, point DNS at the droplet: `A gubs.ca → <droplet IPv4>`, `A www → <droplet IPv4>` (plus `AAAA` if the droplet has IPv6). Check with `dig +short gubs.ca`.
- [ ] **T11c [ric]** Set up email for @gubs.ca: forwarding is enough to start (registrar forwarding, Cloudflare Email Routing or ImprovMX) for news@, tips@, corrections@, ads@ and privacy@, all to your inbox. The site publishes these addresses. Add SPF/DMARC records once a sender exists (needed for T32 newsletter).
- [x] **T12a [agent]** Domain wired in: nginx (apex canonical, www→apex, ACME path), `.env.example`, config defaults, site emails (done 2026-11-04).
- [x] **T12b [ric/agent]** (blocked: T11b, T13) On the droplet: `sudo DOMAIN=gubs.ca CERT_EMAIL=<you> deploy/provision_droplet.sh`. It bootstraps HTTP, gets the Let's Encrypt cert for gubs.ca + www, installs the HTTPS config and enables both timers. Then check `curl -I https://gubs.ca`.
- [ ] **T13 [ric]** Add a read-only deploy key for the private `5protocol` submodule on the droplet. Put `PHONE_PUSH_KEY` in `/opt/gubroadcast/.env` for the market pulse.
- [ ] **T14 [agent]** (blocked: T12) On the droplet, run `python -m gbs ingest` and check every feed in `gbs/newsdesk/feeds.py` returns items. Fix or replace dead RSS URLs and log any changes here. (They couldn't be verified from the build sandbox.)
- [x] **T15 [ric]** Local desks default to Vancouver + DriveBC Open511 (Metro Vancouver box) since 2026-11-06; override with `GBS_LOCAL_*` / `GBS_TRAFFIC_OPEN511_URL`.
- [ ] **T16 [agent]** (blocked: T15) Check that the weather and traffic segments render against live data. Confirm the DriveBC Open511 query parameters (area / bbox) for the chosen region.
- [ ] **T17 [agent]** (ready: 27B at `http://127.0.0.1:8080/v1`, model `qwen3.8-27b`) Point `LLM_BASE_URL` at Strata or the 27B and review 10 real scripts for each beat (open, story, sponsor read, breaking, close). Tune the prompts in `gbs/editorial/scriptwriter.py` and `standards.py`. Persona humour must never appear on serious stories.

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
- [x] **T32 [agent]** The Gu Briefing built: issue composer, Kit + file providers, `gbs newsletter build|send`, weekday timer, sign-up/thanks/confirmed/guide pages, web archive of issues (2026-11-04). See `docs/NEWSLETTER.md`.
- [ ] **T32a [ric]** Kit setup (docs/NEWSLETTER.md §1, §3): free account with news@gubs.ca, a **mailing address** for the footer (CASL), v4 API key in `.env`, double-opt-in form with the redirect URLs, form action URL into `config/site.json`.
- [ ] **T32b [ric]** Domain authentication for gubs.ca in Kit: add its DKIM/return-path records plus a `_dmarc` TXT in Namecheap. Keep a single SPF record (§2).
- [ ] **T32c [ric/agent]** Dry run: a week on `GBS_NEWSLETTER_PROVIDER=file`, read the outbox issues, then a self-test send on `kit`, then go live. Log the first send date in the Findings log.
- [ ] **T32d [agent]** (when Kit Creator plan) Load welcome emails 2–3 as a Kit sequence; add a quarterly re-engagement and pruning job.
- [ ] **T33 [agent]** Social share images: render a 1200x630 card per story (headline + Gu lower-third look, or a frame from the anchor clip) and add `og:image` / `twitter:image`.
- [ ] **T34 [agent]** Burn-in captions on anchor clips (the script is the transcript), then update `/accessibility/` to drop the "known gaps" line.
- [ ] **T35 [agent]** Self-host the two web fonts (Archivo, Source Serif 4) under `/assets/fonts/` so no request goes to Google, and update `/privacy/`.
- [ ] **T36 [agent]** Set `social` handles in `config/site.json` once accounts exist (footer shows only filled ones).

## 5c. Membership, confidentiality, look (2026-11-06)

- [x] **T37 [agent]** Beige newsprint theme (no dark mode); rotating trending headline in the top bar (pausable); date + local weather on the right.
- [x] **T38 [agent]** Sources confidential: no outlet names/links on site, newsletter, RSS, search, JSON-LD; `/about/sources/` removed; on-air scripts never name outlets (`scrub_outlets`). Old template stories render headline-only (their 2nd sentence was the feed's own words).
- [x] **T39 [agent]** Fill thin sections: 12 more feeds, 3 web-only desk briefs per desk per edition (`GBS_SITE_EXTRA_PER_DESK`), live `/local/weather/` + `/local/traffic/`, video page fallback.
- [x] **T40 [agent]** Openverse CC0/public-domain topic images (`gbs/site/images.py`), labelled "Illustrative image", none on sensitive stories.
- [x] **T41 [agent]** Sign-in (Google, Microsoft, GitHub, Facebook) + Stripe membership service, `/login/ /account/ /membership/`. Runbook: `docs/MEMBERSHIP.md`.
- [ ] **T42 [ric]** OAuth clients (at least Google) per `docs/MEMBERSHIP.md` §1, keys into `.env`.
- [ ] **T43 [ric]** Stripe account for Gu + product/prices/key/webhook per §2 (agent can do the dashboard steps in Chrome once the account exists).
- [ ] **T44 [agent]** (blocked: T14) On the droplet, confirm the 12 new feeds return items; drop dead ones.
- [ ] **T45 [ric/agent]** Open-Meteo's free API is non-commercial only. Before ads or paid membership go live, switch weather to Environment Canada (MSC GeoMet, Open Government Licence) or buy an Open-Meteo API plan.
- [ ] **T46 [agent]** Rebase `i18n/languages` on main; drop catalog strings about sources; add tests; ship.
- [ ] **T47 [agent]** (blocked: T17 LLM) Until the LLM is reachable, stories are headline-only. Once it is, review 10 scripts for outlet names leaking.

## 5d. Verified news engine, security, languages (2026-11-09)

- [x] **T48 [agent]** Verification engine (`gbs/verify`, docs/VERIFICATION.md):
  - 2+ independent ownership groups required; facts cross-checked.
  - Gu-written headlines (no source headline is ever reused).
  - Originality gate (no 6-word run) and neutral-language gate.
  - Story-page "How this story was verified" panel.
  - Unverified/old template stories hidden.
- [x] **T49 [agent]** `gbs doctor` (feeds, registry, rewriter, pass/hold), `deploy/doctor.sh` (read-only server + security audit), `deploy/harden.sh` (ufw, fail2ban, unattended upgrades, SSH keys-only).
- [x] **T50 [agent]** nginx:
  - CSP pinned to the one inline script; X-Frame-Options, Referrer-Policy, Permissions-Policy.
  - HSTS includeSubDomains; server_tokens off.
  - Rate limits on /auth /billing /api; dotfiles and db files denied.
- [x] **T51 [agent]** Languages: EN KR JP CN FR SP switch (top-bar right), /ko /ja /zh /fr /es mirrors, 189-string catalogs; stories translated by the LLM (12k chars/lang/run).
- [x] **T52 [agent]** /work-with-us/: inquiry form → `/api/inquiry`.
  - Each inquiry gets a reference number and is routed to ads@ or news@.
  - Optional SMTP; tracked with `gbs inquiries`.
- [ ] **T53 [ric]** On the droplet:
  1. `sudo bash /opt/gubroadcast/deploy/update.sh` (it finds the kwon9000 Ollama over Tailscale).
  2. `sudo bash /opt/gubroadcast/deploy/doctor.sh`, then paste the output.
  3. After adding your SSH key: `sudo bash /opt/gubroadcast/deploy/harden.sh`.
- [ ] **T54 [ric]** Keep kwon9000 Ollama running; the 27B is the only writer. When it's off, nothing new publishes.
- [ ] **T55 [agent]** (after T53) Tune: watch `gbs doctor` held reasons for a day; adjust ORIG_RUN, loaded-word list, cluster thresholds.
- [x] **T56 [agent]** External checks (`gbs/verify/external.py`):
  - GDELT wider coverage: panel line; never confirms on its own; max 10 per edition.
  - Google Fact Check flags: a match holds the story; needs `GOOGLE_FACTCHECK_API_KEY`.
  - trafilatura full-text cross-check: internal, robots.txt respected; `GBS_FULLTEXT=1`.
- [ ] **T57 [ric]** Optional: Google Fact Check API key (console.cloud.google.com → APIs → Fact Check Tools API → Credentials → API key) into `.env` as `GOOGLE_FACTCHECK_API_KEY`.
- [x] **T58 [agent]** AionUi enablement: `scripts/gu.ps1` (droplet tasks over SSH from kwon9000) and `docs/AIONUI.md` (27B model setup, "Gu ops" assistant instructions, scheduled checks).
- [ ] **T60 [ric]** Approve REQ "expose 27B to tailnet" in #garden-overseer (`tailscale serve --bg --tcp 18080 tcp://127.0.0.1:8080` on kwon9000). Ollama there has only qwen2.5-coder:7b; the 27B is llama-server on 127.0.0.1:8080. update.sh now prefers :18080 and swaps an earlier Ollama pick. `GBS_MAX_REWRITES` default 24 → 8 (shared 2-slot 27B); lower it in `.env` too if it was copied as 24.
- [ ] **T59 [ric]** AionUi setup per docs/AIONUI.md §1 (model URL, clone, `gu.ps1 ssh-test`, paste the instructions).

## 6. Housekeeping

- [x] **T28 [ric]** Review and merge PR #1 (`groundwork/news-bridge`) into `main`.
- [ ] **T29 [agent]** Add CI (GitHub Actions): checkout with the submodule, run `pytest -q`.
- [ ] **T30 [agent]** Bump the `vendor/5protocol` pin when 5protocol's news pipeline changes, and re-run tests.

---

## Local 27B work order (added 2026-11-07)

Tasks the local 27B can do without Ric, smallest first. One task per session; run `pytest -q` before committing.

1. **T29** CI workflow (one YAML file).
2. **T19** Stronger same-event clustering: start with the Jaccard fallback plus tests using real headline pairs. Leave embeddings for later.
3. **T17** Point `LLM_BASE_URL` at the 27B and review 10 scripts per beat. Tune `scriptwriter.py` one beat at a time.
4. **T33** Social share cards (1200x630, one story at a time, then `og:image`).
5. **T18** `gbs review` CLI first (a web page later).
6. **T5** GPU handoff, local half only. The 27B is parked by brain_server's `HALTED` flag at the 5protocol repo root. **Before using it, confirm `HALTED` parks only the brain and not the trader.**

Needs internet once (do it while online): T35 (font files), T24/T25 (ad network, analytics).

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

- 2026-11-09: External check of gubs.ca:
  - 200, rebuilt every 15 min, account service up, billing off.
  - Missing CSP/XFO/Referrer-Policy; nginx version exposed.
  - Ticker and headlines were the outlets' own headlines word for word, now fixed by the engine.
  - Droplet internals unchecked: DO console signed out; doctor.sh written for Ric.
  - Ollama on kwon9000 listens on 100.111.143.71:11434 (tailnet); llama-server is 127.0.0.1:8080 only.

- 2026-11-06: Ric: sources are confidential for operational reasons; site went beige; trending ticker replaces the on-air strip; sign-in + membership (Stripe) modelled on flowerseekingbee.com. Without an LLM the old template copied each feed's first sentence verbatim; it now publishes the headline only. Droplet also runs the Vantage Supplements stack (Spree/puma in Docker), ~1.2 of 2 GB RAM used before the account service.

- 2026-11-06: Droplet gu-broadcast-station-604 (167.99.178.46, TOR1, 2 GB) provisioned; HTTPS cert for gubs.ca + www issued. CBC webfeeds hang from DO IPs (TLS stalls, no close) and froze the first edition; replaced with Global News, plus a hard socket timeout (GBS_FEED_TIMEOUT, 20 s). Submodule pin had been missing from main; restored (53e269f).

- 2026-11-04: Newsletter platform = Kit free plan (10k subs, API on free). Beehiiv create-post API needs Max/Enterprise; Substack has no API.
- 2026-11-04: Domain is gubs.ca. Public emails derive from GBS_SITE_URL's host (config/site.json `emails`).

- 2026-11-04: Harold Yi added as lead anchor of Gu Morning and Gu Evening News, with a fixed signature open (see docs/NEWSROOM.md). Tessa Vale is now assistant anchor and Benji Powers morning co-anchor. When Harold's voice is designed in T7, check that it says the signature line straight.

- 2026-11-04: Site build verified on Python 3.11 and 3.13; screenshots checked at 1366 px and 390 px. Run `pytest tests/test_site.py` after any template change; it fails on any broken internal link.

- 2026-11-07: 27B confirmed on llama.cpp via 5protocol brain_server (127.0.0.1:8080, ctx 32768, ~66 tok/s on the 5090). Also reachable on the tailnet at 100.111.143.71:8081. Ollama retired. See the Local 27B work order above.
