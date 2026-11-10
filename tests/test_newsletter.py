"""The Gu Briefing: issue content, providers, once-a-day sending, site pages."""
import json
import threading
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from zoneinfo import ZoneInfo

import pytest

from tests.helpers import verified

from gbs.config import Settings
from gbs.models import Segment, Story
from gbs.newsletter import run
from gbs.newsletter.compose import build_issue, gather, load_issues, pick
from gbs.site.build import build_site, rebuild_newsletter_pages
from gbs.site.data import public_view

TZ = ZoneInfo("America/Vancouver")
NOW = datetime(2026, 11, 6, 5, 45, tzinfo=TZ)  # a Friday


def _seg(i, desk, title, srcs=1, risk=0.1):
    st = Story(f"{i:02x}" * 32, desk, f"{desk}:bbc", title, "S.", f"https://src.example/{i}", time.time(), risk_score=risk)
    outlets = ["guardian", "npr", "dw", "aljazeera"]
    related = [Story(f"{i:02x}{k}" * 16, desk, f"{desk}:{outlets[k]}", title, "S.", f"https://g.example/{i}/{k}", time.time())
               for k in range(srcs - 1)]
    return Segment(story=st, related=related, anchor_id="Lena Moravec", presenter_title="International Correspondent",
                   script=f"{title}. A second sentence with detail, according to BBC News.")


@pytest.fixture
def cfg(tmp_path, monkeypatch):
    monkeypatch.setattr("gbs.anchors.roster.now_local", lambda: NOW)
    monkeypatch.setattr("gbs.newsletter.compose.PublishedStore.recent",
                        lambda self, days=30: _recent(self, days))
    c = Settings()
    c.site_out, c.data_dir, c.site_url, c.fiveprotocol_push_key = tmp_path / "p", tmp_path / "d", "https://gubs.ca", ""
    return c


def _recent(store, days):
    from gbs.site.data import COLS
    rows = store.db.execute(f"SELECT {','.join(COLS)} FROM published ORDER BY ts DESC").fetchall()
    out = []
    for r in rows:
        d = dict(zip(COLS, r))
        d["sources"] = json.loads(d["sources"] or "[]")
        d = public_view(d)
        d["ts"] = NOW.timestamp() - 3600  # published an hour before the send
        out.append(d)
    return out


def _publish(cfg, segs):
    build_site(cfg, verified(segs), show={"id": "morning", "name": "Gu Morning", "anchor": "harold"})


SEGS = [
    _seg(1, "politics", "Council passes city budget after all-night session", srcs=3),
    _seg(2, "world", "Ceasefire holds for a second night", srcs=4),
    _seg(3, "business", "Central bank holds rates steady", srcs=2),
    _seg(4, "tech", "New AI model claims fewer errors"),
    _seg(5, "sports", "Underdogs win the final in extra time"),
    _seg(6, "asia", "Japan launches a weather satellite"),
    _seg(7, "weather", "Coquitlam forecast: rain, high 9"),
]


def test_issue_contents(cfg):
    _publish(cfg, SEGS)
    arts, weather = gather(cfg, NOW)
    issue = build_issue(cfg, arts, NOW, pulse={"regime": "normal"}, weather=weather,
                        sponsor={"name": "Acme", "web": {"headline": "Try Acme", "body": "It works.", "url": "/advertise/"}})
    top, groups = pick(arts)
    assert top[0]["title"].startswith("Ceasefire")                 # most-covered story leads
    assert len({t["desk"] for t in top}) == 3                       # top 3 from 3 different sections
    assert issue.subject.startswith("Ceasefire")
    assert "GUUd morning, listeners. This is Harold Yi at Gu Broadcasting Station" in issue.html
    assert "Sources:" not in issue.html and "BBC" not in issue.html and "BBC" not in issue.text
    assert "utm_source=gu-briefing" in issue.html and "/story/" in issue.html
    assert "AI-generated characters" in issue.html and "Sponsored" in issue.html
    assert "Market pulse" in issue.html and "Coquitlam forecast" in issue.html
    assert "Coquitlam forecast" not in [t["title"] for t in top]    # weather isn't a top story
    assert "TOP STORIES" in issue.text and "https://gubs.ca/story/" in issue.text


def test_serious_lead_drops_the_pun(cfg):
    _publish(cfg, [_seg(9, "world", "Earthquake kills dozens in Chile", srcs=5)] + SEGS[:3])
    arts, _ = gather(cfg, NOW)
    issue = build_issue(cfg, arts, NOW)
    assert "Good morning, listeners." in issue.html and "GUUd" not in issue.html


def test_too_few_stories(cfg):
    _publish(cfg, SEGS[:1])
    assert run(cfg, send=False, now=NOW) == 1


class FakeKit(BaseHTTPRequestHandler):
    posts = []

    def log_message(self, *a):
        pass

    def do_POST(self):
        assert self.headers["X-Kit-Api-Key"] == "k"
        FakeKit.posts.append((self.path, json.loads(self.rfile.read(int(self.headers["Content-Length"])))))
        b = json.dumps({"broadcast": {"id": 4242}}).encode()
        self.send_response(201); self.send_header("Content-Type", "application/json"); self.end_headers()
        self.wfile.write(b)


def test_kit_send_once_per_day(cfg, monkeypatch):
    FakeKit.posts = []
    srv = HTTPServer(("127.0.0.1", 0), FakeKit)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    monkeypatch.setenv("GBS_NEWSLETTER_PROVIDER", "kit")
    monkeypatch.setenv("KIT_API_KEY", "k")
    monkeypatch.setenv("KIT_API_BASE", f"http://127.0.0.1:{srv.server_port}/v4")
    _publish(cfg, SEGS)
    assert run(cfg, send=True, now=NOW) == 0
    assert run(cfg, send=True, now=NOW) == 0          # second call: already sent, no post
    assert len(FakeKit.posts) == 1
    path, body = FakeKit.posts[0]
    assert path == "/v4/broadcasts"
    assert body["public"] is False and body["subject"].startswith("Ceasefire")
    assert datetime.fromisoformat(body["send_at"]) > datetime.now(timezone.utc)   # scheduled ahead
    assert "Harold Yi" in body["content"] and body["preview_text"]
    assert json.loads((cfg.data_dir / "newsletter" / "sent.json").read_text())["2026-11-06"] == "kit:4242"
    assert run(cfg, send=True, now=NOW, force=True) == 0 and len(FakeKit.posts) == 2
    srv.shutdown()


def test_file_provider_and_pages(cfg, monkeypatch):
    monkeypatch.setenv("GBS_NEWSLETTER_PROVIDER", "file")
    _publish(cfg, SEGS)
    assert run(cfg, send=True, now=NOW) == 0
    assert (cfg.data_dir / "newsletter" / "outbox" / "2026-11-06.html").exists()
    assert not (cfg.data_dir / "newsletter" / "sent.json").exists()   # previews never count as sent
    assert load_issues(cfg)[0]["date"] == "2026-11-06"
    rebuild_newsletter_pages(cfg)
    out = cfg.site_out
    for p in ("newsletter/index.html", "newsletter/thanks/index.html", "newsletter/confirmed/index.html",
              "newsletter/guide/index.html", "newsletter/issues/2026-11-06/index.html"):
        assert (out / p).is_file(), p
    nl = (out / "newsletter" / "index.html").read_text()
    assert "Launching soon" in nl and "/newsletter/issues/2026-11-06/" in nl
    assert "Harold Yi" in (out / "newsletter" / "issues" / "2026-11-06" / "index.html").read_text()


def test_kit_form_when_configured(cfg, monkeypatch):
    import gbs.site.build as b
    real = b.Ctx.__init__

    def patched(self, *a, **k):
        real(self, *a, **k)
        self.site["newsletter"]["action"] = "https://app.kit.com/forms/123/subscriptions"
    monkeypatch.setattr(b.Ctx, "__init__", patched)
    _publish(cfg, SEGS)
    nl = (cfg.site_out / "newsletter" / "index.html").read_text()
    assert 'action="https://app.kit.com/forms/123/subscriptions"' in nl and 'name="email_address"' in nl
    assert "Launching soon" not in nl
