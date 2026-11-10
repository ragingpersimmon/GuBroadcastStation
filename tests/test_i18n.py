"""Six-language site: EN plus KR, JP, CN, FR, SP mirrors with a switcher on every page."""
import time

from gbs.config import Settings
from gbs.models import Segment, Story
from gbs.site.build import build_site
from tests.helpers import verified


def test_language_mirrors_and_switcher(tmp_path, monkeypatch):
    monkeypatch.setenv("GBS_I18N", "1")
    cfg = Settings()
    cfg.site_out, cfg.data_dir, cfg.llm_base_url = tmp_path / "p", tmp_path / "d", ""
    st = Story("a" * 64, "world", "world:bbc", "Council approves plan", "s", "l", time.time())
    build_site(cfg, verified([Segment(story=st, related=[Story("b" * 64, "world", "world:dw", "Plan approved", "s", "l",
                                                                 time.time())], anchor_id="Harold Yi",
                                      script="Council approved the plan. More detail follows.")]))
    for path, short, h1 in (("ko", "KR", "제휴 문의"), ("ja", "JP", "提携のご相談"), ("zh", "CN", "合作"),
                            ("fr", "FR", "Travailler avec nous"), ("es", "SP", "Trabaja con nosotros")):
        page = (cfg.site_out / path / "work-with-us" / "index.html").read_text()
        assert f"<h1>{h1}</h1>" in page
        assert f'href="/{path}/work-with-us/"' in page and f">{short}</a>" in page
    home = (cfg.site_out / "index.html").read_text()
    assert 'hreflang="ko"' in home and 'hreflang="x-default"' in home and ">EN</a>" in home
    assert "/ko/" in (cfg.site_out / "sitemap.xml").read_text()
