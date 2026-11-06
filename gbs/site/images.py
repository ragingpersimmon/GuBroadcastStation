"""Topical stock images for cards and story pages, from Openverse.

Openverse (api.openverse.org) federates openly licensed images. We take only
CC0 and Public Domain Mark images: free for commercial use, no attribution
required (so nothing on the page points at a source). Each desk has a few
scene/object keywords (no people-centred queries), images are downloaded once
into $GBS_DATA_DIR/stock/ and copied to /img/stock/ on build. A story gets a
stable pick from its desk's pool. Every image is labelled "Illustrative image"
on the page: it shows the topic, never the event.

Pool refreshes weekly; GBS_LIVE_DATA=0 never touches the network.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import shutil
import time
import urllib.parse
import urllib.request
from pathlib import Path

log = logging.getLogger("gbs.images")

API = "https://api.openverse.org/v1/images/"
UA = "GuBroadcastStation/1.0 (+https://gubs.ca)"
OK_LICENSES = {"cc0", "pdm"}
PER_QUERY = 6
TTL = 7 * 86400

KEYWORDS = {
    "world": ["globe map", "world map", "city skyline night"],
    "americas": ["toronto skyline", "mountains canada", "new york skyline"],
    "europe": ["european city rooftops", "brussels", "old town square"],
    "asia": ["tokyo street night", "seoul skyline", "temple roof asia"],
    "mideast": ["desert dunes", "old city stone architecture", "dubai skyline"],
    "africa": ["nairobi skyline", "savanna landscape", "cape town"],
    "politics": ["parliament building", "ballot box", "government building columns"],
    "business": ["office towers", "shipping containers port", "factory"],
    "markets": ["stock market chart", "trading screen", "financial district"],
    "consumer": ["grocery store shelves", "shopping cart", "receipt cash"],
    "tech": ["circuit board", "server room", "computer code screen"],
    "science": ["laboratory glassware", "telescope", "nebula space"],
    "entertainment": ["cinema seats", "concert stage lights", "theatre stage"],
    "sports": ["stadium lights", "hockey rink", "soccer field"],
    "weather": ["rain clouds", "storm clouds sky", "sunset clouds"],
    "traffic": ["highway traffic night", "bridge traffic", "city road"],
}


def _get(url: str, timeout: int = 15) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json, image/*"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def _search(q: str) -> list[dict]:
    qs = urllib.parse.urlencode({"q": q, "license": ",".join(sorted(OK_LICENSES)), "mature": "false",
                                 "aspect_ratio": "wide", "page_size": PER_QUERY * 2})
    data = json.loads(_get(f"{API}?{qs}"))
    out = []
    for r in data.get("results", []):
        if (r.get("license") or "").lower() not in OK_LICENSES or not r.get("id"):
            continue
        out.append(r)
        if len(out) >= PER_QUERY:
            break
    return out


def refresh(stock_dir: Path) -> dict:
    """Search every desk, download thumbnails, write pool.json. Returns the pool."""
    pool: dict[str, list[dict]] = {}
    stock_dir.mkdir(parents=True, exist_ok=True)
    for desk, words in KEYWORDS.items():
        items = []
        for w in words:
            try:
                results = _search(w)
            except Exception as exc:
                log.warning("openverse search %r failed: %s", w, exc)
                continue
            for r in results:
                f = stock_dir / f"{r['id']}.jpg"
                if not f.is_file():
                    try:
                        f.write_bytes(_get(r.get("thumbnail") or f"{API}{r['id']}/thumb/"))
                    except Exception as exc:
                        log.warning("thumb %s failed: %s", r["id"], exc)
                        continue
                if f.stat().st_size < 4000:      # error page / placeholder, not a photo
                    f.unlink(missing_ok=True)
                    continue
                # licence + landing page kept for our own audit trail only (never published)
                items.append({"id": r["id"], "file": f.name, "license": r.get("license"),
                              "landing": r.get("foreign_landing_url"), "q": w})
            time.sleep(0.5)                      # stay well inside anonymous rate limits
        if items:
            pool[desk] = items
    if pool:
        (stock_dir / "pool.json").write_text(json.dumps({"ts": time.time(), "pool": pool}, indent=1))
    return pool


def load_pool(data_dir: Path) -> dict:
    stock = Path(data_dir) / "stock"
    pj = stock / "pool.json"
    doc = None
    if pj.is_file():
        try:
            doc = json.loads(pj.read_text())
        except Exception:
            doc = None
    fresh = doc and time.time() - doc.get("ts", 0) < TTL
    if not fresh and os.getenv("GBS_LIVE_DATA", "1") != "0" and os.getenv("GBS_STOCK_IMAGES", "1") != "0":
        try:
            pool = refresh(stock)
            if pool:
                return pool
        except Exception as exc:
            log.warning("stock image refresh failed: %s", exc)
    return (doc or {}).get("pool", {})


def publish(pool: dict, data_dir: Path, out: Path) -> dict[str, list[str]]:
    """Copy pool files to /img/stock/ and return desk -> [public url]."""
    src, dest = Path(data_dir) / "stock", Path(out) / "img" / "stock"
    dest.mkdir(parents=True, exist_ok=True)
    urls: dict[str, list[str]] = {}
    for desk, items in pool.items():
        for it in items:
            f = src / it["file"]
            if not f.is_file():
                continue
            d = dest / it["file"]
            if not d.is_file():
                shutil.copy(f, d)
            urls.setdefault(desk, []).append(f"/img/stock/{it['file']}")
    return urls


def pick(urls: dict[str, list[str]], desk: str, key: str, fallback_desk: str = "world") -> str | None:
    choices = urls.get(desk) or urls.get(fallback_desk) or []
    if not choices:
        return None
    return choices[int(hashlib.sha1(key.encode()).hexdigest(), 16) % len(choices)]
