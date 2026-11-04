"""Where an issue goes.

  file  (default) writes the issue to $GBS_DATA_DIR/newsletter/outbox/ for review;
        nothing is emailed. Use it until Kit is set up.
  kit   Kit (kit.com) API v4: POST /v4/broadcasts with the issue HTML and a send_at a few
        minutes ahead, so a bad issue can still be cancelled in Kit's dashboard. Kit's
        template wraps the content and adds the unsubscribe link and mailing address.
        Free Newsletter plan: up to 10,000 subscribers, unlimited broadcasts, API access.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

from gbs.newsletter.compose import Issue


class SendError(RuntimeError):
    pass


class FileProvider:
    name = "file"

    def __init__(self, outbox: Path):
        self.outbox = outbox

    def send(self, issue: Issue) -> str:
        self.outbox.mkdir(parents=True, exist_ok=True)
        page = (f"<!doctype html><meta charset='utf-8'><title>{issue.subject}</title>"
                f"<p style='font:13px Arial;color:#5b6372'>Subject: <b>{issue.subject}</b><br>Preheader: {issue.preheader}</p>"
                f"{issue.html}")
        p = self.outbox / f"{issue.date}.html"
        p.write_text(page, encoding="utf-8")
        (self.outbox / f"{issue.date}.txt").write_text(issue.text, encoding="utf-8")
        return str(p)


class KitProvider:
    name = "kit"
    API = "https://api.kit.com/v4"

    def __init__(self, api_key: str, template_id: str = "", delay_min: int = 10, base: str | None = None):
        if not api_key:
            raise SendError("KIT_API_KEY is not set")
        self.key, self.template_id, self.delay = api_key, template_id, delay_min
        self.base = (base or self.API).rstrip("/")

    def _post(self, path: str, body: dict) -> dict:
        req = urllib.request.Request(self.base + path, data=json.dumps(body).encode(), method="POST",
                                     headers={"X-Kit-Api-Key": self.key, "Content-Type": "application/json",
                                              "Accept": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.loads(r.read() or b"{}")
        except urllib.error.HTTPError as exc:
            raise SendError(f"Kit {path} -> {exc.code}: {exc.read()[:300]!r}") from exc

    def payload(self, issue: Issue, now: datetime | None = None) -> dict:
        now = now or datetime.now(timezone.utc)
        body = {
            "subject": issue.subject,
            "preview_text": issue.preheader,
            "content": issue.html,
            "description": f"The Gu Briefing {issue.date}",
            "public": False,  # our own web archive is the public copy
            "send_at": (now + timedelta(minutes=self.delay)).astimezone(timezone.utc).isoformat(timespec="seconds"),
            "subscriber_filter": [{"all": [{"type": "all_subscribers"}]}],
        }
        if self.template_id:
            body["email_template_id"] = int(self.template_id)
        return body

    def send(self, issue: Issue) -> str:
        out = self._post("/broadcasts", self.payload(issue))
        bid = (out.get("broadcast") or {}).get("id")
        if not bid:
            raise SendError(f"Kit returned no broadcast id: {out}")
        return f"kit:{bid}"


def provider_from_env(data_dir: Path):
    kind = os.getenv("GBS_NEWSLETTER_PROVIDER", "file").strip().lower()
    if kind == "kit":
        return KitProvider(os.getenv("KIT_API_KEY", ""), os.getenv("KIT_EMAIL_TEMPLATE_ID", ""),
                           int(os.getenv("KIT_SEND_DELAY_MIN", "10")), os.getenv("KIT_API_BASE") or None)
    return FileProvider(data_dir / "newsletter" / "outbox")
