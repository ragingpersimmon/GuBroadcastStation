"""Sign-in + membership service, live local data, stock images, source scrubbing."""
import hashlib
import hmac
import json
import threading
import time
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

from gbs.account import server as acct
from gbs.editorial.rundown import desk_briefs
from gbs.editorial.scriptwriter import scrub_outlets
from gbs.models import Story
from gbs.newsdesk import local
from gbs.site import images
from gbs.site.data import public_view


# ------------------------------------------------------------------ account service

@pytest.fixture
def svc(tmp_path, monkeypatch):
    monkeypatch.setenv("GBS_SESSION_SECRET", "test-secret")
    monkeypatch.setenv("GBS_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("GBS_SITE_URL", "https://gu.example")
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "cid")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "csec")
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_x")
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_x")
    monkeypatch.setenv("STRIPE_PRICE_MONTHLY", "price_m")
    calls = []

    def fake_http(method, url, data=None, headers=None, form=True, timeout=15):
        calls.append((method, url, data))
        if url == acct.PROVIDERS["google"]["token"]:
            assert data["code"] == "good-code" and data["code_verifier"]
            return {"access_token": "at"}
        if url == acct.PROVIDERS["google"]["userinfo"]:
            return {"sub": "123", "email": "reader@example.com", "email_verified": True, "name": "Rea Der"}
        if url.endswith("/checkout/sessions"):
            return {"url": "https://checkout.stripe.test/s/1"}
        raise AssertionError(url)

    monkeypatch.setattr(acct, "http", fake_http)
    srv = ThreadingHTTPServer(("127.0.0.1", 0), acct.Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_port}", calls
    srv.shutdown()


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None


def req(base, path, method="GET", cookies=None, data=None, headers=None):
    h = dict(headers or {})
    if cookies:
        h["Cookie"] = "; ".join(f"{k}={v}" for k, v in cookies.items())
    r = urllib.request.Request(base + path, data=data, headers=h, method=method)
    opener = urllib.request.build_opener(NoRedirect)
    try:
        resp = opener.open(r)
    except urllib.error.HTTPError as e:
        resp = e
    set_c = {}
    for v in resp.headers.get_all("Set-Cookie") or []:
        k, _, rest = v.partition("=")
        set_c[k] = rest.split(";")[0]
    return resp.status, resp.headers.get("Location", ""), set_c, resp.read()


def test_signed_tokens_and_redirect_safety(monkeypatch):
    monkeypatch.setenv("GBS_SESSION_SECRET", "s")
    t = acct.sign({"m": "google:1"}, 60)
    assert acct.unsign(t)["m"] == "google:1"
    assert acct.unsign(t[:-2] + "xx") is None
    assert acct.unsign(acct.sign({"m": 1}, -1)) is None              # expired
    assert acct.safe_next("//evil.example") == "/account/"
    assert acct.safe_next("https://evil.example") == "/account/"
    assert acct.safe_next("/membership/") == "/membership/"


def test_google_sign_in_round_trip_and_checkout(svc):
    base, calls = svc
    st, loc, ck, _ = req(base, "/auth/google/start?next=/membership/")
    assert st == 303 and loc.startswith("https://accounts.google.com/") and "code_challenge=" in loc
    state = dict(x.split("=", 1) for x in loc.split("?", 1)[1].split("&"))["state"]
    # wrong state is refused
    st, loc2, _, _ = req(base, "/auth/google/callback?code=good-code&state=nope", cookies={"gu_oauth": ck["gu_oauth"]})
    assert loc2.startswith("/login/?error=state")
    st, loc, ck2, _ = req(base, f"/auth/google/callback?code=good-code&state={state}", cookies={"gu_oauth": ck["gu_oauth"]})
    assert st == 303 and loc == "/membership/" and ck2["gu_m"] == "0" and ck2["gu_s"]
    st, _, _, body = req(base, "/auth/me", cookies={"gu_s": ck2["gu_s"]})
    me = json.loads(body)
    assert me["signed_in"] and me["email"] == "reader@example.com" and not me["paid"]
    # checkout: cross-site POST refused, same-site POST goes to Stripe
    st, _, _, _ = req(base, "/billing/checkout", "POST", {"gu_s": ck2["gu_s"]}, b"plan=monthly",
                      {"Origin": "https://evil.example"})
    assert st == 403
    st, loc, _, _ = req(base, "/billing/checkout", "POST", {"gu_s": ck2["gu_s"]}, b"plan=monthly",
                        {"Origin": "https://gu.example", "Content-Type": "application/x-www-form-urlencoded"})
    assert loc == "https://checkout.stripe.test/s/1"
    sent = next(d for m, u, d in calls if u.endswith("/checkout/sessions"))
    assert sent["mode"] == "subscription" and sent["line_items[0][price]"] == "price_m"
    assert sent["metadata[member]"] == "google:123" and sent["customer_email"] == "reader@example.com"
    # not-yet-priced plan is unavailable
    st, loc, _, _ = req(base, "/billing/checkout", "POST", {"gu_s": ck2["gu_s"]}, b"plan=yearly",
                        {"Origin": "https://gu.example"})
    assert "error=unavailable" in loc


def _signed(payload: bytes, secret="whsec_x", t=None):
    t = int(t or time.time())
    sig = hmac.new(secret.encode(), f"{t}.".encode() + payload, hashlib.sha256).hexdigest()
    return f"t={t},v1={sig}"


def test_webhook_signature_and_membership_lifecycle(svc):
    base, _ = svc
    acct.member_upsert_login("google:9", "google", "a@b.c", "A")
    ev = {"type": "checkout.session.completed", "data": {"object": {
        "mode": "subscription", "customer": "cus_1", "subscription": "sub_1", "client_reference_id": "google:9",
        "metadata": {"member": "google:9", "plan": "monthly"}}}}
    body = json.dumps(ev).encode()
    st, *_ = req(base, "/billing/webhook", "POST", data=body, headers={"Stripe-Signature": _signed(body, "wrong")})
    assert st == 400
    st, *_ = req(base, "/billing/webhook", "POST", data=body, headers={"Stripe-Signature": _signed(body, t=time.time() - 999)})
    assert st == 400
    st, _, _, out = req(base, "/billing/webhook", "POST", data=body, headers={"Stripe-Signature": _signed(body)})
    assert st == 200 and json.loads(out)["result"] == "checkout applied"
    assert acct.is_paid(acct.member_get("google:9"))
    gone = json.dumps({"type": "customer.subscription.deleted", "data": {"object": {
        "id": "sub_1", "customer": "cus_1", "status": "canceled", "metadata": {}}}}).encode()
    req(base, "/billing/webhook", "POST", data=gone, headers={"Stripe-Signature": _signed(gone)})
    assert not acct.is_paid(acct.member_get("google:9"))
    # founding = one-time payment -> lifetime
    acct.apply_event({"type": "checkout.session.completed", "data": {"object": {
        "mode": "payment", "payment_status": "paid", "customer": "cus_1", "metadata": {"member": "google:9", "plan": "founding"}}}})
    m = acct.member_get("google:9")
    assert m["lifetime"] == 1 and acct.is_paid(m) and acct.founding_count() == 1


def test_banned_member_is_anonymous(svc):
    base, _ = svc
    acct.member_upsert_login("google:7", "google", "x@y.z", "X")
    tok = acct.sign({"m": "google:7"}, 60)
    acct.member_update("google:7", banned=1)
    _, _, _, body = req(base, "/auth/me", cookies={"gu_s": tok})
    assert json.loads(body)["signed_in"] is False


# ------------------------------------------------------------------ local data

WX = {"current": {"temperature_2m": 8.6, "apparent_temperature": 6.1, "weather_code": 61, "wind_speed_10m": 14.2,
                  "relative_humidity_2m": 88},
      "daily": {"time": ["2026-11-06", "2026-11-07"], "weather_code": [61, 3], "temperature_2m_max": [10.2, 11],
                "temperature_2m_min": [5.1, 6], "precipitation_probability_max": [80, 30], "wind_speed_10m_max": [20, 10]}}
TR = {"events": [
    {"status": "ACTIVE", "severity": "MINOR", "event_type": "CONSTRUCTION", "roads": [{"name": "Hwy 1", "direction": "EASTBOUND"}],
     "description": "Lane closure."},
    {"status": "ACTIVE", "severity": "MAJOR", "event_type": "INCIDENT", "roads": [{"name": "Lions Gate Bridge"}],
     "description": "Crash, expect delays."},
    {"status": "ARCHIVED", "severity": "MAJOR", "roads": [{"name": "Old"}]}]}


def test_forecast_and_traffic_parsing():
    f = local.forecast_from_payload("Vancouver", WX)
    assert f["temp"] == 9 and f["cond"] == "light rain" and len(f["days"]) == 2 and f["days"][0]["pop"] == 80
    t = local.traffic_list(TR)
    assert [x["road"] for x in t] == ["Lions Gate Bridge", "Hwy 1"] and t[1]["direction"] == "eastbound"


def test_site_shows_weather_in_bar_and_local_pages(tmp_path):
    from gbs.config import Settings
    from gbs.models import Segment
    from gbs.site.build import build_site
    cfg = Settings()
    cfg.site_out, cfg.data_dir, cfg.site_url = tmp_path / "pub", tmp_path / "data", "https://gu.example"
    ld = cfg.data_dir / "local"
    ld.mkdir(parents=True)
    (ld / "weather.json").write_text(json.dumps({**local.forecast_from_payload("Vancouver", WX), "fetched": time.time()}))
    (ld / "traffic.json").write_text(json.dumps({"events": local.traffic_list(TR), "fetched": time.time()}))
    stock = cfg.data_dir / "stock"
    stock.mkdir()
    (stock / "abc.jpg").write_bytes(b"\xff" * 5000)
    (stock / "pool.json").write_text(json.dumps({"ts": time.time(), "pool": {"tech": [{"id": "abc", "file": "abc.jpg"}]}}))
    st = Story("a" * 64, "tech", "tech:bbc_tech", "Chipmaker unveils faster processor", "S.", "https://x.example", time.time())
    build_site(cfg, [Segment(story=st, anchor_id="Juno Park", script="Chipmaker unveils faster processor. It is fast.")])
    home = (cfg.site_out / "index.html").read_text()
    assert "9&deg;C</b> Light rain" in home and "Chipmaker unveils faster processor" in home   # weather after date; ticker
    assert "/img/stock/abc.jpg" in home and "Illustrative image" in home
    assert (cfg.site_out / "img" / "stock" / "abc.jpg").is_file()
    wx = (cfg.site_out / "local" / "weather" / "index.html").read_text()
    assert "7-day" not in wx and "2-day forecast" in wx and "Feels like 6" in wx
    tr = (cfg.site_out / "local" / "traffic" / "index.html").read_text()
    assert tr.index("Lions Gate Bridge") < tr.index("Hwy 1") and "Old" not in tr
    story = next((cfg.site_out / "story").rglob("*.html")).read_text()
    assert "Illustrative image" in story and "x.example" not in story


def test_stock_pick_is_stable_and_skips_unknown():
    urls = {"tech": ["/a.jpg", "/b.jpg", "/c.jpg"]}
    assert images.pick(urls, "tech", "slug-1") == images.pick(urls, "tech", "slug-1")
    assert images.pick(urls, "sports", "x") is None
    assert images.pick({"world": ["/w.jpg"]}, "sports", "x") == "/w.jpg"


# ------------------------------------------------------------------ confidentiality + fill

def test_scrub_and_public_view():
    assert scrub_outlets("Prices fell, The Guardian reports. That's according to NPR.") == "Prices fell."
    old = {"title": "Rates rise - BBC News", "slug": "x", "sources": [{"source": "business:bbc", "link": "l"}],
           "script": "Rates rise. The central bank moved again today. That's according to BBC News. Full sourcing is on our site."}
    v = public_view(old)
    assert v["title"] == "Rates rise" and v["script"] == "Rates rise." and v["standfirst"] == ""


def test_desk_briefs_fill_thin_desks():
    now = time.time()
    mk = lambda i, d, t: Story(f"{i:064x}", d, f"{d}:x", t, "s", "l", now)
    stories = [mk(1, "sports", "Canucks win in overtime"), mk(2, "sports", "Raptors sign guard"),
               mk(3, "science", "Telescope spots distant galaxy"), mk(4, "weather", "Rain all week"),
               mk(5, "sports", "Whitecaps clinch playoff spot")]
    out = desk_briefs(stories, taken={stories[0].item_hash}, per_desk=1)
    assert [s.story.desk for s in out] == ["sports", "science"]
    assert all(s.story.item_hash != stories[0].item_hash for s in out)
