"""SQLite story store -- durable history for the site archive and rundowns."""
from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path

from gbs.models import Story

SCHEMA = """
CREATE TABLE IF NOT EXISTS stories (
  item_hash TEXT PRIMARY KEY, desk TEXT, source TEXT, title TEXT,
  summary TEXT, link TEXT, ts REAL, risk_score REAL, regime TEXT,
  keywords TEXT, used_in_rundown INTEGER DEFAULT 0
);
CREATE INDEX IF NOT EXISTS ix_ts ON stories(ts);
"""


class StoryStore:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(str(path))
        self.db.executescript(SCHEMA)

    def add(self, stories: list[Story]) -> int:
        cur = self.db.executemany(
            "INSERT OR IGNORE INTO stories VALUES (?,?,?,?,?,?,?,?,?,?,0)",
            [(s.item_hash, s.desk, s.source, s.title, s.summary, s.link, s.ts,
              s.risk_score, s.regime, json.dumps(s.keywords)) for s in stories])
        self.db.commit()
        return cur.rowcount

    def recent(self, hours: float = 12, unused_only: bool = True) -> list[Story]:
        q = "SELECT item_hash,desk,source,title,summary,link,ts,risk_score,regime,keywords FROM stories WHERE ts>=?"
        if unused_only:
            q += " AND used_in_rundown=0"
        rows = self.db.execute(q + " ORDER BY ts DESC", (time.time() - hours * 3600,)).fetchall()
        return [Story(*r[:9], keywords=json.loads(r[9] or "[]")) for r in rows]

    def mark_used(self, hashes: list[str]) -> None:
        self.db.executemany("UPDATE stories SET used_in_rundown=1 WHERE item_hash=?", [(h,) for h in hashes])
        self.db.commit()
