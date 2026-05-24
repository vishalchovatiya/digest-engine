from __future__ import annotations
import argparse
import os
from pathlib import Path
import yaml
from .planner import is_due
from .sources import fetch_items
from .pipeline import filter_and_score
from .renderer import render_email
from .mailer import send_email
from .store import mark_run, mark_sent


def load_configs() -> list[dict]:
    configs = []
    digests_dir = Path(__file__).resolve().parent.parent / 'digests'
    for path in sorted(digests_dir.glob('*.yaml')):
        with open(path, 'r', encoding='utf-8') as f:
            cfg = yaml.safe_load(f)
            configs.append(cfg)
    return configs


def resolve_recipients(config: dict) -> list[str]:
    recipients = config.get('email', {}).get('to', []) or []
    default_to = os.getenv('DIGEST_TO_EMAIL', '').strip()
    if default_to:
        recipients.append(default_to)
    recipients = [r.strip() for r in recipients if r and r.strip()]
    deduped = []
    seen = set()
    for r in recipients:
        if r.lower() not in seen:
            seen.add(r.lower())
            deduped.append(r)
    return deduped


def run_digest(config: dict, dry_run: bool) -> None:
    items = []
    for source in config.get('sources', []):
        try:
            items.extend(fetch_items(config['id'], source))
        except Exception as e:
            print(f"[WARN] source failed for {config['id']}: {source.get('url')} -> {e}")
    selected = filter_and_score(config, items)
    email_html = render_email(config, [
        {
            'title': i.title,
            'url': i.url,
            'summary': i.summary,
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
    if not recipients:
        raise RuntimeError(f"No recipients configured for digest {config['id']}")

    if dry_run:
        print(f"[DRY RUN] would send {config['id']} to {recipients}")
        mark_run(config['id'], True)
        return

    send_email(config['email']['subject'], email_html, recipients)
    for item in selected:
        mark_sent(config['id'], item.url)
    mark_run(config['id'], True)
    print(f"[INFO] sent {config['id']} to {recipients}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--due', action='store_true', help='Run all due digests')
    parser.add_argument('--digest', help='Run one digest by id')
    parser.add_argument('--dry-run', action='store_true', help='Render but do not send')
    args = parser.parse_args()

    configs = load_configs()
    if args.digest:
        match = next((c for c in configs if c['id'] == args.digest), None)
        if not match:
            raise SystemExit(f"Digest not found: {args.digest}")
        run_digest(match, args.dry_run)
        return

    if args.due:
        any_run = False
        for cfg in configs:
            if is_due(cfg):
                any_run = True
                run_digest(cfg, args.dry_run)
        if not any_run:
            print('[INFO] no digests due')
        return

    raise SystemExit('Use --due or --digest <id>')


if __name__ == '__main__':
    main()
