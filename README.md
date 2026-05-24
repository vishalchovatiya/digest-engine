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
- Multi-product CAD price watch (one digest tracks many products & retailers)
- URL/title deduplication and clustering across sources
- Per-source health logs in SQLite + `--health` CLI
- Schema validation of digest YAMLs (generator fails fast on bad config)
- SQLite state tracking — no duplicate sends across runs, auto-pruned
- Resend email delivery

See [docs/digest-schedules.md](docs/digest-schedules.md) for the current
list of digests, their schedules, and the workflow files they generate.

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

See the auto-generated [docs/digest-schedules.md](docs/digest-schedules.md)
for the canonical list (it is rewritten every time you run
`scripts/generate_workflows.py`).

| Digest id | Schedule (local) | Focus |
|-----------|------------------|-------|
| `vscode-weekly` | Mon 05:00 America/Toronto | VS Code updates, Copilot, productivity |
| `ai-tools-weekly` | Mon 05:00 America/Toronto | Claude, Perplexity, Copilot, OpenAI, HuggingFace |
| `general-motors-weekly` | Mon 05:00 America/Toronto | General Motors news, weighted toward GM Canada / Ontario |
| `gta-events-weekly` | Thu 05:00 America/Toronto | GTA events, weighted to free / Scarborough-east-GTA / kid-friendly / clothing sales |
| `product-price-watch` *(disabled)* | Daily 05:00 America/Toronto (when enabled) | Multi-product price watch — one digest, many products & retailers. See `digests/product-price-watch.yaml_OFF` |

### Disabled digest templates (`*.yaml_OFF`)

Templates that ship in the repo but are not active use the `.yaml_OFF`
extension. The loader and the workflow generator both glob `digests/*.yaml`,
so a `.yaml_OFF` file is naturally invisible to them — no special-case code,
flag, or test is needed to keep it dormant.

To enable a disabled template:

1. Rename the file from `<name>.yaml_OFF` to `<name>.yaml`.
2. Open it and review the `id:` field plus any placeholder URLs or settings
   the template flagged in its header comment.
3. Run `python scripts/generate_workflows.py` to emit
   `.github/workflows/digest-<id>.yml`.
4. Run the smoke tests: `python tests/smoke_test.py`.
5. Commit the renamed YAML and the new workflow.

### Enabling the multi-product price watch

`digests/product-price-watch.yaml_OFF` is a *single* digest that tracks
real CAD prices for *many* products. You don't need a separate digest
per product — add products under the `products:` list.

```yaml
type: price_watch
products:
  - id: galaxy-watch-8
    name: Samsung Galaxy Watch 8 (44mm)
    desired_price_cad: 399.99
    urls:
      - retailer: Best Buy Canada
        url: https://www.bestbuy.ca/en-ca/product/...
      - retailer: Walmart Canada
        url: https://www.walmart.ca/en/ip/...
  - id: pixel-9
    name: Google Pixel 9
    desired_price_cad: 799.99
    urls:
      - retailer: Best Buy Canada
        url: https://www.bestbuy.ca/en-ca/product/...
```

To enable:

1. Open `digests/product-price-watch.yaml_OFF` and fill in real product-page
   URLs (prefer exact SKU pages, not search listings).
2. Rename the file from `product-price-watch.yaml_OFF` to
   `product-price-watch.yaml`.
3. Run `python scripts/generate_workflows.py` and commit the new
   `.github/workflows/digest-product-price-watch.yml`.

**How it works.** `src/price_tracker.py` fetches each URL, extracts the
most likely CAD price via JSON-LD then a visible-text regex, persists the
observation to SQLite (`price_history` table), and surfaces an item when
the price is first observed, changes vs the previous run, or drops to/
below `desired_price_cad`. Email is rendered through the standard
template; the title shows retailer, current price, previous price, change
direction, and threshold flag.

**Limitations.** Some retailers (Amazon, Walmart, Best Buy) render prices
client-side via JavaScript; for those URLs the digest reports "price
unavailable". Pair this digest with camelcamelcamel/RedFlagDeals if you
need cent-level accuracy on a JS-rendered page.

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

## Source health logs

Every source fetch is recorded in the SQLite `source_health` table at
`data/state.db`. For each source we store:

| Column | Meaning |
|--------|---------|
| `digest_id` | which digest fetched it |
| `source_url` | the URL that was fetched |
| `status` | `ok` (items returned), `empty` (no items), or `error` |
| `item_count` | number of items the fetch returned |
| `duration_ms` | how long the fetch took |
| `error` | exception message when `status='error'` |
| `run_utc` | timestamp of the fetch |

View recent health from the CLI:

```bash
# Last 100 source fetches across all digests
python -m src.main --health

# Filtered to one digest
python -m src.main --health --digest gta-events-weekly
```

This is the fastest way to spot a broken feed before it starts dropping
items from your inbox.

## State DB pruning

`data/state.db` is the only persisted state. To keep it small, the engine
auto-prunes old rows on every digest run with these retention windows:

- `sent_items` — 30 days (no duplicate sends within the window)
- `source_health` — 60 days of fetch history
- `price_history` — 180 days of price observations

You can also prune manually:

```bash
python -m src.main --prune
```

## Deduplication & clustering

The pipeline normalizes URLs (strips `utm_*`, `gclid`, `fbclid`, anchors)
and clusters items with high title-token overlap (Jaccard ≥ 0.6). For each
cluster the highest-scored item wins and its summary is annotated with
`+N duplicate source(s)` so you can see how many feeds carried the story.
This is fully deterministic — no LLM involved.

## Notes

- Rotate any API key that was exposed outside your secret store.
- GitHub Actions cron runs in UTC (see DST caveat above).
- SQLite state file (`data/state.db`) is git-ignored; it is created on first run.
- Source fetching is best-effort: if one source fails the others still run and a
  `[WARN]` is printed.
- `.github/workflows/digest-*.yml` files are auto-generated — commit them but
  do not edit them manually; edit the digest YAML and re-run the generator.
