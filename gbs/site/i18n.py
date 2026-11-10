"""Site translation: every English page is re-published under /<lang>/ in each
enabled language (config/languages.json).

How a page is translated
  1. The finished English HTML is split into translation units: each run of text
     plus inline markup inside a block element ("See our <a>guidelines</a>.").
     Inline tags become markers (⟦1⟧...⟦/1⟧) so the translator sees whole sentences
     but can't break the markup. translate="no" elements (names, outlets, the Gu
     brand) and <time> become atomic markers and are never translated.
  2. Each unit resolves from, in order: the hand-written catalog
     (config/i18n/<code>.json, menus and labels), the translation cache
     (data/translations.db), or the LLM, batched and under a per-run budget.
  3. Units with no translation yet stay in English, marked lang="en", and fill in on
     a later build. Internal links get the /<lang> prefix; html lang/dir, canonical,
     the language switcher and an "AI-translated" notice are set per language.
Pages whose English bytes haven't changed and were fully translated last time are
skipped, so a 15-minute rebuild only touches what changed.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import sqlite3
import urllib.request
from pathlib import Path

log = logging.getLogger("gbs.i18n")
REPO = Path(__file__).resolve().parents[2]
LANG_CONF = REPO / "config" / "languages.json"
CATALOG_DIR = REPO / "config" / "i18n"

# strings gu.js needs, English defaults; catalogs override under "js"
JS_STRINGS = {
    "copied": "Link copied",
    "search_hint": "Type a word or a name to search the last 30 days of stories.",
    "search_count": "{n} stories match \"{q}\"",
    "search_none": "No stories match \"{q}\". Try fewer words or check the spelling.",
    "with": "with",
}
NOTICE = "This page was translated from English by AI."
NOTICE_LINK = "Read the original in English"
LEGAL_NOTE = "If this translation differs from the English version, the English version applies."
VIDEO_NOTE = "This video is in English."
LEGAL_PATHS = ("/privacy/", "/terms/", "/cookies/")
NO_PREFIX = ("/assets/", "/v/", "/img/", "/social/")
NO_PREFIX_EXT = (".xml", ".json", ".webmanifest", ".mp4", ".png", ".svg", ".jpg", ".webp")

BLOCK = {"html", "head", "body", "main", "header", "footer", "nav", "section", "article", "aside", "div", "p",
         "ul", "ol", "li", "h1", "h2", "h3", "h4", "h5", "h6", "table", "thead", "tbody", "tfoot", "tr", "td", "th",
         "blockquote", "figure", "figcaption", "form", "details", "summary", "dl", "dt", "dd", "fieldset", "legend",
         "title", "button", "label", "select", "option"}
SKIP = {"script", "style", "code", "pre", "svg", "video", "audio", "iframe", "textarea", "template", "noscript", "time",
        "meta", "link", "input"}
VOID = {"br", "img", "wbr", "hr", "input", "source"}
ATTRS = ("alt", "title", "placeholder", "aria-label")
# brand and show names stay as they are in every language
NO_TRANSLATE = {"Gu Broadcasting Station", "Gu", "Gu Morning", "Gu Evening News", "Gu Weekend", "Gu-cast",
                "The Gu Briefing", "Facebook", "LinkedIn", "Reddit"}
LETTER = re.compile(r"[^\W\d_]", re.U)
MARK = re.compile(r"⟦(/?)(\d+)⟧")


# ------------------------------------------------------------------ config

def all_languages() -> list[dict]:
    return json.loads(LANG_CONF.read_text(encoding="utf-8"))["languages"]


def enabled_languages() -> list[dict]:
    conf = json.loads(LANG_CONF.read_text(encoding="utf-8"))
    if os.getenv("GBS_I18N", "1") == "0":   # translation off: English only, no switcher
        return [next(L for L in conf["languages"] if L["code"] == "en")]
    want = os.getenv("GBS_LANGUAGES", "").strip()
    codes = [c.strip() for c in want.split(",") if c.strip()] if want else conf["enabled"]
    by = {L["code"]: L for L in conf["languages"]}
    out = [by["en"]] + [by[c] for c in codes if c in by and c != "en"]
    return out


def lang_prefix(L: dict) -> str:
    return f"/{L['path']}" if L.get("path") else ""


def catalog(code: str) -> dict:
    p = CATALOG_DIR / f"{code}.json"
    if not p.exists():
        return {"strings": {}, "js": {}, "patterns": []}
    d = json.loads(p.read_text(encoding="utf-8"))
    pats = [(re.compile(k), v) for k, v in (d.get("patterns") or {}).items()]
    return {"strings": d.get("strings", {}), "js": d.get("js", {}), "patterns": pats}


# ------------------------------------------------------------------ cache

class Cache:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(str(path))
        self.db.execute("CREATE TABLE IF NOT EXISTS t (lang TEXT, h TEXT, src TEXT, out TEXT, PRIMARY KEY(lang, h))")

    @staticmethod
    def key(src: str) -> str:
        return hashlib.sha256(src.encode("utf-8")).hexdigest()[:32]

    def get_many(self, lang: str, srcs: set[str]) -> dict[str, str]:
        out = {}
        keys = {self.key(s): s for s in srcs}
        ks = list(keys)
        for i in range(0, len(ks), 500):
            chunk = ks[i:i + 500]
            q = f"SELECT h, out FROM t WHERE lang=? AND h IN ({','.join('?' * len(chunk))})"
            for h, o in self.db.execute(q, [lang, *chunk]):
                out[keys[h]] = o
        return out

    def put_many(self, lang: str, pairs: dict[str, str]) -> None:
        self.db.executemany("INSERT OR REPLACE INTO t VALUES (?,?,?,?)",
                            [(lang, self.key(s), s, o) for s, o in pairs.items()])
        self.db.commit()


# ------------------------------------------------------------------ units

def _is_block(node) -> bool:
    return getattr(node, "name", None) in BLOCK


def _atomic(tag) -> bool:
    return tag.name in SKIP or tag.name in VOID or tag.get("translate") == "no"


def _encode(nodes, slots: dict) -> str:
    from bs4 import Comment, NavigableString, Tag
    out = []
    for n in nodes:
        if isinstance(n, Comment):
            continue
        if isinstance(n, NavigableString):
            out.append(str(n))
        elif isinstance(n, Tag):
            i = len(slots) + 1
            if _atomic(n):
                slots[i] = ("atom", n)
                out.append(f"⟦{i}⟧")
            else:
                slots[i] = ("tag", n)
                out.append(f"⟦{i}⟧{_encode(list(n.children), slots)}⟦/{i}⟧")
    return "".join(out)


def _has_text(core: str) -> bool:
    return bool(LETTER.search(MARK.sub(" ", core)))


class Unit:
    __slots__ = ("nodes", "slots", "core", "lead", "trail")

    def __init__(self, nodes):
        self.nodes, self.slots = nodes, {}
        raw = _encode(nodes, self.slots)
        stripped = raw.strip()
        self.lead = raw[:len(raw) - len(raw.lstrip())]
        self.trail = raw[len(raw.rstrip()):]
        self.core = re.sub(r"\s+", " ", stripped)


def collect_units(soup) -> list[Unit]:
    units: list[Unit] = []

    def walk(el):
        run = []

        def flush():
            if not run:
                return
            from bs4 import NavigableString
            bare_text = any(isinstance(n, NavigableString) and n.strip() for n in run)
            if bare_text:  # a sentence with inline markup: one unit
                u = Unit(list(run))
                if _has_text(u.core):
                    units.append(u)
            else:          # sibling items (menu links, buttons, meta): one unit per item
                for n in run:
                    if getattr(n, "name", None) and not _atomic(n):
                        walk(n)
            run.clear()
        for ch in list(el.children):
            if _is_block(ch):
                flush()
                if ch.get("translate") != "no":
                    walk(ch)
            else:
                run.append(ch)  # text and inline tags (SKIP/translate=no tags become atomic markers)
        flush()
    root = soup.find("html") or soup
    walk(root)
    return units


def collect_attrs(soup) -> list[tuple]:
    out = []
    for tag in soup.find_all(True):
        if tag.get("translate") == "no" or tag.find_parent(attrs={"translate": "no"}):
            continue
        for a in ATTRS:
            v = tag.get(a)
            if isinstance(v, str) and _has_text(v):
                out.append((tag, a, v.strip()))
        if tag.name == "meta" and (tag.get("name") == "description" or
                                   tag.get("property") in ("og:title", "og:description")):
            v = tag.get("content", "")
            if _has_text(v):
                out.append((tag, "content", v.strip()))
    return out


def markers_ok(src: str, dst: str) -> bool:
    return sorted(MARK.findall(src)) == sorted(MARK.findall(dst))


def decode(unit: Unit, translated: str, soup):
    """Rebuild nodes from a translated core, cloning each inline tag's shell."""
    from bs4 import NavigableString
    out, stack = [], []
    pos = 0

    def emit(node):
        (stack[-1].append(node) if stack else out.append(node))

    for m in MARK.finditer(translated):
        if m.start() > pos:
            emit(NavigableString(translated[pos:m.start()]))
        closing, idx = m.group(1) == "/", int(m.group(2))
        kind, orig = unit.slots[idx]
        if kind == "atom":
            emit(_clone(orig, soup, deep=True))
        elif not closing:
            shell = _clone(orig, soup, deep=False)
            stack.append(shell)
        else:
            shell = stack.pop()
            emit(shell)
        pos = m.end()
    if pos < len(translated):
        emit(NavigableString(translated[pos:]))
    return out


def _clone(tag, soup, deep: bool):
    from bs4 import BeautifulSoup
    if deep:
        return BeautifulSoup(str(tag), "html.parser").contents[0]
    new = soup.new_tag(tag.name)
    for k, v in tag.attrs.items():
        new[k] = v
    return new


def replace_unit(unit: Unit, new_nodes, soup) -> None:
    from bs4 import NavigableString
    first = unit.nodes[0]
    seq = ([NavigableString(unit.lead)] if unit.lead else []) + new_nodes + \
          ([NavigableString(unit.trail)] if unit.trail else [])
    for n in seq:
        first.insert_before(n)
    for n in unit.nodes:
        n.extract()


def mark_english(unit: Unit, soup) -> None:
    """Untranslated text stays English, labelled for screen readers and search."""
    from bs4 import NavigableString
    parent = unit.nodes[0].parent
    if parent is not None and all(n.parent is parent for n in unit.nodes) and \
            len([c for c in parent.children if not (isinstance(c, NavigableString) and not c.strip())]) == \
            len([n for n in unit.nodes if not (isinstance(n, NavigableString) and not n.strip())]):
        parent["lang"] = "en"
        return
    span = soup.new_tag("span", lang="en")
    unit.nodes[0].insert_before(span)
    for n in unit.nodes:
        span.append(n.extract())


# ------------------------------------------------------------------ resolve

class Resolver:
    """catalog -> cache -> (pending for the LLM)."""

    def __init__(self, L: dict, cache: Cache):
        self.L, self.cache = L, cache
        cat = catalog(L["code"])
        self.cat, self.js, self.pats = cat["strings"], cat["js"], cat["patterns"]
        self.known: dict[str, str] = {}

    def lookup_catalog(self, core: str) -> str | None:
        if core in self.cat:
            return self.cat[core]
        for rx, tpl in self.pats:   # values that change: "Feels like 6°", "Fri Nov 6", "3 active incidents"
            m = rx.fullmatch(core)
            if m:
                out = tpl
                for k, v in m.groupdict().items():
                    out = out.replace("{" + k + "}", self.cat.get(v, v) if v else "")
                return out
        for sep in (" | ", ": "):  # "Weather | Gu Broadcasting Station", "Watch: Gu Evening News"
            if sep in core:
                head, tail = core.rsplit(sep, 1) if sep == " | " else core.split(sep, 1)
                th = self.cat.get(head) if head in self.cat else (head if head in NO_TRANSLATE else None)
                tt = self.cat.get(tail) if tail in self.cat else (tail if tail in NO_TRANSLATE else None)
                if th is not None and tt is not None:
                    return f"{th}{sep}{tt}"
        if "⟦" in core:  # every text segment is a catalog phrase -> translate segment-wise
            pieces = MARK.split(core)[::3]  # split() yields text, slash, index, text, ...
            texts = [p.strip() for p in pieces if _has_text(p)]
            if texts and all(t in self.cat for t in texts):
                res, last = [], 0
                for m in MARK.finditer(core):
                    res.append(_swap(core[last:m.start()], self.cat))
                    res.append(m.group(0))
                    last = m.end()
                res.append(_swap(core[last:], self.cat))
                return "".join(res)
        return None

    def prime(self, cores: set[str]) -> set[str]:
        """Fill self.known from catalog + cache; return cores still missing."""
        missing = set()
        need_cache = set()
        for c in cores:
            if c in self.known:
                continue
            hit = c if c in NO_TRANSLATE else self.lookup_catalog(c)
            if hit is not None:
                self.known[c] = hit
            else:
                need_cache.add(c)
        if need_cache:
            self.known.update(self.cache.get_many(self.L["code"], need_cache))
            missing = {c for c in need_cache if c not in self.known}
        return missing

    def t(self, s: str) -> str:
        """Plain-string translation (notices, JSON data); English if unknown."""
        return self.known.get(s) or self.cat.get(s) or s


def _swap(text: str, cat: dict) -> str:
    s = text.strip()
    if not _has_text(s) or s not in cat:
        return text
    lead = text[:len(text) - len(text.lstrip())]
    trail = text[len(text.rstrip()):]
    return lead + cat[s] + trail


# ------------------------------------------------------------------ LLM

def llm_translate(cfg, L: dict, cores: list[str], budget_chars: int) -> dict[str, str]:
    """Translate in batches through the OpenAI-compatible endpoint. Returns validated pairs."""
    if not cfg.llm_base_url or not cores:
        return {}
    done, spent, batch, size = {}, 0, [], 0
    order = sorted(cores, key=len)  # short chrome-like strings first: most reuse per char

    def run(items):
        system = (f"You are a professional news translator. Translate each English string in the JSON array into "
                  f"{L['llm']}. Rules: keep meaning exact, add nothing, omit nothing; keep every marker like ⟦3⟧ and "
                  "⟦/3⟧ exactly as is, in the right place; keep names of people, shows and the brand 'Gu' "
                  "unchanged; translate 'Confirmed' as a verified-news label; keep numbers and URLs. Reply with only a JSON array of the translated strings, same "
                  "length and order.")
        from gbs.editorial.scriptwriter import resolve_model
        body = {"model": resolve_model(cfg), "temperature": 0.2,
                "messages": [{"role": "system", "content": system},
                             {"role": "user", "content": json.dumps(items, ensure_ascii=False)}]}
        headers = {"Content-Type": "application/json"}
        if cfg.llm_api_key:
            headers["Authorization"] = f"Bearer {cfg.llm_api_key}"
        req = urllib.request.Request(f"{cfg.llm_base_url}/chat/completions", data=json.dumps(body).encode(),
                                     headers=headers)
        with urllib.request.urlopen(req, timeout=int(os.getenv("GBS_TRANSLATE_TIMEOUT", "180"))) as r:
            text = json.loads(r.read())["choices"][0]["message"]["content"]
        text = re.sub(r"<think>.*?</think>", "", text, flags=re.S).strip()
        text = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.M).strip()
        arr = json.loads(text[text.find("["): text.rfind("]") + 1])
        if not isinstance(arr, list) or len(arr) != len(items):
            raise ValueError(f"expected {len(items)} items, got {len(arr) if isinstance(arr, list) else type(arr)}")
        for src, dst in zip(items, arr):
            if isinstance(dst, str) and dst.strip() and markers_ok(src, dst):
                done[src] = dst.strip()

    for c in order:
        if spent + len(c) > budget_chars:
            break
        batch.append(c)
        size += len(c)
        spent += len(c)
        if len(batch) >= 40 or size >= 6000:
            _safe(run, batch, L)
            batch, size = [], 0
    if batch:
        _safe(run, batch, L)
    return done


def _safe(fn, batch, L):
    try:
        fn(list(batch))
    except Exception as exc:
        log.warning("translation batch failed (%s, %d items): %s", L["code"], len(batch), exc)


# ------------------------------------------------------------------ page localization

def _prefix_links(soup, prefix: str) -> None:
    for tag in soup.find_all(True):
        if tag.get("hreflang") is not None:
            continue
        for attr in ("href", "src", "action"):
            v = tag.get(attr)
            if not isinstance(v, str) or not v.startswith("/") or v.startswith("//"):
                continue
            path = v.split("#")[0].split("?")[0]
            if path.startswith(NO_PREFIX) or path.endswith(NO_PREFIX_EXT):
                continue
            tag[attr] = prefix + v


def localize_html(html_text: str, path: str, L: dict, R: Resolver, site_url: str) -> tuple[str, bool]:
    """Returns (localized html, complete?)."""
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html_text, "html.parser")
    prefix = lang_prefix(L)
    units = collect_units(soup)
    complete = True
    for u in units:
        tr = R.known.get(u.core)
        if tr is None:
            complete = False
            mark_english(u, soup)
            continue
        replace_unit(u, decode(u, tr, soup), soup)
    for tag, attr, v in collect_attrs(soup):
        tr = R.known.get(re.sub(r"\s+", " ", v))
        if tr is None:
            complete = False
        else:
            tag[attr] = tr
    root = soup.find("html")
    root["lang"], root["dir"], root["data-prefix"] = L["code"], L["dir"], prefix
    for link in soup.find_all("link", rel="canonical"):
        link["href"] = site_url + prefix + path
    og = soup.find("meta", property="og:url")
    if og:
        og["content"] = site_url + prefix + path
    js = soup.find("script", id="gu-l10n")
    if js:
        js.string = json.dumps({**JS_STRINGS, **R.js, "intl": L.get("intl", L["code"])}, ensure_ascii=False)
    for a in soup.select("nav.langs a[hreflang]"):
        if a.get("hreflang") == L["code"]:
            a["aria-current"] = "true"
        elif a.has_attr("aria-current"):
            del a["aria-current"]
    main = soup.find("main")
    if main is not None and path != "/404.html":
        note = soup.new_tag("p", attrs={"class": "note i18n-note"})
        note.append(R.t(NOTICE) + " ")
        a = soup.new_tag("a", href=path, hreflang="en", lang="en")
        a.string = R.t(NOTICE_LINK)
        note.append(a)
        main.insert(0, note)
        if path in LEGAL_PATHS:
            legal = soup.new_tag("p", attrs={"class": "legal-flag"})
            legal.string = R.t(LEGAL_NOTE)
            main.append(legal)
    for player in soup.find_all("div", class_="player"):
        vn = soup.new_tag("p", attrs={"class": "note"})
        vn.string = R.t(VIDEO_NOTE)
        player.insert_after(vn)
    _prefix_links(soup, prefix)
    return "<!doctype html>" + str(soup).replace("<!DOCTYPE html>", "").replace("<!doctype html>", ""), complete


def _page_cores(html_text: str) -> set[str]:
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html_text, "html.parser")
    cores = {u.core for u in collect_units(soup)}
    cores |= {re.sub(r"\s+", " ", v) for _, _, v in collect_attrs(soup)}
    return cores


def _page_order(paths: set[str]) -> list[str]:
    def rank(p):
        if p == "/":
            return (0, p)
        if p.startswith("/story/"):
            return (2, "".join(chr(0x10FFFF - ord(c)) for c in p))  # newest dates first
        if p.count("/") <= 2:
            return (1, p)
        return (3, p)
    return sorted(paths, key=rank)


def localize_site(ctx) -> dict:
    """Publish every changed English page in each enabled language."""
    from gbs.site.build import dest_of
    langs = [L for L in enabled_languages() if L["code"] != "en"]
    if os.getenv("GBS_I18N", "1") == "0":
        return {}
    if not langs:
        return {}
    cfg = ctx.cfg
    cache = Cache(cfg.data_dir / "translations.db")
    man_p = cfg.data_dir / "i18n_manifest.json"
    manifest = json.loads(man_p.read_text()) if man_p.exists() else {}
    html_paths = _page_order({p for p in ctx.pages if p.endswith(("/", ".html"))})
    english = {}
    for p in html_paths:
        f = dest_of(ctx.out, p)
        if f.is_file():
            english[p] = f.read_text(encoding="utf-8")
    hashes = {p: hashlib.sha256(t.encode()).hexdigest()[:20] for p, t in english.items()}
    # per language per build; the 27B also writes the news, so translation gets a modest share each run
    budget = int(os.getenv("GBS_TRANSLATE_MAX_CHARS", "12000"))
    stats = {}
    for L in langs:
        m = manifest.setdefault(L["code"], {})
        todo = [p for p in english if not (m.get(p, {}).get("h") == hashes[p] and m[p].get("complete")
                                            and dest_of(ctx.out, lang_prefix(L) + p).is_file())]
        R = Resolver(L, cache)
        cores: set[str] = {NOTICE, NOTICE_LINK, LEGAL_NOTE, VIDEO_NOTE}
        for p in todo:
            cores |= _page_cores(english[p])
        missing = R.prime(cores)
        if missing:
            new = llm_translate(cfg, L, sorted(missing), budget)
            if new:
                cache.put_many(L["code"], new)
                R.known.update(new)
        n_done = 0
        for p in todo:
            out_html, complete = localize_html(english[p], p, L, R, cfg.site_url)
            dest = dest_of(ctx.out, lang_prefix(L) + p)
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(out_html, encoding="utf-8")
            m[p] = {"h": hashes[p], "complete": complete}
            n_done += 1
        _localize_data(ctx, L, R)
        stats[L["code"]] = {"pages": n_done, "skipped": len(english) - len(todo), "untranslated": len(missing) - len(
            [c for c in missing if c in R.known])}
        log.info("i18n %s: %s", L["code"], stats[L["code"]])
    man_p.parent.mkdir(parents=True, exist_ok=True)
    man_p.write_text(json.dumps(manifest))
    return stats


def _localize_data(ctx, L: dict, R: Resolver) -> None:
    """Per-language search index and status feed for gu.js."""
    prefix = lang_prefix(L)
    idx_p = ctx.out / "search-index.json"
    if idx_p.is_file():
        idx = json.loads(idx_p.read_text(encoding="utf-8"))
        loc = [{**i, "t": R.t(i["t"]), "s": R.t(i["s"]), "d": R.t(i["d"]), "u": prefix + i["u"]} for i in idx]
        d = ctx.out / L["path"] / "search-index.json"
        d.parent.mkdir(parents=True, exist_ok=True)
        d.write_text(json.dumps(loc, ensure_ascii=False), encoding="utf-8")
    st_p = ctx.out / "status.json"
    if st_p.is_file():
        st = json.loads(st_p.read_text(encoding="utf-8"))
        st["show"]["url"] = prefix + st["show"]["url"]
        st["anchor"]["url"] = prefix + st["anchor"]["url"]
        if st.get("pulse"):
            st["pulse"] = R.t(st["pulse"])
        if st.get("breaking"):
            st["breaking"] = {"title": R.t(st["breaking"]["title"]), "url": prefix + st["breaking"]["url"]}
        (ctx.out / L["path"] / "status.json").write_text(json.dumps(st, ensure_ascii=False), encoding="utf-8")
