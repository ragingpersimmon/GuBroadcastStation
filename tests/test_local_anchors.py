"""Local anchor engine: tokenizer, GPU handoff, and a full studio pass against
a fake ComfyUI (upload -> prompt -> history -> view -> free)."""
import io
import json
import threading
import wave
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

import gbs.anchors.comfy_client as cc
import gbs.cli as cli
from gbs.anchors.comfy_tokenize import tokenize
from gbs.config import Settings
from gbs.studio.render import wan_frames

INFINITETALK_EXPORT = {
    "1": {"class_type": "LoadImage", "inputs": {"image": "anchor.png"}},
    "2": {"class_type": "LoadAudio", "inputs": {"audio": "read.wav"}},
    "3": {"class_type": "MultiTalkWav2VecEmbeds", "inputs": {"audio": ["2", 0], "num_frames": 81, "fps": 25}},
    "4": {"class_type": "WanVideoTextEncode", "inputs": {"positive_prompt": "a man talking", "negative_prompt": "bad"}},
    "5": {"class_type": "WanVideoSampler", "inputs": {"seed": 42, "steps": 4, "text_embeds": ["4", 0]}},
    "6": {"class_type": "VHS_VideoCombine", "inputs": {"filename_prefix": "InfiniteTalk", "frame_rate": 25}},
}
OMNIVOICE_EXPORT = {
    "1": {"class_type": "LoadAudio", "inputs": {"audio": "ref.wav"}},
    "2": {"class_type": "OmniVoiceTTS", "inputs": {"text": "hello", "ref_audio": ["1", 0], "seed": 7}},
    "3": {"class_type": "SaveAudio", "inputs": {"audio": ["2", 0], "filename_prefix": "audio/tts"}},
}
DESIGN_EXPORT = {
    "1": {"class_type": "OmniVoiceDesign", "inputs": {"text": "hello", "instruct": "calm man", "seed": 1}},
    "2": {"class_type": "SaveAudio", "inputs": {"audio": ["1", 0], "filename_prefix": "audio/x"}},
}
PORTRAIT_EXPORT = {
    "1": {"class_type": "CLIPTextEncode", "inputs": {"text": "a cat", "clip": ["9", 0]}},
    "2": {"class_type": "CLIPTextEncode", "inputs": {"text": "ugly", "clip": ["9", 0]}},
    "3": {"class_type": "KSampler", "inputs": {"seed": 5, "positive": ["1", 0], "negative": ["2", 0]}},
    "4": {"class_type": "SaveImage", "inputs": {"filename_prefix": "ComfyUI", "images": ["3", 0]}},
}


def test_tokenize_infinitetalk():
    wf, hits = tokenize(INFINITETALK_EXPORT, "anchor_talking")
    assert set(hits) >= {"REF_IMAGE", "AUDIO_PATH", "NUM_FRAMES", "POSITIVE", "NEGATIVE", "SEED", "OUT_PREFIX"}
    assert wf["3"]["inputs"]["audio"] == ["2", 0]          # links untouched
    assert wf["3"]["inputs"]["fps"] == 25                  # non-job inputs untouched


def test_tokenize_tts_and_portrait():
    _, h = tokenize(OMNIVOICE_EXPORT, "tts")
    assert set(h) == {"VOICE_REF", "TEXT", "SEED", "OUT_PREFIX"}
    _, h = tokenize(DESIGN_EXPORT, "tts_design")
    assert set(h) == {"TEXT", "VOICE_PROMPT", "SEED", "OUT_PREFIX"}
    wf, h = tokenize(PORTRAIT_EXPORT, "anchor_portrait")
    assert wf["1"]["inputs"]["text"] == "{{POSITIVE}}" and wf["2"]["inputs"]["text"] == "{{NEGATIVE}}"


def test_wan_frames():
    for sec in (0.5, 3.3, 40, 61.7):
        f = wan_frames(sec)
        assert f % 4 == 1 and f >= sec * 25


def _wav(seconds=2.0) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(16000)
        w.writeframes(b"\x00\x00" * int(16000 * seconds))
    return buf.getvalue()


class FakeComfy(BaseHTTPRequestHandler):
    prompts, uploads, frees = [], [], 0

    def log_message(self, *a):
        pass

    def _json(self, obj):
        b = json.dumps(obj).encode()
        self.send_response(200); self.send_header("Content-Type", "application/json"); self.end_headers()
        self.wfile.write(b)

    def do_GET(self):
        if self.path == "/system_stats":
            return self._json({"system": {}})
        if self.path.startswith("/history/"):
            pid = self.path.rsplit("/", 1)[1]
            wf = FakeComfy.prompts[int(pid)]
            if any(n["class_type"] == "SaveAudio" for n in wf.values()):
                out = {"9": {"audio": [{"filename": f"voice{pid}.wav", "subfolder": "gbs", "type": "output"}]}}
            elif any(n["class_type"] == "SaveImage" for n in wf.values()):
                out = {"9": {"images": [{"filename": f"p{pid}.png", "subfolder": "", "type": "output"}]}}
            else:
                out = {"9": {"gifs": [{"filename": f"clip{pid}.mp4", "subfolder": "gbs", "type": "output"}]}}
            return self._json({pid: {"status": {"status_str": "success"}, "outputs": out}})
        if self.path.startswith("/view"):
            self.send_response(200); self.end_headers()
            return self.wfile.write(_wav() if ".wav" in self.path else b"FILEDATA")

    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(n)
        if self.path == "/upload/image":
            name = body.split(b'filename="')[1].split(b'"')[0].decode()
            FakeComfy.uploads.append(name)
            return self._json({"name": name, "subfolder": "gbs", "type": "input"})
        if self.path == "/prompt":
            FakeComfy.prompts.append(json.loads(body)["prompt"])
            return self._json({"prompt_id": str(len(FakeComfy.prompts) - 1)})
        if self.path == "/free":
            FakeComfy.frees += 1
            return self._json({})


@pytest.fixture
def comfy(tmp_path, monkeypatch):
    FakeComfy.prompts, FakeComfy.uploads, FakeComfy.frees = [], [], 0
    srv = HTTPServer(("127.0.0.1", 0), FakeComfy)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    wfdir = tmp_path / "wf"
    wfdir.mkdir()
    for kind, src in (("anchor_talking", INFINITETALK_EXPORT), ("tts", OMNIVOICE_EXPORT),
                      ("tts_design", DESIGN_EXPORT), ("anchor_portrait", PORTRAIT_EXPORT)):
        (wfdir / f"{kind}.json").write_text(json.dumps(tokenize(src, kind)[0]))
    monkeypatch.setattr(cc, "WORKFLOW_DIR", wfdir)
    monkeypatch.setattr(cc.time, "sleep", lambda s: None)
    yield f"http://127.0.0.1:{srv.server_port}"
    srv.shutdown()


def _talent(tmp_path, with_voice: bool):
    face = tmp_path / "tessa.png"
    face.write_bytes(b"PNG")
    voice = tmp_path / "tessa.wav"
    if with_voice:
        voice.write_bytes(_wav(10))
    return {"id": "tessa", "name": "Tessa Vale", "title": "Chief Anchor", "kind": "anchor", "sample": "Good evening.",
            "comfy": {"ref_image": str(face), "voice_ref": str(voice), "voice_prompt": "crisp female anchor", "seed": 9}}


@pytest.mark.parametrize("with_voice", [True, False])
def test_studio_pass_local(comfy, tmp_path, monkeypatch, with_voice):
    talent = _talent(tmp_path, with_voice)
    monkeypatch.setattr("gbs.anchors.roster.load_roster", lambda: [talent])
    monkeypatch.setattr("shutil.which", lambda name: None)  # no ffmpeg: copy raw clip
    monkeypatch.setenv("GBS_GPU_HANDOFF", "command")
    marker = tmp_path / "handoff.log"
    monkeypatch.setenv("GBS_LLM_UNLOAD_CMD", f"echo unload >> {marker}")
    monkeypatch.setenv("GBS_LLM_RELOAD_CMD", f"echo reload >> {marker}")
    cfg = Settings()
    cfg.site_out, cfg.data_dir, cfg.comfy_url, cfg.anchor_engine = tmp_path / "p", tmp_path / "d", comfy, "comfy"
    rundown = [{"kind": "open", "slug": "open-1", "title": "Gu Evening News", "anchor": "Tessa Vale",
                "script": "Good evening. This is Gu.", "sources": []},
               {"kind": "story", "slug": "s1", "title": "Budget passes", "anchor": "Tessa Vale",
                "script": "The budget passed, according to CBC News.", "sources": [{"source": "x", "link": "y"}]}]
    out = cli.render_rundown(cfg, rundown, top=2)
    assert out == {"open-1": "/v/open-1.mp4", "s1": "/v/s1.mp4"}
    kinds = [("SaveAudio" in json.dumps(p), "OmniVoiceDesign" in json.dumps(p)) for p in FakeComfy.prompts]
    assert len(FakeComfy.prompts) == 4                                   # (tts + talking) x 2
    assert kinds[0] == (True, not with_voice)                            # clone vs design workflow
    talk = FakeComfy.prompts[1]
    assert talk["1"]["inputs"]["image"] == "gbs/tessa.png"               # portrait uploaded
    assert talk["2"]["inputs"]["audio"].startswith("gbs/voice")          # TTS wav uploaded
    assert talk["3"]["inputs"]["num_frames"] == wan_frames(2.0)          # sized from audio
    assert talk["5"]["inputs"]["seed"] == 9
    assert FakeComfy.frees == 1                                          # VRAM released once
    assert marker.read_text().split() == ["unload", "reload"]            # LLM out, then back
    # second pass skips clips that already exist
    FakeComfy.prompts.clear()
    cli.render_rundown(cfg, rundown, top=2)
    assert FakeComfy.prompts == []
