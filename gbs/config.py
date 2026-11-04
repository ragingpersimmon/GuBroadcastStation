"""Central env-driven config. Every knob has a safe default so the
pipeline runs end-to-end on a laptop with nothing but feedparser."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


def _env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


@dataclass
class Settings:
    # Where the 5protocol checkout lives (git submodule at vendor/5protocol
    # by default). The bridge imports news_ingest / news_signal_engine
    # from here instead of copying them.
    fiveprotocol_path: Path = field(default_factory=lambda: Path(
        _env("FIVEPROTOCOL_PATH", str(Path(__file__).resolve().parent.parent / "vendor" / "5protocol"))))

    # Optional: 5protocol's live push server (tailnet) for the market
    # regime state that powers the "Market Pulse" segment.
    fiveprotocol_news_url: str = field(default_factory=lambda: _env(
        "FIVEPROTOCOL_NEWS_URL", "http://nebulizer:8699/news.json"))
    fiveprotocol_push_key: str = field(default_factory=lambda: _env("PHONE_PUSH_KEY"))

    data_dir: Path = field(default_factory=lambda: Path(_env("GBS_DATA_DIR", "data")))
    site_out: Path = field(default_factory=lambda: Path(_env("GBS_SITE_OUT", "public")))
    site_url: str = field(default_factory=lambda: _env("GBS_SITE_URL", "https://example.com").rstrip("/"))
    site_name: str = field(default_factory=lambda: _env("GBS_SITE_NAME", "Gu Broadcast Station"))

    # LLM (OpenAI-compatible). Same env names as 5protocol core/llm_brain
    # so Strata over the tailnet / strata_tunnel.py just works.
    llm_base_url: str = field(default_factory=lambda: _env("LLM_BASE_URL").rstrip("/"))
    llm_model: str = field(default_factory=lambda: _env("LLM_MODEL", "strata"))
    llm_api_key: str = field(default_factory=lambda: _env("LLM_API_KEY"))

    # ComfyUI on the 5090 box (StarNet / Tailscale)
    comfy_url: str = field(default_factory=lambda: _env("COMFY_URL", "http://kwon9000:8188").rstrip("/"))

    rundown_size: int = field(default_factory=lambda: int(_env("GBS_RUNDOWN_SIZE", "12")))

    @property
    def db_path(self) -> Path:
        return self.data_dir / "stories.db"


def settings() -> Settings:
    return Settings()
