"""
Lightweight YAML config validation for digest configs.

No external dependency — we implement just enough structural validation to
catch typos and shape mistakes early. Two config shapes are supported:

  * content digests (default) — `sources`, `filters`, `scoring`, `render`
  * price-watch digests        — `type: price_watch`, `products`

Use `validate_config(cfg)` to validate a single config and
`validate_configs(configs)` to validate a list (returns a list of error
strings; empty list means everything is OK).
"""
from __future__ import annotations

from typing import Any

_VALID_SCHEDULE_TYPES = {"weekly", "daily"}
_VALID_DAYS = {"monday", "tuesday", "wednesday", "thursday",
               "friday", "saturday", "sunday"}
_VALID_SOURCE_TYPES = {"rss", "webpage", "github"}


def _err(prefix: str, msg: str) -> str:
    return f"{prefix}: {msg}"


def _require_keys(prefix: str, obj: dict, keys: list[str]) -> list[str]:
    errors = []
    for k in keys:
        if k not in obj:
            errors.append(_err(prefix, f"missing required field '{k}'"))
    return errors


def _validate_schedule(prefix: str, schedule: Any) -> list[str]:
    errors: list[str] = []
    if not isinstance(schedule, dict):
        return [_err(prefix, "schedule must be a mapping")]
    stype = schedule.get("type", "weekly")
    if stype not in _VALID_SCHEDULE_TYPES:
        errors.append(_err(prefix, f"schedule.type must be one of {sorted(_VALID_SCHEDULE_TYPES)} (got {stype!r})"))
    if stype == "weekly":
        day = schedule.get("day_of_week", "")
        if not isinstance(day, str) or day.lower() not in _VALID_DAYS:
            errors.append(_err(prefix, f"schedule.day_of_week must be one of {sorted(_VALID_DAYS)} (got {day!r})"))
    for fld in ("hour", "minute"):
        if fld in schedule and not isinstance(schedule[fld], int):
            errors.append(_err(prefix, f"schedule.{fld} must be int"))
    hour = schedule.get("hour", 0)
    minute = schedule.get("minute", 0)
    if isinstance(hour, int) and not (0 <= hour <= 23):
        errors.append(_err(prefix, f"schedule.hour out of range 0-23 (got {hour})"))
    if isinstance(minute, int) and not (0 <= minute <= 59):
        errors.append(_err(prefix, f"schedule.minute out of range 0-59 (got {minute})"))
    tz = schedule.get("timezone", "UTC")
    if not isinstance(tz, str):
        errors.append(_err(prefix, "schedule.timezone must be a string"))
    return errors


def _validate_sources(prefix: str, sources: Any) -> list[str]:
    errors: list[str] = []
    if not isinstance(sources, list) or not sources:
        return [_err(prefix, "sources must be a non-empty list")]
    for i, src in enumerate(sources):
        sp = f"{prefix}.sources[{i}]"
        if not isinstance(src, dict):
            errors.append(_err(sp, "must be a mapping"))
            continue
        stype = src.get("type")
        if stype not in _VALID_SOURCE_TYPES:
            errors.append(_err(sp, f"type must be one of {sorted(_VALID_SOURCE_TYPES)} (got {stype!r})"))
        if not isinstance(src.get("url"), str) or not src.get("url"):
            errors.append(_err(sp, "url must be a non-empty string"))
    return errors


def _validate_filters(prefix: str, filters: Any) -> list[str]:
    errors: list[str] = []
    if filters is None:
        return errors
    if not isinstance(filters, dict):
        return [_err(prefix, "filters must be a mapping")]
    for fld in ("include_keywords", "exclude_keywords"):
        val = filters.get(fld)
        if val is None:
            continue
        if not isinstance(val, list) or any(not isinstance(x, str) for x in val):
            errors.append(_err(prefix, f"filters.{fld} must be a list of strings"))
    for fld in ("freshness_days", "max_items"):
        if fld in filters and not isinstance(filters[fld], int):
            errors.append(_err(prefix, f"filters.{fld} must be int"))
    if "require_any_keywords" in filters and not isinstance(filters["require_any_keywords"], bool):
        errors.append(_err(prefix, "filters.require_any_keywords must be bool"))
    return errors


def _validate_scoring(prefix: str, scoring: Any) -> list[str]:
    errors: list[str] = []
    if scoring is None:
        return errors
    if not isinstance(scoring, dict):
        return [_err(prefix, "scoring must be a mapping")]
    for fld in ("keyword_hit", "title_keyword_hit",
                "recency_boost_days", "recency_boost_score"):
        if fld in scoring and not isinstance(scoring[fld], int):
            errors.append(_err(prefix, f"scoring.{fld} must be int"))
    for wfld in ("keyword_weights", "penalty_weights", "source_weights"):
        wmap = scoring.get(wfld)
        if wmap is None:
            continue
        if not isinstance(wmap, dict):
            errors.append(_err(prefix, f"scoring.{wfld} must be a mapping of str -> int"))
            continue
        for k, v in wmap.items():
            if not isinstance(k, str) or not isinstance(v, int):
                errors.append(_err(prefix, f"scoring.{wfld}['{k}'] must be int (got {type(v).__name__})"))
    return errors


def _validate_products(prefix: str, products: Any) -> list[str]:
    errors: list[str] = []
    if not isinstance(products, list) or not products:
        return [_err(prefix, "products must be a non-empty list for price_watch digests")]
    for i, p in enumerate(products):
        pp = f"{prefix}.products[{i}]"
        if not isinstance(p, dict):
            errors.append(_err(pp, "must be a mapping"))
            continue
        errors.extend(_require_keys(pp, p, ["id", "name", "urls"]))
        if "desired_price_cad" in p and not isinstance(p["desired_price_cad"], (int, float)):
            errors.append(_err(pp, "desired_price_cad must be a number"))
        urls = p.get("urls")
        if not isinstance(urls, list) or not urls:
            errors.append(_err(pp, "urls must be a non-empty list"))
            continue
        for j, u in enumerate(urls):
            up = f"{pp}.urls[{j}]"
            if not isinstance(u, dict):
                errors.append(_err(up, "must be a mapping with retailer + url"))
                continue
            if not isinstance(u.get("retailer"), str) or not u.get("retailer"):
                errors.append(_err(up, "retailer must be a non-empty string"))
            if not isinstance(u.get("url"), str) or not u.get("url"):
                errors.append(_err(up, "url must be a non-empty string"))
    return errors


def validate_config(cfg: Any) -> list[str]:
    """Return list of human-readable errors for one digest config (empty = OK)."""
    if not isinstance(cfg, dict):
        return ["config must be a YAML mapping"]
    digest_id = cfg.get("id", "<unknown>")
    prefix = f"digest[{digest_id}]"
    errors: list[str] = []
    errors.extend(_require_keys(prefix, cfg, ["id", "schedule", "email"]))
    if not isinstance(cfg.get("id", ""), str) or not cfg.get("id", ""):
        errors.append(_err(prefix, "id must be a non-empty string"))
    if "enabled" in cfg and not isinstance(cfg["enabled"], bool):
        errors.append(_err(prefix, "enabled must be bool"))
    errors.extend(_validate_schedule(prefix, cfg.get("schedule")))

    email = cfg.get("email")
    if not isinstance(email, dict):
        errors.append(_err(prefix, "email must be a mapping"))
    else:
        if not isinstance(email.get("subject"), str) or not email.get("subject"):
            errors.append(_err(prefix, "email.subject must be a non-empty string"))
        to = email.get("to", [])
        if to is not None and not isinstance(to, list):
            errors.append(_err(prefix, "email.to must be a list (possibly empty)"))

    if "profile_notes" in cfg and not isinstance(cfg["profile_notes"], dict):
        errors.append(_err(prefix, "profile_notes must be a mapping"))

    dtype = cfg.get("type", "content")
    if dtype == "price_watch":
        errors.extend(_validate_products(prefix, cfg.get("products")))
    else:
        errors.extend(_validate_sources(prefix, cfg.get("sources")))
        errors.extend(_validate_filters(prefix, cfg.get("filters")))
        errors.extend(_validate_scoring(prefix, cfg.get("scoring")))
    return errors


def validate_configs(configs: list[dict]) -> list[str]:
    errors: list[str] = []
    for cfg in configs:
        errors.extend(validate_config(cfg))
    return errors
