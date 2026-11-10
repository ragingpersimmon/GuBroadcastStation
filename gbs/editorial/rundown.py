"""Build the show rundown: cluster coverage of one event across outlets,
rank by (independent outlets confirming it, urgency, recency), and spread
across desks so the broadcast is global rather than ten copies of one story.

Gu's promise is "confirmed by multiple sources": a story counts as
confirmed when at least two independent news organizations report it
(distinct outlets, so BBC World and BBC Europe count once). Confirmed
stories always outrank single reports; web-only briefs require it."""
from __future__ import annotations

import re
import time

from gbs.models import Segment, Story

_STOP = set("a an the of to in on for and or with at by from as is are was were be after over amid says say said new".split())


def _tokens(title: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9]+", title.lower()) if len(w) > 2 and w not in _STOP}


def _names(text: str) -> set[str]:
    """Capitalised words that aren't sentence starts: people, places, organisations."""
    out = set()
    for m in re.finditer(r"(?<![.!?]\s)(?<!^)\b([A-Z][a-zA-Z\-']{2,})", text or ""):
        w = m.group(1).lower()
        if w not in _STOP:
            out.add(w)
    return out


def outlet_count(members) -> int:
    """Independent organisations among the reports: distinct ownership groups in the
    (internal) source registry, so BBC News + BBC Sport, or two Guardian feeds, count once."""
    from gbs.verify.checker import profile
    return len({profile(m.source)["group"] for m in members})


def _similar(a: set, b: set, threshold: float = 0.45) -> bool:
    if not a or not b:
        return False
    return len(a & b) / len(a | b) >= threshold


def _same_event(t: set, n: set, toks: set, names: set) -> bool:
    if _similar(t, toks):
        return True
    # different headline wording, same event: share 2+ names and a fair share of words
    return len(n & names) >= 2 and _similar(t, toks, 0.2)


def cluster(stories: list[Story]) -> list[list[Story]]:
    clusters: list[tuple[set, set, list[Story]]] = []
    for s in stories:
        t = _tokens(s.title)
        n = _names(s.title) | _names((s.summary or "")[:240])
        for toks, names, members in clusters:
            if _same_event(t, n, toks, names):
                members.append(s)
                toks |= t
                names |= n
                break
        else:
            clusters.append((t, n, [s]))
    return [m for _, _, m in clusters]


def score(members: list[Story], now: float | None = None) -> float:
    now = now or time.time()
    outlets = outlet_count(members)
    urgency = max(m.risk_score for m in members)
    age_h = (now - max(m.ts for m in members)) / 3600
    confirmed = 5.0 if outlets >= 2 else 0.0          # confirmed stories always outrank single reports
    return confirmed + outlets * 1.0 + urgency * 2.0 + max(0.0, 1.0 - age_h / 12)


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
                skip_slugs: set[str] | None = None, min_sources: int = 2) -> list[Segment]:
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
        from gbs.verify.checker import corroborate
        if not corroborate(members, min_sources)["confirmed"]:   # web briefs: confirmed stories only
            continue
        seg = Segment(story=lead, related=[m for m in members if m is not lead])
        per[lead.desk] = per.get(lead.desk, 0) + 1
        if lead.item_hash in skip_slugs:          # already published (keyed by lead report)
            continue
        out.append(seg)
    return out
