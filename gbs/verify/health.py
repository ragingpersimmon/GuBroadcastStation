"""`gbs doctor`: is the newsroom able to verify and publish?

Read-only. Checks feed health (which configured feeds produced items in the last
24 h), source-registry coverage (outlets the checker doesn't know can't confirm),
the rewriter (LLM reachable, which model), and the verification log (how many
stories passed / were held back, and why). Exit 1 when something needs action.
"""
from __future__ import annotations

import json
import time
import urllib.request
from collections import Counter

from gbs.config import Settings


def log_edition(cfg: Settings, published: int, held: list) -> None:
    rec = {"ts": int(time.time()), "published": published, "held": len(held),
           "problems": sorted({p for s in held for p in (s.verify or {}).get("problems", [])})}
    path = cfg.data_dir / "verify_log.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as f:
        f.write(json.dumps(rec) + "\n")


def feed_health(cfg: Settings, hours: float = 24) -> dict:
    from gbs.newsdesk.feeds import WORLD_FEEDS
    from gbs.newsdesk.store import StoryStore
    seen = Counter(s.source for s in StoryStore(cfg.db_path).recent(hours=hours, unused_only=False))
    return {"live": {k: seen[k] for k in WORLD_FEEDS if seen[k]}, "silent": sorted(k for k in WORLD_FEEDS if not seen[k])}


def registry_gaps() -> list[str]:
    from gbs.newsdesk.feeds import WORLD_FEEDS
    from gbs.verify.checker import profile
    return sorted({profile(k)["name"] for k in WORLD_FEEDS if profile(k)["type"] == "unknown"})


def llm_status(cfg: Settings) -> dict:
    if not cfg.llm_base_url:
        return {"ok": False, "why": "LLM_BASE_URL not set: nothing new can be published"}
    from gbs.editorial.scriptwriter import resolve_model
    try:
        with urllib.request.urlopen(f"{cfg.llm_base_url}/models", timeout=8) as r:
            r.read()
        model = resolve_model(cfg)
        return {"ok": bool(model), "url": cfg.llm_base_url, "model": model or "(none found)"}
    except Exception as exc:
        return {"ok": False, "url": cfg.llm_base_url, "why": f"unreachable: {exc}"}


def verify_stats(cfg: Settings, hours: float = 24) -> dict:
    path = cfg.data_dir / "verify_log.jsonl"
    if not path.is_file():
        return {"editions": 0}
    cut = time.time() - hours * 3600
    recs = [json.loads(l) for l in path.read_text().splitlines()[-500:] if l.strip()]
    recs = [r for r in recs if r["ts"] >= cut]
    why = Counter(p.split(":")[0] for r in recs for p in r["problems"])
    return {"editions": len(recs), "published": sum(r["published"] for r in recs),
            "held": sum(r["held"] for r in recs), "top_reasons": why.most_common(5)}


def doctor(cfg: Settings) -> int:
    fh, gaps, llm, vs = feed_health(cfg), registry_gaps(), llm_status(cfg), verify_stats(cfg)
    print("== Gu newsroom doctor ==")
    print(f"rewriter: {'OK ' + llm.get('model', '') if llm['ok'] else 'DOWN - ' + llm.get('why', '')}")
    print(f"feeds: {len(fh['live'])} live, {len(fh['silent'])} silent in 24 h")
    for k in fh["silent"]:
        print(f"   silent: {k}")
    print("source registry: " + ("all outlets known" if not gaps else "UNKNOWN (cannot confirm): " + ", ".join(gaps)))
    if vs.get("editions"):
        print(f"last 24 h: {vs['editions']} editions, {vs['published']} stories published, {vs['held']} held back")
        for reason, n in vs["top_reasons"]:
            print(f"   held: {reason} x{n}")
    else:
        print("last 24 h: no editions logged")
    bad = (not llm["ok"]) or bool(gaps) or len(fh["silent"]) > len(fh["live"])
    return 1 if bad else 0
