"""Scripts for every on-air beat: show open, story reads (by the desk's
reporter), sponsor bumpers, breaking bumpers and the close.

LLM: any OpenAI-compatible endpoint (Strata over StarNet by default --
same LLM_BASE_URL / LLM_MODEL / LLM_API_KEY env as 5protocol llm_brain).
Every beat has a deterministic template fallback so the show never stalls.
"""
from __future__ import annotations

import json
import logging
import re
import urllib.request

from gbs.config import Settings
from gbs.editorial.standards import STANDARDS, is_sensitive, tone_instruction
from gbs.models import Segment
from gbs.newsdesk.feeds import outlet_of

log = logging.getLogger("gbs.script")

OUTLET_NAMES = {
    "bbc": "BBC News", "bbc_europe": "BBC News", "bbc_asia": "BBC News", "bbc_mideast": "BBC News",
    "bbc_africa": "BBC News", "bbc_business": "BBC News", "bbc_tech": "BBC News",
    "bbc_science": "BBC News", "bbc_entertainment": "BBC News", "bbc_sport": "BBC Sport",
    "aljazeera": "Al Jazeera", "guardian": "The Guardian", "guardian_politics": "The Guardian",
    "guardian_culture": "The Guardian", "guardian_money": "The Guardian",
    "npr": "NPR", "npr_politics": "NPR", "dw": "DW", "france24": "France 24", "un_news": "UN News",
    "cbc": "CBC News", "cbc_canada": "CBC News", "cbc_politics": "CBC News", "cbc_sports": "CBC Sports",
    "cbc_business": "CBC News", "nhk": "NHK", "korea_herald": "The Korea Herald",
    "ars": "Ars Technica", "nasa": "NASA", "open-meteo": "Open-Meteo", "open511": "DriveBC",
}


def outlet_name(source_key: str) -> str:
    o = outlet_of(source_key)
    if o.startswith("gdelt:"):
        o = o[6:]
    return OUTLET_NAMES.get(o, o)


def _chat(cfg: Settings, system: str, user: str, timeout: int = 90) -> str:
    payload = {"model": cfg.llm_model, "temperature": 0.5,
               "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}
    headers = {"Content-Type": "application/json"}
    if cfg.llm_api_key:
        headers["Authorization"] = f"Bearer {cfg.llm_api_key}"
    req = urllib.request.Request(f"{cfg.llm_base_url}/chat/completions",
                                 data=json.dumps(payload).encode(), headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        text = json.loads(r.read())["choices"][0]["message"]["content"]
    return re.sub(r"<think>.*?</think>", "", text, flags=re.S).strip().strip('"')


def _try_llm(cfg: Settings, system: str, user: str, fallback: str) -> str:
    if cfg.llm_base_url:
        try:
            out = _chat(cfg, system, user)
            if out:
                return out
        except Exception as exc:
            log.warning("LLM failed (%s); using template", exc)
    return fallback


def _material(seg: Segment) -> str:
    return "\n".join(f"- {outlet_name(s.source)}: {s.title}. {s.summary[:600]}"
                     for s in [seg.story, *seg.related[:3]])


def seg_sensitive(seg: Segment) -> bool:
    return is_sensitive(seg.story.title, seg.story.summary)


# ---------------- story reads ----------------

def template_script(seg: Segment, talent: dict | None = None) -> str:
    s = seg.story
    outlets = ", ".join(dict.fromkeys(outlet_name(x["source"]) for x in seg.sources))
    summary = re.split(r"(?<=[.!?])\s", s.summary.strip())[0] if s.summary else ""
    body = f"{s.title}. " + (f"{summary} " if summary and summary.lower() != s.title.lower() else "")
    return f"{body}That's according to {outlets}. Full sourcing is on our site."


def write_script(cfg: Settings, seg: Segment, talent: dict) -> str:
    system = (f"{STANDARDS}\n{tone_instruction(talent, seg_sensitive(seg))}\n"
              "Write a spoken news read of 60-110 words for this story. Output the read only, no sign-off.")
    user = f"Desk: {seg.story.desk}\nMaterial:\n{_material(seg)}"
    return _try_llm(cfg, system, user, template_script(seg, talent))


# ---------------- show bookends & bumpers ----------------

def write_open(cfg: Settings, show: dict, anchor: dict, rundown: list[Segment]) -> str:
    heads = [s.story.title for s in rundown[:3]]
    serious = any(seg_sensitive(s) for s in rundown[:3])
    fallback = f"This is {show['name']} on Gu. I'm {anchor['name']}. " + \
        ("Tonight: " if show["id"] == "evening" else "Top stories: ") + "; ".join(heads) + "."
    system = (f"{STANDARDS}\n{tone_instruction(anchor, serious)}\n"
              f"Write the cold open for '{show['name']}' in 25 words or fewer (Executive Producer "
              "Priya Sati: tighten the open). Tease the headlines given without adding facts. Name the "
              "show and station (Gu). Output the read only.")
    return _try_llm(cfg, system, "Headlines:\n" + "\n".join(f"- {h}" for h in heads), fallback)


def write_close(cfg: Settings, show: dict, anchor: dict) -> str:
    fallback = f"That's {show['name']}. Sources for every story are on our site. I'm {anchor['name']}, and this is Gu."
    system = (f"{STANDARDS}\n{tone_instruction(anchor, False)}\n"
              f"Write a sign-off for '{show['name']}' in 20 words or fewer. Mention sources are on the site. "
              "No news facts. Output the read only.")
    return _try_llm(cfg, system, "Sign off.", fallback)


def write_breaking(cfg: Settings, echo: dict, seg: Segment) -> str:
    fallback = f"Breaking update from Gu: {seg.story.title}. Details from {outlet_name(seg.story.source)} as they come in."
    system = (f"{STANDARDS}\n{tone_instruction(echo, True)}\n"
              "Write a breaking-news bumper of 30 words or fewer: urgent but not alarmist. Start with "
              "'Breaking update from Gu:'. Attribute the outlet. Output the read only.")
    return _try_llm(cfg, system, f"Material:\n{_material(seg)}", fallback)


def write_sponsor_read(cfg: Settings, talent: dict, sponsor: dict) -> str:
    """Arbi Ong: native-feeling but always labelled, sponsor claims kept verbatim."""
    copy = sponsor.get("on_air", "")
    fallback = f"Sponsored by {sponsor['name']}. {copy}"
    system = (f"{tone_instruction(talent, False)}\nYou are reading a paid sponsor message (Sponsorship "
              "Integration Producer Arbi Ong: punchy but legal). Begin with exactly 'Sponsored by "
              f"{sponsor['name']}.' then deliver the sponsor copy in your voice in 35 words or fewer. Keep "
              "every claim, price, offer and URL in the copy exactly as given; add no new claims. "
              "Output the read only.")
    out = _try_llm(cfg, system, f"Sponsor copy: {copy}", fallback)
    return out if out.startswith(f"Sponsored by {sponsor['name']}") else fallback
