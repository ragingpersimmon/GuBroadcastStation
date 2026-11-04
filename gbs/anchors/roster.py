from __future__ import annotations

import json
from pathlib import Path

ROSTER_PATH = Path(__file__).resolve().parents[2] / "config" / "anchors.json"


def load_roster(path: Path = ROSTER_PATH) -> list[dict]:
    return json.loads(path.read_text())["anchors"]


def anchor_for_desk(desk: str, roster: list[dict]) -> dict:
    for a in roster:
        if desk in a.get("desks", []):
            return a
    return roster[0]
