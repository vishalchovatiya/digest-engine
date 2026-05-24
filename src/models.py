from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class ContentItem:
    digest_id: str
    source_type: str
    source_url: str
    title: str
    url: str
    summary: str = ""
    published_at: datetime | None = None
    score: int = 0
    matched_keywords: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
