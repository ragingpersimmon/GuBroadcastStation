"""Local desks: Celeste Storm's weather (Open-Meteo, keyless) and Flip
Torres's traffic (any Open511 events feed, e.g. DriveBC). Defaults to
Vancouver / DriveBC's Metro Vancouver box; override with GBS_LOCAL_NAME,
GBS_LOCAL_LAT/LON and GBS_TRAFFIC_OPEN511_URL. The on-air segments are
Stories so they flow through the normal rundown; `snapshot()` feeds the
site (top-bar weather, /local/weather/, /local/traffic/) from a 15-minute
cache in $GBS_DATA_DIR/local/. GBS_LIVE_DATA=0 (tests) never touches the
network."""
from __future__ import annotations

import hashlib
import json
import logging
import os
import time
import urllib.parse
import urllib.request

from gbs.models import Story

log = logging.getLogger("gbs.local")

WMO = {0: "clear skies", 1: "mostly clear", 2: "partly cloudy", 3: "overcast", 45: "fog", 48: "freezing fog",
       51: "light drizzle", 53: "drizzle", 55: "heavy drizzle", 61: "light rain", 63: "rain", 65: "heavy rain",
       66: "freezing rain", 67: "heavy freezing rain", 71: "light snow", 73: "snow", 75: "heavy snow",
       77: "snow grains", 80: "showers", 81: "heavy showers", 82: "violent showers", 85: "snow showers",
       86: "heavy snow showers", 95: "thunderstorms", 96: "thunderstorms with hail", 99: "severe thunderstorms with hail"}


def _get(url: str, timeout: int = 15):
    req = urllib.request.Request(url, headers={"User-Agent": "gbs-local/0.1"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def _hash(*parts: str) -> str:
    return hashlib.sha256("|".join(parts).encode()).hexdigest()


def weather_from_payload(place: str, d: dict) -> Story:
    cur, day = d.get("current", {}), d.get("daily", {})
    now_t = cur.get("temperature_2m")
    cond = WMO.get(cur.get("weather_code"), "mixed conditions")
    hi, lo = (day.get("temperature_2m_max") or [None])[0], (day.get("temperature_2m_min") or [None])[0]
    pop = (day.get("precipitation_probability_max") or [None])[0]
    later = WMO.get((day.get("weather_code") or [None])[0], cond)
    parts = [f"Right now in {place}: {cond}" + (f", {round(now_t)} degrees" if now_t is not None else "") + "."]
    if hi is not None and lo is not None:
        parts.append(f"Today: {later}, high {round(hi)}, low {round(lo)}.")
    if pop is not None:
        parts.append(f"Chance of precipitation {pop} percent.")
    date = (day.get("time") or [time.strftime("%Y-%m-%d")])[0]
    return Story(item_hash=_hash("weather", place, date, str(int(time.time() // 3600))), desk="weather",
                 source="weather:open-meteo", title=f"{place} forecast: {later}, high {round(hi) if hi is not None else '?'}",
                 summary=" ".join(parts), link="https://open-meteo.com/", ts=time.time())


DEFAULT_PLACE = ("Vancouver", "49.2827", "-123.1207")
DEFAULT_OPEN511 = ("https://api.open511.gov.bc.ca/events?format=json&status=ACTIVE"
                   "&bbox=-123.35,49.00,-122.40,49.45&limit=200")


def place() -> tuple[str, str, str]:
    return (os.getenv("GBS_LOCAL_NAME") or DEFAULT_PLACE[0], os.getenv("GBS_LOCAL_LAT") or DEFAULT_PLACE[1],
            os.getenv("GBS_LOCAL_LON") or DEFAULT_PLACE[2])


def weather() -> Story | None:
    where, lat, lon = place()
    q = urllib.parse.urlencode({
        "latitude": lat, "longitude": lon, "timezone": "auto", "forecast_days": 1,
        "current": "temperature_2m,weather_code",
        "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max"})
    try:
        return weather_from_payload(where, _get(f"https://api.open-meteo.com/v1/forecast?{q}"))
    except Exception as exc:
        log.warning("weather unavailable: %s", exc)
        return None


def traffic_from_payload(place: str, d: dict, limit: int = 4) -> Story | None:
    events = [e for e in d.get("events", []) if e.get("status", "ACTIVE") == "ACTIVE"]
    major = sorted(events, key=lambda e: {"MAJOR": 0, "MODERATE": 1}.get(e.get("severity"), 2))[:limit]
    if not major:
        return None
    lines = []
    for e in major:
        road = ", ".join(r.get("name", "") for r in e.get("roads", [])[:1] if r.get("name"))
        desc = (e.get("headline") or e.get("event_type") or "incident").replace("_", " ").lower()
        lines.append(f"{desc} on {road}" if road else desc)
    return Story(item_hash=_hash("traffic", place, str(int(time.time() // 900))), desk="traffic",
                 source="traffic:open511", title=f"{place} traffic: {len(events)} active incidents",
                 summary="Active incidents: " + "; ".join(lines) + ".",
                 link=os.getenv("GBS_TRAFFIC_LINK", "https://www.drivebc.ca/"), ts=time.time())


def traffic() -> Story | None:
    url = os.getenv("GBS_TRAFFIC_OPEN511_URL") or DEFAULT_OPEN511
    try:
        return traffic_from_payload(place()[0], _get(url))
    except Exception as exc:
        log.warning("traffic unavailable: %s", exc)
        return None


LOCAL = {"weather": weather, "traffic": traffic}


# ---------------------------------------------------------------- site snapshot

def _live() -> bool:
    return os.getenv("GBS_LIVE_DATA", "1") != "0"


def _cached(cache_dir, name: str, ttl: int, fetch):
    """Fresh cache -> it; else fetch and store; on failure the stale copy (or None)."""
    from pathlib import Path
    path = Path(cache_dir) / f"{name}.json"
    stale = None
    if path.is_file():
        try:
            stale = json.loads(path.read_text())
            if time.time() - path.stat().st_mtime < ttl:
                return stale
        except Exception:
            stale = None
    if not _live():
        return stale
    try:
        data = fetch()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data))
        return data
    except Exception as exc:
        log.warning("%s unavailable: %s", name, exc)
        return stale


def forecast_from_payload(name: str, d: dict) -> dict:
    cur, day = d.get("current", {}), d.get("daily", {})
    days = []
    for i, date in enumerate(day.get("time") or []):
        g = lambda k: (day.get(k) or [None] * (i + 1))[i]
        days.append({"date": date, "cond": WMO.get(g("weather_code"), "mixed conditions"),
                     "hi": g("temperature_2m_max"), "lo": g("temperature_2m_min"),
                     "pop": g("precipitation_probability_max"), "wind": g("wind_speed_10m_max")})
    t = cur.get("temperature_2m")
    return {"place": name, "temp": round(t) if t is not None else None,
            "feels": round(cur["apparent_temperature"]) if cur.get("apparent_temperature") is not None else None,
            "cond": WMO.get(cur.get("weather_code"), "mixed conditions"), "wind": cur.get("wind_speed_10m"),
            "humidity": cur.get("relative_humidity_2m"), "days": days, "fetched": time.time()}


def traffic_list(d: dict, limit: int = 40) -> list[dict]:
    rank = {"MAJOR": 0, "MODERATE": 1, "MINOR": 2}
    out = []
    for ev in d.get("events", []):
        if ev.get("status", "ACTIVE") != "ACTIVE":
            continue
        roads = [r.get("name") for r in ev.get("roads", []) if r.get("name")]
        dirn = next((r.get("direction") for r in ev.get("roads", []) if r.get("direction")), "")
        out.append({"road": ", ".join(dict.fromkeys(roads)) or "Unnamed road",
                    "type": (ev.get("event_type") or "incident").replace("_", " ").lower(),
                    "severity": (ev.get("severity") or "unknown").lower(),
                    "direction": (dirn or "").replace("_", " ").lower() if dirn not in ("NONE", "BOTH") else "",
                    "text": (ev.get("description") or ev.get("headline") or "").strip()[:400],
                    "updated": ev.get("updated") or ev.get("created") or ""})
    out.sort(key=lambda x: (rank.get(x["severity"].upper(), 3), x["road"]))
    return out[:limit]


def snapshot(cache_dir) -> dict:
    """{"weather": forecast dict | None, "traffic": [events] | None} for the site."""
    name, lat, lon = place()

    def _wx():
        q = urllib.parse.urlencode({
            "latitude": lat, "longitude": lon, "timezone": "auto", "forecast_days": 7,
            "current": "temperature_2m,apparent_temperature,weather_code,wind_speed_10m,relative_humidity_2m",
            "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max,wind_speed_10m_max"})
        return forecast_from_payload(name, _get(f"https://api.open-meteo.com/v1/forecast?{q}", timeout=8))

    def _tr():
        return {"events": traffic_list(_get(os.getenv("GBS_TRAFFIC_OPEN511_URL") or DEFAULT_OPEN511, timeout=8)),
                "fetched": time.time()}

    return {"weather": _cached(cache_dir, "weather", 900, _wx), "traffic": _cached(cache_dir, "traffic", 600, _tr)}
