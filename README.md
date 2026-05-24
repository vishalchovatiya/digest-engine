# Digest Engine

Lean multi-digest email engine using GitHub Actions + Python + Resend.

Each digest has its own GitHub Actions workflow with its own cron schedule — no shared
hourly poller. Schedules are defined in the digest YAML and converted to UTC cron
automatically by `scripts/generate_workflows.py`.

## Features

- One repo, multiple digests — each digest is one YAML file
- Per-digest GitHub Actions workflow with its own cron (generated from YAML)
- `workflow_dispatch` on every workflow for instant manual runs with optional `dry_run`
- Public sources only (no login required)
- Structured keyword filters in YAML (no LLM required)
- SQLite state tracking — no duplicate sends across runs
- Resend email delivery

## Project structure

```
digest-engine/
├─ .github/workflows/
│  ├─ digest-<id>.yml      # per-digest workflow (auto-generated — do not edit)
│  └─ manual.yml           # manual trigger for any digest by id
├─ digests/                # one digest per YAML file
│  ├─ vscode-weekly.yaml
│  ├─ ai-tools-weekly.yaml
│  └─ general-motors-weekly.yaml
├─ scripts/
│  └─ generate_workflows.py  # reads digests/*.yaml → writes .github/workflows/digest-<id>.yml
├─ src/                    # planner, fetching, filtering, rendering, email, state
│  ├─ __init__.py
│  ├─ main.py              # CLI entrypoint
│  ├─ mailer.py            # Resend delivery
│  ├─ models.py            # ContentItem dataclass
│  ├─ pipeline.py          # filter + score
│  ├─ planner.py           # schedule due-check (used for local --due runs)
│  ├─ renderer.py          # Jinja2 HTML render
│  ├─ sources.py           # RSS and webpage fetcher
│  └─ store.py             # SQLite state (runs + sent items)
├─ templates/
│  └─ email.html.j2        # HTML email template
├─ tests/
│  └─ smoke_test.py        # offline smoke tests (no network, no email)
├─ .env.example            # copy to .env and fill values
├─ requirements.txt
└─ data/state.db           # created at runtime (git-ignored)
```

---

## Quick start (local)

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
# Edit .env — set RESEND_API_KEY, DIGEST_FROM_EMAIL, DIGEST_TO_EMAILS
```

Export in your shell (or use `direnv`):

```bash
export RESEND_API_KEY=re_...
export DIGEST_FROM_EMAIL="Digest <digest@yourdomain.com>"
export DIGEST_TO_EMAILS="you@example.com,teammate@example.com"
```

### 3. Local run commands

| Goal | Command |
|------|---------|
| Dry-run one digest (no email) | `python -m src.main --digest vscode-weekly --dry-run` |
| Dry-run all due digests | `python -m src.main --due --dry-run` |
| Send one digest | `python -m src.main --digest vscode-weekly` |
| Run all due digests (live send) | `python -m src.main --due` |
| Offline smoke tests | `python tests/smoke_test.py` |
| pytest | `python -m pytest tests/smoke_test.py -v` |

### 4. Preview rendered output

Every run writes `data/rendered/<digest-id>.html`. Open in a browser to
preview the email before sending.

---

## GitHub Codespaces (free tier)

This repo ships with `.devcontainer/devcontainer.json` so you can develop in
the browser without installing Python locally. The devcontainer only installs
project dependencies (Python 3.11 + `requirements.txt`) — it deliberately
does **not** pin a list of VS Code extensions. Your personal extensions,
settings, and keybindings come from **Settings Sync** on your GitHub / VS
Code account, so every Codespace you open looks like your own editor.

### Open the repo in Codespaces

1. On GitHub, click **Code → Codespaces → Create codespace on main**.
2. Wait ~30–60 s for `postCreateCommand` to install Python dependencies.
3. VS Code opens in the browser. Your synced extensions, settings, and
   keybindings load from your GitHub / VS Code account (see Settings Sync
   below).

### Load your personal extensions via Settings Sync

GitHub Codespaces cannot force-install a user's Settings Sync extensions
from a repo config — that list lives on your account, not in this repo.
Make sure Settings Sync is turned on so it flows into every Codespace:

1. Sign in to VS Code (desktop or web) with the **same GitHub account** you
   use for Codespaces.
2. Open the Command Palette (`Ctrl/Cmd+Shift+P`) and run
   **Settings Sync: Turn On…**. Enable at least *Extensions*, *Settings*,
   and *Keybindings*.
3. Open the Codespace. VS Code in the browser (or the desktop client
   attached to the Codespace) will pull your synced extensions and apply
   your settings automatically.
4. If something is missing after the Codespace opens, run
   **Settings Sync: Sync Now** from the Command Palette, or install the
   extension once inside the Codespace — Settings Sync will pick it up for
   next time.

The repo devcontainer intentionally ships **no `extensions` list** so it
won't conflict with or shadow your synced set. Only project-level VS Code
*settings* (Python interpreter path, pytest config, file excludes) are
defined in `.devcontainer/devcontainer.json`.

### Free-tier considerations

GitHub gives free accounts ~120 core-hours/month of Codespaces compute. To
stay well under the quota:

- **Stop the Codespace** when you walk away (Codespaces tab → ⋯ → Stop).
- **Delete the Codespace** when you no longer need it (the container restarts
  fast, so recreating it is cheap).
- The 2-core machine type is the cheapest — keep the default in
  `.devcontainer/devcontainer.json`; do not upgrade unless you need it.
- Auto-stop is on by default (30 min idle). You can lower this in your
  GitHub Codespaces settings.

### Test commands inside the Codespace

Run from the integrated terminal — no `RESEND_API_KEY` is required for any
of these (they are offline / dry-run):

```bash
# Validate workflow generator output (no writes, exit 1 if drift)
python scripts/generate_workflows.py --check

# Regenerate per-digest workflows (writes .github/workflows/digest-*.yml)
python scripts/generate_workflows.py

# Preview a digest's generated workflow without writing to disk
python scripts/generate_workflows.py --dry-run

# Offline smoke tests (no network, no email)
python tests/smoke_test.py

# Same suite via pytest
python -m pytest tests/smoke_test.py -v

# Dry-run a real digest pipeline (writes data/rendered/<id>.html)
python -m src.main --digest vscode-weekly --dry-run
```

### Live sends from a Codespace (optional)

Live sends require Resend credentials. Use **Codespaces secrets**, not the
default Actions secrets — they are separate stores:

1. GitHub → **Settings → Codespaces → Codespaces secrets → New secret**.
2. Add `RESEND_API_KEY`, `DIGEST_FROM_EMAIL`, `DIGEST_TO_EMAILS` and grant
   access to this repository.
3. Restart the Codespace so the env vars become available.
4. `python -m src.main --digest <id>` will now send.

Configure the same three values as **Actions secrets** (Settings → Secrets
and variables → Actions) for the scheduled workflows.

---

## GitHub setup

### 1. Push the repo

Make the repository public on GitHub (the scheduled workflows only run for
public repos on the free tier).

```bash
git remote add origin https://github.com/<you>/<repo>.git
git push -u origin main
```

### 2. Add GitHub Secrets

Go to **Settings → Secrets and variables → Actions** and create:

| Secret | Description |
|--------|-------------|
| `RESEND_API_KEY` | API key from [resend.com](https://resend.com) |
| `DIGEST_FROM_EMAIL` | Verified sender address (e.g. `Digest <digest@yourdomain.com>`) |
| `DIGEST_TO_EMAILS` | Default recipient(s) — comma-separated list, appended to each digest's `email.to` (deduped case-insensitively) |

### 3. Generate per-digest workflows

Run the generator from the project root:

```bash
python scripts/generate_workflows.py
```

This reads every `digests/*.yaml` file and writes
`.github/workflows/digest-<id>.yml` for each **enabled** digest.
Commit and push the generated files:

```bash
git add .github/workflows/
git commit -m "chore: generate per-digest workflows"
git push
```

> **Re-run after every schedule or id change.** The generator is idempotent —
> it only overwrites files whose content changed.

#### Generator options

| Command | Effect |
|---------|--------|
| `python scripts/generate_workflows.py` | Write all workflows |
| `python scripts/generate_workflows.py --dry-run` | Print to stdout, no file writes |
| `python scripts/generate_workflows.py --check` | Exit 1 if any workflow needs updating (CI guard) |

### 4. Automatic scheduled runs

Once the workflows are committed to `main`, GitHub runs each digest on its own
cron automatically. No manual intervention is needed.

Check run history at **Actions → Digest: \<name\>**.

#### UTC cron and DST caveat

GitHub Actions cron is **always UTC**. The generator converts each digest's
`timezone`/`hour`/`minute` to UTC using the timezone's *standard-time* offset
(i.e. the January offset). During daylight saving time the workflow will fire
one hour earlier in wall-clock time. This is a known GitHub Actions limitation.
To compensate for DST, adjust `hour` in the digest YAML by ±1 for the half of
the year you care about, then re-run the generator.

---

## Manual testing in GitHub Actions

### Test a specific digest with dry_run

1. Go to **Actions** → select **Digest: \<name\>** (or **Manual — Run any digest**)
2. Click **Run workflow**
3. Set `dry_run` to `true`
4. Click **Run workflow**

The workflow renders the email HTML and prints `[DRY RUN] would send …` — no
email is sent. Download the rendered artefact from the run summary if you want
to inspect the HTML output.

### Test any digest by id (manual.yml)

Use the **Manual — Run any digest** workflow when you want to trigger a digest
that doesn't have a cron scheduled yet, or when testing a newly added digest:

1. **Actions → Manual — Run any digest → Run workflow**
2. Enter the digest id (e.g. `vscode-weekly`)
3. Set `dry_run: true` for a preview run

---

## Digest YAML schedule fields

```yaml
schedule:
  type: weekly          # "weekly" or "daily"
  day_of_week: friday   # weekly only: monday–sunday
  hour: 18              # local hour (0–23)
  minute: 0             # local minute (0–59)
  timezone: America/Toronto  # IANA timezone name
```

The generator converts these fields to a UTC cron string. For example:

| Local schedule | UTC cron |
|----------------|----------|
| Friday 18:00 America/Toronto (EST=UTC-5) | `0 23 * * 5` |
| Sunday 10:00 America/Toronto (EST=UTC-5) | `0 15 * * 0` |
| Monday 09:00 UTC | `0 9 * * 1` |

---

## Built-in digests

| Digest id | Schedule (local) | Focus |
|-----------|------------------|-------|
| `vscode-weekly` | Mon 05:00 America/Toronto | VS Code updates, Copilot, productivity |
| `ai-tools-weekly` | Mon 05:00 America/Toronto | Claude, Perplexity, Copilot, OpenAI, HuggingFace |
| `general-motors-weekly` | Mon 05:00 America/Toronto | General Motors news, weighted toward GM Canada / Ontario |
| `gta-events-weekly` | Thu 05:00 America/Toronto | GTA events, weighted to free / Scarborough-east-GTA / kid-friendly / clothing sales |
| `galaxy-watch-8-price` *(disabled)* | Daily 05:00 America/Toronto (when enabled) | Price-movement watch across Amazon / Walmart / Best Buy / Costco / Samsung Canada — see template at `digests/galaxy-watch-8-price_OFF.yaml` |

### Enabling the Galaxy Watch 8 price watch

The file `digests/galaxy-watch-8-price_OFF.yaml` ships with `enabled: false`
and a trailing `_OFF` suffix so the generator does NOT emit a scheduled
workflow for it. To turn it on later:

1. Open the file and replace the search-listing placeholder URLs with the
   exact product page URLs for the SKU/colour you want to watch (Amazon,
   Walmart, Best Buy, Costco, Samsung Canada). Search listings work as a
   fallback but the signal is noisier.
2. Rename the file from `galaxy-watch-8-price_OFF.yaml` to
   `galaxy-watch-8-price.yaml` (drop the `_OFF` suffix).
3. Set `enabled: true`.
4. Run `python scripts/generate_workflows.py` and commit the new
   `.github/workflows/digest-galaxy-watch-8-price.yml`.

**Limitations.** This digest reuses the standard content pipeline — it
fetches each retailer URL as a webpage and surfaces items whose text
contains price/deal/drop signals. It does **not** scrape the live price,
diff against yesterday's price, or compare across retailers. Large
retailers (Amazon, Best Buy, Walmart) render prices client-side via
JavaScript, which `requests` + BeautifulSoup cannot evaluate; on those
sources the digest acts as a "something on this page now mentions sale /
clearance / price drop" heuristic. For more reliable single-SKU tracking,
add the exact product URL for the variant you care about and pair this
with a price-alert service (e.g. RedFlagDeals, camelcamelcamel) if you
need cent-level accuracy.

### GTA events digest

`gta-events-weekly` runs Thursday 05:00 America/Toronto (10:00 UTC under
EST) and scans the City of Toronto events calendar, Kids Out and About,
Eventbrite Scarborough/Toronto, Child's Life Scarborough, ChatterBlock,
StyleDemocracy sale roundups, and Reddit r/Scarborough + r/askTO. Scoring
heavily weights *free*, *Scarborough / east end / east Toronto*, *kids /
family*, and *warehouse sale / sample sale / clothing / shoes*. Protests,
rallies, marches, political events, 19+ / nightclub / alcohol-only
events, job fairs, webinars, and crypto/investment pitches are excluded.

Manual local preview (no email):

```bash
python -m src.main --digest gta-events-weekly --dry-run
# open data/rendered/gta-events-weekly.html in a browser
```

---

## Adding a new digest

1. Copy any existing file in `digests/`, change `id`, `schedule`, `sources`,
   `filters`, and `email.subject`.
2. Re-run `python scripts/generate_workflows.py`.
3. Commit and push — the new workflow is live immediately.

> **Re-run the generator after any schedule or source change.** Even though
> source updates do not affect cron, running `python scripts/generate_workflows.py`
> after editing any digest YAML is the simplest way to keep `.github/workflows/`
> in sync — `--check` will fail CI if drift is detected.

## Optional: weighted keywords

Digests can boost certain terms by adding a `keyword_weights` map under
`scoring:`. Matching the term in either the title or summary adds the given
weight. Digests that omit `keyword_weights` keep the original scoring behavior.

```yaml
scoring:
  keyword_hit: 2
  title_keyword_hit: 4
  keyword_weights:
    canada: 5
    oshawa: 6
    ontario: 5
```

---

## Required GitHub Secrets

| Secret | Description |
|--------|-------------|
| `RESEND_API_KEY` | API key from [resend.com](https://resend.com) |
| `DIGEST_FROM_EMAIL` | Verified sender address |
| `DIGEST_TO_EMAILS` | Default recipient(s), comma-separated (optional if `email.to` is set in YAML) |

## DIGEST_FROM_EMAIL format

Use an address on the domain/subdomain you verified in Resend:

- `Vishal Digest <digest@updates.example.com>`
- `digest@updates.example.com`

---

## Notes

- Rotate any API key that was exposed outside your secret store.
- GitHub Actions cron runs in UTC (see DST caveat above).
- SQLite state file (`data/state.db`) is git-ignored; it is created on first run.
- Source fetching is best-effort: if one source fails the others still run and a
  `[WARN]` is printed.
- `.github/workflows/digest-*.yml` files are auto-generated — commit them but
  do not edit them manually; edit the digest YAML and re-run the generator.
