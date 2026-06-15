from __future__ import annotations
from datetime import datetime, timedelta, timezone
from .models import ContentItem
from .store import has_sent
from .dedupe import cluster_items, normalize_url


def filter_and_score(config: dict, items: list[ContentItem]) -> list[ContentItem]:
    filters = config.get('filters', {})
    scoring = config.get('scoring', {})
    include_keywords = [k.lower() for k in filters.get('include_keywords', [])]
    exclude_keywords = [k.lower() for k in filters.get('exclude_keywords', [])]
    freshness_days = filters.get('freshness_days', 7)
    require_any = filters.get('require_any_keywords', False)
    max_items = filters.get('max_items', 5)

    cutoff = datetime.now(timezone.utc) - timedelta(days=freshness_days)
    candidates: list[ContentItem] = []
    for item in items:
        if not item.url:
            continue
        if has_sent(config['id'], item.url) or has_sent(config['id'], normalize_url(item.url)):
            continue
        hay = f"{item.title} {item.summary}".lower()
        if exclude_keywords and any(k in hay for k in exclude_keywords):
            continue
        matched = [k for k in include_keywords if k in hay]
        if require_any and include_keywords and not matched:
            continue
        if item.published_at and item.published_at.tzinfo is None:
            item.published_at = item.published_at.replace(tzinfo=timezone.utc)
        if item.published_at and item.published_at < cutoff:
            continue
        score = 0
        score += len(matched) * scoring.get('keyword_hit', 1)
        title_l = item.title.lower()
        score += sum(1 for k in include_keywords if k in title_l) * scoring.get('title_keyword_hit', 2)
        keyword_weights = scoring.get('keyword_weights') or {}
        if keyword_weights:
            for term, weight in keyword_weights.items():
                if term.lower() in hay:
                    score += int(weight)
        penalty_weights = scoring.get('penalty_weights') or {}
        if penalty_weights:
            for term, weight in penalty_weights.items():
                if term.lower() in hay:
                    score -= int(weight)
        source_weights = scoring.get('source_weights') or {}
        if source_weights and item.source_url:
            score += int(source_weights.get(item.source_url, 0))
        if item.published_at:
            recency_days = scoring.get('recency_boost_days', 7)
            if item.published_at >= datetime.now(timezone.utc) - timedelta(days=recency_days):
                score += scoring.get('recency_boost_score', 1)
        item.score = score
        item.matched_keywords = matched
        candidates.append(item)

    # Cluster near-duplicates (same normalized URL or high title overlap).
    clustered = cluster_items(candidates)
    clustered.sort(key=lambda x: (x.score, x.published_at or datetime.min.replace(tzinfo=timezone.utc)), reverse=True)
    return clustered[:max_items]
