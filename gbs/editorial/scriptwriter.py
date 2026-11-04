"""Turn a Segment into an anchor read.

Uses any OpenAI-compatible endpoint (Strata over StarNet by default --
same LLM_BASE_URL / LLM_MODEL / LLM_API_KEY env as 5protocol llm_brain).
Falls back to a deterministic template so the pipeline never stalls.

Editorial rules baked into the prompt (these are what keep a repackaged
news product publishable and ad-network friendly):
  * rewrite in original words -- no copying article sentences
  * credit the outlet on air ("according to BBC News") and link it on page
  * report only what the source material says; no invented quotes/numbers
"""
from __future__ import annotations

import json
import logging
import re
import urllib.request

from gbs.config import Settings
from gbs.models import Segment
from gbs.newsdesk.feeds import outlet_of

log = logging.getLogger("gbs.script")

SYSTEM = (
    "You are the script editor for Gu Broadcast Station, an AI-anchored world news "
    "broadcast. Write a spoken news read of 60-110 words for the named anchor. Rules: "
    "use your own wording, never copy sentences from the source text; attribute facts "
    "on air to the outlet(s) given; state only facts present in the material; no "
    "invented quotes, figures or speculation; neutral tone; no sign-off. Output the "
    "read only."
)

OUTLET_NAMES = {
    "bbc": "BBC News", "bbc_europe": "BBC News", "bbc_asia": "BBC News", "bbc_mideast": "BBC News",
    "bbc_africa": "BBC News", "bbc_business": "BBC News", "bbc_tech": "BBC News",
    "bbc_science": "BBC News", "aljazeera": "Al Jazeera", "guardian": "The Guardian",
    "npr": "NPR", "dw": "DW", "france24": "France 24", "un_news": "UN News", "cbc": "CBC News",
    "cbc_canada": "CBC News", "nhk": "NHK", "korea_herald": "The Korea Herald",
    "ars": "Ars Technica", "nasa": "NASA",
}


def outlet_name(source_key: str) -> str:
    o = outlet_of(source_key)
    if o.startswith("gdelt:"):
        o = o[6:]
    return OUTLET_NAMES.get(o, o)


def _material(seg: Segment) -> str:
    lines = []
    for s in [seg.story, *seg.related[:3]]:
        lines.append(f"- {outlet_name(s.source)}: {s.title}. {s.summary[:600]}")
    return "\n".join(lines)


def template_script(seg: Segment, anchor_name: str) -> str:
    s = seg.story
    outlets = ", ".join(dict.fromkeys(outlet_name(x["source"]) for x in seg.sources))
    summary = re.split(r"(?<=[.!?])\s", s.summary.strip())[0] if s.summary else ""
    body = f"{s.title}. " + (f"{summary} " if summary and summary.lower() != s.title.lower() else "")
    return f"{body}That's according to {outlets}. Full sourcing is on our site."


def llm_script(cfg: Settings, seg: Segment, anchor_name: str, timeout: int = 90) -> str:
    payload = {
        "model": cfg.llm_model,
        "temperature": 0.4,
        "messages": [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": f"Anchor: {anchor_name}\nDesk: {seg.story.desk}\nMaterial:\n{_material(seg)}"},
        ],
    }
    headers = {"Content-Type": "application/json"}
    if cfg.llm_api_key:
        headers["Authorization"] = f"Bearer {cfg.llm_api_key}"
    req = urllib.request.Request(f"{cfg.llm_base_url}/chat/completions",
                                 data=json.dumps(payload).encode(), headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        text = json.loads(r.read())["choices"][0]["message"]["content"]
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.S).strip()  # Qwen thinking blocks
    return text


def write_script(cfg: Settings, seg: Segment, anchor_name: str) -> str:
    if cfg.llm_base_url:
        try:
            return llm_script(cfg, seg, anchor_name)
        except Exception as exc:
            log.warning("LLM script failed (%s); using template", exc)
    return template_script(seg, anchor_name)
