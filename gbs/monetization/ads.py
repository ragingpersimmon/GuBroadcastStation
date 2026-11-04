"""Sponsors, on-air reads and web ad slots."""
from __future__ import annotations

import html
import json
from pathlib import Path

from gbs.models import Segment

SPONSORS_PATH = Path(__file__).resolve().parents[2] / "config" / "sponsors.json"


class AdBook:
    def __init__(self, path: Path = SPONSORS_PATH):
        self.cfg = json.loads(path.read_text())
        self.sponsors = [s for s in self.cfg.get("sponsors", []) if s.get("active")]
        self._rot = 0

    def _pick(self, desk: str) -> dict | None:
        pool = [s for s in self.sponsors if not s.get("desks") or desk in s["desks"]]
        if not pool:
            return None
        s = pool[self._rot % len(pool)]
        self._rot += 1
        return s

    def assign_on_air(self, rundown: list[Segment], write_fn=None) -> None:
        """Every Nth segment carries a labelled sponsor read. write_fn(sponsor, seg)
        lets the presenter voice it (scriptwriter.write_sponsor_read)."""
        every = max(1, int(self.cfg.get("on_air_every_n_segments", 4)))
        for i, seg in enumerate(rundown):
            if i and i % every == 0:
                s = self._pick(seg.story.desk)
                if s and s.get("on_air"):
                    seg.sponsor_read = (write_fn(s, seg) if write_fn
                                        else f"Sponsored by {s['name']}. {s['on_air']}")

    def web_slot(self, slot: str, desk: str = "world") -> str:
        net = self.cfg.get("ad_network", {})
        if net.get("enabled") and net.get("slots", {}).get(slot):
            return (f'<ins class="adsbygoogle" style="display:block" data-ad-client="{html.escape(net["client_id"])}" '
                    f'data-ad-slot="{html.escape(net["slots"][slot])}" data-ad-format="auto"></ins>'
                    '<script>(adsbygoogle=window.adsbygoogle||[]).push({});</script>')
        s = self._pick(desk)
        if not s or not s.get("web"):
            return ""
        w = s["web"]
        return (f'<aside class="ad ad-{slot}"><span class="ad-label">Sponsored</span>'
                f'<a href="{html.escape(w["url"])}" rel="sponsored"><strong>{html.escape(w["headline"])}</strong>'
                f'<span>{html.escape(w.get("body", ""))}</span></a></aside>')

    def head_tag(self) -> str:
        net = self.cfg.get("ad_network", {})
        if not net.get("enabled"):
            return ""
        return ('<script async src="https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js'
                f'?client={html.escape(net["client_id"])}" crossorigin="anonymous"></script>')

    def ads_txt(self) -> str:
        net = self.cfg.get("ad_network", {})
        return net.get("ads_txt", "") if net.get("enabled") else ""
