"""Newsroom roster, show clock, assignment desk, standards gate, local desks,
and a full `gbs rundown` edition (no network)."""
import json
from datetime import datetime
from zoneinfo import ZoneInfo

import gbs.cli as cli
from gbs.anchors.roster import (by_id, current_show, load_newsroom, load_roster,
                                presenter_for_desk, should_render)
from gbs.config import Settings
from gbs.editorial.standards import is_sensitive, tone_instruction
from gbs.models import Story
from gbs.newsdesk.local import traffic_from_payload, weather_from_payload
from gbs.newsdesk.store import StoryStore

TZ = ZoneInfo("America/Vancouver")
NR = load_newsroom()


def at(y, m, d, hh, mm):
    return datetime(y, m, d, hh, mm, tzinfo=TZ)


def test_roster_complete():
    names = {t["name"] for t in NR["talent"]}
    assert len(NR["talent"]) == 21
    assert {"Tessa Vale", "NOVA", "ECHO", "Lena Moravec", "Arbi Ong"} <= names
    assert all("heygen" in t for t in load_roster())            # every on-air talent renders
    assert not any(t["kind"] == "production" for t in load_roster())


def test_show_clock():
    assert current_show(NR, at(2026, 11, 4, 6, 30))["anchor"] == "benji"   # Wed morning
    assert current_show(NR, at(2026, 11, 4, 18, 0))["anchor"] == "tessa"   # Wed evening
    assert current_show(NR, at(2026, 11, 7, 12, 0))["anchor"] == "nick"    # Saturday
    assert current_show(NR, at(2026, 11, 4, 13, 0))["anchor"] == "nova"    # weekday midday
    assert current_show(NR, at(2026, 11, 4, 2, 0))["anchor"] == "nova"     # overnight
    eve = current_show(NR, at(2026, 11, 4, 18, 0))
    assert should_render(eve, at(2026, 11, 4, 18, 5)) and not should_render(eve, at(2026, 11, 4, 18, 20))


def test_assignment_desk():
    tessa = by_id(NR, "tessa")
    want = {"politics": "Marcus Bell", "asia": "Lena Moravec", "business": "Rafael Tertelbach",
            "tech": "Juno Park", "consumer": "Dana Ruiz", "weather": "Celeste Storm",
            "traffic": "Flip Torres", "entertainment": "Lola Sparks", "sports": 'Troy "Coach" Maddox',
            "unknown": "Tessa Vale"}
    for desk, name in want.items():
        assert presenter_for_desk(desk, NR, tessa)["name"] == name


def test_standards_gate():
    assert is_sensitive("Earthquake kills dozens in Chile")
    assert not is_sensitive("Local bakery wins national bread award")
    coach = by_id(NR, "coach")
    assert "No jokes" in tone_instruction(coach, True)
    assert "yelling" in tone_instruction(coach, False)


def test_local_desks():
    w = weather_from_payload("Coquitlam", {
        "current": {"temperature_2m": 7.4, "weather_code": 61},
        "daily": {"time": ["2026-11-04"], "weather_code": [63], "temperature_2m_max": [9.1],
                  "temperature_2m_min": [4.2], "precipitation_probability_max": [90]}})
    assert w.desk == "weather" and "light rain" in w.summary and "high 9" in w.summary
    t = traffic_from_payload("Metro Vancouver", {"events": [
        {"status": "ACTIVE", "severity": "MAJOR", "headline": "COLLISION", "roads": [{"name": "Highway 1"}]},
        {"status": "ARCHIVED", "headline": "OLD"}]})
    assert t.desk == "traffic" and "collision on Highway 1" in t.summary
    assert traffic_from_payload("X", {"events": []}) is None


def test_full_edition(tmp_path, monkeypatch):
    cfg = Settings()
    cfg.data_dir, cfg.site_out, cfg.llm_base_url, cfg.fiveprotocol_push_key = \
        tmp_path / "d", tmp_path / "p", "", ""
    cfg.render_on_run = False
    monkeypatch.setattr(cli, "settings", lambda: cfg)
    monkeypatch.setattr("gbs.anchors.roster.now_local", lambda: at(2026, 11, 4, 18, 0))
    import time
    mk = lambda h, desk, title, risk=0.0: Story(h * 8, desk, f"{desk}:bbc", title, f"{title}. More detail here.",
                                               f"https://ex.com/{h}", time.time(), risk_score=risk)
    StoryStore(cfg.db_path).add([
        mk("a", "politics", "Council passes city budget"),
        mk("b", "world", "Ceasefire holds for second night"),
        mk("c", "sports", "Underdogs win championship final"),
        mk("d", "business", "Markets fall sharply on rate fears", risk=0.8),
        mk("e", "tech", "New AI model claims fewer errors"),
    ])
    assert cli.main(["rundown"]) == 0
    order = json.loads((cfg.site_out / "rundown.json").read_text())
    kinds = [e["kind"] for e in order]
    assert kinds[0] == "breaking" and order[0]["anchor"] == "ECHO"      # risk 0.8 >= 0.7
    assert kinds[1] == "open" and order[1]["anchor"] == "Tessa Vale"    # evening show
    assert kinds[-1] == "close"
    presenters = {e["desk"]: e["anchor"] for e in order if e["kind"] == "story"}
    assert presenters["politics"] == "Marcus Bell" and presenters["sports"] == 'Troy "Coach" Maddox'
    sponsored = [e for e in order if e.get("sponsor_read")]
    assert sponsored and all(e["sponsor_read"].startswith("Sponsored by") for e in sponsored)
    index = (cfg.site_out / "index.html").read_text()
    assert "Gu Evening News" in index and 'class="breaking"' in index
    assert "fictional, AI-generated" in (cfg.site_out / "about" / "index.html").read_text()
    # edition persisted for the background studio pass, and the site picks up rendered clips
    show, bookends, pulse, segs = cli.load_edition(cfg)
    assert show["anchor"] == "tessa" and len(segs) == len([e for e in order if e["kind"] == "story"])
    (cfg.site_out / "v").mkdir()
    (cfg.site_out / "v" / f"{segs[0].slug}.mp4").write_bytes(b"x")
    from gbs.site.build import build_site
    build_site(cfg, segs, pulse=pulse, show=show, bookends=bookends)
    assert f"/v/{segs[0].slug}.mp4" in (cfg.site_out / "index.html").read_text()
