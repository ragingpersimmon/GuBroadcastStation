"""Local desks: Celeste Storm's weather (Open-Meteo, keyless) and Flip
Torres's traffic (any Open511 events feed, e.g. DriveBC). Both are off
until GBS_LOCAL_LAT/LON (weather) and GBS_TRAFFIC_OPEN511_URL (traffic)
are set. Output is a Story so it flows through the normal rundown."""
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


def weather() -> Story | None:
    lat, lon = os.getenv("GBS_LOCAL_LAT"), os.getenv("GBS_LOCAL_LON")
    if not (lat and lon):
        return None
    place = os.getenv("GBS_LOCAL_NAME", "our area")
    q = urllib.parse.urlencode({
        "latitude": lat, "longitude": lon, "timezone": "auto", "forecast_days": 1,
        "current": "temperature_2m,weather_code",
        "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max"})
    try:
        return weather_from_payload(place, _get(f"https://api.open-meteo.com/v1/forecast?{q}"))
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
    url = os.getenv("GBS_TRAFFIC_OPEN511_URL")
    if not url:
        return None
    try:
        return traffic_from_payload(os.getenv("GBS_LOCAL_NAME", "Area"), _get(url))
    except Exception as exc:
        log.warning("traffic unavailable: %s", exc)
        return None


LOCAL = {"weather": weather, "traffic": traffic}
