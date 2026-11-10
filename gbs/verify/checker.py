"""Active source checker + originality and neutrality gates.

Every story goes through `verify()` after the LLM writes it. A story is
published only when it is (a) corroborated by >= MIN_SOURCES independent news
organisations (distinct ownership groups, trusted enough, at least one of them
a news organisation rather than an official source), (b) original: its
headline and script share no run of ORIG_RUN+ words with any source title or
summary and no source headline is reused, and (c) neutral: no loaded words.
Facts that appear in only one report are passed to the writer as
"unconfirmed: leave out", so the script carries only cross-checked facts.
"""
from __future__ import annotations

import json
import os
import re
import time
import unicodedata
from functools import lru_cache
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
REGISTRY = REPO / "config" / "source_registry.json"
ORIG_RUN = 6            # longest allowed shared run of words with any source text
MIN_WEIGHT = 0.5        # outlets below this can't confirm
WINDOW_H = 72           # corroborating reports must be within this many hours of each other

LOADED = {
    # sensational / editorialising words a neutral wire read avoids (whole words, case-insensitive)
    "shocking", "stunning", "slams", "slammed", "blasts", "blasted", "destroys", "destroyed by", "epic",
    "outrageous", "disgraceful", "heroic", "evil", "radical", "extremist", "regime", "terrorist",
    "thug", "thugs", "brutal", "horrific", "catastrophic", "chaos", "meltdown", "bombshell", "explosive",
    "jaw-dropping", "mind-blowing", "unbelievable", "slaughter", "massacre", "genius", "idiot",
    "liar", "hoax", "fake news", "woke", "so-called", "admits", "finally", "clearly", "obviously",
    "of course", "notorious", "infamous", "controversial", "embattled", "hardline", "firebrand",
}
# words that are fine when quoting an official finding; they are allowed when the source reports use them too
_ALLOW_IF_IN_SOURCES = {"terrorist", "massacre", "regime", "extremist", "controversial", "hardline", "catastrophic"}

_STOP = set("a an the of to in on at for and or but with by from as is are was were be been it its this that "
            "these those has have had will would can could may might says said say new over after before into "
            "about up out more than amid".split())


@lru_cache(maxsize=1)
def registry() -> dict:
    try:
        return json.loads(REGISTRY.read_text())["outlets"]
    except Exception:
        return {}


def outlet_of(source_key: str) -> str:
    from gbs.editorial.scriptwriter import outlet_name
    return outlet_name(source_key)


def profile(source_key: str) -> dict:
    name = outlet_of(source_key)
    p = registry().get(name)
    if p:
        return {"name": name, **p}
    # unknown outlet: its own group, untrusted until reviewed
    return {"name": name, "group": f"unknown:{name}", "country": "?", "type": "unknown", "weight": 0.0}


# ------------------------------------------------------------------ text helpers

def _norm(text: str) -> str:
    text = unicodedata.normalize("NFKD", text or "")
    return text.replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')


def words(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+(?:'[a-z]+)?", _norm(text).lower())


def numbers(text: str) -> set[str]:
    """Figures as written, normalised: 1,200 -> 1200; 3.5% -> 3.5%; '12 million' -> 12million."""
    out = set()
    for m in re.finditer(r"(\d[\d,]*(?:\.\d+)?)\s*(%|percent|per cent|million|billion|trillion|bn|m\b)?", _norm(text), re.I):
        n = m.group(1).replace(",", "")
        unit = (m.group(2) or "").lower().replace("percent", "%").replace("per cent", "%").replace("bn", "billion")
        if unit == "m":
            unit = "million"
        if len(n) == 4 and n.startswith(("19", "20")) and not unit:
            continue                      # years aren't claims
        out.add(n + unit)
    return out


def names(text: str) -> set[str]:
    """Proper nouns not at a sentence start."""
    out = set()
    for sent in re.split(r"(?<=[.!?])\s+", _norm(text)):
        toks = re.findall(r"[A-Za-z][A-Za-z'\-]+", sent)
        for t in toks[1:]:
            if t[0].isupper() and t.lower() not in _STOP and len(t) > 2:
                out.add(t.lower())
    return out


# ------------------------------------------------------------------ corroboration

def corroborate(members: list, min_sources: int = 2) -> dict:
    """members: Story objects on one event. Independent = distinct ownership groups,
    trusted (weight >= MIN_WEIGHT), within WINDOW_H of the newest report."""
    newest = max((m.ts for m in members), default=time.time())
    groups: dict[str, dict] = {}
    for m in members:
        p = profile(m.source)
        if p["weight"] < MIN_WEIGHT or newest - m.ts > WINDOW_H * 3600:
            continue
        groups.setdefault(p["group"], p)
    news_orgs = [p for p in groups.values() if p["type"] != "official"]
    countries = {p["country"] for p in groups.values()}
    n = len(groups)
    confirmed = n >= min_sources and len(news_orgs) >= 1
    return {"independent": n, "countries": len(countries), "official": len(groups) - len(news_orgs),
            "confirmed": confirmed, "unknown_outlets": sorted({profile(m.source)["name"] for m in members
                                                                if profile(m.source)["type"] == "unknown"})}


def cross_check(members: list) -> dict:
    """Facts (figures, names) found in 2+ independent groups are confirmed; in one group only, unconfirmed."""
    by_group: dict[str, dict] = {}
    for m in members:
        g = profile(m.source)["group"]
        t = f"{m.title}. {m.summary}"
        f = by_group.setdefault(g, {"numbers": set(), "names": set()})
        f["numbers"] |= numbers(t)
        f["names"] |= names(t)
    def tally(kind):
        seen: dict[str, int] = {}
        for f in by_group.values():
            for x in f[kind]:
                seen[x] = seen.get(x, 0) + 1
        return seen
    nums, nms = tally("numbers"), tally("names")
    multi = len(by_group) >= 2
    conf_n = sorted(k for k, v in nums.items() if v >= 2)
    conf_names = sorted(k for k, v in nms.items() if v >= 2)
    unconf_n = sorted(k for k, v in nums.items() if v < 2) if multi else []
    return {"confirmed_numbers": conf_n, "unconfirmed_numbers": unconf_n,
            "confirmed_names": conf_names, "groups": len(by_group)}


# ------------------------------------------------------------------ originality + neutrality

def _runs(a: list[str], b: list[str]) -> int:
    """Longest common run of words (dynamic programming, short texts)."""
    best, prev = 0, [0] * (len(b) + 1)
    for x in a:
        cur = [0] * (len(b) + 1)
        for j, y in enumerate(b, 1):
            if x == y:
                cur[j] = prev[j - 1] + 1
                if cur[j] > best:
                    best = cur[j]
        prev = cur
    return best


def originality(headline: str, script: str, members: list) -> dict:
    mine = words(f"{headline} . {script}")
    longest, reused = 0, False
    for m in members:
        src = words(f"{m.title} . {m.summary}")
        longest = max(longest, _runs(mine, src))
        if words(headline) and words(headline) == words(m.title):
            reused = True
    # a run made only of a multi-word name (e.g. 'united nations security council') is not copying;
    # ORIG_RUN is set high enough that names alone rarely reach it
    return {"longest_shared_run": longest, "headline_reused": reused,
            "ok": longest < ORIG_RUN and not reused}


def neutrality(text: str, members: list | None = None) -> dict:
    t = " " + _norm(text).lower() + " "
    src = " ".join(_norm(f"{m.title} {m.summary}").lower() for m in members or [])
    hits = []
    for w in LOADED:
        if re.search(rf"(?<![a-z]){re.escape(w)}(?![a-z])", t):
            if w in _ALLOW_IF_IN_SOURCES and re.search(rf"(?<![a-z]){re.escape(w)}(?![a-z])", src):
                continue
            hits.append(w)
    exclam = text.count("!")
    return {"loaded": sorted(hits), "exclamations": exclam, "ok": not hits and exclam == 0}


def unconfirmed_used(script: str, facts: dict) -> list[str]:
    used = numbers(script)
    return sorted(x for x in used if x in set(facts.get("unconfirmed_numbers", [])))


# ------------------------------------------------------------------ the gate

def verify(headline: str, script: str, members: list, min_sources: int | None = None) -> dict:
    min_sources = int(os.getenv("GBS_MIN_SOURCES", "2")) if min_sources is None else min_sources
    c = corroborate(members, min_sources)
    f = cross_check(members)
    o = originality(headline, script, members)
    n = neutrality(f"{headline} {script}", members)
    bad_facts = unconfirmed_used(script, f)
    problems = []
    if not c["confirmed"]:
        problems.append(f"only {c['independent']} independent source(s)")
    if not o["ok"]:
        problems.append("reuses a source headline" if o["headline_reused"]
                        else f"copies a {o['longest_shared_run']}-word run from a source")
    if not n["ok"]:
        problems.append("loaded language: " + ", ".join(n["loaded"]) if n["loaded"] else "exclamation marks")
    if bad_facts:
        problems.append("uses figures only one source reports: " + ", ".join(bad_facts))
    if not headline.strip() or len(words(script)) < 25:
        problems.append("no rewritten headline/script")
    return {"publish": not problems, "problems": problems, "corroboration": c,
            "facts": {"confirmed": len(f["confirmed_numbers"]) + len(f["confirmed_names"]),
                      "unconfirmed_dropped": len(f["unconfirmed_numbers"])},
            "originality": o, "neutrality": n, "checked": int(time.time())}


def public_summary(v: dict | None) -> dict | None:
    """What a reader may see: counts and pass/fail. No outlet names, ever."""
    if not v:
        return None
    c = v.get("corroboration", {})
    return {"independent": c.get("independent", 0), "countries": c.get("countries", 0),
            "facts_confirmed": v.get("facts", {}).get("confirmed", 0),
            "facts_dropped": v.get("facts", {}).get("unconfirmed_dropped", 0),
            "original": v.get("originality", {}).get("ok", False),
            "neutral": v.get("neutrality", {}).get("ok", False), "checked": v.get("checked")}
