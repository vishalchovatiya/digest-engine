# Digest Engine

Lean multi-digest email engine using GitHub Actions + Python + Resend.

## Features

- One repo for multiple digests
- One workflow for scheduled and manual runs
- Public sources only (no login required)
- Structured filters in YAML (no LLM compiler)
- SQLite state tracking to avoid duplicates
- Resend email delivery

## Project structure

```
digest-engine/
├─ .github/workflows/digests.yml   # scheduled/manual workflow
├─ digests/                        # one digest per YAML file
│  ├─ vscode-weekly.yaml
│  └─ ai-tools-weekly.yaml
├─ src/                            # planner, fetching, filtering, rendering, email, state
│  ├─ __init__.py
│  ├─ main.py                      # CLI entrypoint
│  ├─ mailer.py                    # Resend delivery
│  ├─ models.py                    # ContentItem dataclass
│  ├─ pipeline.py                  # filter + score
│  ├─ planner.py                   # schedule due-check
│  ├─ renderer.py                  # Jinja2 HTML render
│  ├─ sources.py                   # RSS and webpage fetcher
│  └─ store.py                     # SQLite state (runs + sent items)
├─ templates/
│  └─ email.html.j2                # shared HTML email template
├─ tests/
│  └─ smoke_test.py                # offline smoke test (no network, no email)
├─ .env.example                    # copy to .env and fill values
├─ requirements.txt
└─ data/state.db                   # created at runtime (git-ignored)
```

## Quick start

### 1. Clone and set up environment

```bash
git clone <your-repo-url>
cd digest-engine
python -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Configure credentials

```bash
cp .env.example .env
# Edit .env and set RESEND_API_KEY, DIGEST_FROM_EMAIL, DIGEST_TO_EMAIL
```

Then export in your shell (or use a tool like `direnv`):

```bash
export RESEND_API_KEY=re_...
export DIGEST_FROM_EMAIL="Digest <digest@yourdomain.com>"
export DIGEST_TO_EMAIL=you@example.com
```

### 3. Run commands

| Goal | Command |
|------|---------|
| Dry-run a specific digest (no email sent) | `python -m src.main --digest vscode-weekly --dry-run` |
| Dry-run all due digests | `python -m src.main --due --dry-run` |
| Send a specific digest | `python -m src.main --digest vscode-weekly` |
| Run all due digests (live send) | `python -m src.main --due` |
| Offline smoke test | `python tests/smoke_test.py` |

### 4. Rendered output

Every run writes `data/rendered/<digest-id>.html` — open in a browser to preview the email before sending.

## Required GitHub Secrets

| Secret | Description |
|--------|-------------|
| `RESEND_API_KEY` | API key from [resend.com](https://resend.com) |
| `DIGEST_FROM_EMAIL` | Verified sender address |
| `DIGEST_TO_EMAIL` | Default recipient (optional) |

## Adding a new digest

Copy any existing YAML file in `digests/`, change `id`, `schedule`, `sources`, `filters`, and `email.subject`. The engine picks it up automatically on the next run.

## DIGEST_FROM_EMAIL format

Use an address on the domain/subdomain you verified in Resend:

- `Vishal Digest <digest@updates.example.com>`
- `digest@updates.example.com`

## Notes

- Rotate any API key that was exposed outside your secret store.
- GitHub Actions cron runs in UTC.
- SQLite state file (`data/state.db`) is git-ignored; it is created on first run.
- Source fetching is best-effort: if one source fails, the others still run and a `[WARN]` is printed.
