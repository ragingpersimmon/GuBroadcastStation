"""Test helpers for the verification engine."""
import re


def verified(segs, keep_titles=True):
    """Mark hand-built test segments as verified + rewritten (unit tests of the site
    builder, not of the checker). The headline stays the test title so assertions read naturally."""
    for s in segs:
        s.headline = s.headline or s.story.title
        s.verify = {"publish": True, "corroboration": {"independent": 1 + len(s.related), "countries": 1},
                    "facts": {"confirmed": 0, "unconfirmed_dropped": 0},
                    "originality": {"ok": True}, "neutrality": {"ok": True}, "checked": 0}
    return segs


def fake_chat(cfg, system, user, timeout=0):
    """Deterministic stand-in for the LLM: an original headline (sorted words of the first
    report, so no source run survives) and a fixed original read."""
    if "HEADLINE:" not in system:   # bookends, sponsor reads, opens
        return "Here is the latest from the Gu newsroom."
    first = re.search(r"Report 1: (.+?)\. ", user)
    ws = sorted(set(re.findall(r"[a-z]+", (first.group(1) if first else "story").lower())))
    head = "Gu summary " + " ".join(ws[:6])
    read = ("Gu has reviewed independent reports on this development and presents only the points they "
            "share, with each claim attributed to the people who made it. Officials gave no further detail "
            "today, and the newsroom will update this account when additional confirmation arrives.")
    return f"HEADLINE: {head}\nREAD: {read}"
