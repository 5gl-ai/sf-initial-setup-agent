#!/usr/bin/env bash
# If `./setup.sh` says "permission denied" (e.g. when first running this from
# a Google-Drive-synced copy of the repo on a new machine — Drive doesn't
# always preserve the POSIX executable bit), bootstrap with `bash setup.sh`
# instead. This script will then chmod the rest of the runnables for you.
set -e
cd "$(dirname "$0")"

# Self-heal mode bits in case Drive sync (or a fresh extract) stripped them.
chmod +x setup.sh run.sh \
         prereqs.py retrieve_metadata.py web_ui.py troubleshoot.py sf_initial_setup_agent.py \
         2>/dev/null || true
chmod +x *.command 2>/dev/null || true

VENV="$HOME/.sf-initial-setup-agent-venv"
[ -d "$VENV" ] || python3 -m venv "$VENV"
# shellcheck disable=SC1091
source "$VENV/bin/activate"
pip install -q --upgrade pip
pip install -q -r requirements.txt

command -v sf >/dev/null || {
  echo "Installing Salesforce CLI..."
  npm install -g @salesforce/cli
}

# The agent prompts for an Anthropic API key on first run if one isn't found
# in the environment or ~/.5gl-agents-env, so no key check is needed here.

echo "✅ Ready. Run ./run.sh  (or double-click 'Run sf-initial-setup-agent.command' in Finder)"
