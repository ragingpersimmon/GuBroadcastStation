"""End-to-end offline test: local RSS files -> 5protocol NewsFeedPoller
(via the bridge) -> store -> rundown -> scripts -> static site."""
import json
import os
from pathlib import Path

import pytest

from gbs.anchors.comfy_client import fill
from gbs.config import Settings
from gbs.editorial.rundown import build_rundown, cluster
from gbs.editorial.scriptwriter import write_script
from gbs.models import Story
from gbs.newsdesk.fiveprotocol_bridge import NewsBridge
from gbs.newsdesk.store import StoryStore
from gbs.site.build import build_site

FIVEP = Path(os.getenv("FIVEPROTOCOL_PATH", Path(__file__).resolve().parents[1] / "vendor" / "5protocol"))
needs_5p = pytest.mark.skipif(not (FIVEP / "news_ingest.py").exists(), reason="5protocol checkout missing")

RSS = """<?xml version="1.0"?><rss version="2.0"><channel><title>t</title>
{items}</channel></rss>"""
ITEM = "<item><title>{t}</title><link>{l}</link><description>{d}</description></item>"


def _feed(tmp: Path, name: str, rows) -> str:
    p = tmp / f"{name}.xml"
    p.write_text(RSS.format(items="".join(ITEM.format(t=t, l=l, d=d) for t, l, d in rows)))
    return str(p)


def _cfg(tmp: Path) -> Settings:
    c = Settings()
    c.fiveprotocol_path = FIVEP
    c.data_dir = tmp / "data"
    c.site_out = tmp / "public"
    c.llm_base_url = ""
    c.fiveprotocol_push_key = ""
    return c


@needs_5p
def test_bridge_to_site(tmp_path):
    feeds = {
        "world:bbc": _feed(tmp_path, "bbc", [
            ("Earthquake strikes off coast of Chile", "https://bbc.example/1", "A magnitude 7 quake struck <b>near</b> Valparaiso."),
            ("Leaders meet for climate summit in Brazil", "https://bbc.example/2", "Talks open in Belem."),
        ]),
        "world:guardian": _feed(tmp_path, "guardian", [
            ("Powerful earthquake strikes off Chile coast", "https://guardian.example/9", "Tsunami warning issued."),
        ]),
        "asia:nhk": _feed(tmp_path, "nhk", [
            ("Japan launches new weather satellite", "https://nhk.example/3", "H3 rocket lifted off."),
        ]),
    }
    cfg = _cfg(tmp_path)
    bridge = NewsBridge(cfg, feeds=feeds)
    stories = bridge.pull()
    assert len(stories) == 4
    assert all(s.link.startswith("https://") for s in stories)
    assert "<b>" not in stories[0].summary  # 5protocol HTML scrub applied
    assert {s.desk for s in stories} == {"world", "asia"}
    assert bridge.pull() == []  # 5protocol seen-set dedupe persisted

    store = StoryStore(cfg.db_path)
    assert store.add(stories) == 4
    rundown = build_rundown(store.recent())
    assert len(rundown) == 3  # two quake reports merged into one segment
    quake = next(s for s in rundown if "earthquake" in s.story.title.lower())
    assert len(quake.sources) == 2
    lena = {"name": "Lena Moravec", "title": "International Correspondent", "style": "Calm.", "sample": "x"}
    for seg in rundown:
        seg.anchor_id, seg.presenter_title = lena["name"], lena["title"]
        seg.script = write_script(cfg, seg, lena)
        assert "according to" not in seg.script                # no on-air outlet credits
        assert seg.script == seg.story.title.rstrip(".") + "."   # no LLM: headline only, no copied summary

    out = build_site(cfg, rundown, pulse={"regime": "calm"})
    index = (out / "index.html").read_text()
    assert "AI-generated" in index
    quake_pages = list((out / "story").rglob(f"{quake.slug}.html"))
    assert quake_pages and "guardian.example" not in quake_pages[0].read_text()   # sources confidential
    assert "guardian.example/9" in (out / "rundown.json").read_text()             # ...but kept internally
    assert (out / "feed.xml").exists() and (out / "sitemap.xml").exists()
    assert len(json.loads((out / "rundown.json").read_text())) == 3
    # trading-bot state files untouched: bridge writes only under GBS data dir
    assert (cfg.data_dir / "fiveprotocol" / "seen.json").exists()


def test_cluster_keeps_distinct_events_apart():
    mk = lambda t, src: Story(t[:8], "world", src, t, "", "https://x", 0.0)
    c = cluster([mk("Flood hits Bangladesh capital", "world:bbc"),
                 mk("Bangladesh capital hit by flood", "world:dw"),
                 mk("Election results in Kenya", "africa:bbc_africa")])
    assert sorted(len(x) for x in c) == [1, 2]


def test_comfy_fill_types():
    wf = {"3": {"inputs": {"seed": "{{SEED}}", "text": "anchor, {{POSITIVE}}"}}}
    out = fill(wf, {"SEED": 42, "POSITIVE": "navy blazer"})
    assert out["3"]["inputs"]["seed"] == 42
    assert out["3"]["inputs"]["text"] == "anchor, navy blazer"
