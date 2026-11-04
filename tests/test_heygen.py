"""HeyGen Avatar III path against a local fake of the HeyGen API."""
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from gbs.anchors.heygen_client import HeyGenClient, HeyGenError
from gbs.cli import render_rundown
from gbs.config import Settings

ANCHOR = {"name": "Mina Gu", "heygen": {"character_type": "avatar", "avatar_id": "av_1",
          "voice_id": "vo_1", "background": {"type": "color", "value": "#0d0f14"}}}


class FakeHeyGen(BaseHTTPRequestHandler):
    calls: list = []
    polls: dict = {}

    def log_message(self, *a):
        pass

    def _json(self, obj, code=200):
        b = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b)

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        assert self.headers["X-Api-Key"] == "k"
        FakeHeyGen.calls.append((self.path, body))
        self._json({"error": None, "data": {"video_id": f"vid{len(FakeHeyGen.calls)}"}})

    def do_GET(self):
        if self.path.startswith("/v1/video_status.get"):
            vid = self.path.split("video_id=")[1]
            n = FakeHeyGen.polls[vid] = FakeHeyGen.polls.get(vid, 0) + 1
            status = "completed" if n > 1 else "processing"
            url = f"http://127.0.0.1:{self.server.server_port}/files/{vid}.mp4"
            return self._json({"error": None, "data": {"status": status, "video_url": url}})
        if self.path.startswith("/files/"):
            self.send_response(200)
            self.end_headers()
            return self.wfile.write(b"MP4DATA")
        if self.path == "/v2/avatars":
            return self._json({"error": None, "data": {"avatars": [{"avatar_id": "av_1"}]}})
        self._json({"error": "nope"}, 404)


@pytest.fixture
def fake():
    FakeHeyGen.calls, FakeHeyGen.polls = [], {}
    srv = HTTPServer(("127.0.0.1", 0), FakeHeyGen)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_port}"
    srv.shutdown()


def test_payload_avatar_iii_shape():
    p = HeyGenClient.build_payload(ANCHOR, "Hello world.", title="T", test=True)
    scene = p["video_inputs"][0]
    assert scene["character"] == {"type": "avatar", "avatar_id": "av_1", "avatar_style": "normal"}
    assert scene["voice"]["type"] == "text" and scene["voice"]["voice_id"] == "vo_1"
    assert p["dimension"] == {"width": 1920, "height": 1080} and p["test"] is True


def test_payload_talking_photo_and_validation():
    tp = {"name": "X", "heygen": {"character_type": "talking_photo", "talking_photo_id": "tp9", "voice_id": "v"}}
    assert HeyGenClient.build_payload(tp, "hi")["video_inputs"][0]["character"] == \
        {"type": "talking_photo", "talking_photo_id": "tp9"}
    with pytest.raises(HeyGenError):
        HeyGenClient.build_payload({"name": "Y", "heygen": {"avatar_id": "a"}}, "hi")  # no voice


def test_render_rundown_heygen(fake, tmp_path, monkeypatch):
    import gbs.anchors.heygen_client as hc
    monkeypatch.setattr(hc.time, "sleep", lambda s: None)
    monkeypatch.setattr("gbs.anchors.roster.load_roster", lambda: [ANCHOR])
    monkeypatch.setattr("shutil.which", lambda name: None)  # skip ffmpeg compose
    cfg = Settings()
    cfg.site_out, cfg.data_dir = tmp_path / "public", tmp_path / "data"
    cfg.anchor_engine, cfg.heygen_api_key, cfg.heygen_base, cfg.heygen_test = "heygen", "k", fake, True
    rundown = [{"slug": f"s{i}", "title": f"Story {i}", "anchor": "Mina Gu",
                "script": f"Read {i}.", "sponsor_read": "Sponsored by X." if i == 1 else None}
               for i in range(4)]
    out = render_rundown(cfg, rundown, top=2)
    assert out == {"s0": "/v/s0.mp4", "s1": "/v/s1.mp4"}
    assert (cfg.site_out / "v" / "s1.mp4").read_bytes() == b"MP4DATA"
    posts = [b for path, b in FakeHeyGen.calls if path == "/v2/video/generate"]
    assert len(posts) == 2  # both submitted before waiting (parallel render)
    assert posts[1]["video_inputs"][0]["voice"]["input_text"].endswith("Sponsored by X.")
    assert all(b["test"] for b in posts)
