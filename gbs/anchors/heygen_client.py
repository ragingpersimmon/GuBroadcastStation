"""HeyGen Avatar III client -- the default anchor engine.

Avatar III is the engine behind HeyGen's standard v2 generate endpoint:
    POST https://api.heygen.com/v2/video/generate   (X-Api-Key header)
    GET  https://api.heygen.com/v1/video_status.get?video_id=...
HeyGen does the voice too (voice.type="text"), so no local TTS is needed.

Each anchor in config/newsroom.json carries a `heygen` block:
    {"character_type": "avatar" | "talking_photo",
     "avatar_id": "...",              # public / instant avatar (type avatar)
     "talking_photo_id": "...",       # photo avatar (e.g. ComfyUI-designed face)
     "avatar_style": "normal",
     "voice_id": "...", "speed": 1.0,
     "background": {"type": "color", "value": "#0d0f14"}   # or {"type":"image","url":...}
    }
"""
from __future__ import annotations

import json
import time
import urllib.parse
import urllib.request
from pathlib import Path

API = "https://api.heygen.com"
MAX_CHARS = 5000  # HeyGen per-scene text cap; our reads are ~100 words


class HeyGenError(RuntimeError):
    pass


class HeyGenClient:
    def __init__(self, api_key: str, base: str = API, timeout: int = 60):
        if not api_key:
            raise HeyGenError("HEYGEN_API_KEY not set")
        self.key, self.base, self.timeout = api_key, base.rstrip("/"), timeout

    def _req(self, method: str, path: str, body: dict | None = None) -> dict:
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(self.base + path, data=data, method=method, headers={
            "X-Api-Key": self.key, "Accept": "application/json",
            **({"Content-Type": "application/json"} if data else {})})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                out = json.loads(r.read())
        except urllib.error.HTTPError as e:
            raise HeyGenError(f"HeyGen {method} {path} -> {e.code}: {e.read()[:300]!r}") from e
        if out.get("error"):
            raise HeyGenError(f"HeyGen error: {out['error']}")
        return out.get("data") or {}

    # -- discovery (use once to fill config/newsroom.json) --
    def list_avatars(self) -> list[dict]:
        return self._req("GET", "/v2/avatars").get("avatars", [])

    def list_voices(self) -> list[dict]:
        return self._req("GET", "/v2/voices").get("voices", [])

    def remaining_quota(self) -> dict:
        return self._req("GET", "/v2/user/remaining_quota")

    # -- generation --
    @staticmethod
    def build_payload(anchor: dict, text: str, title: str = "", test: bool = False,
                      width: int = 1920, height: int = 1080, callback_id: str = "") -> dict:
        h = anchor.get("heygen") or {}
        ctype = h.get("character_type", "avatar")
        if ctype == "talking_photo":
            if not h.get("talking_photo_id"):
                raise HeyGenError(f"{anchor.get('name')}: heygen.talking_photo_id missing")
            character = {"type": "talking_photo", "talking_photo_id": h["talking_photo_id"]}
        else:
            if not h.get("avatar_id"):
                raise HeyGenError(f"{anchor.get('name')}: heygen.avatar_id missing")
            character = {"type": "avatar", "avatar_id": h["avatar_id"],
                         "avatar_style": h.get("avatar_style", "normal")}
        if not h.get("voice_id"):
            raise HeyGenError(f"{anchor.get('name')}: heygen.voice_id missing")
        scene = {
            "character": character,
            "voice": {"type": "text", "input_text": text[:MAX_CHARS],
                      "voice_id": h["voice_id"], "speed": float(h.get("speed", 1.0))},
        }
        if h.get("background"):
            scene["background"] = h["background"]
        body = {"video_inputs": [scene], "dimension": {"width": width, "height": height},
                "test": bool(test)}
        if title:
            body["title"] = title[:100]
        if callback_id:
            body["callback_id"] = callback_id
        return body

    def generate(self, anchor: dict, text: str, **kw) -> str:
        data = self._req("POST", "/v2/video/generate", self.build_payload(anchor, text, **kw))
        vid = data.get("video_id")
        if not vid:
            raise HeyGenError(f"no video_id in response: {data}")
        return vid

    def status(self, video_id: str) -> dict:
        q = urllib.parse.urlencode({"video_id": video_id})
        return self._req("GET", f"/v1/video_status.get?{q}")

    def wait(self, video_id: str, max_wait: float = 1800, poll: float = 10) -> dict:
        deadline = time.time() + max_wait
        while time.time() < deadline:
            st = self.status(video_id)
            s = st.get("status")
            if s == "completed":
                return st
            if s == "failed":
                raise HeyGenError(f"video {video_id} failed: {st.get('error')}")
            time.sleep(poll)
        raise TimeoutError(f"HeyGen video {video_id} not done after {max_wait}s")

    def render(self, anchor: dict, text: str, dest: Path, **kw) -> Path:
        """Generate, wait, download. video_url is a signed, expiring URL --
        download immediately."""
        st = self.wait(self.generate(anchor, text, **kw))
        dest.parent.mkdir(parents=True, exist_ok=True)
        with urllib.request.urlopen(st["video_url"], timeout=300) as r:
            dest.write_bytes(r.read())
        return dest
