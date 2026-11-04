"""python -m gbs <command>

  ingest     pull world news through the 5protocol bridge into the story store
  pulse      print the live 5protocol market regime (tailnet)
  rundown    build + script the rundown and publish the static site
  run        ingest + rundown in one go (what the systemd timer calls)
  studio     render anchor videos for the latest edition + rebuild site (ANCHOR_ENGINE=comfy|heygen)
  comfy-tokenize <export.json> --kind anchor_talking|tts|tts_design|anchor_portrait
             turn a ComfyUI API-format export into a GBS workflow template
  comfy-portraits / comfy-voices [--force]
             design each character's locked face / voice once
  newsroom   show who's on air now and the desk assignments
  heygen-list  list HeyGen avatars + voices to fill config/newsroom.json
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


def save_edition(cfg, show, bookends, pulse, rundown) -> None:
    """Persist the full edition so `studio` can render later and rebuild the site."""
    cfg.data_dir.mkdir(parents=True, exist_ok=True)
    doc = {"show": show, "bookends": bookends, "pulse": pulse, "segments": [
        {"story": s.story.to_dict(), "related": [r.to_dict() for r in s.related],
         "anchor_id": s.anchor_id, "presenter_title": s.presenter_title,
         "script": s.script, "sponsor_read": s.sponsor_read} for s in rundown]}
    (cfg.data_dir / "edition.json").write_text(json.dumps(doc, ensure_ascii=False))


def load_edition(cfg):
    from gbs.models import Segment, Story
    doc = json.loads((cfg.data_dir / "edition.json").read_text())
    segs = [Segment(story=Story(**d["story"]), related=[Story(**r) for r in d["related"]],
                    anchor_id=d["anchor_id"], presenter_title=d["presenter_title"],
                    script=d["script"], sponsor_read=d["sponsor_read"]) for d in doc["segments"]]
    return doc["show"], doc["bookends"], doc["pulse"], segs


def cmd_rundown(cfg) -> int:
    from gbs.anchors.roster import (by_id, current_show, load_newsroom, now_local,
                                    presenter_for_desk, should_render)
    from gbs.editorial.rundown import build_rundown
    from gbs.editorial import scriptwriter as sw
    from gbs.models import Segment
    from gbs.monetization.ads import AdBook
    from gbs.newsdesk.fiveprotocol_bridge import market_pulse
    from gbs.newsdesk.local import LOCAL
    from gbs.newsdesk.store import StoryStore
    from gbs.site.build import build_site

    nr = load_newsroom()
    now = now_local()
    show = current_show(nr, now)
    anchor = by_id(nr, show["anchor"])
    store = StoryStore(cfg.db_path)
    stories = store.recent(hours=12)
    if not stories:
        print("no fresh stories -- run `ingest` first")
        return 1
    rundown = build_rundown(stories, size=cfg.rundown_size)

    # local desks for this show (weather -> Celeste, traffic -> Flip), slotted after the lead
    for i, name in enumerate(show.get("local_segments", [])):
        st = LOCAL[name]() if name in LOCAL else None
        if st:
            rundown.insert(min(len(rundown), 2 + i), Segment(story=st))

    # assignment desk: each story goes to the reporter who owns its desk
    for seg in rundown:
        p = presenter_for_desk(seg.story.desk, nr, anchor)
        seg.anchor_id, seg.presenter_title = p["name"], p["title"]
        seg.script = sw.write_script(cfg, seg, p)

    by_name = {t["name"]: t for t in nr["talent"]}
    AdBook().assign_on_air(rundown, write_fn=lambda sp, seg: sw.write_sponsor_read(cfg, by_name[seg.anchor_id], sp))
    pulse = market_pulse(cfg)

    def _bk(kind, talent, script, title):
        return {"kind": kind, "slug": f"{kind}-{show['id']}-{now:%Y%m%d-%H%M}", "title": title,
                "desk": "", "anchor": talent["name"], "presenter_title": talent["title"],
                "script": script, "sources": [], "sponsor_read": None}

    bookends = {"open": _bk("open", anchor, sw.write_open(cfg, show, anchor, rundown), show["name"]),
                "close": _bk("close", anchor, sw.write_close(cfg, show, anchor), show["name"])}
    brk = nr.get("breaking", {})
    hot = next((s for s in rundown if s.story.risk_score >= brk.get("risk_threshold", 1.1)), None)
    if hot is None and pulse.get("regime") in brk.get("on_regime", []):
        hot = next((s for s in rundown if s.story.desk in ("business", "markets")), None)
    if hot is not None:
        echo = by_id(nr, brk["anchor"])
        bookends["breaking"] = _bk("breaking", echo, sw.write_breaking(cfg, echo, hot), hot.story.title)

    save_edition(cfg, show, bookends, pulse, rundown)
    videos = {}
    if cfg.render_on_run and should_render(show, now):
        build_site(cfg, rundown, pulse=pulse, show=show, bookends=bookends)  # writes rundown.json
        top = cfg.render_top or show.get("render_top", 1)
        videos = render_rundown(cfg, json.loads((cfg.site_out / "rundown.json").read_text()), top=top)
    out = build_site(cfg, rundown, pulse=pulse, videos=videos, show=show, bookends=bookends)
    store.mark_used([s.story.item_hash for s in rundown] +
                    [r.item_hash for s in rundown for r in s.related])
    print(f"{show['name']} ({anchor['name']}): published {len(rundown)} segments -> {out}")
    return 0


def _ticker(rundown: list[dict]) -> str:
    return "   \u2022   ".join(s["title"] for s in rundown if s.get("kind", "story") == "story")


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
        from gbs.studio.gpu import gpu_for_render
        from gbs.studio.render import comfy_tts, talking_head
        comfy = ComfyClient(cfg.comfy_url, timeout=120)
        if not comfy.healthy():
            log.error("ComfyUI unreachable at %s", cfg.comfy_url)
            return {}
        vdone = cfg.site_out / "v"
        with gpu_for_render(comfy):
            for seg in todo:
                if (vdone / f"{seg['slug']}.mp4").exists():
                    continue  # rendered by an earlier studio pass
                try:
                    a = roster[seg["anchor"]]
                    text = _text(seg)
                    wav = comfy_tts(comfy, a, text, work, seg["slug"])
                    raws[seg["slug"]] = talking_head(comfy, a, wav, work, seg["slug"], text=text)
                except Exception as exc:
                    log.error("local render failed for %s: %s", seg["slug"], exc)

    ticker = _ticker(rundown)
    out = {}
    for seg in todo:
        raw = raws.get(seg["slug"])
        if not raw:
            continue
        final = vdir / f"{seg['slug']}.mp4"
        if shutil.which("ffmpeg"):
            subprocess.run(compose_cmd(raw, final, seg["title"], seg["anchor"], ticker,
                                       title=seg.get("presenter_title", "")), check=True)
        else:
            shutil.copy(raw, final)
        out[seg["slug"]] = f"/v/{seg['slug']}.mp4"
        print("rendered", final)
        from gbs.studio.social import eligible, social_cut_cmd
        if shutil.which("ffmpeg") and eligible(seg):
            sdir = cfg.site_out / "social"
            sdir.mkdir(parents=True, exist_ok=True)
            subprocess.run(social_cut_cmd(final, sdir / f"{seg['slug']}.mp4", seg["title"]), check=False)
    return out


def cmd_studio(cfg) -> int:
    """Render video for the latest edition (skipping clips already done) and
    republish the site with players. Safe to run on its own timer."""
    import fcntl
    from gbs.site.build import build_site
    cfg.data_dir.mkdir(parents=True, exist_ok=True)
    lock = open(cfg.data_dir / "studio.lock", "w")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        print("studio already running")
        return 0
    if not (cfg.data_dir / "edition.json").exists():
        print("no edition yet -- run `rundown` first")
        return 1
    show, bookends, pulse, segs = load_edition(cfg)
    rundown = json.loads((cfg.site_out / "rundown.json").read_text())
    top = cfg.render_top or show.get("render_top", 1)
    done = render_rundown(cfg, rundown, top=top)
    build_site(cfg, segs, pulse=pulse, show=show, bookends=bookends)
    print(f"rendered {len(done)}/{min(len(rundown), top)} with {cfg.anchor_engine}; site rebuilt")
    return 0


def cmd_comfy_tokenize(cfg, src: str, kind: str) -> int:
    from pathlib import Path
    from gbs.anchors.comfy_client import WORKFLOW_DIR
    from gbs.anchors.comfy_tokenize import tokenize_file
    dest, hits, missing = tokenize_file(Path(src), kind, WORKFLOW_DIR)
    for tok, where in sorted(hits.items()):
        print(f"  {{{{{tok}}}}} -> {', '.join(where)}")
    if missing:
        print(f"WARNING: no input found for {sorted(missing)} -- edit {dest} by hand")
    print("wrote", dest)
    return 1 if missing else 0


def _comfy(cfg):
    from gbs.anchors.comfy_client import ComfyClient
    c = ComfyClient(cfg.comfy_url, timeout=120)
    if not c.healthy():
        raise SystemExit(f"ComfyUI unreachable at {cfg.comfy_url}")
    return c


def cmd_comfy_portraits(cfg, force: bool) -> int:
    """Design each on-air character's face (writes candidates; you lock one in)."""
    import shutil
    from gbs.anchors.roster import load_roster
    from gbs.studio.gpu import gpu_for_render
    from gbs.studio.render import _local, comfy_portrait
    comfy = _comfy(cfg)
    with gpu_for_render(comfy):
        for t in load_roster():
            dest = _local(t["comfy"]["ref_image"])
            if dest.exists() and not force:
                continue
            img = comfy_portrait(comfy, t, cfg.data_dir / "portraits")
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(img, dest)
            print(f"{t['name']}: {dest}")
    return 0


def cmd_comfy_voices(cfg, force: bool) -> int:
    """Design each character's voice once from voice_prompt, reading their
    signature line, and save it as the cloning reference so the voice is
    identical in every future segment."""
    import shutil
    from gbs.anchors.roster import load_roster
    from gbs.studio.gpu import gpu_for_render
    from gbs.studio.render import _local, comfy_tts
    comfy = _comfy(cfg)
    with gpu_for_render(comfy):
        for t in load_roster():
            from gbs.studio.render import _voice_ref
            dest = _local(t["comfy"]["voice_ref"])
            if _voice_ref(t["comfy"]) and not force:
                continue
            t = {**t, "comfy": {**t["comfy"], "voice_ref": ""}}
            wav = comfy_tts(comfy, t, t["sample"], cfg.data_dir / "voices", f"{t['id']}_ref")
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(wav, dest.with_suffix(wav.suffix))
            print(f"{t['name']}: {dest.with_suffix(wav.suffix)}")
    return 0


def cmd_newsroom(cfg) -> int:
    from gbs.anchors.roster import by_id, current_show, load_newsroom, now_local, should_render
    nr = load_newsroom()
    now = now_local()
    show = current_show(nr, now)
    a = by_id(nr, show["anchor"])
    print(f"{now:%a %H:%M %Z}  ON AIR: {show['name']} with {a['name']} "
          f"(video this edition: {'yes' if should_render(show, now) else 'no'})")
    print("\nassignment desk:")
    for t in nr["talent"]:
        if t.get("desks"):
            print(f"  {t['name']:<24} {', '.join(t['desks'])}")
    if cfg.anchor_engine == "heygen":
        missing = [t["name"] for t in nr["talent"] if "heygen" in t
                   and not (t["heygen"].get("avatar_id") or t["heygen"].get("talking_photo_id"))]
        if missing:
            print("\nno HeyGen avatar yet:", ", ".join(missing))
    else:
        from gbs.anchors.comfy_client import WORKFLOW_DIR
        from gbs.studio.render import _local, _voice_ref
        on_air = [t for t in nr["talent"] if "comfy" in t]
        no_face = [t["name"] for t in on_air if not _local(t["comfy"]["ref_image"]).is_file()]
        no_voice = [t["name"] for t in on_air if not _voice_ref(t["comfy"])]
        no_wf = [w for w in ("anchor_portrait", "tts", "tts_design", "anchor_talking")
                 if not (WORKFLOW_DIR / f"{w}.json").exists()]
        print(f"\nengine: comfy @ {cfg.comfy_url}")
        if no_wf:
            print("workflows to export + tokenize:", ", ".join(no_wf))
        if no_face:
            print("no locked portrait:", ", ".join(no_face))
        if no_voice:
            print("no locked voice:", ", ".join(no_voice))
    return 0


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
    p.add_argument("command", choices=["ingest", "pulse", "rundown", "run", "studio", "comfy-ping",
                                       "heygen-list", "newsroom", "comfy-tokenize", "comfy-portraits",
                                       "comfy-voices"])
    p.add_argument("src", nargs="?", help="comfy-tokenize: API-format export to convert")
    p.add_argument("--kind", choices=["anchor_talking", "tts", "tts_design", "anchor_portrait"])
    p.add_argument("--force", action="store_true", help="regenerate existing portraits/voices")
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
    if a.command == "comfy-tokenize":
        if not (a.src and a.kind):
            p.error("comfy-tokenize needs <export.json> --kind ...")
        return cmd_comfy_tokenize(cfg, a.src, a.kind)
    if a.command == "comfy-portraits":
        return cmd_comfy_portraits(cfg, a.force)
    if a.command == "comfy-voices":
        return cmd_comfy_voices(cfg, a.force)
    if a.command == "newsroom":
        return cmd_newsroom(cfg)
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
