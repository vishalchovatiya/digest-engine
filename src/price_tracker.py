"""
Multi-product price-watch runtime.

Activated by setting `type: price_watch` on a digest config. The config
exposes a `products:` list, each product has one or more retailer URLs. We
fetch every URL, extract the most likely CAD price using a small set of
deterministic regex/JSON-LD heuristics, diff against the last observation
in SQLite, and produce a list of "observations" that the existing email
template can render.

We intentionally avoid headless browsers and JavaScript execution. Some
retailers render prices client-side; for those, extraction returns None
and we report "price unavailable" rather than guessing.
"""
from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from typing import Iterable

import requests
from bs4 import BeautifulSoup

from .store import get_last_price, record_price, record_source_health

HEADERS = {
    'User-Agent': 'digest-engine/1.0 (+https://github.com/)',
    'Accept-Language': 'en-CA,en;q=0.9',
}

# Match prices like  $399.99, CA$399, CAD 1,299.00, $1,234.56
_PRICE_RE = re.compile(
    r'(?:CA\s*\$|CAD\s*\$?|\$)\s*(\d{1,3}(?:,\d{3})*(?:\.\d{1,2})?|\d+(?:\.\d{1,2})?)',
    re.IGNORECASE,
)


@dataclass
class PriceObservation:
    product_id: str
    product_name: str
    retailer: str
    url: str
    current_price: float | None
    previous_price: float | None
    desired_price: float | None
    change: str  # 'new' | 'down' | 'up' | 'same' | 'unavailable'
    threshold_met: bool

    @property
    def title(self) -> str:
        if self.current_price is None:
            return f"{self.product_name} — {self.retailer}: price unavailable"
        arrow = {"down": "↓", "up": "↑", "same": "·", "new": "★"}.get(self.change, "")
        prev = f" (was ${self.previous_price:.2f})" if self.previous_price is not None else ""
        flag = " — meets target" if self.threshold_met else ""
        return f"{self.product_name} — {self.retailer}: ${self.current_price:.2f} {arrow}{prev}{flag}"

    @property
    def summary(self) -> str:
        bits = []
        if self.desired_price is not None:
            bits.append(f"desired ≤ ${self.desired_price:.2f}")
        if self.previous_price is not None and self.current_price is not None:
            delta = self.current_price - self.previous_price
            bits.append(f"Δ ${delta:+.2f}")
        bits.append(f"status: {self.change}")
        return "  ·  ".join(bits)


def extract_price_cad(html: str) -> float | None:
    """Best-effort CAD price extraction. Prefers JSON-LD, falls back to regex."""
    if not html:
        return None
    soup = BeautifulSoup(html, 'html.parser')
    for tag in soup.find_all('script', attrs={'type': 'application/ld+json'}):
        try:
            payload = json.loads(tag.string or '')
        except Exception:
            continue
        candidate = _price_from_jsonld(payload)
        if candidate is not None:
            return candidate
    visible_text = soup.get_text(' ', strip=True)
    return _price_from_text(visible_text)


def _price_from_jsonld(payload) -> float | None:
    if isinstance(payload, list):
        for item in payload:
            v = _price_from_jsonld(item)
            if v is not None:
                return v
        return None
    if not isinstance(payload, dict):
        return None
    offers = payload.get('offers')
    if offers is not None:
        v = _price_from_jsonld(offers)
        if v is not None:
            return v
    price = payload.get('price') or payload.get('lowPrice')
    if price is not None:
        try:
            return float(str(price).replace(',', ''))
        except ValueError:
            return None
    return None


def _price_from_text(text: str) -> float | None:
    if not text:
        return None
    candidates: list[float] = []
    for match in _PRICE_RE.finditer(text):
        raw = match.group(1).replace(',', '')
        try:
            val = float(raw)
        except ValueError:
            continue
        if 5 <= val <= 100000:
            candidates.append(val)
    if not candidates:
        return None
    # Prefer the most-frequent price (mode); ties broken by smallest value —
    # retailers usually show the live price multiple times in markup.
    counts: dict[float, int] = {}
    for v in candidates:
        counts[v] = counts.get(v, 0) + 1
    best_count = max(counts.values())
    best = [v for v, c in counts.items() if c == best_count]
    return min(best)


def _fetch_html(url: str) -> str:
    r = requests.get(url, headers=HEADERS, timeout=30)
    r.raise_for_status()
    return r.text


def _classify(prev: float | None, curr: float | None) -> str:
    if curr is None:
        return 'unavailable'
    if prev is None:
        return 'new'
    if curr < prev:
        return 'down'
    if curr > prev:
        return 'up'
    return 'same'


def run_price_watch(config: dict, *, _fetcher=None) -> list[PriceObservation]:
    """
    Fetch every product/retailer URL, extract prices, diff against history,
    persist new observations, and return the list of PriceObservation
    objects (one per retailer URL). `_fetcher` is injectable for tests.
    """
    digest_id = config['id']
    fetcher = _fetcher or _fetch_html
    observations: list[PriceObservation] = []
    for product in config.get('products', []):
        product_id = product['id']
        product_name = product.get('name', product_id)
        desired = product.get('desired_price_cad')
        for url_entry in product.get('urls', []):
            retailer = url_entry['retailer']
            url = url_entry['url']
            start = time.time()
            try:
                html = fetcher(url)
                duration_ms = int((time.time() - start) * 1000)
            except Exception as exc:
                duration_ms = int((time.time() - start) * 1000)
                record_source_health(digest_id, url, 'error', 0, duration_ms, str(exc))
                observations.append(PriceObservation(
                    product_id=product_id, product_name=product_name,
                    retailer=retailer, url=url, current_price=None,
                    previous_price=None, desired_price=desired,
                    change='unavailable', threshold_met=False,
                ))
                continue
            curr = extract_price_cad(html)
            prev = get_last_price(digest_id, product_id, retailer, url)
            status = 'ok' if curr is not None else 'empty'
            record_source_health(digest_id, url, status, 1 if curr is not None else 0, duration_ms)
            record_price(digest_id, product_id, retailer, url, curr)
            threshold_met = (
                curr is not None and desired is not None and curr <= float(desired)
            )
            observations.append(PriceObservation(
                product_id=product_id, product_name=product_name,
                retailer=retailer, url=url, current_price=curr,
                previous_price=prev, desired_price=desired,
                change=_classify(prev, curr), threshold_met=threshold_met,
            ))
    return observations


def observations_to_items(observations: Iterable[PriceObservation]) -> list[dict]:
    """Convert observations into the dict shape the email template expects."""
    items = []
    for o in observations:
        items.append({
            'title': o.title,
            'url': o.url,
            'summary': o.summary,
            'score': 0,
            'matched_keywords': [o.change] if o.change != 'same' else [],
        })
    return items


def notable_observations(observations: list[PriceObservation]) -> list[PriceObservation]:
    """Return only price moves worth surfacing in email."""
    return [
        o for o in observations
        if o.change in ('new', 'down', 'up') or o.threshold_met
    ]
