# sf-initial-setup-agent

Bootstraps a complete Salesforce metadata project for an org. Given a username and alias, it authenticates, generates a comprehensive manifest (filling the gaps the default `sf project generate manifest --from-org` leaves), strips managed-package noise, and retrieves everything for source-controlled work.

Built and maintained by [5GL.ai](https://5gl.ai), a Salesforce consulting firm.

## Architecture (v0.2)

The bootstrap workflow is a deterministic pipeline of shell and Python scripts under `scripts/`, run by `run_pipeline.sh`. The Python agent is a **supervisor**, not the executor:

- **Happy path:** the pipeline runs end-to-end with no LLM in the loop. Fast, cheap, deterministic, inspectable.
- **Failure path:** when a step fails, the agent loads the failed step's log into Claude (Sonnet 4.6), gives it a focused tool surface (`read_log`, `rerun_step`, `resume_pipeline`, `read_file`, `write_file`, `run_sf`, `run_shell`), and lets Claude diagnose, fix, and retry.

You can also run `./run_pipeline.sh` directly — without the agent, without an Anthropic key — for CI or scripted use.

## What the pipeline does

| Step | Script | What it does |
|---|---|---|
| 01 | `01_auth.sh` | Verify the user is authed as the expected username; run `sf org login web` if not |
| 02 | `02_create_project.sh` | Scaffold the SFDX project at `<dir>/<alias>-metadata` |
| 03 | `03_pin_api_version.py` | Pin `sourceApiVersion` to the org's max so newer types aren't invisible |
| 04 | `04_generate_manifest.sh` | Generate the initial manifest from the org |
| 05 | `05_complete_profiles.py` | Add the parent types Profile/PermissionSet reference (otherwise they retrieve gutted) |
| 06 | `06_enumerate_folders.py` | Enumerate Report/Dashboard/Document/EmailTemplate folders explicitly |
| 07 | `07_detect_communities.py` | If Experience Cloud is on, add `Network`/`ExperienceBundle`/`CustomSite`/etc. |
| 08 | `08_strip_managed.py` | Remove `InstalledPackage` and any namespaced members |
| 09 | `09_detect_omnistudio.py` | Warn if OmniStudio/Vlocity/Industry Cloud is present (separate toolchain) |
| 10 | `10_retrieve.sh` | `sf project retrieve start --wait 3600` |
| 11 | `11_summarize.sh` | Print file count and project paths |
| 12 | `12_record_sync_state.py` | Write `.5gl-sync-state.json` for a future monitoring agent |

## What's NOT included (by design)

- **Data** (records of any object) — separate `sf-data-export-agent` planned
- **OmniStudio / Vlocity / Industry Cloud** metadata — uses a different metadata system; the pipeline detects and warns
- **Tooling-API-only items** like Setup Audit Trail history, Apex test coverage, debug logs — separate monitoring agent planned
- **Managed-package internals** — intentionally stripped

## Prerequisites

- macOS
- [Salesforce CLI v2](https://developer.salesforce.com/tools/salesforcecli) (`sf`) — installed automatically by `setup.sh` if `npm` is available
- Node.js (for the `sf` install)
- Python 3.9+
- An Anthropic API key (only needed if a step fails and you want repair-mode help) — get one at [console.anthropic.com](https://console.anthropic.com)
- A Salesforce org you can authenticate to

## Install

```bash
git clone https://github.com/5GL-ai/sf-initial-setup-agent.git
cd sf-initial-setup-agent
./setup.sh
./run.sh
```

On first run the agent prompts for your Anthropic API key (input hidden) and saves it to `~/.5gl-agents-env` as the shared key for all 5GL agents. Subsequent runs read it from there automatically.

A one-command installer (`5GL-ai/sf-agent-installer`) is in development.

## Running

### Default (agent supervises)

```bash
./run.sh
```

You'll be prompted for: Salesforce username, sandbox flag, org alias, and a project parent directory (via the macOS folder picker). Last-used values are remembered in `~/.sf-initial-setup-agent-config.json`.

If the pipeline succeeds, the agent exits (with an option to ask Claude a follow-up question). If it fails, the agent loads the failed step's log and works with you to fix it.

### Pipeline-only (no LLM, e.g. for CI)

```bash
ALIAS=AcmeProd \
USERNAME=steve@acme.com \
SANDBOX=0 \
PROJECT_PARENT_DIR=$HOME/sf-projects \
AGENT_VERSION=ci \
./run_pipeline.sh
```

Useful env vars:
- `START_FROM=05_complete_profiles.py` — skip earlier steps
- `ONLY=10_retrieve.sh` — run exactly one step

Logs land in `<project_dir>/logs/`.

## Environment variables

The agent reads `FIVEGL_ANTHROPIC_API_KEY` first, then falls back to `ANTHROPIC_API_KEY`. The namespaced name lets the agent coexist with other tools (Cursor, Claude Code, etc.) that use the standard `ANTHROPIC_API_KEY`.

## Safety

- `read_file` / `write_file` are confined to the project directory you select.
- `run_shell` refuses commands that reference `~/.sfdx`, `~/.ssh`, `~/.aws`, dotfiles, the `gh` config dir, or `~/.5gl-agents-env`.
- The agent confirms before destructive operations.
- Step `01_auth.sh` aborts if the authenticated org's username doesn't match what you typed (case-insensitive) — guards against retrieving from the wrong org.

## Sync state

After a successful retrieve, `12_record_sync_state.py` writes `<project>/.5gl-sync-state.json` with timestamp, org id, manifest hash, and file count. A future monitoring agent will read this to query `SetupAuditTrail` for what changed since the last sync and offer incremental re-retrieves.

## Disclaimer

Provided as-is. The agent runs commands against your Salesforce org and your local filesystem. Review what it's doing — it pauses before destructive operations, but you should still understand each step. Not affiliated with or endorsed by Salesforce, Inc.
