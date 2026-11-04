"""Harold Yi's signature open: fixed first half, daypart greeting, spoken
'GUUd' -> 'Good', one cheesier variant per week on a Friday, never on a
serious lead; Harold leads, co-anchor reads the anchor desk."""
import json
import time
from datetime import datetime
from zoneinfo import ZoneInfo

import gbs.cli as cli
from gbs.anchors.roster import by_id, load_newsroom
from gbs.config import Settings
from gbs.editorial.scriptwriter import write_signature_open
from gbs.models import Segment, Story
from gbs.newsdesk.store import StoryStore

TZ = ZoneInfo("America/Vancouver")
NR = load_newsroom()
HAROLD = by_id(NR, "harold")
SHOWS = {s["id"]: s for s in NR["shows"]}
LINE = "This is Harold Yi at Gu Broadcasting Station, where we follow the story for your better insight."


def segs(*titles):
    return [Segment(story=Story(f"{i}" * 64, "world", "world:bbc", t, "", "https://x", 0.0)) for i, t in enumerate(titles)]


def cfg_(tmp_path):
    c = Settings()
    c.llm_base_url, c.data_dir, c.site_out, c.fiveprotocol_push_key = "", tmp_path / "d", tmp_path / "p", ""
    c.render_on_run = False
    return c


LIGHT = segs("Bakery wins national bread award", "Council passes budget", "Rocket launch goes ahead")


def test_morning_and_evening_standard(tmp_path):
    cfg = cfg_(tmp_path)
    wed_am = datetime(2026, 11, 4, 6, 0, tzinfo=TZ)
    text, said = write_signature_open(cfg, SHOWS["morning"], HAROLD, LIGHT, now=wed_am, state_path=tmp_path / "s.json")
    assert text.startswith(f"GUUd morning, listeners. {LINE} Today we have")
    assert said.startswith(f"Good morning, listeners. {LINE}")             # voice never says "G-U-U-d"
    assert "Bakery wins national bread award" in text
    text, said = write_signature_open(cfg, SHOWS["evening"], HAROLD, LIGHT, now=wed_am.replace(hour=18),
                                      state_path=tmp_path / "s.json")
    assert text.startswith(f"Good evening, listeners. {LINE} Tonight we have") and text == said


def test_serious_lead_drops_pun_and_variant(tmp_path):
    cfg = cfg_(tmp_path)
    fri = datetime(2026, 11, 6, 6, 0, tzinfo=TZ)
    grim = segs("Earthquake kills dozens in Chile", "Council passes budget")
    text, _ = write_signature_open(cfg, SHOWS["morning"], HAROLD, grim, now=fri, state_path=tmp_path / "s.json")
    assert text.startswith(f"Good morning, listeners. {LINE}") and "GUUd" not in text
    assert not (tmp_path / "s.json").exists()          # the week's variant is not spent


def test_one_variant_per_week_on_friday(tmp_path):
    cfg = cfg_(tmp_path)
    st = tmp_path / "s.json"
    variants = {v["text"] for v in HAROLD["signature"]["variants"]}
    thu = datetime(2026, 11, 5, 6, 0, tzinfo=TZ)
    assert write_signature_open(cfg, SHOWS["morning"], HAROLD, LIGHT, now=thu, state_path=st)[0].startswith("GUUd morning, listeners. " + LINE)
    fri = datetime(2026, 11, 6, 6, 0, tzinfo=TZ)
    first = write_signature_open(cfg, SHOWS["morning"], HAROLD, LIGHT, now=fri, state_path=st)[0]
    used = next(v for v in variants if first.startswith(v))
    assert used != "GUUd morning, listeners. " + LINE and "Today we have" in first
    again = write_signature_open(cfg, SHOWS["evening"], HAROLD, LIGHT, now=fri.replace(hour=18), state_path=st)[0]
    assert again.startswith(f"Good evening, listeners. {LINE}")      # spent for the week
    nxt = write_signature_open(cfg, SHOWS["evening"], HAROLD, LIGHT, now=datetime(2026, 11, 13, 18, 0, tzinfo=TZ),
                               state_path=st)[0]
    assert any(nxt.startswith(v) for v in variants if v.startswith("Good evening"))
    no = write_signature_open(cfg, SHOWS["morning"], HAROLD, LIGHT, now=datetime(2026, 11, 20, 6, 0, tzinfo=TZ),
                              state_path=st, allow_variant=False)[0]
    assert no.startswith("GUUd morning, listeners. " + LINE)


def test_edition_harold_leads_vale_assists(tmp_path, monkeypatch):
    cfg = cfg_(tmp_path)
    monkeypatch.setattr(cli, "settings", lambda: cfg)
    monkeypatch.setattr("gbs.anchors.roster.now_local", lambda: datetime(2026, 11, 4, 18, 20, tzinfo=TZ))
    StoryStore(cfg.db_path).add([
        Story("a" * 64, "politics", "politics:npr", "Council passes budget", "Detail.", "https://e/1", time.time()),
        Story("b" * 64, "unknowndesk", "x:bbc", "Bakery wins bread award", "Detail.", "https://e/2", time.time()),
    ])
    assert cli.main(["rundown"]) == 0
    order = json.loads((cfg.site_out / "rundown.json").read_text())
    op = next(x for x in order if x["kind"] == "open")
    assert op["anchor"] == "Harold Yi" and LINE in op["script"] and op["spoken"].startswith("Good evening")
    who = {x["desk"]: x["anchor"] for x in order if x["kind"] == "story"}
    assert who["politics"] == "Marcus Bell" and who["unknowndesk"] == "Tessa Vale"
    assert next(x for x in order if x["kind"] == "close")["anchor"] == "Harold Yi"
    shows = (cfg.site_out / "shows" / "evening" / "index.html").read_text()
    assert "Harold Yi" in shows and "Tessa Vale" in shows
