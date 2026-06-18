from __future__ import annotations
import argparse
import os
import re
import time
from pathlib import Path
import yaml
from .planner import is_due
from .sources import fetch_items
from .pipeline import filter_and_score
from .renderer import render_email
from .mailer import send_email
from .store import (
    mark_run, mark_sent, record_source_health,
    recent_source_health, prune,
)
from .config_schema import validate_configs, validate_config
from .price_tracker import (
    run_price_watch, observations_to_items, notable_observations,
)


def _send_credentials_available() -> bool:
    """True only when both RESEND_API_KEY and DIGEST_FROM_EMAIL are non-empty."""
    return bool((os.environ.get('RESEND_API_KEY') or '').strip()) and \
        bool((os.environ.get('DIGEST_FROM_EMAIL') or '').strip())


def _effective_dry_run(dry_run: bool) -> bool:
    """Return True if we should skip the live send.

    Honours the explicit --dry-run flag, and also auto-degrades to dry-run
    when send credentials are missing so scheduled runs render the HTML
    artifact rather than failing the Actions job.
    """
    if dry_run:
        return True
    if not _send_credentials_available():
        print("[WARN] RESEND_API_KEY or DIGEST_FROM_EMAIL is empty — "
              "auto-degrading to dry-run (HTML rendered, no email sent).")
        return True
    return False


def load_configs() -> list[dict]:
    configs = []
    digests_dir = Path(__file__).resolve().parent.parent / 'digests'
    for path in sorted(digests_dir.glob('*.yaml')):
        with open(path, 'r', encoding='utf-8') as f:
            cfg = yaml.safe_load(f)
            configs.append(cfg)
    errors = validate_configs(configs)
    if errors:
        for e in errors:
            print(f"[CONFIG-ERROR] {e}")
        raise SystemExit("Invalid digest config(s) — see [CONFIG-ERROR] lines above.")
    return configs


# Resend accepts either "email@example.com" or "Name <email@example.com>".
# Validate the bare address part of each recipient so a malformed entry in
# DIGEST_TO_EMAILS (or a digest's email.to) is dropped with a warning rather
# than reaching Resend and failing the whole job with a ValidationError.
_EMAIL_RE = re.compile(r'^[^@\s]+@[^@\s]+\.[^@\s]+$')
_NAMED_ADDR_RE = re.compile(r'^.*<\s*([^@\s<>]+@[^@\s<>]+\.[^@\s<>]+)\s*>$')


def _is_valid_recipient(addr: str) -> bool:
    if _EMAIL_RE.match(addr):
        return True
    m = _NAMED_ADDR_RE.match(addr)
    return bool(m and _EMAIL_RE.match(m.group(1)))


def resolve_recipients(config: dict) -> list[str]:
    recipients = list(config.get('email', {}).get('to', []) or [])
    env_value = os.getenv('DIGEST_TO_EMAILS', '')
    for part in env_value.split(','):
        addr = part.strip()
        if addr:
            recipients.append(addr)
    recipients = [r.strip() for r in recipients if r and r.strip()]
    deduped = []
    seen = set()
    for r in recipients:
        if r.lower() not in seen:
            seen.add(r.lower())
            deduped.append(r)
    valid = []
    for r in deduped:
        if _is_valid_recipient(r):
            valid.append(r)
        else:
            print(f"[WARN] dropping malformed recipient address: {r!r}")
    return valid


def _fetch_with_health(digest_id: str, source: dict) -> list:
    """Wrap source fetch to record health metrics per source."""
    start = time.time()
    try:
        items = fetch_items(digest_id, source)
        duration_ms = int((time.time() - start) * 1000)
        status = 'ok' if items else 'empty'
        record_source_health(digest_id, source.get('url', ''), status,
                             item_count=len(items), duration_ms=duration_ms)
        return items
    except Exception as exc:
        duration_ms = int((time.time() - start) * 1000)
        record_source_health(digest_id, source.get('url', ''), 'error',
                             item_count=0, duration_ms=duration_ms, error=str(exc))
        print(f"[WARN] source failed for {digest_id}: {source.get('url')} -> {exc}")
        return []


def run_price_watch_digest(config: dict, dry_run: bool) -> None:
    dry_run = _effective_dry_run(dry_run)
    observations = run_price_watch(config)
    notable = notable_observations(observations)
    items_for_email = observations_to_items(notable) if notable else observations_to_items(observations)

    email_html = render_email(config, items_for_email)
    project_root = Path(__file__).resolve().parent.parent
    out_dir = project_root / 'data' / 'rendered'
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / f"{config['id']}.html"
    out_file.write_text(email_html, encoding='utf-8')
    print(f"[INFO] rendered {out_file}")

    if not notable:
        print(f"[INFO] no notable price moves for {config['id']} "
              f"({len(observations)} observations recorded)")
        mark_run(config['id'], True)
        return

    recipients = resolve_recipients(config)

    if dry_run:
        print(f"[DRY RUN] would send {config['id']} to {recipients} "
              f"({len(notable)} notable obs)")
        mark_run(config['id'], True)
        return

    if not recipients:
        raise RuntimeError(f"No valid recipients configured for digest {config['id']}")

    send_email(config['email']['subject'], email_html, recipients)
    mark_run(config['id'], True)
    print(f"[INFO] sent {config['id']} to {recipients}")


def run_digest(config: dict, dry_run: bool) -> None:
    if config.get('type') == 'price_watch':
        run_price_watch_digest(config, dry_run)
        return

    dry_run = _effective_dry_run(dry_run)
    items = []
    for source in config.get('sources', []):
        items.extend(_fetch_with_health(config['id'], source))
    selected = filter_and_score(config, items)
    email_html = render_email(config, [
        {
            'title': i.title,
            'url': i.url,
            'summary': (i.summary or '') + (
                f"  ·  +{i.metadata['duplicate_count']} duplicate source(s)"
                if i.metadata.get('duplicate_count') else ''
            ),
            'score': i.score,
            'matched_keywords': i.matched_keywords,
        }
        for i in selected
    ])

    # Always resolve output directory relative to project root (parent of src/)
    project_root = Path(__file__).resolve().parent.parent
    out_dir = project_root / 'data' / 'rendered'
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / f"{config['id']}.html"
    out_file.write_text(email_html, encoding='utf-8')
    print(f"[INFO] rendered {out_file}")

    if not selected:
        print(f"[INFO] no items selected for {config['id']}")
        mark_run(config['id'], True)
        return

    recipients = resolve_recipients(config)

    if dry_run:
        print(f"[DRY RUN] would send {config['id']} to {recipients}")
        mark_run(config['id'], True)
        return

    if not recipients:
        raise RuntimeError(f"No valid recipients configured for digest {config['id']}")

    send_email(config['email']['subject'], email_html, recipients)
    for item in selected:
        mark_sent(config['id'], item.url)
    mark_run(config['id'], True)
    print(f"[INFO] sent {config['id']} to {recipients}")


def _print_health(digest_id: str | None) -> None:
    rows = recent_source_health(digest_id, limit=100)
    if not rows:
        print('[INFO] no source_health entries yet — run a digest first.')
        return
    by_source: dict[tuple[str, str], list[dict]] = {}
    for r in rows:
        by_source.setdefault((r['digest_id'], r['source_url']), []).append(r)
    print(f"{'digest':28} {'status':8} {'items':>5} {'ms':>6}  source")
    print("-" * 100)
    for (did, url), entries in by_source.items():
        latest = entries[0]
        ok = sum(1 for e in entries if e['status'] == 'ok')
        total = len(entries)
        status_str = f"{latest['status']} ({ok}/{total})"
        print(f"{did:28} {status_str:14} {latest['item_count']:>5} {latest['duration_ms']:>6}  {url}")
        if latest.get('error'):
            print(f"  └─ error: {latest['error']}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--due', action='store_true', help='Run all due digests')
    parser.add_argument('--digest', help='Run one digest by id')
    parser.add_argument('--dry-run', action='store_true', help='Render but do not send')
    parser.add_argument('--health', action='store_true', help='Show recent source health and exit')
    parser.add_argument('--prune', action='store_true', help='Prune old state and exit')
    parser.add_argument('--validate', action='store_true', help='Validate digest YAMLs and exit')
    args = parser.parse_args()

    if args.health:
        _print_health(args.digest)
        return

    if args.prune:
        result = prune()
        print(f"[INFO] pruned: {result}")
        return

    configs = load_configs()
    if args.validate:
        # load_configs already validates; reaching here means OK
        print(f"[OK] {len(configs)} digest config(s) validated.")
        return
    if args.digest:
        match = next((c for c in configs if c['id'] == args.digest), None)
        if not match:
            raise SystemExit(f"Digest not found: {args.digest}")
        run_digest(match, args.dry_run)
        # Light pruning each run keeps the DB small without a separate cron.
        prune()
        return

    if args.due:
        any_run = False
        for cfg in configs:
            if is_due(cfg):
                any_run = True
                run_digest(cfg, args.dry_run)
        if not any_run:
            print('[INFO] no digests due')
        prune()
        return

    raise SystemExit('Use --due or --digest <id>')


if __name__ == '__main__':
    main()
