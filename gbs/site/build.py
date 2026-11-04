"""Static site generator for the droplet. Output goes to GBS_SITE_OUT
(nginx serves it directly). Generates: index, one page per segment,
RSS feed, sitemap, ads.txt, advertise + about (AI disclosure) pages."""
from __future__ import annotations

import html
import json
import time
from datetime import datetime, timezone
from email.utils import formatdate
from pathlib import Path

from gbs.config import Settings
from gbs.editorial.scriptwriter import outlet_name
from gbs.models import Segment
from gbs.monetization.ads import AdBook

CSS = """
:root{--bg:#0d0f14;--card:#161a22;--ink:#e9ecf1;--dim:#8b93a3;--accent:#c8102e;--gold:#f2c14e}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.55 system-ui,-apple-system,Segoe UI,sans-serif}
header{display:flex;align-items:center;gap:14px;padding:14px 24px;border-bottom:3px solid var(--accent)}
header .logo{font-weight:800;letter-spacing:.5px}header .logo b{color:var(--accent)}
.pulse{margin-left:auto;font-size:13px;color:var(--dim)}.pulse b{color:var(--gold)}
main{max-width:1100px;margin:0 auto;padding:24px;display:grid;grid-template-columns:1fr 300px;gap:24px}
@media(max-width:860px){main{grid-template-columns:1fr}}
.seg{background:var(--card);border-radius:10px;padding:18px;margin-bottom:16px}
.seg .desk{font-size:11px;text-transform:uppercase;letter-spacing:1px;color:var(--gold)}
.seg h2{margin:4px 0 8px;font-size:20px}.seg a{color:var(--ink)}
.seg .by{font-size:13px;color:var(--dim)}.seg video{width:100%;border-radius:8px;margin:8px 0}
.src{font-size:13px;color:var(--dim)}.src a{color:var(--dim)}
.ad{display:block;border:1px dashed #333a48;border-radius:10px;padding:14px;margin-bottom:16px}
.ad a{color:var(--ink);text-decoration:none;display:flex;flex-direction:column;gap:4px}
.ad-label{font-size:10px;text-transform:uppercase;color:var(--dim)}
footer{text-align:center;color:var(--dim);font-size:13px;padding:24px}
"""


def _page(cfg: Settings, ads: AdBook, title: str, body: str, side: str, pulse: dict) -> str:
    pulse_html = ""
    if pulse.get("regime"):
        pulse_html = f'<div class="pulse">Market pulse: <b>{html.escape(str(pulse["regime"]).upper())}</b></div>'
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(title)}</title><link rel="alternate" type="application/rss+xml" href="/feed.xml">
<style>{CSS}</style>{ads.head_tag()}</head><body>
<header><a class="logo" href="/" style="color:inherit;text-decoration:none"><b>GU</b> BROADCASTING STATION</a>{pulse_html}</header>
{ads.web_slot("top")}
<main><div>{body}</div><div>{side}</div></main>
<footer>Presented by AI-generated anchors and reporters. Stories are rewritten summaries of reporting by the credited outlets; follow source links for original coverage. <a href="/about.html" style="color:inherit">About</a> · <a href="/advertise.html" style="color:inherit">Advertise</a></footer>
</body></html>"""


def _sources_html(seg: Segment) -> str:
    links = " · ".join(
        f'<a href="{html.escape(s["link"])}" rel="noopener" target="_blank">{html.escape(outlet_name(s["source"]))}</a>'
        for s in seg.sources)
    return f'<div class="src">Sources: {links}</div>'


def _seg_card(seg: Segment, link_title: bool = True, video: str | None = None) -> str:
    t = html.escape(seg.story.title)
    title = f'<a href="/s/{seg.slug}.html">{t}</a>' if link_title else t
    vid = f'<video controls preload="none" src="{html.escape(video)}"></video>' if video else ""
    sponsor = f'<p class="by"><em>{html.escape(seg.sponsor_read)}</em></p>' if seg.sponsor_read else ""
    script = "".join(f"<p>{html.escape(p)}</p>" for p in seg.script.split("\n") if p.strip())
    return (f'<article class="seg"><div class="desk">{html.escape(seg.story.desk)}</div><h2>{title}</h2>'
            f'<div class="by">{html.escape(seg.anchor_id)}{(" · " + html.escape(seg.presenter_title)) if seg.presenter_title else ""}</div>{vid}{script}{sponsor}{_sources_html(seg)}</article>')


def _bookend_html(b: dict, video: str | None, cls: str) -> str:
    vid = f'<video controls preload="none" src="{html.escape(video)}"></video>' if video else ""
    label = {"open": "", "breaking": "<div class='desk' style='color:var(--accent)'>BREAKING</div>",
             "close": ""}.get(b["kind"], "")
    return (f'<article class="seg {cls}">{label}<div class="by">{html.escape(b["anchor"])} · '
            f'{html.escape(b["presenter_title"])}</div>{vid}<p>{html.escape(b["script"])}</p></article>')


def _cast_html() -> str:
    try:
        from gbs.anchors.roster import load_newsroom
        nr = load_newsroom()
    except Exception:
        return ""
    on_air = [t for t in nr["talent"] if t.get("kind") != "production"]
    rows = "".join(f"<li><strong>{html.escape(t['name'])}</strong> — {html.escape(t['title'])}</li>" for t in on_air)
    return ("<h3>On air</h3><p>Every on-air presenter below is a fictional, AI-generated character "
            f"(AI-rendered face and voice). None is a real person.</p><ul>{rows}</ul>")


def build_site(cfg: Settings, rundown: list[Segment], pulse: dict | None = None,
               videos: dict | None = None, show: dict | None = None,
               bookends: dict | None = None) -> Path:
    pulse, videos, bookends = pulse or {}, dict(videos or {}), bookends or {}
    out = cfg.site_out
    vdir = out / "v"
    if vdir.is_dir():  # pick up clips rendered by earlier/background studio passes
        for f in vdir.glob("*.mp4"):
            videos.setdefault(f.stem, f"/v/{f.name}")
    (out / "s").mkdir(parents=True, exist_ok=True)
    ads = AdBook()
    side = ads.web_slot("sidebar")
    cards = []
    if "breaking" in bookends:
        b = bookends["breaking"]
        cards.append(_bookend_html(b, videos.get(b["slug"]), "breaking"))
    if "open" in bookends:
        b = bookends["open"]
        cards.append(_bookend_html(b, videos.get(b["slug"]), "open"))
    for i, seg in enumerate(rundown):
        cards.append(_seg_card(seg, video=videos.get(seg.slug)))
        if i == 2:
            cards.append(ads.web_slot("inline", seg.story.desk))
        (out / "s" / f"{seg.slug}.html").write_text(_page(
            cfg, ads, f"{seg.story.title} | {cfg.site_name}",
            _seg_card(seg, link_title=False, video=videos.get(seg.slug)), side, pulse))
    if "close" in bookends:
        b = bookends["close"]
        cards.append(_bookend_html(b, videos.get(b["slug"]), "close"))
    stamp = datetime.now(timezone.utc).strftime("%A %d %B %Y, %H:%M UTC")
    show_name = html.escape(show["name"]) + " · " if show else ""
    (out / "index.html").write_text(_page(
        cfg, ads, cfg.site_name, f'<p class="by">{show_name}Edition of {stamp}</p>' + "".join(cards), side, pulse))
    (out / "about.html").write_text(_page(cfg, ads, f"About | {cfg.site_name}",
        "<article class='seg'><h2>About</h2><p>Gu Broadcasting Station is an AI-presented news "
        "bulletin. Our anchors and reporters are AI-generated characters, not real people. Each segment "
        "is an original rewrite of reporting from the outlets credited beneath it, with links to the "
        f"original coverage. Sponsored messages are always labelled.</p>{_cast_html()}</article>", side, pulse))
    (out / "advertise.html").write_text(_page(cfg, ads, f"Advertise | {cfg.site_name}",
        "<article class='seg'><h2>Advertise with us</h2><p>On-air sponsor reads, pre-roll and "
        "on-site placements. Contact: ads@YOURDOMAIN</p></article>", side, pulse))
    (out / "feed.xml").write_text(_rss(cfg, rundown))
    (out / "sitemap.xml").write_text(_sitemap(cfg, rundown))
    if ads.ads_txt():
        (out / "ads.txt").write_text(ads.ads_txt() + "\n")
    stories = [{"kind": "story", "slug": s.slug, "title": s.story.title, "desk": s.story.desk,
                "anchor": s.anchor_id, "presenter_title": s.presenter_title, "script": s.script,
                "sources": s.sources, "sponsor_read": s.sponsor_read} for s in rundown]
    order = ([bookends["breaking"]] if "breaking" in bookends else []) + \
            ([bookends["open"]] if "open" in bookends else []) + stories + \
            ([bookends["close"]] if "close" in bookends else [])
    (out / "rundown.json").write_text(json.dumps(order, indent=1, ensure_ascii=False))
    return out


def _rss(cfg: Settings, rundown: list[Segment]) -> str:
    items = "".join(
        f"<item><title>{html.escape(s.story.title)}</title><link>{cfg.site_url}/s/{s.slug}.html</link>"
        f"<guid>{cfg.site_url}/s/{s.slug}.html</guid><pubDate>{formatdate(s.story.ts)}</pubDate>"
        f"<description>{html.escape(s.script)}</description></item>" for s in rundown)
    return (f'<?xml version="1.0" encoding="UTF-8"?><rss version="2.0"><channel><title>{html.escape(cfg.site_name)}</title>'
            f"<link>{cfg.site_url}</link><description>AI-anchored world news</description>"
            f"<lastBuildDate>{formatdate(time.time())}</lastBuildDate>{items}</channel></rss>")


def _sitemap(cfg: Settings, rundown: list[Segment]) -> str:
    urls = [f"{cfg.site_url}/"] + [f"{cfg.site_url}/s/{s.slug}.html" for s in rundown]
    return ('<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
            + "".join(f"<url><loc>{u}</loc></url>" for u in urls) + "</urlset>")
