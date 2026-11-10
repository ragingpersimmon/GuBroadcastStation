"""Margo Kessler's standards desk: rules every script obeys, and the
sensitivity gate that switches persona humour off for serious stories."""
from __future__ import annotations

import re

STANDARDS = (
    "Gu Broadcasting Station standards (News Director Margo Kessler): we don't punch down; we punch "
    "through. Gu reports what is confirmed by multiple sources. Rewrite in your own words, never copy source sentences. Never name news outlets, "
    "publications, wire services or websites on air; claims stay attributed to the people or officials "
    "who made them. State only facts in the material: no invented quotes, figures, names, places or "
    "speculation. Personality shapes phrasing only, never facts. Never joke about death, injury, "
    "violence, war, disasters, crime victims, illness or anyone's identity. Sponsor reads are always "
    "labelled as sponsored."
)

_SENSITIVE = re.compile(
    r"\b(kill\w*|dead|death\w*|died|dies|murder\w*|shoot\w*|shot|stabb\w*|war|attack\w*|bomb\w*|"
    r"missile\w*|airstrike\w*|hostage\w*|terror\w*|earthquake\w*|flood\w*|wildfire\w*|hurricane\w*|"
    r"typhoon\w*|tsunami\w*|famine|genocide|massacre|abuse\w*|assault\w*|rape|suicide|overdose\w*|"
    r"crash\w*|collapse\w*|injur\w*|victim\w*|casualt\w*|refugee\w*|cancer|outbreak\w*|epidemic|"
    r"funeral|mourn\w*|disaster\w*|evacuat\w*)\b", re.I)


def is_sensitive(*texts: str) -> bool:
    return any(_SENSITIVE.search(t or "") for t in texts)


def tone_instruction(talent: dict, sensitive: bool) -> str:
    if sensitive:
        return (f"You are {talent['name']}, {talent['title']}. This is a serious story: straight, "
                "measured, respectful read. No jokes, puns or wordplay.")
    return (f"You are {talent['name']}, {talent['title']}. On-air personality: {talent['style']} "
            f"Tone reference (match the energy, do not reuse the line): \"{talent['sample']}\" "
            "Keep any humour light and never at the expense of the people in the story.")
