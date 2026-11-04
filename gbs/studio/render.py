"""Studio: script -> voice -> talking-head anchor -> composited segment.

Stages (each swappable):
  tts()          Piper CLI locally by default (fast, free); swap for XTTS/F5 via ComfyUI.
  talking_head() ComfyUI `anchor_talking` workflow on the 5090 over StarNet.
  compose()      ffmpeg: anchor video + lower third + ticker + bumper/ad pre-roll.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from gbs.anchors.comfy_client import ComfyClient


def tts(text: str, voice: str, out_wav: Path) -> Path:
    piper = shutil.which("piper")
    if not piper:
        raise RuntimeError("piper not installed (pip install piper-tts) -- or route TTS through ComfyUI")
    out_wav.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run([piper, "--model", voice, "--output_file", str(out_wav)],
                   input=text.encode(), check=True)
    return out_wav


def talking_head(comfy: ComfyClient, anchor: dict, audio_name: str, out_dir: Path, prefix: str) -> Path:
    files = comfy.run("anchor_talking", {
        "REF_IMAGE": anchor["ref_image"], "AUDIO_PATH": audio_name,
        "SEED": anchor["seed"], "OUT_PREFIX": prefix,
    }, out_dir)
    vids = [f for f in files if f.suffix in (".mp4", ".webm", ".mov")]
    if not vids:
        raise RuntimeError("anchor_talking workflow produced no video")
    return vids[0]


def _esc(t: str) -> str:
    return t.replace("\\", "\\\\").replace(":", "\\:").replace("'", "’")


def compose_cmd(anchor_mp4: Path, out_mp4: Path, headline: str, anchor_name: str,
                ticker: str, preroll: Path | None = None) -> list[str]:
    """ffmpeg command: lower third + scrolling ticker (+ optional sponsor pre-roll)."""
    vf = (
        "drawbox=y=ih*0.74:w=iw:h=ih*0.14:color=black@0.65:t=fill,"
        f"drawtext=text='{_esc(headline[:80])}':x=40:y=h*0.755:fontsize=h/24:fontcolor=white,"
        f"drawtext=text='{_esc(anchor_name)} · Gu Broadcast Station':x=40:y=h*0.82:fontsize=h/36:fontcolor=0xF2C14E,"
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
