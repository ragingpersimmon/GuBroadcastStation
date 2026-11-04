"""The Gu Briefing newsletter: build and send. See docs/NEWSLETTER.md."""
from __future__ import annotations

import json
import os
from datetime import datetime
from zoneinfo import ZoneInfo

from gbs.config import Settings


def run(cfg: Settings, send: bool, now: datetime | None = None, force: bool = False) -> int:
    from gbs.monetization.ads import AdBook
    from gbs.newsletter.compose import build_issue, gather, save_issue
    from gbs.newsletter.providers import SendError, provider_from_env

    tz = ZoneInfo(os.getenv("GBS_TZ", "America/Vancouver"))
    now = now or datetime.now(tz)
    state_p = cfg.data_dir / "newsletter" / "sent.json"
    state = json.loads(state_p.read_text()) if state_p.exists() else {}
    date = now.strftime("%Y-%m-%d")
    if send and state.get(date) and not force:
        print(f"already sent {date}: {state[date]}")
        return 0

    arts, weather = gather(cfg, now)
    pulse = {}
    try:
        from gbs.newsdesk.fiveprotocol_bridge import market_pulse
        pulse = market_pulse(cfg)
    except Exception:
        pass
    ads = AdBook()
    sponsor = ads._pick("world") if ads.sponsors else None
    issue = build_issue(cfg, arts, now, pulse=pulse, weather=weather, sponsor=sponsor)
    if issue is None:
        print(f"not enough stories in the last 24h ({len(arts)}) -- no issue for {date}")
        return 1
    p = save_issue(cfg, issue)
    print(f"built {date}: {issue.subject!r} ({len(issue.slugs)} stories) -> {p}")
    if not send:
        return 0
    prov = provider_from_env(cfg.data_dir)
    try:
        ref = prov.send(issue)
    except SendError as exc:
        print(f"send failed ({prov.name}): {exc}")
        return 2
    if prov.name != "file":  # previews don't count as sent
        state[date] = ref
        state_p.parent.mkdir(parents=True, exist_ok=True)
        state_p.write_text(json.dumps(state, indent=1))
    print(f"{'scheduled' if prov.name == 'kit' else 'written'}: {ref}")
    return 0
