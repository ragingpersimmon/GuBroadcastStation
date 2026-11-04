from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Optional


@dataclass
class Story:
    """One ingested headline. `source` is the outlet key, `link` the
    original article -- every published segment must credit both."""
    item_hash: str
    desk: str               # world, americas, europe, asia, mideast, africa, business, tech, science
    source: str
    title: str
    summary: str
    link: str
    ts: float
    risk_score: float = 0.0  # 5protocol news_signal_engine score (0..1): urgency proxy
    regime: str = "normal"
    keywords: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Segment:
    """A rundown slot: one story (plus related coverage) ready for an anchor."""
    story: Story
    related: list = field(default_factory=list)   # other Story objects on the same event
    anchor_id: str = ""
    script: str = ""
    sponsor_read: Optional[str] = None

    @property
    def sources(self) -> list:
        seen, out = set(), []
        for s in [self.story, *self.related]:
            if s.source not in seen:
                seen.add(s.source)
                out.append({"source": s.source, "link": s.link})
        return out

    @property
    def slug(self) -> str:
        base = re.sub(r"[^a-z0-9]+", "-", self.story.title.lower()).strip("-")[:70]
        return f"{base}-{self.story.item_hash[:8]}"
