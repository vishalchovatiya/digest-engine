from __future__ import annotations
import re
from datetime import datetime, timezone
import requests
import feedparser
from bs4 import BeautifulSoup
from dateutil import parser as dateparser
from .models import ContentItem

HEADERS = {
    'User-Agent': 'digest-engine/1.0 (+https://github.com/)'
}


def fetch_items(digest_id: str, source: dict) -> list[ContentItem]:
    stype = source['type']
    if stype == 'rss':
        return _from_rss(digest_id, source['url'])
    if stype == 'webpage':
        return _from_webpage(digest_id, source['url'])
    if stype == 'github':
        return _from_webpage(digest_id, source['url'])
    raise ValueError(f'Unsupported source type: {stype}')


def _from_rss(digest_id: str, url: str) -> list[ContentItem]:
    feed = feedparser.parse(url)
    items = []
    for e in feed.entries[:30]:
        published = None
        if getattr(e, 'published', None):
            try:
                published = dateparser.parse(e.published)
            except Exception:
                published = None
        items.append(ContentItem(
            digest_id=digest_id,
            source_type='rss',
            source_url=url,
            title=getattr(e, 'title', '').strip(),
            url=getattr(e, 'link', '').strip(),
            summary=BeautifulSoup(getattr(e, 'summary', ''), 'html.parser').get_text(' ', strip=True),
            published_at=published,
        ))
    return items


def _from_webpage(digest_id: str, url: str) -> list[ContentItem]:
    r = requests.get(url, headers=HEADERS, timeout=30)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, 'html.parser')
    items = []
    seen = set()
    for a in soup.select('a[href]'):
        title = a.get_text(' ', strip=True)
        href = a.get('href', '').strip()
        if not title or len(title) < 8:
            continue
        if href.startswith('#') or href.startswith('javascript:'):
            continue
        full_url = requests.compat.urljoin(url, href)
        key = (title.lower(), full_url)
        if key in seen:
            continue
        seen.add(key)
        text = re.sub(r'\s+', ' ', title)
        items.append(ContentItem(
            digest_id=digest_id,
            source_type='webpage',
            source_url=url,
            title=text,
            url=full_url,
            summary='',
            published_at=datetime.now(timezone.utc),
        ))
        if len(items) >= 80:
            break
    return items
