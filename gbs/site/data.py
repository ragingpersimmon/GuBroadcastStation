"""Published-article store + site taxonomy.

Every edition upserts its segments here, so the site has history:
sections, archives, people pages and search all build from this table,
not just from the current rundown."""
from __future__ import annotations

import json
import re
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path

# Top-level sections -> desks they contain. Order = nav order.
SECTIONS = [
    {"id": "world", "name": "World", "path": "/world/", "desks": ["world", "americas", "europe", "asia", "mideast", "africa"],
     "subs": [("americas", "Americas"), ("europe", "Europe"), ("asia", "Asia-Pacific"), ("mideast", "Middle East"), ("africa", "Africa")]},
    {"id": "politics", "name": "Politics", "path": "/politics/", "desks": ["politics"], "subs": []},
    {"id": "business", "name": "Business", "path": "/business/", "desks": ["business", "markets", "consumer"],
     "subs": [("markets", "Markets"), ("consumer", "Consumer")]},
    {"id": "tech", "name": "Tech", "path": "/tech/", "desks": ["tech"], "subs": []},
    {"id": "science", "name": "Science", "path": "/science/", "desks": ["science"], "subs": []},
    {"id": "entertainment", "name": "Entertainment", "path": "/entertainment/", "desks": ["entertainment"], "subs": []},
    {"id": "sports", "name": "Sports", "path": "/sports/", "desks": ["sports"], "subs": []},
    {"id": "local", "name": "Local", "path": "/local/", "desks": ["weather", "traffic"],
     "subs": [("weather", "Weather"), ("traffic", "Traffic")]},
]
DESK_NAMES = {"world": "World", "americas": "Americas", "europe": "Europe", "asia": "Asia-Pacific",
              "mideast": "Middle East", "africa": "Africa", "politics": "Politics", "business": "Business",
              "markets": "Markets", "consumer": "Consumer", "tech": "Tech", "science": "Science",
              "entertainment": "Entertainment", "sports": "Sports", "weather": "Weather", "traffic": "Traffic"}


def section_of(desk: str) -> dict:
    for s in SECTIONS:
        if desk in s["desks"]:
            return s
    return SECTIONS[0]


def desk_path(desk: str) -> str:
    sec = section_of(desk)
    if desk == sec["id"] or desk not in dict(sec["subs"]):
        return sec["path"]
    return f"{sec['path']}{desk}/"


SCHEMA = """
CREATE TABLE IF NOT EXISTS published (
  slug TEXT PRIMARY KEY, ts REAL, story_ts REAL, show_id TEXT, desk TEXT, title TEXT,
  standfirst TEXT, script TEXT, presenter TEXT, presenter_title TEXT, sources TEXT,
  sponsor_read TEXT, video TEXT, risk REAL
);
CREATE INDEX IF NOT EXISTS ix_pub_ts ON published(ts);
"""
COLS = ["slug", "ts", "story_ts", "show_id", "desk", "title", "standfirst", "script", "presenter",
        "presenter_title", "sources", "sponsor_read", "video", "risk"]


def standfirst(script: str, title: str) -> str:
    first = re.split(r"(?<=[.!?])\s", (script or "").strip())
    for s in first:
        if s and s.strip(". ").lower() != title.strip(". ").lower():
            return s[:280]
    return ""


class PublishedStore:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(str(path))
        self.db.executescript(SCHEMA)

    def upsert(self, rows: list[dict]) -> None:
        for r in rows:
            old = self.db.execute("SELECT ts, video FROM published WHERE slug=?", (r["slug"],)).fetchone()
            if old:  # keep first-published time; keep a video once we have one
                r["ts"] = old[0]
                r["video"] = r.get("video") or old[1]
            self.db.execute(f"INSERT OR REPLACE INTO published ({','.join(COLS)}) VALUES ({','.join('?' * len(COLS))})",
                            [json.dumps(r[c]) if c == "sources" else r.get(c) for c in COLS])
        self.db.commit()

    def slugs(self) -> set[str]:
        return {r[0] for r in self.db.execute("SELECT slug FROM published")}

    def recent(self, days: int = 30) -> list[dict]:
        rows = self.db.execute(f"SELECT {','.join(COLS)} FROM published WHERE ts>=? ORDER BY ts DESC",
                               (time.time() - days * 86400,)).fetchall()
        out = []
        for row in rows:
            d = dict(zip(COLS, row))
            d["sources"] = json.loads(d["sources"] or "[]")   # internal only: never rendered
            out.append(public_view(d))
        return out


_TITLE_TAIL = re.compile(r"\s+[-|\u2013\u2014]\s+(BBC( News| Sport)?|The Guardian|NPR|Al Jazeera|DW|France 24|"
                         r"Global News|UN News|NHK( WORLD)?|The Korea Herald|Ars Technica|NASA|Reuters|AP News|CNBC|"
                         r"ESPN|The Verge|MarketWatch|ScienceDaily)\s*$", re.I)


def public_view(a: dict) -> dict:
    """What the public may see of a stored story. Sources stay confidential
    (Ric, 2026-11-06): outlet names come out of the text, and stories written
    by the old no-LLM template (headline + the feed's own first sentence +
    "according to ...") fall back to the headline only, since that sentence
    was the outlet's words, not ours."""
    from gbs.editorial.scriptwriter import scrub_outlets
    title = _TITLE_TAIL.sub("", a.get("title") or "").strip()
    script = a.get("script") or ""
    if re.search(r"Full sourcing is on our site|That's according to", script):
        script = f"{title.rstrip('.')}."
    script = scrub_outlets(script)
    return {**a, "title": title, "script": script, "standfirst": standfirst(script, title)}


def article_url(a: dict) -> str:
    d = datetime.fromtimestamp(a["ts"], timezone.utc)
    return f"/story/{d:%Y/%m/%d}/{a['slug']}.html"
