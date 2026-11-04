"""python -m gbs <command>

  ingest     pull world news through the 5protocol bridge into the story store
  pulse      print the live 5protocol market regime (tailnet)
  rundown    build + script the rundown and publish the static site
  run        ingest + rundown in one go (what the systemd timer calls)
  studio     render anchor videos for the latest rundown (ANCHOR_ENGINE=heygen|comfy)
  heygen-list  list HeyGen avatars + voices to fill config/anchors.json
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
    pulse = market_pulse(cfg)
    videos = {}
    if cfg.render_on_run:
        build_site(cfg, rundown, pulse=pulse)  # writes rundown.json for the renderer
        videos = render_rundown(cfg, json.loads((cfg.site_out / "rundown.json").read_text()),
                                top=cfg.render_top)
    out = build_site(cfg, rundown, pulse=pulse, videos=videos)
    store.mark_used([s.story.item_hash for s in rundown] +
                    [r.item_hash for s in rundown for r in s.related])
    print(f"published {len(rundown)} segments -> {out}")
    return 0


def _ticker(rundown: list[dict]) -> str:
    return "   \u2022   ".join(s["title"] for s in rundown)


def render_rundown(cfg, rundown: list[dict], top: int) -> dict:
    """Render the top-N segments to public/v/<slug>.mp4 with the configured
    anchor engine, then burn in lower third + ticker. Returns {slug: url}."""
    import shutil
    from gbs.anchors.roster import load_roster
    from gbs.studio.render import compose_cmd
    roster = {a["name"]: a for a in load_roster()}
    work = cfg.data_dir / "studio"
    vdir = cfg.site_out / "v"
    vdir.mkdir(parents=True, exist_ok=True)
    todo = rundown[:top]
    raws: dict = {}

    def _text(seg):
        return seg["script"] + (f" {seg['sponsor_read']}" if seg.get("sponsor_read") else "")

    if cfg.anchor_engine == "heygen":
        from gbs.anchors.heygen_client import HeyGenClient
        hg = HeyGenClient(cfg.heygen_api_key, base=cfg.heygen_base)
        # submit everything first so HeyGen renders in parallel, then collect
        jobs = {}
        for seg in todo:
            try:
                jobs[seg["slug"]] = hg.generate(roster[seg["anchor"]], _text(seg),
                                                title=seg["title"], test=cfg.heygen_test)
            except Exception as exc:
                log.error("HeyGen submit failed for %s: %s", seg["slug"], exc)
        for slug, vid in jobs.items():
            try:
                st = hg.wait(vid)
                import urllib.request
                raw = work / f"{slug}.heygen.mp4"
                raw.parent.mkdir(parents=True, exist_ok=True)
                with urllib.request.urlopen(st["video_url"], timeout=300) as r:
                    raw.write_bytes(r.read())
                raws[slug] = raw
            except Exception as exc:
                log.error("HeyGen render failed for %s: %s", slug, exc)
    else:
        from gbs.anchors.comfy_client import ComfyClient
        from gbs.studio.render import talking_head, tts
        comfy = ComfyClient(cfg.comfy_url)
        if not comfy.healthy():
            log.error("ComfyUI unreachable at %s", cfg.comfy_url)
            return {}
        for seg in todo:
            a = roster[seg["anchor"]]
            wav = tts(_text(seg), a["voice"], work / f"{seg['slug']}.wav")
            # wav must be visible to ComfyUI (rsync to its input/ dir on the GPU box)
            raws[seg["slug"]] = talking_head(comfy, a, wav.name, work, seg["slug"])

    ticker = _ticker(rundown)
    out = {}
    for seg in todo:
        raw = raws.get(seg["slug"])
        if not raw:
            continue
        final = vdir / f"{seg['slug']}.mp4"
        if shutil.which("ffmpeg"):
            subprocess.run(compose_cmd(raw, final, seg["title"], seg["anchor"], ticker), check=True)
        else:
            shutil.copy(raw, final)
        out[seg["slug"]] = f"/v/{seg['slug']}.mp4"
        print("rendered", final)
    return out


def cmd_studio(cfg) -> int:
    rundown = json.loads((cfg.site_out / "rundown.json").read_text())
    done = render_rundown(cfg, rundown, top=cfg.render_top)
    print(f"rendered {len(done)}/{min(len(rundown), cfg.render_top)} segments with {cfg.anchor_engine}")
    return 0 if done else 1


def cmd_heygen_list(cfg) -> int:
    from gbs.anchors.heygen_client import HeyGenClient
    hg = HeyGenClient(cfg.heygen_api_key, base=cfg.heygen_base)
    print("# avatars (avatar_id / name)")
    for a in hg.list_avatars():
        print(f"{a.get('avatar_id')}\t{a.get('avatar_name')}")
    print("\n# voices (voice_id / name / language)")
    for v in hg.list_voices():
        print(f"{v.get('voice_id')}\t{v.get('name')}\t{v.get('language')}")
    try:
        print("\n# quota", json.dumps(hg.remaining_quota()))
    except Exception as exc:
        print("quota unavailable:", exc)
    return 0


def main(argv=None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    p = argparse.ArgumentParser(prog="gbs")
    p.add_argument("command", choices=["ingest", "pulse", "rundown", "run", "studio", "comfy-ping", "heygen-list"])
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
    if a.command == "heygen-list":
        return cmd_heygen_list(cfg)
    if a.command == "comfy-ping":
        from gbs.anchors.comfy_client import ComfyClient
        ok = ComfyClient(cfg.comfy_url).healthy()
        print("ComfyUI", "OK" if ok else "UNREACHABLE", cfg.comfy_url)
        return 0 if ok else 1
    return 2


if __name__ == "__main__":
    sys.exit(main())
