"""Build the show rundown: cluster duplicate coverage of one event,
rank by (outlets covering it, urgency, recency), and spread across desks
so the broadcast is actually global rather than ten copies of one story."""
from __future__ import annotations

import re
import time

from gbs.models import Segment, Story

_STOP = set("a an the of to in on for and or with at by from as is are was were be after over amid says say said new".split())


def _tokens(title: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9]+", title.lower()) if len(w) > 2 and w not in _STOP}


def _similar(a: set, b: set, threshold: float = 0.45) -> bool:
    if not a or not b:
        return False
    return len(a & b) / len(a | b) >= threshold


def cluster(stories: list[Story]) -> list[list[Story]]:
    clusters: list[tuple[set, list[Story]]] = []
    for s in stories:
        t = _tokens(s.title)
        for toks, members in clusters:
            if _similar(t, toks):
                members.append(s)
                toks |= t
                break
        else:
            clusters.append((t, [s]))
    return [m for _, m in clusters]


def score(members: list[Story], now: float | None = None) -> float:
    now = now or time.time()
    outlets = len({m.source.split(":")[-1] for m in members})
    urgency = max(m.risk_score for m in members)
    age_h = (now - max(m.ts for m in members)) / 3600
    return outlets * 1.0 + urgency * 2.0 + max(0.0, 1.0 - age_h / 12)


def build_rundown(stories: list[Story], size: int = 12, per_desk_cap: int = 3) -> list[Segment]:
    ranked = sorted(cluster(stories), key=score, reverse=True)
    per_desk: dict[str, int] = {}
    out: list[Segment] = []
    for members in ranked:
        lead = max(members, key=lambda m: (len(m.summary), m.risk_score))
        if per_desk.get(lead.desk, 0) >= per_desk_cap:
            continue
        per_desk[lead.desk] = per_desk.get(lead.desk, 0) + 1
        out.append(Segment(story=lead, related=[m for m in members if m is not lead]))
        if len(out) >= size:
            break
    return out


def desk_briefs(stories: list[Story], taken: set[str], per_desk: int = 3,
                skip_slugs: set[str] | None = None) -> list[Segment]:
    """Web-only stories: the best clusters per desk that didn't make the broadcast,
    so thin sections (Sports, Science, sub-regions) still fill up. `taken` holds
    item_hashes already in the rundown; `skip_slugs` are already-published pages."""
    skip_slugs = skip_slugs or set()
    per: dict[str, int] = {}
    out: list[Segment] = []
    for members in sorted(cluster(stories), key=score, reverse=True):
        if any(m.item_hash in taken for m in members):
            continue
        lead = max(members, key=lambda m: (len(m.summary), m.risk_score))
        if lead.desk in ("weather", "traffic") or per.get(lead.desk, 0) >= per_desk:
            continue
        seg = Segment(story=lead, related=[m for m in members if m is not lead])
        per[lead.desk] = per.get(lead.desk, 0) + 1
        if seg.slug in skip_slugs:
            continue
        out.append(seg)
    return out
