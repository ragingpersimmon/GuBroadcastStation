# Gu Broadcasting Station

AI-anchored world news. Headlines come in through **5protocol's news pipeline**, get clustered and rewritten into anchor reads, are presented by AI anchors rendered locally on the 5090 (ComfyUI: OmniVoice TTS + InfiniteTalk over StarNet; HeyGen optional), and are published on the droplet with sponsor reads and ad slots.

Backlog: **[TASKS.md](TASKS.md)**. See **[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)** for parts and repos, **[docs/NEWSROOM.md](docs/NEWSROOM.md)** for the cast, shows and desks.

## Quick start

```bash
git clone --recurse-submodules https://github.com/ragingpersimmon/GuBroadcastStation
cd GuBroadcastStation
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # set LLM_BASE_URL, PHONE_PUSH_KEY, GBS_SITE_URL ...
set -a; . ./.env; set +a

python -m gbs ingest      # world feeds -> 5protocol NewsFeedPoller -> data/stories.db
python -m gbs pulse       # live 5protocol market regime (tailnet)
python -m gbs rundown     # rundown + scripts + static site -> $GBS_SITE_OUT
python -m gbs run         # ingest + rundown (systemd timer runs this every 15 min)
python -m gbs newsroom    # who's on air now, desk assignments, missing avatars
python -m gbs heygen-list # HeyGen avatar + voice ids for config/newsroom.json
python -m gbs studio      # render anchor clips for the latest edition + republish (local ComfyUI)
python -m gbs comfy-tokenize export.json --kind anchor_talking   # convert your ComfyUI API export
python -m gbs comfy-portraits / comfy-voices                     # lock each character's face / voice
python -m gbs comfy-ping  # check ComfyUI on kwon9000
```

Tests: `pytest -q` (offline; uses local RSS files through the real 5protocol poller).

## Layout

```
gbs/newsdesk/     5protocol bridge, world feed map, story store
gbs/editorial/    rundown builder, LLM scriptwriter (Strata, template fallback)
gbs/anchors/      HeyGen Avatar III client, ComfyUI client, roster, workflows/
gbs/studio/       TTS, talking head, ffmpeg compose
gbs/monetization/ sponsors, on-air reads, web ad slots
gbs/site/         static site builder
config/           newsroom.json (cast, shows, desks), sponsors.json
deploy/           systemd timer, nginx, droplet provisioning
assets/           locked anchor portraits + reference voices
vendor/5protocol  git submodule
```
