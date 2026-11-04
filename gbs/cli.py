"""python -m gbs <command>

  ingest     pull world news through the 5protocol bridge into the story store
  pulse      print the live 5protocol market regime (tailnet)
  rundown    build + script the rundown and publish the static site
  run        ingest + rundown in one go (what the systemd timer calls)
  studio     render anchor videos for the latest rundown (needs ComfyUI + piper + ffmpeg)
  comfy-ping check ComfyUI on StarNet
"""
from __future__ import annotations

import argparse
import json
import logging
import subprocess
import sys

from gbs.config import settings

log = logging.getLogger("gbs")


def cmd_ingest(cfg) -> int:
    from gbs.newsdesk.fiveprotocol_bridge import NewsBridge
    from gbs.newsdesk.store import StoryStore
    stories = NewsBridge(cfg).pull()
    added = StoryStore(cfg.db_path).add(stories)
    print(f"ingested {len(stories)} new, stored {added}")
    return 0


def cmd_pulse(cfg) -> int:
    from gbs.newsdesk.fiveprotocol_bridge import market_pulse
    print(json.dumps(market_pulse(cfg), indent=2))
    return 0


def cmd_rundown(cfg) -> int:
    from gbs.anchors.roster import anchor_for_desk, load_roster
    from gbs.editorial.rundown import build_rundown
    from gbs.editorial.scriptwriter import write_script
    from gbs.monetization.ads import AdBook
    from gbs.newsdesk.fiveprotocol_bridge import market_pulse
    from gbs.newsdesk.store import StoryStore
    from gbs.site.build import build_site

    store = StoryStore(cfg.db_path)
    stories = store.recent(hours=12)
    if not stories:
        print("no fresh stories -- run `ingest` first")
        return 1
    rundown = build_rundown(stories, size=cfg.rundown_size)
    roster = load_roster()
    for seg in rundown:
        anchor = anchor_for_desk(seg.story.desk, roster)
        seg.anchor_id = anchor["name"]
        seg.script = write_script(cfg, seg, anchor["name"])
    AdBook().assign_on_air(rundown)
    out = build_site(cfg, rundown, pulse=market_pulse(cfg))
    store.mark_used([s.story.item_hash for s in rundown] +
                    [r.item_hash for s in rundown for r in s.related])
    print(f"published {len(rundown)} segments -> {out}")
    return 0


def cmd_studio(cfg) -> int:
    from pathlib import Path
    from gbs.anchors.comfy_client import ComfyClient
    from gbs.anchors.roster import load_roster
    from gbs.studio.render import compose_cmd, talking_head, tts
    rundown = json.loads((cfg.site_out / "rundown.json").read_text())
    roster = {a["name"]: a for a in load_roster()}
    comfy = ComfyClient(cfg.comfy_url)
    if not comfy.healthy():
        print(f"ComfyUI unreachable at {cfg.comfy_url}")
        return 1
    work = cfg.data_dir / "studio"
    ticker = "   •   ".join(s["title"] for s in rundown)
    for seg in rundown:
        a = roster[seg["anchor"]]
        text = seg["script"] + (f" {seg['sponsor_read']}" if seg.get("sponsor_read") else "")
        wav = tts(text, a["voice"], work / f"{seg['slug']}.wav")
        # NOTE: wav must be visible to ComfyUI (rsync to its input/ dir on the GPU box)
        raw = talking_head(comfy, a, wav.name, work, seg["slug"])
        final = cfg.site_out / "v" / f"{seg['slug']}.mp4"
        final.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(compose_cmd(raw, final, seg["title"], a["name"], ticker), check=True)
        print("rendered", final)
    return 0


def main(argv=None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    p = argparse.ArgumentParser(prog="gbs")
    p.add_argument("command", choices=["ingest", "pulse", "rundown", "run", "studio", "comfy-ping"])
    a = p.parse_args(argv)
    cfg = settings()
    if a.command == "ingest":
        return cmd_ingest(cfg)
    if a.command == "pulse":
        return cmd_pulse(cfg)
    if a.command == "rundown":
        return cmd_rundown(cfg)
    if a.command == "run":
        cmd_ingest(cfg)
        return cmd_rundown(cfg)
    if a.command == "studio":
        return cmd_studio(cfg)
    if a.command == "comfy-ping":
        from gbs.anchors.comfy_client import ComfyClient
        ok = ComfyClient(cfg.comfy_url).healthy()
        print("ComfyUI", "OK" if ok else "UNREACHABLE", cfg.comfy_url)
        return 0 if ok else 1
    return 2


if __name__ == "__main__":
    sys.exit(main())
