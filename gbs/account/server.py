"""Sign-in + membership service for gubs.ca (stdlib only, 127.0.0.1:8710).

nginx proxies /auth/ and /billing/ here; everything else on the site stays
static. Pattern follows the flowerseekingbee.com Hive membership.

Sign-in: OAuth 2.0 authorization-code flow (+ PKCE, + state) with any
provider whose client id/secret is set in .env:
    google     GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET
    microsoft  MICROSOFT_CLIENT_ID / MICROSOFT_CLIENT_SECRET
    github     GITHUB_CLIENT_ID / GITHUB_CLIENT_SECRET
    facebook   FACEBOOK_CLIENT_ID / FACEBOOK_CLIENT_SECRET
Redirect URI to register with each: https://gubs.ca/auth/<provider>/callback
Identity comes from the provider's userinfo endpoint over TLS, using the
access token we just exchanged server-side, so no JWT library is needed.

Session: HMAC-signed cookie `gu_s` (HttpOnly, Secure, SameSite=Lax; Lax so
the provider's top-level redirect back carries it). `gu_m=1` (readable by
JS) marks paying members so the page can hide ad slots.

Billing (off until STRIPE_SECRET_KEY + STRIPE_WEBHOOK_SECRET + a plan's
price id are set): Stripe Checkout (subscription or one-time "founding"),
Billing portal, signed webhook at /billing/webhook. The browser never sees
a Stripe key.

Members: SQLite at $GBS_DATA_DIR/members.db.

    python -m gbs account-server      (systemd: gubroadcast-account.service)
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import os
import secrets
import sqlite3
import time
import urllib.parse
import urllib.request
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

log = logging.getLogger("gbs.account")

REPO = Path(__file__).resolve().parents[2]
PLANS_CONF = REPO / "config" / "membership.json"
SESSION_DAYS = 30
STRIPE_API = "https://api.stripe.com/v1"
PAID_STATES = frozenset({"active", "trialing", "past_due"})
SIG_TOLERANCE = 300

PROVIDERS = {
    "google": {"label": "Google", "auth": "https://accounts.google.com/o/oauth2/v2/auth",
               "token": "https://oauth2.googleapis.com/token",
               "userinfo": "https://openidconnect.googleapis.com/v1/userinfo", "scope": "openid email profile"},
    "microsoft": {"label": "Microsoft", "auth": "https://login.microsoftonline.com/common/oauth2/v2.0/authorize",
                  "token": "https://login.microsoftonline.com/common/oauth2/v2.0/token",
                  "userinfo": "https://graph.microsoft.com/oidc/userinfo", "scope": "openid email profile"},
    "github": {"label": "GitHub", "auth": "https://github.com/login/oauth/authorize",
               "token": "https://github.com/login/oauth/access_token",
               "userinfo": "https://api.github.com/user", "scope": "read:user user:email"},
    "facebook": {"label": "Facebook", "auth": "https://www.facebook.com/v19.0/dialog/oauth",
                 "token": "https://graph.facebook.com/v19.0/oauth/access_token",
                 "userinfo": "https://graph.facebook.com/me?fields=id,name,email", "scope": "email,public_profile"},
}


# ------------------------------------------------------------------ config

def env(name: str, default: str = "") -> str:
    return (os.environ.get(name) or default).strip()


def site_url() -> str:
    return env("GBS_SITE_URL", "https://gubs.ca").rstrip("/")


def secret() -> bytes:
    s = env("GBS_SESSION_SECRET")
    if not s:
        raise RuntimeError("GBS_SESSION_SECRET is not set")
    return s.encode()


def enabled_providers() -> list[str]:
    return [p for p in PROVIDERS if env(f"{p.upper()}_CLIENT_ID") and env(f"{p.upper()}_CLIENT_SECRET")]


def load_plans() -> dict:
    return json.loads(PLANS_CONF.read_text())


def plan_price(plan: dict) -> str:
    return env(plan.get("price_env", ""))


def billing_on() -> bool:
    return bool(env("STRIPE_SECRET_KEY") and env("STRIPE_WEBHOOK_SECRET"))


# ------------------------------------------------------------------ signed tokens

def _b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def _unb64(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def sign(payload: dict, ttl: int) -> str:
    body = _b64(json.dumps({**payload, "exp": int(time.time()) + ttl}, separators=(",", ":")).encode())
    mac = _b64(hmac.new(secret(), body.encode(), hashlib.sha256).digest())
    return f"{body}.{mac}"


def unsign(token: str | None) -> dict | None:
    if not token or "." not in token:
        return None
    body, mac = token.rsplit(".", 1)
    good = _b64(hmac.new(secret(), body.encode(), hashlib.sha256).digest())
    if not hmac.compare_digest(mac, good):
        return None
    try:
        d = json.loads(_unb64(body))
    except Exception:
        return None
    return d if d.get("exp", 0) >= time.time() else None


def safe_next(n: str | None) -> str:
    """Only same-site paths: no open redirects."""
    if not n or not n.startswith("/") or n.startswith("//") or "\\" in n:
        return "/account/"
    return n


# ------------------------------------------------------------------ members

def db_path() -> Path:
    return Path(env("GBS_DATA_DIR", str(REPO / "data"))) / "members.db"


def conn() -> sqlite3.Connection:
    p = db_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(str(p), timeout=5)
    c.row_factory = sqlite3.Row
    c.execute("""CREATE TABLE IF NOT EXISTS members(
        id TEXT PRIMARY KEY, provider TEXT, email TEXT, name TEXT, first_seen REAL, last_seen REAL,
        logins INTEGER DEFAULT 0, banned INTEGER DEFAULT 0, comp INTEGER DEFAULT 0, lifetime INTEGER DEFAULT 0,
        plan TEXT, stripe_customer TEXT, stripe_sub TEXT, sub_status TEXT, period_end REAL)""")
    return c


def member_get(mid: str | None = None, customer: str | None = None) -> dict | None:
    with conn() as c:
        if customer:
            r = c.execute("SELECT * FROM members WHERE stripe_customer=?", (customer,)).fetchone()
        else:
            r = c.execute("SELECT * FROM members WHERE id=?", (mid,)).fetchone()
    return dict(r) if r else None


def member_upsert_login(mid: str, provider: str, email: str, name: str) -> dict:
    now = time.time()
    with conn() as c:
        c.execute("""INSERT INTO members(id, provider, email, name, first_seen, last_seen, logins)
                     VALUES(?,?,?,?,?,?,1) ON CONFLICT(id) DO UPDATE SET email=excluded.email,
                     name=excluded.name, last_seen=excluded.last_seen, logins=logins+1""",
                  (mid, provider, email, name, now, now))
    return member_get(mid)


def member_update(mid: str, **fields) -> None:
    if not fields:
        return
    cols = ", ".join(f"{k}=?" for k in fields)
    with conn() as c:
        c.execute(f"UPDATE members SET {cols} WHERE id=?", (*fields.values(), mid))


def is_paid(m: dict | None) -> bool:
    return bool(m and not m.get("banned") and (m.get("lifetime") or m.get("comp") or m.get("sub_status") in PAID_STATES))


def founding_count() -> int:
    with conn() as c:
        return c.execute("SELECT COUNT(*) FROM members WHERE lifetime=1").fetchone()[0]


def public_member(m: dict | None) -> dict:
    if not m or m.get("banned"):
        return {"signed_in": False, "providers": enabled_providers(), "billing": billing_on()}
    plan = m.get("plan") if is_paid(m) else None
    return {"signed_in": True, "name": m.get("name") or "", "email": m.get("email") or "",
            "provider": m.get("provider"), "paid": is_paid(m), "plan": plan,
            "lifetime": bool(m.get("lifetime")), "renews": m.get("period_end"),
            "status": m.get("sub_status"), "billing": billing_on(), "portal": bool(m.get("stripe_customer"))}


# ------------------------------------------------------------------ http helpers (patched in tests)

def http(method: str, url: str, data: dict | None = None, headers: dict | None = None,
         form: bool = True, timeout: int = 15) -> dict:
    body = None
    h = {"Accept": "application/json", "User-Agent": "gubs-account/1.0", **(headers or {})}
    if data is not None:
        body = urllib.parse.urlencode(data).encode() if form else json.dumps(data).encode()
        h["Content-Type"] = "application/x-www-form-urlencoded" if form else "application/json"
    req = urllib.request.Request(url, data=body, headers=h, method=method)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read() or b"{}")


# ------------------------------------------------------------------ OAuth

def pkce() -> tuple[str, str]:
    verifier = _b64(secrets.token_bytes(32))
    challenge = _b64(hashlib.sha256(verifier.encode()).digest())
    return verifier, challenge


def authorize_url(provider: str, state: str, challenge: str) -> str:
    p = PROVIDERS[provider]
    q = {"client_id": env(f"{provider.upper()}_CLIENT_ID"), "redirect_uri": f"{site_url()}/auth/{provider}/callback",
         "response_type": "code", "scope": p["scope"], "state": state}
    if provider in ("google", "microsoft"):
        q.update(code_challenge=challenge, code_challenge_method="S256")
    if provider == "google":
        q["prompt"] = "select_account"
    return f"{p['auth']}?{urllib.parse.urlencode(q)}"


def exchange(provider: str, code: str, verifier: str) -> dict:
    """code -> {id, email, name}. Raises on any failure."""
    p = PROVIDERS[provider]
    data = {"client_id": env(f"{provider.upper()}_CLIENT_ID"), "client_secret": env(f"{provider.upper()}_CLIENT_SECRET"),
            "code": code, "redirect_uri": f"{site_url()}/auth/{provider}/callback", "grant_type": "authorization_code"}
    if provider in ("google", "microsoft"):
        data["code_verifier"] = verifier
    tok = http("POST", p["token"], data)
    access = tok.get("access_token")
    if not access:
        raise ValueError(f"{provider}: no access token")
    auth = {"Authorization": f"Bearer {access}"}
    u = http("GET", p["userinfo"], headers=auth)
    if provider == "github":
        email = u.get("email")
        try:
            emails = http("GET", "https://api.github.com/user/emails", headers=auth)
            email = next((x["email"] for x in emails if x.get("primary") and x.get("verified")), email) \
                if isinstance(emails, list) else email
        except Exception:
            pass
        return {"id": f"github:{u['id']}", "email": email or "", "name": u.get("name") or u.get("login") or ""}
    if provider == "google" and u.get("email") and not u.get("email_verified", True):
        raise ValueError("google: email not verified")
    sub = u.get("sub") or u.get("id")
    if not sub:
        raise ValueError(f"{provider}: no subject")
    return {"id": f"{provider}:{sub}", "email": u.get("email") or "", "name": u.get("name") or ""}


# ------------------------------------------------------------------ Stripe

def stripe(method: str, path: str, data: dict | None = None) -> dict:
    return http(method, f"{STRIPE_API}{path}", data, headers={"Authorization": f"Bearer {env('STRIPE_SECRET_KEY')}"})


def checkout_session(m: dict, plan: dict) -> str:
    sid = "{CHECKOUT_SESSION_ID}"
    data = {"mode": plan["mode"], "line_items[0][price]": plan_price(plan), "line_items[0][quantity]": "1",
            "success_url": f"{site_url()}/membership/thanks/?session_id={sid}",
            "cancel_url": f"{site_url()}/membership/", "client_reference_id": m["id"],
            "metadata[member]": m["id"], "metadata[plan]": plan["id"], "allow_promotion_codes": "true"}
    if m.get("stripe_customer"):
        data["customer"] = m["stripe_customer"]
    elif m.get("email"):
        data["customer_email"] = m["email"]
    if plan["mode"] == "subscription":
        data["subscription_data[metadata][member]"] = m["id"]
        data["subscription_data[metadata][plan]"] = plan["id"]
    elif not m.get("stripe_customer"):
        data["customer_creation"] = "always"
    return stripe("POST", "/checkout/sessions", data)["url"]


def portal_session(m: dict) -> str:
    return stripe("POST", "/billing_portal/sessions",
                  {"customer": m["stripe_customer"], "return_url": f"{site_url()}/account/"})["url"]


def verify_webhook(payload: bytes, header: str, whsec: str, now: float | None = None) -> dict:
    parts = dict(kv.split("=", 1) for kv in (header or "").split(",") if "=" in kv)
    sigs = [kv.split("=", 1)[1] for kv in (header or "").split(",") if kv.startswith("v1=")]
    t = parts.get("t")
    if not t or not sigs:
        raise ValueError("bad signature header")
    if abs((now or time.time()) - int(t)) > SIG_TOLERANCE:
        raise ValueError("timestamp outside tolerance")
    good = hmac.new(whsec.encode(), f"{t}.".encode() + payload, hashlib.sha256).hexdigest()
    if not any(hmac.compare_digest(good, s) for s in sigs):
        raise ValueError("signature mismatch")
    return json.loads(payload)


def apply_event(ev: dict) -> str:
    kind, obj = ev.get("type", ""), (ev.get("data") or {}).get("object") or {}
    if kind == "checkout.session.completed":
        mid = (obj.get("metadata") or {}).get("member") or obj.get("client_reference_id")
        plan = (obj.get("metadata") or {}).get("plan")
        if not mid or not member_get(mid):
            return "unknown member"
        f = {"stripe_customer": obj.get("customer"), "plan": plan}
        if obj.get("mode") == "payment" and obj.get("payment_status") == "paid":
            f["lifetime"] = 1
        if obj.get("subscription"):
            f.update(stripe_sub=obj["subscription"], sub_status="active")
        member_update(mid, **{k: v for k, v in f.items() if v is not None})
        return "checkout applied"
    if kind.startswith("customer.subscription."):
        mid = (obj.get("metadata") or {}).get("member")
        m = member_get(mid) if mid else member_get(customer=obj.get("customer"))
        if not m:
            return "unknown member"
        status = "canceled" if kind.endswith(".deleted") else obj.get("status")
        f = {"stripe_sub": obj.get("id"), "sub_status": status, "stripe_customer": obj.get("customer"),
             "period_end": obj.get("current_period_end") or
             ((obj.get("items") or {}).get("data") or [{}])[0].get("current_period_end")}
        if (obj.get("metadata") or {}).get("plan"):
            f["plan"] = obj["metadata"]["plan"]
        member_update(m["id"], **{k: v for k, v in f.items() if v is not None})
        return f"subscription {status}"
    return "ignored"


# ------------------------------------------------------------------ handler

class Handler(BaseHTTPRequestHandler):
    server_version = "gubs-account"

    def log_message(self, fmt, *args):  # no IPs or query strings in logs
        log.info("%s %s", self.command, self.path.split("?")[0])

    # --- plumbing
    def cookies(self) -> dict:
        c = SimpleCookie()
        try:
            c.load(self.headers.get("Cookie", ""))
        except Exception:
            return {}
        return {k: v.value for k, v in c.items()}

    def member(self) -> dict | None:
        s = unsign(self.cookies().get("gu_s"))
        if not s:
            return None
        m = member_get(s.get("m"))
        return None if not m or m.get("banned") else m

    def send(self, code: int, body: bytes = b"", ctype: str = "application/json", headers: list | None = None):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Cache-Control", "no-store")
        for k, v in headers or []:
            self.send_header(k, v)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def json(self, obj, code: int = 200, headers: list | None = None):
        self.send(code, json.dumps(obj).encode(), headers=headers)

    def redirect(self, url: str, headers: list | None = None):
        self.send(303, b"", "text/plain", [("Location", url), *(headers or [])])

    @staticmethod
    def cookie(name: str, value: str, max_age: int, http_only: bool = True) -> tuple:
        parts = [f"{name}={value}", "Path=/", f"Max-Age={max_age}", "Secure", "SameSite=Lax"]
        if http_only:
            parts.append("HttpOnly")
        return ("Set-Cookie", "; ".join(parts))

    def session_cookies(self, m: dict) -> list:
        age = SESSION_DAYS * 86400
        return [self.cookie("gu_s", sign({"m": m["id"]}, age), age),
                self.cookie("gu_m", "1" if is_paid(m) else "0", age, http_only=False)]

    def same_origin(self) -> bool:
        o = self.headers.get("Origin") or self.headers.get("Referer") or ""
        return not o or o.startswith(site_url())

    def form(self) -> dict:
        n = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(n) if n else b""
        return {k: v[0] for k, v in urllib.parse.parse_qs(raw.decode()).items()}

    # --- routes
    def do_HEAD(self):
        self.do_GET()

    def do_GET(self):
        u = urllib.parse.urlparse(self.path)
        q = {k: v[0] for k, v in urllib.parse.parse_qs(u.query).items()}
        parts = u.path.strip("/").split("/")
        try:
            if u.path == "/auth/me":
                return self.json(public_member(self.member()))
            if u.path == "/auth/health":
                return self.json({"ok": True, "providers": enabled_providers(), "billing": billing_on()})
            if len(parts) == 3 and parts[0] == "auth" and parts[1] in PROVIDERS:
                if parts[2] == "start":
                    return self.start(parts[1], q)
                if parts[2] == "callback":
                    return self.callback(parts[1], q)
            return self.json({"error": "not found"}, 404)
        except Exception:
            log.exception("GET %s failed", u.path)
            return self.redirect("/login/?error=1")

    def do_POST(self):
        path = urllib.parse.urlparse(self.path).path
        try:
            if path == "/billing/webhook":
                return self.webhook()
            if not self.same_origin():
                return self.json({"error": "bad origin"}, 403)
            if path == "/api/inquiry":
                return self.inquiry(self.form())
            if path == "/auth/logout":
                return self.redirect("/", [self.cookie("gu_s", "", 0), self.cookie("gu_m", "", 0, http_only=False)])
            if path == "/billing/checkout":
                return self.checkout(self.form())
            if path == "/billing/portal":
                m = self.member()
                if not m or not m.get("stripe_customer") or not billing_on():
                    return self.redirect("/account/")
                return self.redirect(portal_session(m))
            return self.json({"error": "not found"}, 404)
        except Exception:
            log.exception("POST %s failed", path)
            return self.redirect("/membership/?error=1")

    def start(self, provider: str, q: dict):
        if provider not in enabled_providers():
            return self.redirect("/login/?error=provider")
        state = secrets.token_urlsafe(24)
        verifier, challenge = pkce()
        tok = sign({"s": state, "v": verifier, "p": provider, "n": safe_next(q.get("next"))}, 600)
        return self.redirect(authorize_url(provider, state, challenge), [self.cookie("gu_oauth", tok, 600)])

    def callback(self, provider: str, q: dict):
        st = unsign(self.cookies().get("gu_oauth"))
        clear = self.cookie("gu_oauth", "", 0)
        if not st or st.get("p") != provider or not q.get("code") or \
                not hmac.compare_digest(st.get("s", ""), q.get("state", "")):
            return self.redirect("/login/?error=state", [clear])
        who = exchange(provider, q["code"], st["v"])
        prior = member_get(who["id"])
        if prior and prior.get("banned"):
            return self.redirect("/login/?error=blocked", [clear])
        m = member_upsert_login(who["id"], provider, who["email"], who["name"])
        return self.redirect(st.get("n") or "/account/", [clear, *self.session_cookies(m)])

    def checkout(self, f: dict):
        m = self.member()
        if not m:
            return self.redirect(f"/login/?next={urllib.parse.quote('/membership/')}")
        plan = next((p for p in load_plans()["plans"] if p["id"] == f.get("plan")), None)
        if not plan or not billing_on() or not plan_price(plan):
            return self.redirect("/membership/?error=unavailable")
        if is_paid(m) and (m.get("lifetime") or plan["mode"] == "subscription"):
            return self.redirect("/account/")
        if plan["mode"] == "payment" and plan.get("limit") and founding_count() >= plan["limit"]:
            return self.redirect("/membership/?error=soldout")
        return self.redirect(checkout_session(m, plan))

    def inquiry(self, f: dict):
        from gbs.account import inquiries
        g, err = inquiries.validate(f)
        if err == "spam":
            return self.redirect("/work-with-us/thanks/")          # don't tell bots they were caught
        if err:
            return self.redirect(f"/work-with-us/?error={err}#form")
        site = json.loads((REPO / "config" / "site.json").read_text())
        rec = inquiries.save(conn(), g, site)
        log.info("inquiry %s (%s)", rec["ref"], rec["kind"])
        return self.redirect(f"/work-with-us/thanks/?ref={urllib.parse.quote(rec['ref'])}")

    def webhook(self):
        n = int(self.headers.get("Content-Length") or 0)
        payload = self.rfile.read(n) if n else b""
        try:
            ev = verify_webhook(payload, self.headers.get("Stripe-Signature", ""), env("STRIPE_WEBHOOK_SECRET"))
        except Exception as exc:
            log.warning("webhook rejected: %s", exc)
            return self.json({"error": "invalid signature"}, 400)
        return self.json({"result": apply_event(ev)})


def serve(host: str = "127.0.0.1", port: int | None = None) -> None:
    secret()  # fail fast without a session secret
    port = port or int(env("GBS_ACCOUNT_PORT", "8710"))
    conn().close()
    log.info("account service on %s:%s; providers=%s billing=%s", host, port, enabled_providers(), billing_on())
    ThreadingHTTPServer((host, port), Handler).serve_forever()
