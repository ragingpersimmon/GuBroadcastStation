"""The hook into 5protocol's news outlet.

Two channels, both optional-failure:

1. INGEST (primary) -- imports 5protocol's `news_ingest.NewsFeedPoller`
   as a library and runs it with GBS's world feed map. We inherit its
   concurrent fetch with hard timeouts, HTML scrubbing, sha256 dedupe
   with a persisted seen-set, and `news_signal_engine` scoring (used here
   as an urgency/"breaking" signal). Nothing is copied: upgrades to the
   5protocol pipeline flow straight into the broadcast.
   State lives under GBS_DATA_DIR so it never touches the trading bot's
   data/news_*.json files.

2. MARKET PULSE (secondary) -- reads the live regime state from the
   5protocol push server (`/news.json`, tailnet, PHONE_PUSH_KEY). That
   endpoint strips links, so it never feeds publishable stories; it only
   drives the Markets segment banner (calm / normal / elevated / crisis).
"""
from __future__ import annotations

import json
import logging
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Optional

from gbs.config import Settings
from gbs.models import Story
from gbs.newsdesk.feeds import WORLD_FEEDS, desk_of

log = logging.getLogger("gbs.bridge")


class FiveProtocolUnavailable(RuntimeError):
    pass


def _load_news_ingest(path: Path):
    """Import 5protocol's news_ingest module from its checkout."""
    if not (path / "news_ingest.py").exists():
        raise FiveProtocolUnavailable(
            f"5protocol not found at {path} -- run `git submodule update --init` "
            f"or set FIVEPROTOCOL_PATH")
    p = str(path)
    if p not in sys.path:
        sys.path.insert(0, p)
    import news_ingest  # noqa: E402  (5protocol module)
    return news_ingest


class NewsBridge:
    def __init__(self, cfg: Settings, feeds: Optional[dict] = None):
        self.cfg = cfg
        self.feeds = dict(feeds or WORLD_FEEDS)
        self._poller = None

    @property
    def poller(self):
        if self._poller is None:
            ni = _load_news_ingest(self.cfg.fiveprotocol_path)
            state = self.cfg.data_dir / "fiveprotocol"
            state.mkdir(parents=True, exist_ok=True)
            # Explicit `feeds` => 5protocol disables its market GDELT/crypto
            # add-ons (see NewsFeedPoller.__init__); space_watch off.
            self._poller = ni.NewsFeedPoller(
                feeds=self.feeds,
                seen_path=str(state / "seen.json"),
                state_path=str(state / "regime_state.json"),
                items_path=str(state / "items.json"),
                space_watch=False,
            )
        return self._poller

    def pull(self) -> list[Story]:
        """One poll pass; returns only never-seen stories."""
        import os
        import socket
        # feedparser opens sockets with no timeout: an outlet that stalls the TLS handshake
        # (CBC from DigitalOcean did) hangs the whole edition. Hard cap every socket.
        socket.setdefaulttimeout(float(os.getenv("GBS_FEED_TIMEOUT", "20")))
        now = time.time()
        stories = []
        for item, snap in self.poller.poll_once():
            if not item.link or not item.title:
                continue  # unattributable -> unpublishable
            stories.append(Story(
                item_hash=item.item_hash,
                desk=desk_of(item.source),
                source=item.source,
                title=item.title,
                summary=item.summary,
                link=item.link,
                ts=now,
                risk_score=float(snap.risk_score),
                regime=str(snap.vol_regime),
                keywords=list(snap.matched_keywords),
            ))
        try:
            self.poller.publish_state()
        except Exception:
            log.exception("publish_state failed (non-fatal)")
        log.info("bridge pulled %d new stories from %d feeds", len(stories), len(self.feeds))
        return stories


def market_pulse(cfg: Settings, timeout: int = 8) -> dict:
    """Live 5protocol regime state, or {} if unreachable/unauthorised."""
    if not cfg.fiveprotocol_push_key:
        return {}
    url = cfg.fiveprotocol_news_url
    sep = "&" if "?" in url else "?"
    url = f"{url}{sep}key={urllib.parse.quote(cfg.fiveprotocol_push_key)}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "gbs-bridge/0.1"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = json.loads(r.read().decode("utf-8", "replace"))
    except Exception as exc:
        log.warning("market pulse unavailable: %s", exc)
        return {}
    chain = data.get("chain") or {}
    return {
        "regime": chain.get("vol_regime", "unknown"),
        "risk_score": chain.get("risk_score"),
        "pause": bool(chain.get("pause_new_entries", False)),
        "top_headlines": [i.get("title", "") for i in (data.get("items") or [])[:5]],
        "freshness": data.get("freshness") or {},
    }
