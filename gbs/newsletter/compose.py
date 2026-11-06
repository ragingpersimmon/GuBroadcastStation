"""The Gu Briefing: one weekday-morning email built from what Gu published
in the last 24 hours.

Issue shape (same every day, so readers learn it):
  Harold Yi's signature open + "Today we have ..." tease
  Top stories (3): headline, one-line standfirst, source credit
  Around the world / Politics / Business / Tech & science / Culture & sports:
      one or two headlines each
  Market pulse + local weather (when available)
  Sponsor (labelled), then AI disclosure and why you're getting this.
The provider (Kit) adds its own unsubscribe link and mailing address."""
from __future__ import annotations

import html
import json
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from urllib.parse import urlencode

from gbs.config import Settings
from gbs.editorial.scriptwriter import outlet_name
from gbs.editorial.standards import is_sensitive
from gbs.site.data import PublishedStore, article_url, section_of

e = html.escape
REPO = Path(__file__).resolve().parents[2]

GROUPS = [("Around the world", {"world"}), ("Politics", {"politics"}), ("Business & money", {"business"}),
          ("Tech & science", {"tech", "science"}), ("Culture & sports", {"entertainment", "sports"})]

# email-safe palette (matches the site)
INK, SLATE, RED, GOLD, RULE, WASH = "#1b1f27", "#5b6372", "#c8102e", "#f2c14e", "#e3e5ea", "#f5f6f8"
SERIF = "Georgia,'Times New Roman',serif"
SANS = "'Helvetica Neue',Arial,sans-serif"


@dataclass
class Issue:
    date: str
    subject: str
    preheader: str
    html: str
    text: str
    slugs: list = field(default_factory=list)

    def to_json(self) -> str:
        return json.dumps(self.__dict__, ensure_ascii=False)


def _rank(a: dict) -> tuple:
    return (len(a.get("sources") or []), a.get("risk") or 0.0, a["ts"])


def pick(articles: list[dict], top_n: int = 3, per_group: int = 2) -> tuple[list[dict], list[tuple[str, list[dict]]]]:
    """Top stories (one per section first, so the top isn't all one desk), then grouped headlines."""
    pool = [a for a in articles if a["desk"] not in ("weather", "traffic")]
    pool.sort(key=_rank, reverse=True)
    top, seen_sec = [], set()
    for a in pool:
        sid = section_of(a["desk"])["id"]
        if sid not in seen_sec:
            top.append(a)
            seen_sec.add(sid)
        if len(top) == top_n:
            break
    used = {a["slug"] for a in top}
    groups = []
    for name, secs in GROUPS:
        items = [a for a in pool if a["slug"] not in used and section_of(a["desk"])["id"] in secs][:per_group]
        used |= {a["slug"] for a in items}
        if items:
            groups.append((name, items))
    return top, groups


def _link(cfg: Settings, path: str, campaign: str) -> str:
    q = urlencode({"utm_source": "gu-briefing", "utm_medium": "email", "utm_campaign": campaign})
    return f"{cfg.site_url}{path}?{q}"


def _credits(a: dict) -> str:
    return ", ".join(dict.fromkeys(outlet_name(s["source"]) for s in a.get("sources") or []))


def _opening(cfg: Settings, top: list[dict]) -> str:
    """Harold Yi's signature open, morning daypart, no weekly variant in email."""
    from gbs.anchors.roster import by_id, load_newsroom
    nr = load_newsroom()
    harold = by_id(nr, "harold")
    sig = harold["signature"]
    serious = any(is_sensitive(a["title"], a.get("standfirst") or "") for a in top)
    greeting = (sig["serious_greeting"] if serious else sig["greeting"])["morning"]
    heads = [a["title"].rstrip(".") for a in top]
    tease = "; ".join(heads[:-1]) + ("; and " if len(heads) > 1 else "") + heads[-1] if heads else "the latest from around the world"
    return f"{greeting} {sig['line']} {sig['lead_in']['morning']}: {tease}."


def build_issue(cfg: Settings, articles: list[dict], now: datetime, pulse: dict | None = None,
                weather: dict | None = None, sponsor: dict | None = None, name: str = "The Gu Briefing") -> Issue | None:
    top, groups = pick(articles)
    if len(top) < 2:
        return None
    date = now.strftime("%Y-%m-%d")
    camp = f"briefing-{date}"
    web = _link(cfg, f"/newsletter/issues/{date}/", camp)
    nice = now.strftime("%A, %B %d, %Y").replace(" 0", " ")
    opening = _opening(cfg, top)
    subject = f"{top[0]['title']}"[:90]
    preheader = " · ".join(a["title"] for a in top[1:3])[:140] if len(top) > 1 else nice

    # ---------------- HTML (table layout, inline styles: works in Gmail/Outlook/Apple Mail)
    def story_block(a: dict, big: bool) -> str:
        url = _link(cfg, article_url(a), camp)
        size = "22px" if big else "17px"
        sf = (f'<p style="margin:6px 0 0;font:16px/1.5 {SERIF};color:{SLATE}">{e(a["standfirst"])}</p>'
              if big and a.get("standfirst") else "")
        cred = _credits(a)
        src = (f'<p style="margin:6px 0 0;font:13px/1.4 {SANS};color:{SLATE}">Sources: {e(cred)}'
               + (" · <b style='color:" + INK + "'>Watch</b>" if a.get("video") else "") + "</p>") if cred else ""
        return (f'<tr><td style="padding:14px 0;border-bottom:1px solid {RULE}">'
                f'<a href="{e(url)}" style="font:bold {size}/1.25 {SERIF};color:{INK};text-decoration:none">{e(a["title"])}</a>'
                f'{sf}{src}</td></tr>')

    rows = [story_block(a, True) for a in top]
    sec_html = []
    for gname, items in groups:
        sec_html.append(f'<tr><td style="padding:22px 0 4px;font:bold 15px/1 {SANS};color:{RED}">{e(gname)}</td></tr>')
        sec_html += [story_block(a, False) for a in items]
    extras = []
    if pulse and pulse.get("regime"):
        extras.append(f'Market pulse: <a href="{e(_link(cfg, "/markets/", camp))}" style="color:{INK}"><b>'
                      f'{e(str(pulse["regime"]).capitalize())}</b></a>')
    if weather:
        extras.append(f'Weather: <a href="{e(_link(cfg, article_url(weather), camp))}" style="color:{INK}">{e(weather["title"])}</a>')
    extra_html = (f'<tr><td style="padding:16px;background:{WASH};font:14px/1.6 {SANS};color:{INK}">'
                  + "<br>".join(extras) + "</td></tr>") if extras else ""
    spons = ""
    if sponsor:
        w = sponsor.get("web") or {}
        surl = w.get("url", "/advertise/")
        surl = surl if surl.startswith("http") else _link(cfg, surl, camp)
        spons = (f'<tr><td style="padding:16px;border:1px solid {GOLD};font:15px/1.5 {SANS};color:{INK}">'
                 f'<span style="font:bold 12px/1 {SANS};color:{SLATE}">Sponsored</span><br>'
                 f'<a href="{e(surl)}" style="color:{INK};font-weight:bold">{e(w.get("headline", sponsor["name"]))}</a><br>'
                 f'{e(w.get("body", ""))}</td></tr>')
    body = f"""<div style="display:none;max-height:0;overflow:hidden">{e(preheader)}</div>
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#ffffff">
<tr><td align="center" style="padding:0 12px">
<table role="presentation" width="600" cellpadding="0" cellspacing="0" style="max-width:600px;width:100%">
<tr><td style="padding:20px 0 12px;border-bottom:3px solid {INK}">
 <span style="font:900 34px/1 {SANS};color:{RED};letter-spacing:-1px">Gu</span>
 <span style="font:bold 15px/1 {SANS};color:{INK}">&nbsp;{e(name)}</span><br>
 <span style="font:13px/2 {SANS};color:{SLATE}">{e(nice)} · <a href="{e(web)}" style="color:{SLATE}">Read on the web</a></span>
</td></tr>
<tr><td style="padding:18px 0 6px;font:17px/1.6 {SERIF};color:{INK};border-left:5px solid {GOLD};padding-left:14px">{e(opening)}</td></tr>
<tr><td style="padding:18px 0 4px;font:bold 15px/1 {SANS};color:{RED}">Top stories</td></tr>
{"".join(rows)}
{"".join(sec_html)}
<tr><td style="height:20px"></td></tr>
{extra_html}
<tr><td style="height:16px"></td></tr>
{spons}
<tr><td style="padding:22px 0 8px;font:13px/1.6 {SANS};color:{SLATE}">
 Gu's anchors and reporters are AI-generated characters. Every story is an original summary of reporting by the outlets
 credited above; follow the links for their full coverage.
 <a href="{e(_link(cfg, "/about/ai/", camp))}" style="color:{SLATE}">How Gu uses AI</a> ·
 <a href="{e(_link(cfg, "/about/corrections/", camp))}" style="color:{SLATE}">Corrections</a><br><br>
 You're getting this because you subscribed to {e(name)} at {e(cfg.site_url.replace("https://", ""))} and confirmed your address.
 Reply to this email to reach the newsroom.
</td></tr>
</table></td></tr></table>"""

    # ---------------- plain text
    t = [f"{name} | {nice}", f"Read on the web: {web}", "", opening, "", "TOP STORIES", ""]
    for a in top:
        t += [a["title"], *([a["standfirst"]] if a.get("standfirst") else []),
              f"Sources: {_credits(a)}", _link(cfg, article_url(a), camp), ""]
    for gname, items in groups:
        t += [gname.upper(), ""]
        for a in items:
            t += [a["title"], _link(cfg, article_url(a), camp), ""]
    if pulse and pulse.get("regime"):
        t.append(f"Market pulse: {str(pulse['regime']).capitalize()}")
    if weather:
        t.append(f"Weather: {weather['title']}")
    if sponsor:
        w = sponsor.get("web") or {}
        t += ["", f"SPONSORED: {w.get('headline', sponsor['name'])}. {w.get('body', '')}"]
    t += ["", "Gu's anchors and reporters are AI-generated characters. Every story is an original summary of reporting "
          "by the outlets credited above.", f"How Gu uses AI: {cfg.site_url}/about/ai/"]
    slugs = [a["slug"] for a in top] + [a["slug"] for _, items in groups for a in items]
    return Issue(date=date, subject=subject, preheader=preheader, html=body, text="\n".join(t), slugs=slugs)


def gather(cfg: Settings, now: datetime, hours: float = 24) -> tuple[list[dict], dict | None]:
    """Stories published in the window, plus the latest weather story."""
    store = PublishedStore(cfg.data_dir / "published.db")
    cutoff = now.timestamp() - hours * 3600
    arts = [a for a in store.recent(2) if a["ts"] >= cutoff]
    weather = next((a for a in arts if a["desk"] == "weather"), None)
    return arts, weather


def issue_dir(cfg: Settings) -> Path:
    return cfg.data_dir / "newsletter" / "issues"


def save_issue(cfg: Settings, issue: Issue) -> Path:
    d = issue_dir(cfg)
    d.mkdir(parents=True, exist_ok=True)
    p = d / f"{issue.date}.json"
    p.write_text(issue.to_json(), encoding="utf-8")
    return p


def load_issues(cfg: Settings) -> list[dict]:
    d = issue_dir(cfg)
    if not d.is_dir():
        return []
    out = []
    for p in sorted(d.glob("*.json"), reverse=True):
        try:
            out.append(json.loads(p.read_text(encoding="utf-8")))
        except Exception:
            continue
    return out
