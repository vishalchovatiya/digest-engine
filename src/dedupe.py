"""
Lightweight URL/title normalization and near-duplicate clustering.

Goals:
  * collapse items that differ only by tracking query params or anchor
    fragments to a single canonical URL,
  * group items whose titles share substantial token overlap into one
    cluster, keeping the highest-scored item as the representative.

Everything here is deterministic — no LLM, no learned model.
"""
from __future__ import annotations

import re
from typing import Iterable
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode

from .models import ContentItem

_TRACKING_PARAM_PREFIXES = ("utm_", "mc_", "_hs", "vero_")
_TRACKING_PARAMS = {
    "gclid", "fbclid", "msclkid", "igshid", "mc_eid", "mc_cid",
    "ref", "ref_src", "ref_url", "share", "share_id",
    "spm", "trk", "feature", "ocid", "cmpid",
}

_STOPWORDS = {
    "the", "a", "an", "and", "or", "of", "for", "in", "on", "at",
    "to", "with", "is", "are", "be", "by", "from", "this", "that",
    "it", "its", "as", "but", "if", "not", "&",
}

_PUNCT_RE = re.compile(r"[^\w\s]+", re.UNICODE)
_WS_RE = re.compile(r"\s+")


def normalize_url(url: str) -> str:
    """Strip tracking query params and fragments; lowercase scheme/host."""
    if not url:
        return url
    try:
        parts = urlsplit(url)
    except ValueError:
        return url
    query_pairs = []
    for k, v in parse_qsl(parts.query, keep_blank_values=False):
        kl = k.lower()
        if kl in _TRACKING_PARAMS:
            continue
        if any(kl.startswith(p) for p in _TRACKING_PARAM_PREFIXES):
            continue
        query_pairs.append((k, v))
    new_query = urlencode(query_pairs)
    scheme = parts.scheme.lower() or "https"
    netloc = parts.netloc.lower()
    path = parts.path.rstrip("/") or parts.path
    return urlunsplit((scheme, netloc, path, new_query, ""))


def normalize_title(title: str) -> str:
    if not title:
        return ""
    lowered = title.lower()
    cleaned = _PUNCT_RE.sub(" ", lowered)
    cleaned = _WS_RE.sub(" ", cleaned).strip()
    return cleaned


def title_tokens(title: str) -> set[str]:
    norm = normalize_title(title)
    return {tok for tok in norm.split() if tok and tok not in _STOPWORDS and len(tok) > 2}


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    inter = len(a & b)
    union = len(a | b)
    if union == 0:
        return 0.0
    return inter / union


def cluster_items(items: Iterable[ContentItem], threshold: float = 0.6) -> list[ContentItem]:
    """
    Cluster items by normalized URL and Jaccard title-token overlap.
    For each cluster the highest-score (then most recent) item wins; its
    `metadata['duplicate_count']` records how many siblings collapsed into it.
    """
    items = list(items)
    if not items:
        return []

    norm_urls: list[str] = []
    token_sets: list[set[str]] = []
    for it in items:
        norm_urls.append(normalize_url(it.url))
        token_sets.append(title_tokens(it.title))

    n = len(items)
    parent = list(range(n))

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: int, b: int) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    url_map: dict[str, int] = {}
    for i, u in enumerate(norm_urls):
        if not u:
            continue
        if u in url_map:
            union(i, url_map[u])
        else:
            url_map[u] = i

    for i in range(n):
        for j in range(i + 1, n):
            if find(i) == find(j):
                continue
            if _jaccard(token_sets[i], token_sets[j]) >= threshold:
                union(i, j)

    clusters: dict[int, list[int]] = {}
    for i in range(n):
        clusters.setdefault(find(i), []).append(i)

    out: list[ContentItem] = []
    for members in clusters.values():
        def sort_key(idx: int):
            it = items[idx]
            return (it.score, it.published_at or 0)
        members.sort(key=sort_key, reverse=True)
        best = items[members[0]]
        if len(members) > 1:
            best.metadata = dict(best.metadata)
            best.metadata["duplicate_count"] = len(members) - 1
        out.append(best)
    return out
