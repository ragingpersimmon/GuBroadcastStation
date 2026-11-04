"""Static prose pages: about, standards, AI, corrections, sources, contact,
tips, advertise, sponsorship guidelines and the legal set.

Legal pages are starting templates written for a small Canadian operator
(config/site.json `jurisdiction`). They are not legal advice: have them
reviewed before launch (TASKS.md T31)."""
from __future__ import annotations

import html
import json
from pathlib import Path
from urllib.parse import urlparse

from gbs.editorial.scriptwriter import OUTLET_NAMES
from gbs.newsdesk.feeds import WORLD_FEEDS, outlet_of

e = html.escape
REPO = Path(__file__).resolve().parents[2]
UPDATED = "November 4, 2026"


def _mail(addr: str) -> str:
    return f'<a href="mailto:{e(addr)}">{e(addr)}</a>'


def _legal_flag() -> str:
    return (f'<p class="legal-flag">Last updated {UPDATED}. This page describes how Gu works today. '
            'If anything here changes, we will update this page and the date above.</p>')


def about(ctx):
    n = ctx.site
    return ("/about/", "About Gu", "An AI-presented news service that summarizes reporting from trusted outlets and "
            "credits every source.",
            f"""<p>Gu Broadcasting Station is a news service presented entirely by AI-generated anchors and reporters.
Around the clock, Gu reads the world's news from established outlets, picks the stories that matter, and
presents short, original summaries on screen and on this site. Every story links to the reporting it is
based on.</p>
<h2>What Gu is</h2>
<ul><li>A summary service. Gu does not send reporters into the field. Our stories rewrite and condense reporting
by the outlets credited on each page, and we link to their original coverage.</li>
<li>Presented by AI characters. Harold Yi, Tessa Vale, NOVA, Lena Moravec and the rest of our cast
are fictional, AI-generated presenters. None of them is a real person. <a href="/people/">Meet the cast</a>.</li>
<li>Always on. A new edition goes out about every 15 minutes, with flagship shows in the morning, evening and
at weekends. <a href="/shows/">See the schedule</a>.</li></ul>
<h2>How we decide what to cover</h2>
<p>Gu reads more than two dozen news feeds across world, politics, business, technology, science, entertainment and
sports. Stories covered by several outlets rank higher. Each edition is balanced across regions and topics so that one
story can't crowd out the rest of the world. Our <a href="/about/standards/">editorial standards</a> explain the rules
every script follows, and <a href="/about/ai/">How Gu uses AI</a> explains the technology.</p>
<h2>Who runs Gu</h2>
<p>Gu is operated by {e(n['operator'])}, based in {e(n['jurisdiction'])}, and was founded in {e(n['founded'])}.
Gu is funded by sponsors and advertising. Sponsors never choose or shape our stories; see our
<a href="/advertise/guidelines/">sponsorship guidelines</a>.</p>
<h2>Get in touch</h2>
<p>News tips: <a href="/tips/">send a tip</a>. Errors: <a href="/about/corrections/">request a correction</a>.
Everything else: <a href="/contact/">contact us</a>.</p>""")


def standards(ctx):
    return ("/about/standards/", "Editorial standards",
            "The rules every Gu script follows, whoever presents it.",
            """<p>Gu's newsroom is automated, but its rules are not optional. Every script, whether it is a story,
a show open, a breaking update or a sponsor message, is written under these standards. News director Margo Kessler's
line sums them up: we don't punch down; we punch through. Lead anchor Harold Yi's sign-on says the rest: we
follow the story for your better insight.</p>
<h2>Accuracy</h2>
<ul><li>We state only what our sources report. No invented quotes, figures, names, places or speculation.</li>
<li>When outlets disagree, we say so, or we wait.</li>
<li>Breaking updates are short and attributed, and they are marked as developing.</li></ul>
<h2>Attribution</h2>
<ul><li>Every story names its sources on air ("according to...") and links to them on the page.</li>
<li>We write in our own words. We never republish another outlet's article text.</li></ul>
<h2>Tone</h2>
<ul><li>Our presenters have personalities, and that shows in how they speak, never in the facts.</li>
<li>No jokes, puns or wordplay on stories about death, injury, violence, war, disasters, crime victims, illness or
anyone's identity. Serious stories get a straight read, whoever presents them.</li>
<li>We don't mock the people in our stories.</li></ul>
<h2>Independence</h2>
<ul><li>Sponsors and advertisers have no say over what we cover or how.</li>
<li>Every sponsor message is labelled, on air and on the page. See our <a href="/advertise/guidelines/">sponsorship
guidelines</a>.</li></ul>
<h2>Transparency about AI</h2>
<ul><li>Every on-air character is disclosed as AI-generated, in our footer, on every story and on their profile page.</li>
<li>We never use AI to create realistic images or video of real events or real people.</li>
<li>Illustrations are labelled as illustrations.</li></ul>
<h2>Corrections</h2>
<p>When we get something wrong, we fix it and say so. See our <a href="/about/corrections/">corrections policy</a>.</p>
<h2>Who does what in the newsroom</h2>
<table><thead><tr><th>Role</th><th>What it means in practice</th></tr></thead><tbody>
<tr><td><a href="/people/margo/">Margo Kessler</a>, News Director</td><td>These standards, applied to every script.</td></tr>
<tr><td><a href="/people/priya/">Priya Sati</a>, Executive Producer</td><td>Builds each edition: merges coverage of the same event, balances desks, keeps the open tight.</td></tr>
<tr><td><a href="/people/dex/">Dex Okafor</a>, Assignment Desk</td><td>Sends each story to the reporter who covers that beat.</td></tr>
<tr><td><a href="/people/arbi/">Arbi Ong</a>, Sponsorship Integration</td><td>Keeps sponsor reads labelled, accurate and separate from the news.</td></tr>
<tr><td><a href="/people/owen/">Owen Pike</a>, Video Editor</td><td>On-screen names, titles and the headline ticker.</td></tr>
<tr><td><a href="/people/mina/">Mina Cho</a>, Digital &amp; Social</td><td>Clips real news segments for social video; nothing else gets clipped.</td></tr>
<tr><td><a href="/people/kai/">Kai Love</a>, AI Anchor Operator</td><td>Pacing and delivery of the AI presenters.</td></tr>
</tbody></table>""")


def ai(ctx):
    return ("/about/ai/", "How Gu uses AI",
            "What is automated at Gu, what isn't, and where the facts come from.",
            """<p>Gu is an experiment in AI-presented news, and we think you should know exactly how it works.</p>
<h2>The facts come from journalists</h2>
<p>Gu reads news feeds from established outlets such as BBC News, The Guardian, NPR, CBC, Al Jazeera, DW and NHK.
<a href="/about/sources/">See the full list</a>. The facts in every Gu story come from that reporting, and every story
links to it.</p>
<h2>What AI does</h2>
<table><thead><tr><th>Step</th><th>What happens</th></tr></thead><tbody>
<tr><td>Selection</td><td>Software groups articles about the same event, ranks them by how widely they are covered and how
urgent they are, and balances each edition across regions and topics.</td></tr>
<tr><td>Writing</td><td>A language model running on our own hardware rewrites each story as a short spoken script, under
our <a href="/about/standards/">editorial standards</a>. If the model is unavailable, a plain summary of the source
headline is used instead.</td></tr>
<tr><td>Voice</td><td>An AI voice model gives each character a consistent synthetic voice. Voices are invented; we do not
clone real people.</td></tr>
<tr><td>Video</td><td>An AI video model animates each character's portrait to the script. The portraits are generated and
depict no real person.</td></tr>
</tbody></table>
<h2>What AI doesn't do</h2>
<ul><li>It doesn't report. Gu has no reporters in the field, and we never present AI output as eyewitness reporting.</li>
<li>It doesn't make images of real events or real people.</li>
<li>It doesn't decide what sponsors say. Sponsor copy is provided by the sponsor and labelled.</li></ul>
<h2>Known limits</h2>
<p>Summaries can lose nuance, and AI can make mistakes. That is why every story links to its sources, and why we
correct errors openly. If something looks wrong, <a href="/about/corrections/">tell us</a>.</p>""")


def corrections(ctx):
    path = REPO / "config" / "corrections.json"
    items = json.loads(path.read_text()).get("corrections", []) if path.exists() else []
    if items:
        log = "<ul>" + "".join(f'<li><strong>{e(c["date"])}</strong>: <a href="{e(c["url"])}">{e(c["title"])}</a>. '
                               f'{e(c["note"])}</li>' for c in items) + "</ul>"
    else:
        log = "<p>No corrections have been published yet.</p>"
    return ("/about/corrections/", "Corrections",
            "How to report an error, and every correction we have made.",
            f"""<p>We correct errors promptly and openly. If a Gu story misstates what its sources reported, or a source
itself has issued a correction, we fix the story and add a note explaining what changed.</p>
<h2>Report an error</h2>
<p>Email {_mail(ctx.emails['corrections'])} with the story link and what is wrong. A link to a source helps us check
quickly. We aim to review every report within one business day.</p>
<h2>What we change</h2>
<ul><li>Factual errors are corrected in the story with a dated note at the end.</li>
<li>Clips that contain an error are taken down and re-rendered or removed.</li>
<li>Typos and formatting fixes are made without a note.</li></ul>
<h2>Published corrections</h2>{log}""")


def sources(ctx):
    seen = {}
    for key, url in WORLD_FEEDS.items():
        o = outlet_of(key)
        name = OUTLET_NAMES.get(o, o)
        host = urlparse(url).hostname or ""
        home = "https://" + ".".join(host.split(".")[-2:]) if host.count(".") >= 1 else url
        overrides = {"BBC News": "https://www.bbc.com/news", "BBC Sport": "https://www.bbc.com/sport",
                     "CBC News": "https://www.cbc.ca/news", "CBC Sports": "https://www.cbc.ca/sports",
                     "NPR": "https://www.npr.org", "The Guardian": "https://www.theguardian.com",
                     "UN News": "https://news.un.org", "NHK": "https://www3.nhk.or.jp/nhkworld/",
                     "DW": "https://www.dw.com", "France 24": "https://www.france24.com/en/",
                     "Al Jazeera": "https://www.aljazeera.com", "The Korea Herald": "https://www.koreaherald.com",
                     "Ars Technica": "https://arstechnica.com", "NASA": "https://www.nasa.gov"}
        seen.setdefault(name, overrides.get(name, home))
    rows = "".join(f'<li><a href="{e(u)}" rel="noopener">{e(n)}</a></li>' for n, u in sorted(seen.items()))
    return ("/about/sources/", "Our sources",
            "The outlets whose reporting Gu summarizes and links to.",
            f"""<p>Every Gu story is based on reporting from the outlets below, and links to the original article.
We read their public news feeds, and we encourage you to read and support them.</p>
<ul>{rows}</ul>
<p>Local weather comes from <a href="https://open-meteo.com/" rel="noopener">Open-Meteo</a>. Traffic, where available,
comes from public road-event feeds such as <a href="https://www.drivebc.ca/" rel="noopener">DriveBC</a>. Our market
pulse is computed from business headlines.</p>
<p>Are you a publisher with a question about how we use your reporting? Email {_mail(ctx.emails['general'])}.</p>""")


def contact(ctx):
    m = ctx.emails
    return ("/contact/", "Contact Gu", "How to reach the right part of Gu.",
            f"""<table><tbody>
<tr><th>News tips</th><td>{_mail(m['tips'])} or <a href="/tips/">send a tip</a></td></tr>
<tr><th>Corrections</th><td>{_mail(m['corrections'])}, see <a href="/about/corrections/">corrections</a></td></tr>
<tr><th>Advertising &amp; sponsorship</th><td>{_mail(m['advertising'])}, see <a href="/advertise/">advertise</a></td></tr>
<tr><th>Privacy requests</th><td>{_mail(m['privacy'])}, see <a href="/privacy/">privacy policy</a></td></tr>
<tr><th>Publishers &amp; everything else</th><td>{_mail(m['general'])}</td></tr>
</tbody></table>
<p>We read every message. We usually reply within two business days.</p>""")


def tips(ctx):
    return ("/tips/", "Send a tip", "Know about a story the world's outlets are missing? Tell us.",
            f"""<p>Gu summarizes reporting from established outlets, so the best tips point us to coverage we have
missed: a story that matters to your community, a region we under-cover, or a source we should be reading.</p>
<p>Email {_mail(ctx.emails['tips'])}. Include links where you can.</p>
<h2>Protect yourself</h2>
<p>Email is not anonymous. If your tip is sensitive, consider contacting an established investigative outlet
that offers secure channels, such as SecureDrop. Gu cannot protect sources the way a field newsroom can.</p>""")


def advertise(ctx):
    return ("/advertise/", "Advertise with Gu",
            "Sponsor reads, pre-roll and display placements on an always-on news service.",
            f"""<p>Gu is on air all day, with flagship morning, evening and weekend shows and a short update every 15
minutes. Your message can sit alongside the news, clearly labelled, without ever shaping it.</p>
<h2>Formats</h2>
<table><thead><tr><th>Format</th><th>What you get</th></tr></thead><tbody>
<tr><td>On-air sponsor read</td><td>Read by the presenter in a labelled "Sponsored by" slot, roughly one per four
stories. Your copy, your claims, read word for word.</td></tr>
<tr><td>Show sponsorship</td><td>Presenting sponsor of Gu Morning, Gu Evening News or Gu Weekend, with mentions in the
open and close.</td></tr>
<tr><td>Video pre-roll</td><td>Your video before anchor clips, labelled "Sponsored".</td></tr>
<tr><td>Display</td><td>Leaderboard, in-feed and sidebar placements across the site, labelled "Sponsored".</td></tr>
<tr><td>Newsletter</td><td>One sponsor slot in The Gu Briefing.</td></tr>
</tbody></table>
<h2>Audience and rates</h2>
<p>Ask for our current media kit with traffic, audience and rates: {_mail(ctx.emails['advertising'])}.</p>
<h2>The rules</h2>
<p>Sponsors never influence coverage, and every placement is labelled. Read the
<a href="/advertise/guidelines/">sponsorship guidelines</a> before you book.</p>""")


def guidelines(ctx):
    return ("/advertise/guidelines/", "Sponsorship guidelines",
            "How sponsor messages work at Gu, and what we won't run.",
            """<h2>Separation</h2>
<ul><li>Sponsors have no input into which stories we cover or how.</li>
<li>Sponsor reads never run inside a story about the sponsor or its competitors.</li>
<li>No sponsor read runs next to coverage of a tragedy.</li></ul>
<h2>Labelling</h2>
<ul><li>Every on-air read starts with "Sponsored by" and the sponsor's name.</li>
<li>Every web placement is labelled "Sponsored", and every sponsored link is marked as sponsored.</li></ul>
<h2>Your copy</h2>
<ul><li>Our presenters deliver your copy in their own voice, but every claim, price, offer and web address stays word
for word.</li>
<li>You are responsible for your claims being accurate and lawful.</li></ul>
<h2>What we don't accept</h2>
<ul><li>Political or issue advertising.</li>
<li>Gambling, tobacco, vaping, cannabis, weapons and adult products.</li>
<li>Get-rich-quick schemes, unregistered financial products and miracle health claims.</li>
<li>Anything that imitates Gu's news presentation or uses our characters to endorse a product outside a labelled
slot.</li></ul>""")


def privacy(ctx):
    s, m = ctx.site, ctx.emails
    return ("/privacy/", "Privacy policy", "What we collect, why, and your choices.",
            f"""{_legal_flag()}
<p>This policy covers the Gu website, newsletter and video. {e(s['operator'])} ("we") operates Gu from
{e(s['jurisdiction'])} and handles personal information in line with Canada's Personal Information Protection and
Electronic Documents Act (PIPEDA), Canada's Anti-Spam Legislation (CASL) for our emails, and applicable provincial law.</p>
<h2>What we collect</h2>
<ul><li><strong>Reading the site:</strong> standard server logs (IP address, browser, pages requested, time) kept for
security and to count traffic. We keep raw logs for no more than 30 days.</li>
<li><strong>Newsletter:</strong> your email address and when you confirmed it. We use a confirm-by-email (double opt-in) sign-up, so you only get The Gu Briefing after you ask for it. It's sent through our email provider, Kit (kit.com), which also records opens and clicks so we can see which stories readers want. You can unsubscribe from any issue in one click.</li>
<li><strong>Messages you send us:</strong> your email and what you write, used to reply.</li>
<li><strong>Advertising:</strong> if ad-network ads are switched on, our partner may use cookies. See the
<a href="/cookies/">cookie policy</a>.</li></ul>
<h2>What we don't do</h2>
<ul><li>We don't sell personal information.</li>
<li>We don't require an account to read Gu.</li></ul>
<h2>Who we share with</h2>
<p>Service providers that run parts of Gu for us: hosting, email delivery and, if enabled, an ad network. They may
process data outside Canada.</p>
<h2>Your choices and rights</h2>
<p>You can unsubscribe from any newsletter in one click. You can ask to see, correct or delete the personal information
we hold about you, or withdraw consent, by emailing {_mail(m['privacy'])}. We respond within 30 days. If you are not
satisfied, you can complain to the Office of the Privacy Commissioner of Canada.</p>
<h2>Children</h2><p>Gu is a general news service and is not directed at children under 13.</p>""")


def terms(ctx):
    s = ctx.site
    return ("/terms/", "Terms of use", "The terms for using the Gu website and video.",
            f"""{_legal_flag()}
<h2>Using Gu</h2>
<p>You may read, watch and share links to Gu for personal, non-commercial use. Please don't scrape, republish or
redistribute Gu stories or video in bulk without written permission.</p>
<h2>AI-presented content</h2>
<p>Gu stories are AI-written summaries of third-party reporting, presented by AI-generated characters. They may contain
errors. Check the linked sources before relying on any story, and don't treat Gu as professional, financial, medical or
legal advice. The market pulse is a reading of the news, not a recommendation to buy or sell anything.</p>
<h2>Third-party content</h2>
<p>Linked articles belong to their publishers and are governed by their terms.</p>
<h2>Our content</h2>
<p>Gu's scripts, characters, video, design and name belong to {e(s['operator'])}. Our characters may not be used to
endorse anything without permission.</p>
<h2>Liability</h2>
<p>Gu is provided "as is". To the extent the law allows, we are not liable for losses arising from use of Gu.</p>
<h2>Governing law</h2><p>These terms are governed by the laws of {e(s['jurisdiction'])}.</p>
<h2>Contact</h2><p>{_mail(ctx.emails['general'])}</p>""")


def cookies(ctx):
    on = ctx.ads.cfg.get("ad_network", {}).get("enabled")
    status = ("Ad-network advertising is currently switched on. You will be asked for your choice the first time you visit."
              if on else "Gu currently sets no advertising or tracking cookies.")
    return ("/cookies/", "Cookie policy", "Which cookies Gu uses and how to control them.",
            f"""{_legal_flag()}
<p><strong>{e(status)}</strong></p>
<h2>What we store in your browser</h2>
<table><thead><tr><th>Item</th><th>Purpose</th><th>Kept for</th></tr></thead><tbody>
<tr><td>gu-consent (local storage)</td><td>Remembers your cookie choice</td><td>Until you clear it</td></tr>
<tr><td>Ad-network cookies (only when advertising is on and you accept)</td><td>Showing and measuring ads</td><td>Set by
the ad partner; see its policy</td></tr>
</tbody></table>
<h2>Your choices</h2>
<p>Choose "Essential only" in the cookie notice, or clear site data in your browser settings to be asked again.</p>""")


def accessibility(ctx):
    return ("/accessibility/", "Accessibility", "Our commitment to making Gu usable by everyone.",
            f"""<p>We want everyone to be able to read and watch Gu.</p>
<h2>What we do</h2>
<ul><li>Every video has the full script printed beneath it on the story page.</li>
<li>Pages work with keyboard navigation and screen readers, and show a visible focus outline.</li>
<li>Text meets WCAG 2.1 AA contrast in light and dark mode, and the site respects reduced-motion settings.</li>
<li>Pages reflow on small screens and when zoomed to 200%.</li></ul>
<h2>Known gaps</h2>
<ul><li>Video clips don't yet have burned-in captions. The script on each page is the full transcript.</li></ul>
<h2>Tell us</h2>
<p>If something on Gu doesn't work for you, email {_mail(ctx.emails['general'])} and we'll fix it.</p>""")


def all_pages(ctx):
    return [f(ctx) for f in (about, standards, ai, corrections, sources, contact, tips, advertise, guidelines,
                             privacy, terms, cookies, accessibility)]
