"""Mina Cho's social desk: 9:16 vertical cuts of rendered story segments
(centre crop on the anchor + headline caption) for Shorts/Reels/TikTok.
Only real news segments are clipped -- bookends and sponsor-only beats are not."""
from __future__ import annotations

from pathlib import Path

from gbs.studio.render import _esc


def eligible(entry: dict) -> bool:
    return entry.get("kind", "story") == "story" and bool(entry.get("sources"))


def social_cut_cmd(src: Path, out: Path, headline: str, handle: str = "@gu") -> list[str]:
    vf = ("crop=ih*9/16:ih:(iw-ih*9/16)/2:0,scale=1080:1920,"
          "drawbox=y=ih*0.06:w=iw:h=ih*0.12:color=black@0.6:t=fill,"
          f"drawtext=text='{_esc(headline[:60])}':x=(w-tw)/2:y=h*0.1:fontsize=h/34:fontcolor=white,"
          f"drawtext=text='{_esc(handle)} · sources in bio':x=(w-tw)/2:y=h*0.92:fontsize=h/48:fontcolor=0xF2C14E")
    return ["ffmpeg", "-y", "-i", str(src), "-vf", vf, "-c:v", "libx264", "-preset", "veryfast",
            "-crf", "23", "-c:a", "aac", "-t", "60", str(out)]
