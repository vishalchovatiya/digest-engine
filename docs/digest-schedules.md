# Digest schedules

Auto-generated from `digests/*.yaml` by `scripts/generate_workflows.py --schedules-doc`.
Edit the digest YAMLs (not this file) and re-run the generator.

## Active digests

| Digest id | Type | Schedule (local) | UTC cron | Workflow file | Purpose |
|---|---|---|---|---|---|
| `ai-tools-weekly` | content | Monday 05:00 America/Toronto | `0 10 * * 1` | `.github/workflows/digest-ai-tools-weekly.yml` | Weekly AI tooling changes that are most relevant to practical daily use. |
| `general-motors-weekly` | content | Monday 05:00 America/Toronto | `0 10 * * 1` | `.github/workflows/digest-general-motors-weekly.yml` | Weekly GM updates with extra priority for Canada/Ontario operations and engineering-relevant news. |
| `gta-events-weekly` | content | Thursday 05:00 America/Toronto | `0 10 * * 4` | `.github/workflows/digest-gta-events-weekly.yml` | Thursday morning scan for practical GTA events, prioritizing free, Scarborough/east-GTA, kid-friendly, and clothing sale opportunities. Distance from Scarboroug |
| `vscode-weekly` | content | Monday 05:00 America/Toronto | `0 10 * * 1` | `.github/workflows/digest-vscode-weekly.yml` | Weekly VS Code features and workflow improvements worth trying. |

## Disabled templates (`*.yaml_OFF`)

Templates ship in the repo but are not active. Rename to `*.yaml` and re-run the generator to enable.

- `digests/product-price-watch.yaml_OFF`
