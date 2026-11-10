"""External checks that strengthen (never replace) the source checker.

    gdelt_coverage   GDELT DOC 2.0 (free, no key): how widely the event is covered worldwide
                     right now. Shown as "wider coverage" and used to rank; it never confirms a
                     story on its own (GDELT indexes every kind of site).
    factcheck_flags  Google Fact Check Tools claim search (free, API key in
                     GOOGLE_FACTCHECK_API_KEY): if fact-checkers recently rated a matching claim
                     false/misleading, the story is held back for a human look.
    fulltext         trafilatura (optional, GBS_FULLTEXT=1): pulls the full text of source
                     articles, robots.txt respected, cached, INTERNAL ONLY, so facts can be
                     cross-checked against more than feed summaries.

All three are cached under $GBS_DATA_DIR/verify_cache/, time-boxed, and off when
GBS_LIVE_DATA=0 (tests). Any failure = "no signal", never a crash.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import time
import urllib.parse
import urllib.request
import urllib.robotparser
from pathlib import Path

log = logging.getLogger("gbs.verify.external")
UA = "GuBroadcastStation-verify/1.0 (+https://gubs.ca/about/standards/)"
GDELT = "https://api.gdeltproject.org/api/v2/doc/doc"
FACTCHECK = "https://factchecktools.googleapis.com/v1alpha1/claims:search"
FALSE_RX = re.compile(r"false|fake|misleading|incorrect|pants on fire|no evidence|fabricat|hoax|baseless|"
                      r"distort|unsupported|wrong|faux|falso|거짓|虚假|誤り", re.I)
_last_gdelt = [0.0]
_gdelt_calls = [0]   # per process = per edition; GDELT's 5 s spacing makes each call cost time


def _live() -> bool:
    return os.getenv("GBS_LIVE_DATA", "1") != "0"


def _get_json(url: str, timeout: int = 12):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = r.read()
    return json.loads(raw) if raw.strip() else {}


class Cache:
    def __init__(self, data_dir: Path, name: str, ttl: int):
        self.path, self.ttl = Path(data_dir) / "verify_cache" / f"{name}.json", ttl
        try:
            self.d = json.loads(self.path.read_text())
        except Exception:
            self.d = {}

    def get(self, key):
        v = self.d.get(key)
        return v["v"] if v and time.time() - v["t"] < self.ttl else None

    def put(self, key, value):
        self.d[key] = {"t": time.time(), "v": value}
        now = time.time()
        self.d = {k: v for k, v in self.d.items() if now - v["t"] < self.ttl}   # prune
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.d))


def query_terms(names: list[str], headline: str, n: int = 4) -> list[str]:
    """Most specific terms: names confirmed by 2+ reports first, then long headline words."""
    out = [x for x in names if len(x) > 3][:n]
    if len(out) < 2:
        words = sorted({w for w in re.findall(r"[a-z]{5,}", headline.lower())}, key=len, reverse=True)
        out += [w for w in words if w not in out][: n - len(out)]
    return out


# ------------------------------------------------------------------ GDELT

def gdelt_coverage(data_dir: Path, terms: list[str], http=_get_json) -> dict | None:
    if not _live() or os.getenv("GBS_GDELT", "1") == "0" or len(terms) < 2:
        return None
    key = " ".join(sorted(terms))
    cache = Cache(data_dir, "gdelt", 3 * 3600)
    hit = cache.get(key)
    if hit is not None:
        return hit
    if _gdelt_calls[0] >= int(os.getenv("GBS_GDELT_MAX", "10")):
        return None
    _gdelt_calls[0] += 1
    wait = 5.2 - (time.time() - _last_gdelt[0])          # GDELT allows 1 request / 5 s
    if wait > 0:
        time.sleep(wait)
    q = " ".join(f'"{t}"' if " " in t else t for t in terms)
    url = GDELT + "?" + urllib.parse.urlencode({"query": q, "mode": "ArtList", "format": "json",
                                                "maxrecords": 75, "timespan": "48h", "sort": "DateDesc"})
    try:
        _last_gdelt[0] = time.time()
        arts = (http(url) or {}).get("articles", [])
    except Exception as exc:
        log.info("gdelt: %s", exc)
        return None
    res = {"articles": len(arts), "domains": len({a.get("domain") for a in arts if a.get("domain")}),
           "countries": len({a.get("sourcecountry") for a in arts if a.get("sourcecountry")}),
           "languages": len({a.get("language") for a in arts if a.get("language")})}
    cache.put(key, res)
    return res


# ------------------------------------------------------------------ Google Fact Check Tools

def factcheck_flags(data_dir: Path, terms: list[str], headline: str, http=_get_json) -> list[dict]:
    key = os.getenv("GOOGLE_FACTCHECK_API_KEY", "").strip()
    if not key or not _live() or len(terms) < 2:
        return []
    q = " ".join(terms)
    cache = Cache(data_dir, "factcheck", 6 * 3600)
    hit = cache.get(q)
    if hit is None:
        url = FACTCHECK + "?" + urllib.parse.urlencode({"query": q, "maxAgeDays": 30, "pageSize": 20, "key": key})
        try:
            hit = (http(url) or {}).get("claims", [])
        except Exception as exc:
            log.info("factcheck: %s", exc)
            return []
        cache.put(q, hit)
    mine = set(re.findall(r"[a-z]{4,}", headline.lower())) | {t.lower() for t in terms}
    flags = []
    for c in hit:
        text = c.get("text", "")
        overlap = mine & set(re.findall(r"[a-z]{4,}", text.lower()))
        for r in c.get("claimReview", []):
            if FALSE_RX.search(r.get("textualRating", "")) and len(overlap) >= max(2, len(mine) // 3):
                flags.append({"claim": text[:200], "rating": r.get("textualRating", ""),
                              "reviewer": (r.get("publisher") or {}).get("name", ""), "url": r.get("url", "")})
    return flags


# ------------------------------------------------------------------ full text (internal only)

_robots: dict[str, urllib.robotparser.RobotFileParser | None] = {}


def _allowed(url: str) -> bool:
    host = urllib.parse.urlsplit(url)
    base = f"{host.scheme}://{host.netloc}"
    if base not in _robots:
        rp = urllib.robotparser.RobotFileParser(base + "/robots.txt")
        try:
            rp.read()
        except Exception:
            rp = None
        _robots[base] = rp
    rp = _robots[base]
    return bool(rp and rp.can_fetch(UA, url))


def fulltext(data_dir: Path, url: str) -> str:
    """Article body for internal cross-checking only. Never published, never shown to the writer."""
    if os.getenv("GBS_FULLTEXT", "0") != "1" or not _live() or not url.startswith("http"):
        return ""
    try:
        import trafilatura
    except ImportError:
        return ""
    d = Path(data_dir) / "verify_cache" / "fulltext"
    f = d / (hashlib.sha1(url.encode()).hexdigest() + ".txt")
    if f.is_file() and time.time() - f.stat().st_mtime < 3 * 86400:
        return f.read_text()
    if not _allowed(url):
        return ""
    try:
        html = trafilatura.fetch_url(url)
        text = (trafilatura.extract(html, include_comments=False, include_tables=False) or "")[:20000]
    except Exception as exc:
        log.info("fulltext %s: %s", url, exc)
        return ""
    d.mkdir(parents=True, exist_ok=True)
    f.write_text(text)
    return text
