"""Web security config: CSP pins the one inline script; every header-setting location keeps the headers."""
import base64
import hashlib
import re
from pathlib import Path

from gbs.site import assets

DEPLOY = Path(__file__).resolve().parents[1] / "deploy"


def test_csp_hash_matches_the_inline_member_script():
    h = base64.b64encode(hashlib.sha256(assets.MEMBER_JS.encode()).digest()).decode()
    csp = (DEPLOY / "nginx_security_headers.conf").read_text()
    assert f"'sha256-{h}'" in csp, "MEMBER_JS changed: update the sha256 in deploy/nginx_security_headers.conf"
    assert "'unsafe-inline'" not in re.search(r"script-src[^;]+", csp).group(0)
    for h in ("frame-ancestors 'none'", "object-src 'none'", "X-Frame-Options", "Referrer-Policy", "Permissions-Policy"):
        assert h in csp


def test_locations_with_own_headers_include_the_security_snippet():
    conf = (DEPLOY / "nginx_gubroadcast.conf").read_text()
    main = conf.split("server_name gubs.ca;", 1)[1]
    for loc in re.findall(r"location[^{]*\{[^}]*\}", main):
        if "add_header" in loc:
            assert "gubs-security-headers.conf" in loc, loc
    assert "location ~ /\\. { deny all; }" in main and "limit_req zone=gubs_auth" in main
    assert "server_tokens off" in (DEPLOY / "nginx_http_hardening.conf").read_text()


def test_only_inline_scripts_are_data_or_the_pinned_one(tmp_path):
    from gbs.config import Settings
    from gbs.models import Segment, Story
    from gbs.site.build import build_site
    from tests.helpers import verified
    cfg = Settings()
    cfg.site_out, cfg.data_dir = tmp_path / "p", tmp_path / "d"
    build_site(cfg, verified([Segment(story=Story("a" * 64, "world", "world:bbc", "Test", "s", "l", 0.0),
                                      anchor_id="Lena Moravec", script="One. Two.")]))
    for f in cfg.site_out.rglob("*.html"):
        for attrs, body in re.findall(r"<script([^>]*)>(.*?)</script>", f.read_text(), re.S):
            if "src=" in attrs or "application/json" in attrs or "application/ld+json" in attrs:
                continue
            assert body == assets.MEMBER_JS, f"unpinned inline script in {f}"
