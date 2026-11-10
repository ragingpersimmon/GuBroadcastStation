"""Full-site build: every promised page exists and every internal link,
script, stylesheet, image and video on every page resolves to a file."""
import json
import re
import time
from html.parser import HTMLParser
from pathlib import Path

import pytest

from tests.helpers import verified

from gbs.config import Settings
from gbs.models import Segment, Story
from gbs.site.build import build_site

DESKS = ["world", "americas", "europe", "asia", "mideast", "africa", "politics", "business", "markets",
         "consumer", "tech", "science", "entertainment", "sports", "weather", "traffic"]
PRESENTER = {"politics": ("Marcus Bell", "Politics Reporter"), "sports": ('Troy "Coach" Maddox', "Sports Reporter"),
             "tech": ("Juno Park", "Technology Reporter")}

EXPECTED = ["/", "/latest/", "/live/", "/world/", "/world/asia/", "/world/africa/", "/politics/", "/business/",
            "/business/markets/", "/business/consumer/", "/tech/", "/science/", "/entertainment/", "/sports/",
            "/local/", "/local/weather/", "/local/traffic/", "/markets/", "/video/", "/shows/", "/shows/evening/",
            "/shows/gucast/", "/people/", "/people/tessa/", "/people/margo/", "/people/coach/", "/archive/", "/search/",
            "/newsletter/", "/newsletter/thanks/", "/newsletter/confirmed/", "/newsletter/guide/", "/about/", "/about/standards/", "/about/ai/", "/about/corrections/", "/login/", "/account/", "/membership/", "/membership/thanks/", "/work-with-us/", "/work-with-us/thanks/",
            "/contact/", "/tips/", "/advertise/", "/advertise/guidelines/", "/privacy/", "/terms/", "/cookies/",
            "/accessibility/", "/sitemap/", "/404.html", "/feed.xml", "/world/feed.xml", "/sitemap.xml",
            "/news-sitemap.xml", "/robots.txt", "/manifest.webmanifest", "/search-index.json", "/assets/gu.css",
            "/assets/gu.js", "/assets/favicon.svg"]


def resolve(out: Path, url: str) -> Path:
    rel = url.split("#")[0].split("?")[0].lstrip("/")
    return out / (rel + "index.html" if rel == "" or rel.endswith("/") else rel)


class Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.urls, self.ld = [], []
        self._ld = False

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        for k in ("href", "src"):
            if a.get(k):
                self.urls.append(a[k])
        self._ld = tag == "script" and a.get("type") == "application/ld+json"

    def handle_data(self, data):
        if self._ld:
            self.ld.append(data)
            self._ld = False


@pytest.fixture
def site(tmp_path, monkeypatch):
    monkeypatch.setattr("gbs.anchors.roster.now_local",
                        lambda: __import__("datetime").datetime(2026, 11, 4, 18, 0))
    cfg = Settings()
    cfg.site_out, cfg.data_dir, cfg.site_url = tmp_path / "public", tmp_path / "data", "https://gu.example"
    segs = []
    for i, d in enumerate(DESKS * 2):
        st = Story(f"{i:08x}" * 8, d, f"{d}:bbc", f"Story {i} on the {d} desk: council votes on plan",
                   "Summary.", f"https://src.example/{i}", time.time() - i * 60, risk_score=0.1)
        name, title = PRESENTER.get(d, ("Lena Moravec", "International Correspondent"))
        segs.append(Segment(story=st, anchor_id=name, presenter_title=title,
                            script=f"Story {i} on the {d} desk. The council voted, according to BBC News.\nSecond paragraph.",
                            sponsor_read="Sponsored by Gu Broadcasting Station. Advertise with us." if i == 4 else None))
    verified(segs)
    (cfg.site_out / "v").mkdir(parents=True)
    (cfg.site_out / "v" / f"{segs[0].slug}.mp4").write_bytes(b"x")
    show = {"id": "evening", "name": "Gu Evening News", "anchor": "tessa"}
    bookends = {"open": {"kind": "open", "slug": "open-evening-1", "title": "Gu Evening News", "anchor": "Tessa Vale",
                         "presenter_title": "Chief Anchor", "script": "Good evening. This is Gu."},
                "breaking": {"kind": "breaking", "slug": "breaking-1", "title": segs[3].story.title, "anchor": "ECHO",
                             "presenter_title": "AI Breaking/Weather Anchor", "script": "Breaking update from Gu."},
                "close": {"kind": "close", "slug": "close-1", "title": "x", "anchor": "Tessa Vale",
                          "presenter_title": "Chief Anchor", "script": "That's Gu."}}
    build_site(cfg, verified(segs), pulse={"regime": "elevated", "top_headlines": ["Rates rise"]}, show=show, bookends=bookends)
    return cfg, segs


def test_every_page_exists(site):
    cfg, segs = site
    missing = [u for u in EXPECTED if not resolve(cfg.site_out, u).is_file()]
    assert not (cfg.site_out / "about" / "sources").exists()
    assert not missing, missing
    assert len(list((cfg.site_out / "story").rglob("*.html"))) == len(segs)


def test_no_broken_internal_links(site):
    cfg, _ = site
    out = cfg.site_out
    broken, pages = {}, list(out.rglob("*.html"))
    assert len(pages) > 80
    for page in pages:
        p = Links()
        p.feed(page.read_text())
        for u in p.urls:
            if u.startswith(("http://", "https://", "mailto:", "#", "data:")) or u.startswith("//"):
                continue
            if not resolve(out, u).is_file():
                broken.setdefault(u, str(page.relative_to(out)))
        for blob in p.ld:
            json.loads(blob)  # every JSON-LD block is valid
    assert not broken, broken


def test_story_page_contents(site):
    cfg, segs = site
    page = next((cfg.site_out / "story").rglob(f"{segs[4].slug}.html")).read_text()
    assert "src.example" not in page and "BBC" not in page      # sources stay confidential
    assert "according to" not in page and 'class="sources"' not in page
    assert "Developing" in page                                  # one outlet: not confirmed
    assert "Sponsored message read on air" in page               # sponsor labelled
    assert "AI presenter" in page and "/about/ai/" in page        # disclosure
    assert '"@type": "NewsArticle"' in page
    assert "Second paragraph." in page
    lead = next((cfg.site_out / "story").rglob(f"{segs[0].slug}.html")).read_text()
    assert f"/v/{segs[0].slug}.mp4" in lead


def test_home_and_chrome(site):
    cfg, segs = site
    home = (cfg.site_out / "index.html").read_text()
    assert "Trending" in home and "data-ticker" in home and "Gu Evening News" in home and "Tessa Vale" in home
    assert 'class="breaking"' in home and "/membership/" in home and 'href="/login/"' in home
    assert "/about/sources/" not in home and "outlets credited" not in home
    assert "Good evening. This is Gu." in home
    assert "None" not in re.sub(r"<script.*?</script>", "", home, flags=re.S)
    people = (cfg.site_out / "people" / "coach" / "index.html").read_text()
    assert "Sports Reporter" in people and "AI-generated" in people
    idx = json.loads((cfg.site_out / "search-index.json").read_text())
    assert len(idx) == len(segs) and all(i["u"].startswith("/story/") for i in idx)
    assert "/story/" in (cfg.site_out / "sitemap.xml").read_text()


def test_history_survives_next_edition(site, tmp_path):
    cfg, segs = site
    st = Story("f" * 64, "world", "world:bbc", "A brand new story", "S.", "https://n.example", time.time())
    build_site(cfg, verified([Segment(story=st, anchor_id="Lena Moravec", script="A brand new story. More.")]))
    assert len(json.loads((cfg.site_out / "search-index.json").read_text())) == len(segs) + 1
    assert "A brand new story" in (cfg.site_out / "index.html").read_text()
    assert next((cfg.site_out / "story").rglob(f"{segs[5].slug}.html")).exists()   # old pages kept
