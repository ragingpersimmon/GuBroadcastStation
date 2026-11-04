"""Studio: script -> voice -> talking-head anchor -> composited segment.

Local engine (ANCHOR_ENGINE=comfy, default) -- all on the 5090 via ComfyUI:
  comfy_tts()     `tts` workflow (OmniVoice / Chatterbox node): script -> wav, per-character voice
  talking_head()  `anchor_talking` workflow (InfiniteTalk on WanVideoWrapper): portrait + wav -> mp4
  compose_cmd()   ffmpeg: lower third + ticker (+ sponsor pre-roll)
Portraits, reference voices and wavs are pushed with ComfyUI's /upload endpoint,
so nothing has to be copied to the PC by hand.
"""
from __future__ import annotations

import json
import math
import re
import shutil
import subprocess
import wave
from pathlib import Path

from gbs.anchors.comfy_client import ComfyClient

REPO = Path(__file__).resolve().parents[2]
FPS = 25  # InfiniteTalk / Wan2.1 native


def _local(path: str) -> Path:
    p = Path(path)
    return p if p.is_absolute() else REPO / p


def audio_seconds(path: Path, text: str = "") -> float:
    try:
        with wave.open(str(path)) as w:
            return w.getnframes() / float(w.getframerate())
    except Exception:
        pass
    if shutil.which("ffprobe"):
        try:
            out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                                  "-of", "json", str(path)], capture_output=True, text=True, timeout=30)
            return float(json.loads(out.stdout)["format"]["duration"])
        except Exception:
            pass
    return max(2.0, len(text.split()) / 2.6)  # ~156 wpm news read


def wan_frames(seconds: float, fps: int = FPS) -> int:
    """Wan models want 4n+1 frames."""
    n = math.ceil(seconds * fps)
    return n + (1 - n % 4) % 4 if n % 4 != 1 else n


def _voice_ref(c: dict) -> Path | None:
    if not c.get("voice_ref"):
        return None
    base = _local(c["voice_ref"])
    for p in [base, *(base.with_suffix(x) for x in (".wav", ".flac", ".mp3"))]:
        if p.is_file():
            return p
    return None


def comfy_tts(comfy: ComfyClient, talent: dict, text: str, out_dir: Path, prefix: str) -> Path:
    c = talent.get("comfy", {})
    vals = {"TEXT": text, "SEED": c.get("seed", 0), "OUT_PREFIX": f"gbs/{prefix}_voice",
            "VOICE_PROMPT": c.get("voice_prompt", "")}
    ref = _voice_ref(c)
    if ref:  # locked voice: clone from the saved reference every time
        vals["VOICE_REF"] = comfy.upload(ref)
        workflow = "tts"
    else:    # no reference yet: design from the prompt (run `comfy-voices` to lock it)
        workflow = "tts_design"
    files = comfy.run(workflow, vals, out_dir)
    auds = [f for f in files if f.suffix.lower() in (".wav", ".flac", ".mp3", ".ogg")]
    if not auds:
        raise RuntimeError("tts workflow produced no audio")
    return auds[0]


def talking_head(comfy: ComfyClient, talent: dict, audio: Path, out_dir: Path, prefix: str,
                 text: str = "") -> Path:
    c = talent.get("comfy", {})
    ref = _local(c.get("ref_image", ""))
    if not ref.is_file():
        raise RuntimeError(f"{talent['name']}: portrait {ref} missing -- run `python -m gbs comfy-portraits`")
    files = comfy.run("anchor_talking", {
        "REF_IMAGE": comfy.upload(ref), "AUDIO_PATH": comfy.upload(audio),
        "NUM_FRAMES": wan_frames(audio_seconds(audio, text)),
        "POSITIVE": c.get("motion_prompt", "a news presenter speaking to camera at a studio desk, "
                                            "natural head movement, steady framing"),
        "SEED": c.get("seed", 0), "OUT_PREFIX": f"gbs/{prefix}",
    }, out_dir)
    vids = [f for f in files if f.suffix.lower() in (".mp4", ".webm", ".mov")]
    if not vids:
        raise RuntimeError("anchor_talking workflow produced no video")
    return vids[0]


def comfy_portrait(comfy: ComfyClient, talent: dict, out_dir: Path) -> Path:
    c = talent["comfy"]
    files = comfy.run("anchor_portrait", {
        "POSITIVE": c["look_prompt"], "SEED": c.get("seed", 0), "OUT_PREFIX": f"gbs/{talent['id']}_portrait",
        "NEGATIVE": "blurry, deformed, extra fingers, text, watermark, logo, cartoon",
        "REF_IMAGE": "",
    }, out_dir)
    imgs = [f for f in files if f.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp")]
    if not imgs:
        raise RuntimeError("anchor_portrait workflow produced no image")
    return imgs[0]


def _esc(t: str) -> str:
    return t.replace("\\", "\\\\").replace(":", "\\:").replace("'", "’")


def compose_cmd(anchor_mp4: Path, out_mp4: Path, headline: str, anchor_name: str,
                ticker: str, preroll: Path | None = None, title: str = "") -> list[str]:
    """ffmpeg command: lower third + scrolling ticker (+ optional sponsor pre-roll)."""
    vf = (
        "drawbox=y=ih*0.74:w=iw:h=ih*0.14:color=black@0.65:t=fill,"
        f"drawtext=text='{_esc(headline[:80])}':x=40:y=h*0.755:fontsize=h/24:fontcolor=white,"
        f"drawtext=text='{_esc(anchor_name)}{(' · ' + _esc(title)) if title else ''}':x=40:y=h*0.82:fontsize=h/36:fontcolor=0xF2C14E,"
        "drawbox=y=ih*0.93:w=iw:h=ih*0.07:color=0x8B0000@0.9:t=fill,"
        f"drawtext=text='{_esc(ticker)}':y=h*0.945:x=w-mod(t*120\\,w+tw):fontsize=h/32:fontcolor=white"
    )
    if preroll is None:
        return ["ffmpeg", "-y", "-i", str(anchor_mp4), "-vf", vf, "-c:a", "aac",
                "-c:v", "libx264", "-preset", "veryfast", "-crf", "21", str(out_mp4)]
    return ["ffmpeg", "-y", "-i", str(preroll), "-i", str(anchor_mp4), "-filter_complex",
            f"[1:v]{vf}[a];[0:v][0:a][a][1:a]concat=n=2:v=1:a=1[v][au]",
            "-map", "[v]", "-map", "[au]", "-c:v", "libx264", "-preset", "veryfast",
            "-crf", "21", "-c:a", "aac", str(out_mp4)]
