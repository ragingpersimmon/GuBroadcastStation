"""Newsroom: talent, the assignment desk (Dex Okafor: desk -> reporter)
and the show clock (which anchor is on air right now)."""
from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

NEWSROOM_PATH = Path(__file__).resolve().parents[2] / "config" / "newsroom.json"


def load_newsroom(path: Path = NEWSROOM_PATH) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def load_roster(path: Path = NEWSROOM_PATH) -> list[dict]:
    """On-air talent only (anchors, AI anchors, reporters)."""
    return [t for t in load_newsroom(path)["talent"] if t.get("kind") != "production"]


def by_id(nr: dict, tid: str) -> dict:
    for t in nr["talent"]:
        if t["id"] == tid:
            return t
    raise KeyError(tid)


def presenter_for_desk(desk: str, nr: dict, fallback: dict) -> dict:
    """Assignment desk: the reporter who owns this desk, else the show anchor."""
    for t in nr["talent"]:
        if t.get("kind") == "reporter" and desk in t.get("desks", []):
            return t
    return fallback


def _hm(s: str) -> int:
    h, m = s.split(":")
    return int(h) * 60 + int(m)


def now_local() -> datetime:
    return datetime.now(ZoneInfo(os.getenv("GBS_TZ", "America/Vancouver")))


def current_show(nr: dict, now: datetime | None = None) -> dict:
    now = now or now_local()
    mins = now.hour * 60 + now.minute
    for show in nr["shows"]:
        if show.get("default"):
            continue
        if now.weekday() in show["days"] and _hm(show["start"]) <= mins < _hm(show["end"]):
            return show
    return next(s for s in nr["shows"] if s.get("default"))


def should_render(show: dict, now: datetime | None = None) -> bool:
    now = now or now_local()
    return (now.minute // 15) in show.get("render_quarters", [0])
