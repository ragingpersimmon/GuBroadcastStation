"""Full static news site for the droplet (nginx serves GBS_SITE_OUT).

Page map (every link in the nav/footer resolves; tests crawl it):
  /                          home: lead package, latest, now-on-Gu, section rails, video
  /latest/  /live/           newest stories; the current edition in running order
  /world/ /world/<region>/   sections + sub-sections (+ /<section>/feed.xml)
  /politics/ /business/ /business/markets/ /business/consumer/ /tech/ /science/
  /entertainment/ /sports/ /local/ /local/weather/ /local/traffic/
  /markets/                  5protocol market pulse + business desk
  /story/YYYY/MM/DD/<slug>.html
  /video/                    every story with an anchor clip
  /shows/ /shows/<id>/       schedule, anchor, latest edition
  /people/ /people/<id>/     on-air cast + newsroom, stories by presenter
  /archive/ /archive/YYYY-MM-DD/
  /search/ (+ /search-index.json)   /newsletter/
  /about/ /about/standards/ /about/ai/ /about/corrections/   (no public sources page: sources are confidential)
  /login/ /account/ /membership/ /membership/thanks/   (sign-in + Stripe membership; service: gbs/account/server.py)
  /contact/ /tips/ /advertise/ /advertise/guidelines/
  /privacy/ /terms/ /cookies/ /accessibility/ /sitemap/ /404.html
  /feed.xml /sitemap.xml /news-sitemap.xml /robots.txt /manifest.webmanifest /ads.txt
"""
from __future__ import annotations

import html
import json
import shutil
import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from email.utils import formatdate
from pathlib import Path
from urllib.parse import quote, urlparse
from zoneinfo import ZoneInfo

from gbs.config import Settings
from gbs.editorial.standards import is_sensitive
from gbs.models import Segment
from gbs.monetization.ads import AdBook
from gbs.newsdesk import local as localdesk
from gbs.site import assets, images, pages
from gbs.site.data import (DESK_NAMES, SECTIONS, PublishedStore, article_url, desk_path,
                           section_of, standfirst)

REPO = Path(__file__).resolve().parents[2]
SITE_CONF = REPO / "config" / "site.json"
e = html.escape


# ------------------------------------------------------------------ context

class Ctx:
    def __init__(self, cfg: Settings, show, pulse, bookends):
        import os
        from gbs.anchors.roster import load_newsroom
        self.cfg, self.pulse, self.bookends = cfg, pulse or {}, bookends or {}
        self.site = json.loads(SITE_CONF.read_text())
        self.nr = load_newsroom()
        self.show = show or next(s for s in self.nr["shows"] if s.get("default"))
        self.tz = ZoneInfo(os.getenv("GBS_TZ", "America/Vancouver"))
        self.ads = AdBook()
        self.host = urlparse(cfg.site_url).hostname or "gubs.ca"
        self.emails = {k: f"{v}@{self.host}" for k, v in self.site["emails"].items()}
        self.talent = {t["id"]: t for t in self.nr["talent"]}
        self.by_name = {t["name"]: t for t in self.nr["talent"]}
        self.out = cfg.site_out
        self.written: list[str] = []
        self.articles: list[dict] = []
        self.portraits: dict[str, str] = {}
        self.localdata = localdesk.snapshot(cfg.data_dir / "local")
        self.stock: dict[str, list[str]] = {}
        from gbs.account import server as acct
        self.providers = [(p, acct.PROVIDERS[p]["label"]) for p in acct.enabled_providers()]
        self.membership = acct.load_plans()
        self.billing = acct.billing_on()
        self.plan_live = {pl["id"]: bool(self.billing and acct.plan_price(pl)) for pl in self.membership["plans"]}

    def anchor(self, show=None):
        return self.talent[(show or self.show)["anchor"]]

    def local(self, ts: float) -> datetime:
        return datetime.fromtimestamp(ts, self.tz)


def write(ctx: Ctx, path: str, content: str, sitemap: bool = True) -> None:
    rel = path.lstrip("/")
    dest = ctx.out / (rel + "index.html" if (rel == "" or rel.endswith("/")) else rel)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(content, encoding="utf-8")
    if sitemap and path.endswith(("/", ".html")) and path != "/404.html":
        ctx.written.append(path)


# ------------------------------------------------------------------ atoms

def t_iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, timezone.utc).isoformat(timespec="seconds")


def time_tag(ctx: Ctx, ts: float, rel: bool = False, fmt: str = "%b %d, %Y %I:%M %p %Z") -> str:
    label = ctx.local(ts).strftime(fmt).replace(" 0", " ")
    return f'<time datetime="{t_iso(ts)}"{" data-rel" if rel else ""}>{e(label)}</time>'


def person_id(ctx: Ctx, name: str) -> str | None:
    t = ctx.by_name.get(name)
    return t["id"] if t else None


def person_link(ctx: Ctx, name: str) -> str:
    pid = person_id(ctx, name)
    return f'<a href="/people/{pid}/">{e(name)}</a>' if pid else e(name)


def initials(name: str) -> str:
    parts = [p for p in name.replace('"', "").split() if p[0].isalpha()]
    return (parts[0][0] + (parts[-1][0] if len(parts) > 1 else "")).upper()


def portrait(ctx: Ctx, tid: str, cls: str = "") -> str:
    t = ctx.talent[tid]
    if tid in ctx.portraits:
        return f'<img class="portrait {cls}" src="{ctx.portraits[tid]}" alt="{e(t["name"])}, AI-generated presenter">'
    return f'<span class="portrait mono {cls}" aria-hidden="true">{e(initials(t["name"]))}</span>'


def video_tag(a: dict) -> str:
    if not a.get("video"):
        return ""
    return (f'<div class="player"><video controls preload="none" playsinline src="{e(a["video"])}">'
            f'</video></div>')


def stock_img(ctx: Ctx, a: dict) -> str | None:
    if is_sensitive(a["title"], a.get("standfirst") or ""):
        return None          # no stock scenery on stories about death, war, disasters...
    return images.pick(ctx.stock, a["desk"], a["slug"])


def thumb(ctx: Ctx, a: dict, url: str) -> str:
    src = stock_img(ctx, a)
    if not src:
        return ""
    return (f'<a class="thumb" href="{url}" tabindex="-1" aria-hidden="true"><img src="{src}" alt="" loading="lazy" '
            f'width="600" height="338"><span class="ill">Illustrative image</span></a>')


def card(ctx: Ctx, a: dict, size: str = "m", deck: bool = False, kicker: bool = True,
         show_video: bool = False, meta: bool = True, img: bool = False) -> str:
    url = article_url(a)
    k = f'<a class="kicker" href="{desk_path(a["desk"])}">{e(DESK_NAMES.get(a["desk"], a["desk"].title()))}</a>' if kicker else ""
    badge = '<span class="badge-video">Watch</span>' if a.get("video") and not show_video else ""
    d = f'<p class="deck">{e(a["standfirst"])}</p>' if deck and a.get("standfirst") else ""
    m = (f'<p class="meta">{person_link(ctx, a["presenter"])}{time_tag(ctx, a["ts"], rel=True)}</p>'
         if meta else "")
    vid = video_tag(a) if show_video else ""
    if img and not (show_video and a.get("video")):
        vid = thumb(ctx, a, url)
    return (f'<article class="card">{vid}{k}<h3 class="hl hl-{size}"><a href="{url}">{badge}{e(a["title"])}</a></h3>'
            f'{d}{m}</article>')


def empty(msg: str) -> str:
    return f'<p class="empty">{e(msg)}</p>'


# ------------------------------------------------------------------ chrome

def trending(ctx: Ctx, n: int = 8) -> list[dict]:
    """Rotating top-bar headlines: the current edition in running order (ranked by
    how widely each event is covered and how urgent it is), then the newest."""
    pool = [a for a in ctx.articles if a["desk"] not in ("weather", "traffic")]
    cur = [a for a in pool if a.get("_current")]
    seen, out = set(), []
    for a in cur + pool:
        if a["slug"] not in seen:
            seen.add(a["slug"])
            out.append(a)
        if len(out) >= n:
            break
    return out


def weather_bit(ctx: Ctx) -> str:
    w = (ctx.localdata or {}).get("weather")
    if not w or w.get("temp") is None:
        return ""
    return (f'<a class="wx" href="/local/weather/" title="{e(w["place"])} weather">'
            f'<b>{w["temp"]}&deg;C</b> {e(w["cond"].capitalize())}<span class="wx-place">, {e(w["place"])}</span></a>')


def onair_bar(ctx: Ctx) -> str:
    items = trending(ctx)
    now = datetime.now(ctx.tz)
    today = now.strftime("%a, %b %d").replace(" 0", " ")
    lis = "".join(f'<li{"" if i == 0 else " hidden"}><a href="{article_url(a)}">{e(a["title"])}</a></li>'
                  for i, a in enumerate(items))
    ticker = (f'<div class="ticker" data-ticker><ul>{lis}</ul></div>'
              f'<button class="tick-pause" type="button" aria-label="Pause trending headlines" data-pause>&#10073;&#10073;</button>'
              if items else '<div class="ticker"><span>New stories every 15 minutes</span></div>')
    return (f'<div class="onair" role="region" aria-label="Trending now"><div class="wrap">'
            f'<a class="tally" href="/latest/"><i aria-hidden="true"></i>Trending</a>{ticker}'
            f'<span class="right"><time id="today" data-tz="{e(str(ctx.tz))}" datetime="{now:%Y-%m-%d}">{e(today)}</time>'
            f'{weather_bit(ctx)}</span></div></div>')


def nav(active: str | None) -> str:
    items = []
    for s in SECTIONS:
        cur = ' aria-current="page"' if active == s["id"] else ""
        sub = ""
        if s["subs"]:
            sub = '<ul class="sub">' + "".join(
                f'<li><a href="{s["path"]}{d}/">{e(n)}</a></li>' for d, n in s["subs"]) + "</ul>"
        items.append(f'<li><a href="{s["path"]}"{cur}>{e(s["name"])}</a>{sub}</li>')
    for path, name, key in (("/markets/", "Markets", "markets"), ("/video/", "Video", "video"),
                            ("/shows/", "Shows", "shows")):
        cur = ' aria-current="page"' if active == key else ""
        items.append(f'<li><a href="{path}"{cur}>{name}</a></li>')
    return (f'<nav class="primary" aria-label="Sections"><div class="wrap"><ul class="top">{"".join(items)}</ul>'
            f'</div></nav>')


def masthead(ctx: Ctx) -> str:
    return (f'<header class="mast"><div class="wrap">'
            f'<a class="brand" href="/" aria-label="Gu Broadcasting Station home"><span class="gu">Gu</span>'
            f'<span class="full">Broadcasting Station</span></a>'
            f'<div class="tools"><a class="btn ghost" href="/search/">Search</a>'
            f'<a class="btn ghost member-cta" href="/membership/">Become a member</a>'
            f'<a class="btn" href="/login/" data-account>Sign in</a>'
            f'<a class="btn solid" href="/newsletter/">Get the briefing</a>'
            f'<button class="btn navtoggle" aria-expanded="false" aria-controls="nav">Menu</button></div>'
            f'</div></header>')


def breaking_band(ctx: Ctx) -> str:
    b = ctx.bookends.get("breaking")
    if not b:
        return ""
    target = next((a for a in ctx.articles if a["title"] == b["title"]), None)
    link = f'<a href="{article_url(target)}">{e(b["title"])}</a>' if target else f'<a href="/live/">{e(b["title"])}</a>'
    return f'<div class="breaking" role="alert"><div class="wrap"><strong>Breaking</strong>{link}</div></div>'


def footer(ctx: Ctx) -> str:
    sec = "".join(f'<li><a href="{s["path"]}">{e(s["name"])}</a></li>' for s in SECTIONS)
    watch = "".join(f'<li><a href="{u}">{n}</a></li>' for u, n in (
        ("/live/", "Latest edition"), ("/video/", "Video"), ("/shows/", "Shows"), ("/people/", "Anchors & reporters"),
        ("/markets/", "Markets"), ("/local/weather/", "Weather")))
    about = "".join(f'<li><a href="{u}">{n}</a></li>' for u, n in (
        ("/about/", "About Gu"), ("/about/standards/", "Editorial standards"), ("/about/ai/", "How Gu uses AI"),
        ("/about/corrections/", "Corrections"), ("/contact/", "Contact"),
        ("/tips/", "Send a tip")))
    biz = "".join(f'<li><a href="{u}">{n}</a></li>' for u, n in (
        ("/membership/", "Membership"), ("/account/", "Your account"),
        ("/advertise/", "Advertise"), ("/advertise/guidelines/", "Sponsorship guidelines"),
        ("/newsletter/", ctx.site["newsletter"]["name"]), ("/feed.xml", "RSS feeds"), ("/archive/", "Archive"),
        ("/sitemap/", "Site map")))
    legal = "".join(f'<li><a href="{u}">{n}</a></li>' for u, n in (
        ("/privacy/", "Privacy policy"), ("/terms/", "Terms of use"), ("/cookies/", "Cookie policy"),
        ("/accessibility/", "Accessibility")))
    social = " ".join(f'<a href="{e(u)}" rel="me noopener">{e(n)}</a>' for n, u in ctx.site["social"].items() if u)
    return (f'<footer class="site"><div class="wrap"><div class="cols5">'
            f'<div><h2>Sections</h2><ul>{sec}</ul></div><div><h2>Watch</h2><ul>{watch}</ul></div>'
            f'<div><h2>About</h2><ul>{about}</ul></div><div><h2>Business</h2><ul>{biz}</ul></div>'
            f'<div><h2>Legal</h2><ul>{legal}</ul></div></div>'
            f'<div class="base"><span class="gu">Gu</span>'
            f'<span>Every Gu anchor and reporter is an AI-generated character. Every story is written in our own '
            f'words. Images marked "Illustrative" show the topic, not the event.</span>'
            f'<span>{social}</span><span>&copy; {datetime.now().year} {e(ctx.site["operator"])}</span></div>'
            f'</div></footer>')


def shell(ctx: Ctx, path: str, title: str, body: str, desc: str = "", active: str | None = None,
          og_type: str = "website", jsonld: dict | None = None, extra_head: str = "", top_ad: bool = True) -> str:
    full = title if title == ctx.cfg.site_name else f"{title} | {ctx.cfg.site_name}"
    desc = desc or ctx.site["tagline"]
    url = ctx.cfg.site_url + path
    ld = f'<script type="application/ld+json">{json.dumps(jsonld)}</script>' if jsonld else ""
    cookie = ""
    if ctx.ads.cfg.get("ad_network", {}).get("enabled"):
        cookie = ('<div class="cookie" role="dialog" aria-label="Cookie choices"><p>Our advertising partner uses '
                  'cookies to show and measure ads. <a href="/cookies/">Cookie policy</a></p>'
                  '<button class="btn solid" data-v="all">Accept ad cookies</button> '
                  '<button class="btn" data-v="essential">Essential only</button></div>')
    ad = f'<div class="wrap ad-top">{ctx.ads.web_slot("top")}</div>' if top_ad else ""
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{e(full)}</title><meta name="description" content="{e(desc)}">
<link rel="canonical" href="{e(url)}"><link rel="icon" href="/assets/favicon.svg" type="image/svg+xml">
<link rel="manifest" href="/manifest.webmanifest"><meta name="theme-color" content="#f3ece0">
<script>try{{if(/(^|; )gu_m=1/.test(document.cookie))document.documentElement.className+=" member"}}catch(e){{}}</script>
<link rel="alternate" type="application/rss+xml" title="{e(ctx.cfg.site_name)}" href="/feed.xml">
<meta property="og:site_name" content="{e(ctx.cfg.site_name)}"><meta property="og:type" content="{og_type}">
<meta property="og:title" content="{e(title)}"><meta property="og:description" content="{e(desc)}">
<meta property="og:url" content="{e(url)}"><meta name="twitter:card" content="summary">
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="{assets.FONTS}"><link rel="stylesheet" href="/assets/gu.css?v={assets.CSS_VER}">
{ctx.ads.head_tag()}{extra_head}{ld}</head><body>
<a class="skip" href="#main">Skip to content</a>
{onair_bar(ctx)}{masthead(ctx)}<div id="nav">{nav(active)}</div>{breaking_band(ctx)}
{ad}<main id="main" class="wrap">{body}</main>{footer(ctx)}{cookie}
<script src="/assets/gu.js?v={assets.JS_VER}" defer></script></body></html>"""


def newsletter_band(ctx: Ctx) -> str:
    n = ctx.site["newsletter"]
    return (f'<section class="newsletter-band" aria-labelledby="nl"><div><h2 id="nl">{e(n["name"])}</h2>'
            f'<p>{e(n["blurb"])}</p></div><a class="btn solid" href="/newsletter/">Sign up</a></section>')


# ------------------------------------------------------------------ pages: news

def page_home(ctx: Ctx) -> None:
    arts = ctx.articles
    if not arts:
        write(ctx, "/", shell(ctx, "/", ctx.cfg.site_name, empty("The first edition is being prepared. Check back in a few minutes.")))
        return
    edition = [a for a in arts if a.get("_current")] or arts[:12]
    lead, rest = edition[0], edition[1:]
    lead_media = video_tag(lead) or thumb(ctx, lead, article_url(lead)).replace('class="thumb"', 'class="thumb lead-img"')
    lead_html = (f'<div>{lead_media}<div class="lowerthird"><a class="kicker" href="{desk_path(lead["desk"])}">'
                 f'{e(DESK_NAMES.get(lead["desk"], ""))}</a><h2 class="hl hl-xl"><a href="{article_url(lead)}">'
                 f'{e(lead["title"])}</a></h2>'
                 + (f'<p class="deck">{e(lead["standfirst"])}</p>' if lead.get("standfirst") else "")
                 + f'<p class="meta">{person_link(ctx, lead["presenter"])}{time_tag(ctx, lead["ts"], rel=True)}</p></div>'
                 + (f'<div class="lead-more">{"".join(card(ctx, a, "s", meta=False) for a in rest[4:8])}</div>' if rest[4:] else "")
                 + "</div>")
    second = '<div class="stack">' + "".join(card(ctx, a, "m", deck=i == 0, img=i == 0) for i, a in enumerate(rest[:4])) + "</div>"
    latest = ('<aside class="latest" aria-labelledby="latest-h"><h2 id="latest-h">Latest <a href="/latest/">All</a></h2><ol>'
              + "".join(f'<li>{time_tag(ctx, a["ts"], fmt="%I:%M")}<a href="{article_url(a)}">{e(a["title"])}</a></li>'
                        for a in arts[:9]) + "</ol></aside>")
    body = f'<h1 class="vh">{e(ctx.cfg.site_name)}: top stories</h1><section class="lead">{lead_html}{second}{latest}</section>'

    op = ctx.bookends.get("open")
    an = ctx.anchor()
    if op:
        body += (f'<section class="nowon" aria-label="Now on Gu"><div class="who">{portrait(ctx, an["id"])}'
                 f'<div><strong><a href="/shows/{ctx.show["id"]}/">{e(ctx.show["name"])}</a></strong><br>'
                 f'{person_link(ctx, an["name"])}</div></div><p class="open">{e(op["script"])}</p>'
                 f'<a class="btn solid" href="/live/">Watch the edition</a></section>')
    body += ctx.ads.web_slot("inline")

    used = {a["slug"] for a in edition[:9]}
    rails = []
    for s in SECTIONS:
        items = [a for a in arts if a["desk"] in s["desks"] and a["slug"] not in used][:5]
        if not items:
            continue
        rails.append(f'<section class="rail" aria-labelledby="r-{s["id"]}"><h2 id="r-{s["id"]}">{e(s["name"])} '
                     f'<a href="{s["path"]}">More {e(s["name"].lower())}</a></h2>'
                     f'<div class="first">{card(ctx, items[0], "m", deck=True, kicker=False, img=True)}</div><ul>'
                     + "".join(f'<li>{card(ctx, a, "s", kicker=False, meta=False)}</li>' for a in items[1:]) + "</ul></section>")
    body += f'<div class="rails">{"".join(rails)}</div>'
    vids = [a for a in arts if a.get("video")][:4]
    if vids:
        body += (f'<section aria-labelledby="v-h"><h2 id="v-h" class="block-title">Watch <a href="/video/">All video</a></h2>'
                 f'<div class="grid">{"".join(card(ctx, a, "s", show_video=True) for a in vids)}</div></section>')
    body += newsletter_band(ctx)
    org = {"@context": "https://schema.org", "@type": "NewsMediaOrganization", "name": ctx.cfg.site_name,
           "url": ctx.cfg.site_url, "logo": ctx.cfg.site_url + "/assets/favicon.svg",
           "publishingPrinciples": ctx.cfg.site_url + "/about/standards/",
           "correctionsPolicy": ctx.cfg.site_url + "/about/corrections/",
           "actionableFeedbackPolicy": ctx.cfg.site_url + "/contact/"}
    write(ctx, "/", shell(ctx, "/", ctx.cfg.site_name, body, jsonld=org))


def listing(ctx: Ctx, arts: list[dict]) -> str:
    return '<ol class="listing">' + "".join(
        f'<li>{time_tag(ctx, a["ts"], fmt="%b %d, %I:%M %p")}<div>{card(ctx, a, "m", deck=True)}</div></li>'
        for a in arts) + "</ol>"


def side(ctx: Ctx) -> str:
    most = ctx.articles[:6]
    return ('<aside>' + ctx.ads.web_slot("sidebar") + '<section class="latest"><h2>Latest</h2><ol>'
            + "".join(f'<li>{time_tag(ctx, a["ts"], fmt="%I:%M")}<a href="{article_url(a)}">{e(a["title"])}</a></li>' for a in most)
            + "</ol></section></aside>")


def section_page(ctx: Ctx, path: str, name: str, intro: str, arts: list[dict], active: str,
                 subnav: list[tuple[str, str]] | None = None, feed: str | None = None) -> None:
    sn = ""
    if subnav:
        cur = ' aria-current="page"'
        sn = '<div class="subnav">' + "".join(
            f'<a href="{u}"{cur if u == path else ""}>{e(n)}</a>' for u, n in subnav) + "</div>"
    head = f'<header class="page-head"><h1>{e(name)}</h1><p>{e(intro)}</p>{sn}</header>'
    if arts:
        top = f'<div class="grid grid-3">{"".join(card(ctx, a, "l" if i == 0 else "m", deck=i == 0, kicker=len(subnav or []) > 1, show_video=i == 0, img=True) for i, a in enumerate(arts[:3]))}</div>'
        main = top + ctx.ads.web_slot("inline") + listing(ctx, arts[3:60])
    else:
        main = empty(f"No {name.lower()} stories yet. New stories arrive with every edition, about every 15 minutes.")
    extra = f'<link rel="alternate" type="application/rss+xml" title="{e(name)}" href="{feed}">' if feed else ""
    body = head + f'<div class="cols"><div>{main}</div>{side(ctx)}</div>'
    write(ctx, path, shell(ctx, path, name, body, desc=intro, active=active, extra_head=extra))


SECTION_INTROS = {
    "world": "International news from every region, led by correspondent Lena Moravec.",
    "politics": "Government, elections and policy, with politics reporter Marcus Bell.",
    "business": "Companies, the economy and your money, with Rafael Tertelbach and Dana Ruiz.",
    "tech": "Technology and AI, minus the hype, with Juno Park.",
    "science": "Space, climate, health research and discovery.",
    "entertainment": "Film, TV, music and culture, with Lola Sparks.",
    "sports": "Scores, upsets and the stories behind them, with Troy \"Coach\" Maddox.",
    "local": "Weather with Celeste Storm and traffic with Flip Torres.",
}
SUB_INTROS = {"americas": "North, Central and South America.", "europe": "Europe and the UK.",
              "asia": "Asia and the Pacific.", "mideast": "The Middle East.", "africa": "Africa.",
              "markets": "Markets and the economy.", "consumer": "Prices, scams, recalls and your rights, with Dana Ruiz.",
              "weather": "The forecast with meteorologist Celeste Storm.", "traffic": "Roads and transit with Flip Torres."}


def page_sections(ctx: Ctx) -> None:
    for s in SECTIONS:
        arts = [a for a in ctx.articles if a["desk"] in s["desks"]]
        sub = [(s["path"], f"All {s['name'].lower()}")] + [(f"{s['path']}{d}/", n) for d, n in s["subs"]]
        section_page(ctx, s["path"], s["name"], SECTION_INTROS[s["id"]], arts, s["id"],
                     sub if s["subs"] else None, feed=f"{s['path']}feed.xml")
        write(ctx, f"{s['path']}feed.xml", rss(ctx, arts[:40], s["name"], s["path"]), sitemap=False)
        for d, n in s["subs"]:
            section_page(ctx, f"{s['path']}{d}/", n, SUB_INTROS[d], [a for a in ctx.articles if a["desk"] == d],
                         s["id"], sub)


# ------------------------------------------------------------------ local: live weather + traffic

def _day(d: str) -> str:
    return datetime.strptime(d, "%Y-%m-%d").strftime("%a %b %d").replace(" 0", " ")


def weather_panel(ctx: Ctx, days: int = 7) -> str:
    w = (ctx.localdata or {}).get("weather")
    if not w:
        return empty("The live forecast is refreshing. Check back in a few minutes.")
    now = (f'<section class="wx-now"><p class="wx-place">{e(w["place"])}, right now</p>'
           f'<p class="wx-temp">{w["temp"]}&deg;C</p><p class="wx-cond">{e(w["cond"].capitalize())}</p><ul>'
           + (f'<li>Feels like {w["feels"]}&deg;</li>' if w.get("feels") is not None else "")
           + (f'<li>Wind {round(w["wind"])} km/h</li>' if w.get("wind") is not None else "")
           + (f'<li>Humidity {w["humidity"]}%</li>' if w.get("humidity") is not None else "")
           + "</ul></section>")
    rows = "".join(
        f'<tr><th>{e(_day(d["date"]))}</th><td>{e(d["cond"].capitalize())}</td>'
        f'<td>{"" if d["hi"] is None else round(d["hi"])}&deg; / {"" if d["lo"] is None else round(d["lo"])}&deg;</td>'
        f'<td>{"" if d["pop"] is None else str(d["pop"]) + "%"}</td></tr>' for d in w.get("days", [])[:days])
    table = (f'<table class="wx-days"><caption>{len(w.get("days", [])[:days])}-day forecast</caption><thead><tr><th>Day</th>'
             f'<th>Conditions</th><th>High / low</th><th>Rain chance</th></tr></thead><tbody>{rows}</tbody></table>') if rows else ""
    upd = time_tag(ctx, w.get("fetched") or time.time(), fmt="%I:%M %p %Z")
    return (f'<div class="wx-panel">{now}{table}</div><p class="meta"><span>Updated {upd}. '
            f'Forecast data: Open-Meteo.com (CC BY 4.0).</span></p>')


def traffic_panel(ctx: Ctx, limit: int = 40) -> str:
    t = (ctx.localdata or {}).get("traffic")
    if t is None:
        return empty("Live road conditions are refreshing. Check back in a few minutes.")
    evs = t.get("events", [])[:limit]
    name = localdesk.place()[0]
    if not evs:
        return empty(f"No active road incidents reported around {name} right now.")
    rows = "".join(
        f'<li class="sev-{e(x["severity"])}"><span class="sev">{e(x["severity"].capitalize())}</span><div>'
        f'<strong>{e(x["road"])}</strong>{" (" + e(x["direction"]) + ")" if x.get("direction") else ""}: {e(x["type"])}'
        + (f'<p>{e(x["text"])}</p>' if x.get("text") else "") + "</div></li>" for x in evs)
    upd = time_tag(ctx, t.get("fetched") or time.time(), fmt="%I:%M %p %Z")
    return (f'<p class="meta"><span>{len(t.get("events", []))} active incidents around {e(name)}, most serious first. '
            f'Updated {upd}.</span></p><ul class="traffic">{rows}</ul>'
            '<p class="meta">Road event data: DriveBC, Open Government Licence &ndash; British Columbia.</p>')


def page_local(ctx: Ctx) -> None:
    sec = next(x for x in SECTIONS if x["id"] == "local")
    sub = [(sec["path"], "All local")] + [(f"{sec['path']}{d}/", n) for d, n in sec["subs"]]
    name = localdesk.place()[0]

    def page(path, title, intro, top, arts):
        sn = '<div class="subnav">' + "".join(
            f'<a href="{u}"{" aria-current=" + chr(34) + "page" + chr(34) if u == path else ""}>{e(n)}</a>' for u, n in sub) + "</div>"
        body = (f'<header class="page-head"><h1>{e(title)}</h1><p>{e(intro)}</p>{sn}</header>'
                f'<div class="cols"><div>{top}'
                + (f'<h2 class="block-title">On air</h2>{listing(ctx, arts[:20])}' if arts else "")
                + f'</div>{side(ctx)}</div>')
        write(ctx, path, shell(ctx, path, title, body, desc=intro, active="local"))

    wx = [a for a in ctx.articles if a["desk"] == "weather"]
    tr = [a for a in ctx.articles if a["desk"] == "traffic"]
    page("/local/weather/", "Weather", f"The forecast for {name}, with meteorologist Celeste Storm. Updated every 15 minutes.",
         weather_panel(ctx), wx)
    page("/local/traffic/", "Traffic", f"Roads and transit around {name}, with Flip Torres. Updated every 10 minutes.",
         traffic_panel(ctx), tr)
    both = (f'<h2 class="block-title">Weather <a href="/local/weather/">Full forecast</a></h2>{weather_panel(ctx, 3)}'
            f'<h2 class="block-title">Traffic <a href="/local/traffic/">All incidents</a></h2>{traffic_panel(ctx, 6)}')
    page("/local/", "Local", f"{name} weather with Celeste Storm and traffic with Flip Torres.", both,
         sorted(wx + tr, key=lambda a: -a["ts"]))


def page_latest_live(ctx: Ctx) -> None:
    body = ('<header class="page-head"><h1>Latest news</h1><p>Every story Gu has published, newest first.</p></header>'
            f'<div class="cols"><div>{listing(ctx, ctx.articles[:80]) if ctx.articles else empty("No stories yet.")}</div>{side(ctx)}</div>')
    write(ctx, "/latest/", shell(ctx, "/latest/", "Latest news", body))

    an = ctx.anchor()
    parts = [f'<header class="page-head"><h1>{e(ctx.show["name"])}</h1><p>The current edition in running order, '
             f'presented by {person_link(ctx, an["name"])}. A new edition goes out about every 15 minutes.</p></header>']
    seq = []
    for key in ("breaking", "open"):
        if ctx.bookends.get(key):
            seq.append(("b", ctx.bookends[key]))
    seq += [("a", a) for a in ctx.articles if a.get("_current")]
    if ctx.bookends.get("close"):
        seq.append(("b", ctx.bookends["close"]))
    items = []
    for kind, x in seq:
        if kind == "b":
            v = f"/v/{x['slug']}.mp4" if (ctx.out / "v" / f"{x['slug']}.mp4").exists() else ""
            vid = video_tag({"video": v})
            label = {"breaking": "Breaking", "open": "Open", "close": "Close"}[x["kind"]]
            items.append(f'<li><span class="kicker">{label}</span><div>{vid}<p class="meta">{person_link(ctx, x["anchor"])}</p>'
                         f'<p class="body">{e(x["script"])}</p></div></li>')
        else:
            items.append(f'<li><span class="kicker">{e(DESK_NAMES.get(x["desk"], ""))}</span><div>'
                         f'{card(ctx, x, "m", deck=True, kicker=False, show_video=True)}</div></li>')
    parts.append('<ol class="listing">' + "".join(items) + "</ol>" if items else empty("The next edition is on its way."))
    write(ctx, "/live/", shell(ctx, "/live/", f"Watch: {ctx.show['name']}", "".join(parts)))


def page_story(ctx: Ctx, a: dict) -> None:
    url = article_url(a)
    sec = section_of(a["desk"])
    crumbs = f'<nav class="crumbs" aria-label="Breadcrumb"><a href="{sec["path"]}">{e(sec["name"])}</a>'
    if desk_path(a["desk"]) != sec["path"]:
        crumbs += f'<span aria-hidden="true">/</span><a href="{desk_path(a["desk"])}">{e(DESK_NAMES[a["desk"]])}</a>'
    crumbs += "</nav>"
    pid = person_id(ctx, a["presenter"])
    by = (f'<div class="byline">{portrait(ctx, pid) if pid else ""}<div><div class="name">{person_link(ctx, a["presenter"])}</div>'
          f'<div class="role">{e(a.get("presenter_title") or "")}, AI presenter</div>'
          f'<div class="when">Published {time_tag(ctx, a["ts"])}</div></div></div>')
    paras = "".join(f"<p>{e(p)}</p>" for p in a["script"].split("\n") if p.strip())
    sponsor = (f'<aside class="sponsor-box"><span class="lbl">Sponsored message read on air</span>{e(a["sponsor_read"])}</aside>'
               if a.get("sponsor_read") else "")
    note = ('<p class="note">Written in Gu\'s own words and presented by an AI-generated character. '
            '<a href="/about/ai/">How Gu uses AI</a>. Spotted an error? <a href="/about/corrections/">Request a correction</a>.</p>')
    hero = ""
    if not a.get("video"):
        src = stock_img(ctx, a)
        if src:
            hero = (f'<figure class="hero"><img src="{src}" alt="" width="1200" height="675">'
                    f'<figcaption>Illustrative image: it shows the topic, not this event.</figcaption></figure>')
    full = ctx.cfg.site_url + url
    share = ('<div class="share" aria-label="Share">'
             f'<a href="https://twitter.com/intent/tweet?url={quote(full)}&text={quote(a["title"])}" rel="noopener" target="_blank">Post on X</a>'
             f'<a href="https://www.facebook.com/sharer/sharer.php?u={quote(full)}" rel="noopener" target="_blank">Facebook</a>'
             f'<a href="https://www.linkedin.com/sharing/share-offsite/?url={quote(full)}" rel="noopener" target="_blank">LinkedIn</a>'
             f'<a href="https://www.reddit.com/submit?url={quote(full)}&title={quote(a["title"])}" rel="noopener" target="_blank">Reddit</a>'
             f'<a href="mailto:?subject={quote(a["title"])}&body={quote(full)}">Email</a>'
             '<button type="button" data-copy>Copy link</button></div>')
    rel = [x for x in ctx.articles if x["desk"] in sec["desks"] and x["slug"] != a["slug"]][:4]
    related = (f'<section class="related"><h2 class="block-title">More {e(sec["name"].lower())} '
               f'<a href="{sec["path"]}">All</a></h2><div class="grid">{"".join(card(ctx, x, "s", img=True) for x in rel)}</div></section>'
               if rel else "")
    body = (f'<div class="cols"><article class="article">{crumbs}<h1 class="hl hl-xl">{e(a["title"])}</h1>'
            + (f'<p class="deck">{e(a["standfirst"])}</p>' if a.get("standfirst") else "")
            + f'{by}{video_tag(a)}{hero}<div class="body">{paras}</div>{sponsor}{note}{share}</article>{side(ctx)}</div>{related}')
    ld = {"@context": "https://schema.org", "@type": "NewsArticle", "headline": a["title"][:110],
          "datePublished": t_iso(a["ts"]), "dateModified": t_iso(a["ts"]), "mainEntityOfPage": full,
          "articleSection": DESK_NAMES.get(a["desk"], ""),
          "author": {"@type": "Person", "name": a["presenter"], "url": f"{ctx.cfg.site_url}/people/{pid}/" if pid else ctx.cfg.site_url,
                     "description": "AI-generated presenter"},
          "publisher": {"@type": "NewsMediaOrganization", "name": ctx.cfg.site_name,
                        "logo": {"@type": "ImageObject", "url": ctx.cfg.site_url + "/assets/favicon.svg"}}}
    if a.get("video"):
        ld["video"] = {"@type": "VideoObject", "name": a["title"], "contentUrl": ctx.cfg.site_url + a["video"],
                       "uploadDate": t_iso(a["ts"]), "description": a.get("standfirst") or a["title"],
                       "thumbnailUrl": ctx.cfg.site_url + "/assets/favicon.svg"}
    write(ctx, url, shell(ctx, url, a["title"], body, desc=a.get("standfirst") or a["title"], active=sec["id"],
                          og_type="article", jsonld=ld))


def page_video(ctx: Ctx) -> None:
    vids = [a for a in ctx.articles if a.get("video")]
    head = ('<header class="page-head"><h1>Video</h1><p>Every story our AI anchors and reporters have read on air. '
            'New clips arrive through the day as the studio renders them.</p></header>')
    if vids:
        body = head + f'<div class="grid grid-3">{"".join(card(ctx, a, "m", show_video=True) for a in vids[:60])}</div>'
    else:
        onair = [a for a in ctx.articles if a.get("_current")][:9] or ctx.articles[:9]
        cast = [t for t in ctx.nr["talent"] if t["kind"] in ("anchor", "ai_anchor")][:6]
        body = (head + '<p class="empty">The anchor studio is coming online. Until the first clips arrive, here is what our '
                'anchors are reading on air right now; every script is printed on its story page.</p>'
                f'<h2 class="block-title">On air now <a href="/live/">Full edition</a></h2>'
                f'<div class="grid grid-3">{"".join(card(ctx, a, "m", img=True) for a in onair)}</div>'
                '<h2 class="block-title">Your anchors <a href="/people/">Everyone</a></h2><div class="people">'
                + "".join(f'<div class="person">{portrait(ctx, t["id"])}<div><a href="/people/{t["id"]}/"><strong>'
                          f'{e(t["name"])}</strong></a><div class="t">{e(t["title"])}</div></div></div>' for t in cast)
                + '</div>')
    write(ctx, "/video/", shell(ctx, "/video/", "Video", body, active="video"))


def page_markets(ctx: Ctx) -> None:
    p = ctx.pulse
    if p.get("regime"):
        heads = "".join(f"<li>{e(h)}</li>" for h in p.get("top_headlines", []) if h)
        card_ = (f'<section class="pulse-card"><p>Gu market pulse</p><p class="regime">{e(str(p["regime"]).capitalize())}</p>'
                 f'<p>A reading of market-moving news: calm, normal, elevated or crisis. It updates with every edition.</p>'
                 + (f"<p>Driving it now:</p><ul>{heads}</ul>" if heads else "") + "</section>")
    else:
        card_ = empty("The market pulse is offline right now. Business headlines below are still current.")
    arts = [a for a in ctx.articles if a["desk"] in ("business", "markets", "consumer")]
    body = ('<header class="page-head"><h1>Markets</h1><p>How the news is moving markets, with business reporter '
            f'{person_link(ctx, "Rafael Tertelbach")}. Not investment advice.</p></header>'
            f'<div class="cols"><div>{card_}{listing(ctx, arts[:40]) if arts else ""}</div>{side(ctx)}</div>')
    write(ctx, "/markets/", shell(ctx, "/markets/", "Markets", body, active="markets"))


DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def show_when(show: dict) -> str:
    if show.get("default"):
        return "Around the clock, between our flagship shows"
    d = show["days"]
    days = "Weekdays" if d == [0, 1, 2, 3, 4] else "Weekends" if d == [5, 6] else ", ".join(DAYS[i] for i in d)
    fmt = lambda s: datetime.strptime(s, "%H:%M").strftime("%I:%M %p").lstrip("0")
    return f"{days}, {fmt(show['start'])} to {fmt(show['end'])}"


SHOW_BLURBS = {"morning": "Wake up with Harold Yi and Benji Powers: the overnight headlines, the weather and your commute.",
               "evening": "The day's defining stories, told straight, with lead anchor Harold Yi and assistant anchor Tessa Vale.",
               "weekend": "The week's big stories, calmly explained.",
               "gucast": "A short update every 15 minutes, read by Gu's AI prime anchor."}


def page_shows(ctx: Ctx) -> None:
    cards = []
    for s in ctx.nr["shows"]:
        a = ctx.talent[s["anchor"]]
        live = s["id"] == ctx.show["id"]
        cards.append(f'<article class="showcard{" live" if live else ""}"><h2 class="hl hl-l"><a href="/shows/{s["id"]}/">{e(s["name"])}</a></h2>'
                     f'<p class="sched">{e(show_when(s))} ({e(str(ctx.tz))}){", on air now" if live else ""}</p>'
                     f'<p>{e(SHOW_BLURBS.get(s["id"], ""))}</p>' + "".join(
                         f'<div class="person">{portrait(ctx, x["id"])}<div>{person_link(ctx, x["name"])}'
                         f'<div class="t">{e(x["title"])}</div></div></div>'
                         for x in [a] + ([ctx.talent[s["co_anchor"]]] if s.get("co_anchor") else [])) + '</article>')
        recent = [x for x in ctx.articles if x.get("show_id") == s["id"]][:20]
        body = (f'<header class="page-head"><h1>{e(s["name"])}</h1><p>{e(SHOW_BLURBS.get(s["id"], ""))}</p>'
                f'<p class="sched">{e(show_when(s))}, {e(str(ctx.tz))} time. Presented by {person_link(ctx, a["name"])}'
                + (f' with {person_link(ctx, ctx.talent[s["co_anchor"]]["name"])}' if s.get("co_anchor") else "")
                + '.</p></header>'
                + ('<p><a class="btn solid" href="/live/">Watch the current edition</a></p>' if live else "")
                + (f'<h2 class="block-title">Recent stories on {e(s["name"])}</h2>{listing(ctx, recent)}' if recent
                   else empty(f"{s['name']} stories will appear here after its next edition.")))
        write(ctx, f"/shows/{s['id']}/", shell(ctx, f"/shows/{s['id']}/", s["name"], body, active="shows"))
    brk = ctx.talent[ctx.nr["breaking"]["anchor"]]
    body = ('<header class="page-head"><h1>Shows</h1><p>Gu is on air all day. Flagship shows run at fixed times; '
            f'Gu-cast fills every gap; breaking news cuts in with {person_link(ctx, brk["name"])} whenever it happens.</p></header>'
            f'<div class="grid">{"".join(cards)}</div>')
    write(ctx, "/shows/", shell(ctx, "/shows/", "Shows", body, active="shows"))


def page_people(ctx: Ctx) -> None:
    groups = [("Anchors", ("anchor",)), ("AI anchor unit", ("ai_anchor",)), ("Reporters & correspondents", ("reporter",)),
              ("Newsroom", ("production",))]
    hosted = defaultdict(list)
    for s in ctx.nr["shows"]:
        hosted[s["anchor"]].append(s)
        if s.get("co_anchor"):
            hosted[s["co_anchor"]].append(s)
    blocks = []
    for label, kinds in groups:
        ppl = [t for t in ctx.nr["talent"] if t["kind"] in kinds]
        blocks.append(f'<h2 class="block-title">{e(label)}</h2><div class="people">' + "".join(
            f'<div class="person">{portrait(ctx, t["id"])}<div><a href="/people/{t["id"]}/"><strong>{e(t["name"])}</strong></a>'
            f'<div class="t">{e(t["title"])}</div></div></div>' for t in ppl) + "</div>")
        for t in ppl:
            mine = [a for a in ctx.articles if a["presenter"] == t["name"]][:30]
            on_air = t["kind"] != "production"
            facts = []
            if t.get("signature"):
                facts.append("Opens every edition of " + ", ".join(
                    f'<a href="/shows/{s["id"]}/">{e(s["name"])}</a>' for s in hosted[t["id"]] if s["anchor"] == t["id"])
                    + " with the station's signature line")
            if hosted.get(t["id"]):
                facts.append("Hosts " + ", ".join(f'<a href="/shows/{s["id"]}/">{e(s["name"])}</a>' for s in hosted[t["id"]]))
            if t.get("desks"):
                facts.append("Covers " + ", ".join(f'<a href="{desk_path(d)}">{e(DESK_NAMES.get(d, d))}</a>' for d in t["desks"]))
            if t["id"] == ctx.nr["breaking"]["anchor"]:
                facts.append("Reads every breaking-news update")
            kind_note = ("An AI-generated on-air character. The face and voice are synthetic; every script is written "
                         "under Gu's editorial standards." if on_air else
                         "A role in Gu's AI newsroom: this character stands for the editorial rules the system follows.")
            body = (f'<div class="profile">{portrait(ctx, t["id"], "lg")}<div><h1 class="hl hl-xl">{e(t["name"])}</h1>'
                    f'<p class="deck">{e(t["title"])}</p></div></div><div class="cols"><div class="prose">'
                    f'<p>{e(t["style"])}</p><blockquote><p>{e(t["sample"])}</p></blockquote>'
                    + "".join(f"<p>{f}.</p>" for f in facts) + f'<p class="note">{e(kind_note)}</p></div>{side(ctx)}</div>'
                    + (f'<h2 class="block-title">Latest from {e(t["name"])}</h2>{listing(ctx, mine)}' if mine else
                       (empty(f"{t['name']}'s stories will appear here after their next segment.") if on_air else "")))
            ld = {"@context": "https://schema.org", "@type": "Person", "name": t["name"], "jobTitle": t["title"],
                  "description": "AI-generated character", "worksFor": {"@type": "NewsMediaOrganization", "name": ctx.cfg.site_name}}
            write(ctx, f"/people/{t['id']}/", shell(ctx, f"/people/{t['id']}/", t["name"], body, desc=f"{t['name']}, {t['title']}", jsonld=ld))
    body = ('<header class="page-head"><h1>Anchors &amp; reporters</h1><p>Meet the Gu team. Every face and voice '
            'on Gu is AI-generated, and none of them is a real person.</p></header>' + "".join(blocks))
    write(ctx, "/people/", shell(ctx, "/people/", "Anchors & reporters", body))


def page_archive(ctx: Ctx) -> None:
    by_day = defaultdict(list)
    for a in ctx.articles:
        by_day[ctx.local(a["ts"]).strftime("%Y-%m-%d")].append(a)
    days = sorted(by_day, reverse=True)
    rows = "".join(f'<li><span>{e(datetime.strptime(d, "%Y-%m-%d").strftime("%A, %B %d, %Y").replace(" 0", " "))}</span>'
                   f'<a href="/archive/{d}/">{len(by_day[d])} stories</a></li>' for d in days)
    body = ('<header class="page-head"><h1>Archive</h1><p>Every day of Gu coverage from the last '
            f'{ctx.site["archive_days"]} days. Story pages stay online after they leave this list.</p></header>'
            + (f'<ul class="listing">{rows}</ul>' if rows else empty("The archive starts with the first edition.")))
    write(ctx, "/archive/", shell(ctx, "/archive/", "Archive", body))
    for d in days:
        nice = datetime.strptime(d, "%Y-%m-%d").strftime("%A, %B %d, %Y").replace(" 0", " ")
        body = f'<header class="page-head"><h1>{e(nice)}</h1><p><a href="/archive/">All dates</a></p></header>' + listing(ctx, by_day[d])
        write(ctx, f"/archive/{d}/", shell(ctx, f"/archive/{d}/", f"Archive: {nice}", body))


def page_search(ctx: Ctx) -> None:
    idx = [{"t": a["title"], "s": a.get("standfirst") or "", "p": a["presenter"], "d": DESK_NAMES.get(a["desk"], ""),
            "u": article_url(a), "date": ctx.local(a["ts"]).strftime("%b %d")} for a in ctx.articles]
    write(ctx, "/search-index.json", json.dumps(idx, ensure_ascii=False), sitemap=False)
    body = ('<header class="page-head"><h1>Search</h1></header>'
            '<form id="search-form" class="stack-form" role="search" action="/search/" method="get">'
            '<label class="vh" for="q">Search stories</label><input id="q" name="q" type="search" placeholder="Search stories, people, places" autocomplete="off">'
            '<button class="btn solid" type="submit">Search</button></form>'
            '<p id="search-status" class="meta" aria-live="polite"></p><ol id="results" class="listing"></ol>'
            '<noscript><p class="empty">Search needs JavaScript. You can browse by <a href="/archive/">date</a> or section instead.</p></noscript>')
    write(ctx, "/search/", shell(ctx, "/search/", "Search", body))


def signup_form(ctx: Ctx, fid: str = "em") -> str:
    n = ctx.site["newsletter"]
    if n.get("action"):
        return (f'<form class="stack-form" method="post" action="{e(n["action"])}">'
                f'<label class="vh" for="{fid}">Email address</label>'
                f'<input id="{fid}" name="{e(n.get("email_field", "email_address"))}" type="email" required '
                'placeholder="you@example.com" autocomplete="email">'
                '<button class="btn solid" type="submit">Subscribe</button></form>'
                '<p class="meta">We\'ll email you a link to confirm. Unsubscribe from any issue in one click.</p>')
    return (f'<p><a class="btn solid" href="mailto:{ctx.emails["general"]}?subject=Subscribe%20to%20{quote(n["name"])}">'
            'Subscribe by email</a></p><p class="meta">Send the email as is. We\'ll add you when the first issue goes out '
            'and ask you to confirm.</p>')


def page_newsletter(ctx: Ctx) -> None:
    from gbs.newsletter.compose import load_issues
    n = ctx.site["newsletter"]
    issues = load_issues(ctx.cfg)
    live = bool(n.get("action"))
    status = "" if live else "<p><strong>Launching soon.</strong> Sign up now and you'll get the first issue.</p>"
    past = ("<h2>Recent issues</h2><ul>" + "".join(
        f'<li><a href="/newsletter/issues/{i["date"]}/">{e(datetime.strptime(i["date"], "%Y-%m-%d").strftime("%A, %B %d").replace(" 0", " "))}</a>: '
        f'{e(i["subject"])}</li>' for i in issues[:30]) + "</ul>") if issues else ""
    body = (f'<header class="page-head"><h1>{e(n["name"])}</h1><p>{e(n["blurb"])}</p></header><div class="cols"><div class="prose">'
            f'{status}{signup_form(ctx)}'
            '<h2>What you get</h2><ul><li>The three stories that matter most, each in two lines.</li>'
            '<li>One or two headlines from every desk: world, politics, business, tech and science, culture and sports.</li>'
            '<li>The market pulse and the local forecast.</li>'
            f'<li>One labelled sponsor message at most. {e(n.get("cadence", ""))}, about a three-minute read.</li></ul>'
            '<p>Signing up gets you a free one-page guide: <a href="/newsletter/guide/">how to read a news story in 60 seconds</a>.</p>'
            f'{past}'
            '<h2>Your address</h2><p>We use it only to send The Gu Briefing, through our email provider Kit. We never sell it. '
            'See the <a href="/privacy/">privacy policy</a>.</p>'
            '<h2>Prefer a feed?</h2><p>Follow every section by RSS: <a href="/feed.xml">all stories</a>, or add '
            '<code>feed.xml</code> to any section address, for example <a href="/world/feed.xml">/world/feed.xml</a>.</p>'
            f'</div>{side(ctx)}</div>')
    write(ctx, "/newsletter/", shell(ctx, "/newsletter/", n["name"], body))

    write(ctx, "/newsletter/thanks/", shell(ctx, "/newsletter/thanks/", "Check your inbox", (
        '<header class="page-head"><h1>Check your inbox</h1><p>One more step: we\'ve sent you an email with a confirmation '
        'link.</p></header><div class="prose"><p>Click the link in that email to start receiving '
        f'{e(n["name"])}. If it isn\'t there in a few minutes, check your spam or promotions folder, and add '
        f'{e(ctx.emails["general"])} to your contacts so future issues land in your inbox.</p>'
        '<p>While you wait: <a href="/newsletter/guide/">how to read a news story in 60 seconds</a>.</p></div>')))

    write(ctx, "/newsletter/confirmed/", shell(ctx, "/newsletter/confirmed/", "You're subscribed", (
        f'<header class="page-head"><h1>You\'re subscribed</h1><p>Welcome to {e(n["name"])}.</p></header><div class="prose">'
        f'<p>Your first issue arrives at the next send: {e(n.get("cadence", "weekday mornings"))}. Each one has the top '
        'stories and a headline or two from every desk, about three minutes of reading.</p>'
        '<h2>Your free guide</h2><p><a href="/newsletter/guide/">How to read a news story in 60 seconds</a>: five checks '
        'that work on any story.</p>'
        '<h2>One question</h2><p>Which part of the world, or which topic, do you think gets too little coverage? Reply to any '
        f'issue, or email {_mail_link(ctx.emails["tips"])}. We read every reply, and it shapes what we cover.</p>'
        '<p>Meanwhile: <a href="/live/">watch the latest edition</a> or <a href="/people/">meet the anchors</a>.</p></div>')))

    write(ctx, "/newsletter/guide/", shell(ctx, "/newsletter/guide/", "How to read a news story in 60 seconds", (
        '<header class="page-head"><h1>How to read a news story in 60 seconds</h1><p>Five checks that work on any '
        'story, from anyone, including us.</p></header><div class="prose"><ol>'
        '<li><strong>Who reported it first?</strong> Look for the original report, not the account sharing it.</li>'
        '<li><strong>How many independent reports are there?</strong> One report is a lead. Several independent reports '
        'make a story. Gu ranks stories higher when they are widely reported.</li>'
        '<li><strong>What\'s fact and what\'s claim?</strong> "Officials said" and "according to" mark claims, not '
        'confirmed facts. Notice who is speaking.</li>'
        '<li><strong>How old is it?</strong> Check the timestamp. Old stories travel fast when something new happens.</li>'
        '<li><strong>Does the headline match the story?</strong> Read past the first line before you share. If the '
        'details are thinner than the headline, wait.</li></ol>'
        '<p>Gu is presented by AI characters and condenses published reporting, so these checks apply to us too. '
        'If a Gu story fails one, <a href="/about/corrections/">tell us</a>.</p>'
        f'{signup_form(ctx, "em2") if not ctx.site.get("_hide_guide_form") else ""}</div>'),
        desc="Five checks to run on any news story before you believe it or share it."))

    for i in issues[:60]:
        nice = datetime.strptime(i["date"], "%Y-%m-%d").strftime("%A, %B %d, %Y").replace(" 0", " ")
        path = f"/newsletter/issues/{i['date']}/"
        body = (f'<header class="page-head"><h1>{e(n["name"])}: {e(nice)}</h1><p><a href="/newsletter/">All issues '
                f'and sign-up</a></p></header><div class="cols"><div class="issue">{i["html"]}</div>'
                f'<aside><section class="newsletter-band"><div><h2>Get it by email</h2><p>{e(n.get("cadence", ""))}.</p>'
                f'</div></section>{signup_form(ctx, "em3")}</aside></div>')
        write(ctx, path, shell(ctx, path, f"{n['name']}: {nice}", body, desc=i.get("preheader") or n["blurb"]))


def _mail_link(addr: str) -> str:
    return f'<a href="mailto:{e(addr)}">{e(addr)}</a>'


def rebuild_newsletter_pages(cfg: Settings) -> None:
    """Refresh only the newsletter pages (after `gbs newsletter`)."""
    ctx = Ctx(cfg, None, {}, {})
    ctx.articles = PublishedStore(cfg.data_dir / "published.db").recent(ctx.site["archive_days"])
    page_newsletter(ctx)


# ------------------------------------------------------------------ account + membership

def page_account(ctx: Ctx) -> None:
    btns = "".join(f'<a class="btn provider p-{p}" href="/auth/{p}/start?next=/account/" data-next>'
                   f'Continue with {e(label)}</a>' for p, label in ctx.providers)
    login = ('<header class="page-head"><h1>Sign in to Gu</h1><p>One click with an account you already have. '
             'Reading Gu is free and never needs an account; sign in to become a member.</p></header>'
             '<div class="cols"><div class="prose"><p id="auth-msg" class="note" hidden></p>'
             + (f'<div class="providers">{btns}</div>' if btns else
                '<p class="empty">Sign-in is opening soon. Everything on Gu is free to read in the meantime.</p>')
             + '<h2>What we get from your sign-in</h2><p>Your name, email address and an account ID from the provider you '
             'choose. We never see your password and never post anything. See the <a href="/privacy/">privacy policy</a>.</p>'
             f'<p>New here? <a href="/membership/">See membership</a>.</p></div>{side(ctx)}</div>')
    write(ctx, "/login/", shell(ctx, "/login/", "Sign in", login, desc="Sign in to Gu Broadcasting Station."))

    acct = ('<header class="page-head"><h1>Your account</h1></header><div class="cols"><div class="prose" id="account" '
            'data-account-page><p class="empty" data-when="out">You\'re not signed in. <a href="/login/">Sign in</a> to see '
            'your membership.</p><div data-when="in" hidden><p><strong data-f="name"></strong><br><span data-f="email"></span>'
            '<br><span class="meta">Signed in with <span data-f="provider"></span></span></p>'
            '<h2>Membership</h2><p data-f="plan"></p>'
            '<p data-when="free" hidden><a class="btn solid" href="/membership/">Become a member</a></p>'
            '<form data-when="portal" hidden method="post" action="/billing/portal"><button class="btn" type="submit">'
            'Manage billing, receipts or cancel</button></form>'
            '<h2>Sign out</h2><form method="post" action="/auth/logout"><button class="btn" type="submit">Sign out</button></form>'
            '</div><noscript><p class="empty">Your account page needs JavaScript.</p></noscript></div>'
            f'{side(ctx)}</div>')
    write(ctx, "/account/", shell(ctx, "/account/", "Your account", acct), sitemap=False)

    m = ctx.membership
    free = m["free"]
    cols = [f'<article class="plan"><h2>{e(free["name"])}</h2><p class="price">Free</p><ul>'
            + "".join(f"<li>{e(x)}</li>" for x in free["perks"]) + '</ul><a class="btn" href="/login/">Sign in</a></article>']
    for pl in m["plans"]:
        live = ctx.plan_live.get(pl["id"])
        badge = f'<span class="plan-badge">{e(pl["badge"])}</span>' if pl.get("badge") else ""
        action = (f'<form method="post" action="/billing/checkout"><input type="hidden" name="plan" value="{e(pl["id"])}">'
                  f'<button class="btn solid" type="submit">Join: {e(pl["price"])}</button></form>' if live else
                  '<button class="btn" type="button" disabled>Opening soon</button>')
        cols.append(f'<article class="plan{" featured" if pl["id"] == "yearly" else ""}">{badge}<h2>{e(pl["name"])}</h2>'
                    f'<p class="price">{e(pl["price"])} <span>{e(pl["interval"])}</span></p><ul>'
                    + "".join(f"<li>{e(x)}</li>" for x in pl["perks"]) + f"</ul>{action}</article>")
    faq = ('<div class="prose"><h2>Questions</h2>'
           '<h3>Do I need to be a member to read Gu?</h3><p>No. Every story and clip is free. Membership funds the newsroom '
           'and takes the ads away.</p>'
           '<h3>How do I pay?</h3><p>Securely through Stripe. Gu never sees or stores your card number.</p>'
           '<h3>Can I cancel?</h3><p>Yes, any time, from <a href="/account/">your account</a>. Monthly and yearly '
           'memberships run to the end of the period you paid for and then stop.</p>'
           '<h3>Refunds?</h3><p>Email ' + _mail_link(ctx.emails["general"]) + ' within 14 days of a charge and we\'ll refund '
           'it. The Founding Member payment is refundable within 14 days too.</p>'
           '<p class="meta">Prices in Canadian dollars. Taxes may apply. See the <a href="/terms/">terms of use</a>.</p></div>')
    body = ('<header class="page-head"><h1>Membership</h1><p>Gu is free to read. Members keep an always-on AI newsroom running '
            'and get Gu without ads.</p></header><p id="auth-msg" class="note" hidden></p>'
            f'<div class="plans">{"".join(cols)}</div>{faq}')
    write(ctx, "/membership/", shell(ctx, "/membership/", "Membership", body,
                                      desc="Support Gu Broadcasting Station and read without ads."))
    write(ctx, "/membership/thanks/", shell(ctx, "/membership/thanks/", "Welcome, member", (
        '<header class="page-head"><h1>Welcome, member</h1><p>Thank you for supporting Gu.</p></header><div class="prose">'
        '<p>Your payment went through. Your membership switches on within a minute; <a href="/account/">your account</a> '
        'shows it once it does. A receipt is on its way to your email from Stripe.</p>'
        '<p>Meanwhile: <a href="/live/">watch the latest edition</a>.</p></div>')), sitemap=False)


# ------------------------------------------------------------------ prose + machine files

def page_prose(ctx: Ctx) -> None:
    for path, title, desc, body in pages.all_pages(ctx):
        write(ctx, path, shell(ctx, path, title, f'<header class="page-head"><h1>{e(title)}</h1>'
                               f'<p>{e(desc)}</p></header><div class="prose">{body}</div>', desc=desc))
    body = ('<header class="page-head"><h1>Page not found</h1><p>That address doesn\'t match any page on Gu. It may have '
            'moved, or the link may be mistyped.</p></header><form class="stack-form" action="/search/" method="get">'
            '<label class="vh" for="q404">Search stories</label><input id="q404" name="q" type="search" placeholder="Search stories">'
            '<button class="btn solid">Search</button></form><p class="prose">Or go to the <a href="/">front page</a>, '
            'the <a href="/latest/">latest news</a> or the <a href="/sitemap/">site map</a>.</p>')
    write(ctx, "/404.html", shell(ctx, "/404.html", "Page not found", body), sitemap=False)


def page_sitemap_html(ctx: Ctx) -> None:
    groups = defaultdict(list)
    for p in sorted(set(ctx.written)):
        if p.startswith(("/story/", "/archive/2")):
            continue
        top = "/" + p.strip("/").split("/")[0] + "/" if p != "/" else "/"
        groups[top].append(p)
    items = "".join(f'<li><a href="{p}">{e(p)}</a></li>' for g in sorted(groups) for p in groups[g])
    write(ctx, "/sitemap/", shell(ctx, "/sitemap/", "Site map", '<header class="page-head"><h1>Site map</h1>'
                                  '<p>Every section and page on Gu. Stories are listed in the <a href="/archive/">archive</a>.</p></header>'
                                  f'<ul class="prose">{items}<li><a href="/sitemap/">/sitemap/</a></li></ul>'))


def rss(ctx: Ctx, arts: list[dict], title: str, path: str) -> str:
    items = "".join(
        f"<item><title>{e(a['title'])}</title><link>{ctx.cfg.site_url}{article_url(a)}</link>"
        f"<guid isPermaLink=\"true\">{ctx.cfg.site_url}{article_url(a)}</guid><pubDate>{formatdate(a['ts'])}</pubDate>"
        f"<category>{e(DESK_NAMES.get(a['desk'], ''))}</category><description>{e(a['script'])}</description></item>"
        for a in arts)
    name = ctx.cfg.site_name if title == ctx.cfg.site_name else f"{ctx.cfg.site_name}: {title}"
    return (f'<?xml version="1.0" encoding="UTF-8"?><rss version="2.0"><channel><title>{e(name)}</title>'
            f"<link>{ctx.cfg.site_url}{path}</link><description>{e(ctx.site['tagline'])}</description><language>en</language>"
            f"<lastBuildDate>{formatdate(time.time())}</lastBuildDate>{items}</channel></rss>")


def machine_files(ctx: Ctx) -> None:
    base = ctx.cfg.site_url
    write(ctx, "/feed.xml", rss(ctx, ctx.articles[:60], ctx.cfg.site_name, "/"), sitemap=False)
    urls = sorted(set(ctx.written))
    write(ctx, "/sitemap.xml", '<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
          + "".join(f"<url><loc>{base}{u}</loc></url>" for u in urls) + "</urlset>", sitemap=False)
    cutoff = time.time() - 48 * 3600
    news = [a for a in ctx.articles if a["ts"] >= cutoff][:1000]
    write(ctx, "/news-sitemap.xml",
          '<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" '
          'xmlns:news="http://www.google.com/schemas/sitemap-news/0.9">'
          + "".join(f"<url><loc>{base}{article_url(a)}</loc><news:news><news:publication><news:name>{e(ctx.cfg.site_name)}"
                    f"</news:name><news:language>en</news:language></news:publication><news:publication_date>{t_iso(a['ts'])}"
                    f"</news:publication_date><news:title>{e(a['title'])}</news:title></news:news></url>" for a in news)
          + "</urlset>", sitemap=False)
    write(ctx, "/robots.txt", f"User-agent: *\nAllow: /\nDisallow: /rundown.json\nDisallow: /social/\n"
          f"Sitemap: {base}/sitemap.xml\nSitemap: {base}/news-sitemap.xml\n", sitemap=False)
    write(ctx, "/manifest.webmanifest", json.dumps({"name": ctx.cfg.site_name, "short_name": "Gu", "start_url": "/",
          "display": "standalone", "background_color": "#f3ece0", "theme_color": "#f3ece0",
          "icons": [{"src": "/assets/favicon.svg", "sizes": "any", "type": "image/svg+xml"}]}), sitemap=False)
    if ctx.ads.ads_txt():
        write(ctx, "/ads.txt", ctx.ads.ads_txt() + "\n", sitemap=False)
    write(ctx, "/assets/gu.css", assets.CSS, sitemap=False)
    write(ctx, "/assets/gu.js", assets.JS, sitemap=False)
    write(ctx, "/assets/favicon.svg", assets.FAVICON, sitemap=False)


# ------------------------------------------------------------------ entry point

def _rows_from_rundown(ctx: Ctx, rundown: list[Segment], videos: dict, now: float) -> list[dict]:
    rows = []
    for i, s in enumerate(rundown):
        rows.append({"slug": s.slug, "ts": now - i, "story_ts": s.story.ts, "show_id": ctx.show["id"],
                     "desk": s.story.desk, "title": s.story.title, "standfirst": standfirst(s.script, s.story.title),
                     "script": s.script, "presenter": s.anchor_id or ctx.anchor()["name"],
                     "presenter_title": s.presenter_title, "sources": s.sources, "sponsor_read": s.sponsor_read,
                     "video": videos.get(s.slug), "risk": s.story.risk_score})
    return rows


def build_site(cfg: Settings, rundown: list[Segment], pulse: dict | None = None,
               videos: dict | None = None, show: dict | None = None,
               bookends: dict | None = None, extra: list[Segment] | None = None) -> Path:
    ctx = Ctx(cfg, show, pulse, bookends)
    out = ctx.out
    out.mkdir(parents=True, exist_ok=True)
    videos = dict(videos or {})
    vdir = out / "v"
    if vdir.is_dir():  # clips rendered by earlier / background studio passes
        for f in vdir.glob("*.mp4"):
            videos.setdefault(f.stem, f"/v/{f.name}")

    store = PublishedStore(cfg.data_dir / "published.db")
    now = time.time()
    store.upsert(_rows_from_rundown(ctx, rundown, videos, now))
    if extra:  # web-only desk briefs: published, never on air
        rows = _rows_from_rundown(ctx, extra, videos, now - len(rundown))
        for r in rows:
            r["show_id"] = None
        store.upsert(rows)
    current = {s.slug for s in rundown}
    ctx.articles = store.recent(ctx.site["archive_days"])
    for a in ctx.articles:
        a["video"] = a.get("video") or videos.get(a["slug"])
        a["_current"] = a["slug"] in current
    order = {s.slug: i for i, s in enumerate(rundown)}
    cur = sorted([a for a in ctx.articles if a["_current"]], key=lambda a: order[a["slug"]])
    ctx.articles = cur + [a for a in ctx.articles if not a["_current"]]
    ctx.articles[len(cur):] = sorted(ctx.articles[len(cur):], key=lambda a: -a["ts"])

    pdir = REPO / "assets" / "anchors"
    for tid in ctx.talent:
        src = pdir / f"{tid}.png"
        if src.is_file():
            dest = out / "img" / "people" / f"{tid}.png"
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(src, dest)
            ctx.portraits[tid] = f"/img/people/{tid}.png"

    for gone in ("about/sources",):     # pages retired since earlier builds (sources are confidential)
        shutil.rmtree(out / gone, ignore_errors=True)
    ctx.stock = images.publish(images.load_pool(cfg.data_dir), cfg.data_dir, out)

    page_home(ctx)
    page_sections(ctx)
    page_local(ctx)
    page_latest_live(ctx)
    for a in ctx.articles:
        page_story(ctx, a)
    page_video(ctx)
    page_markets(ctx)
    page_shows(ctx)
    page_people(ctx)
    page_archive(ctx)
    page_search(ctx)
    page_newsletter(ctx)
    page_account(ctx)
    page_prose(ctx)
    page_sitemap_html(ctx)
    machine_files(ctx)

    # hand-off for the studio renderer (not public; nginx denies it)
    bk = bookends or {}
    stories = [{"kind": "story", "slug": s.slug, "title": s.story.title, "desk": s.story.desk,
                "anchor": s.anchor_id, "presenter_title": s.presenter_title, "script": s.script,
                "sources": s.sources, "sponsor_read": s.sponsor_read} for s in rundown]
    seq = ([bk["breaking"]] if "breaking" in bk else []) + ([bk["open"]] if "open" in bk else []) + stories + \
          ([bk["close"]] if "close" in bk else [])
    (out / "rundown.json").write_text(json.dumps(seq, indent=1, ensure_ascii=False))
    return out
