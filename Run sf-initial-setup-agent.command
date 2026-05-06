#!/usr/bin/env bash
# Double-click launcher for the sf-initial-setup-agent.
# Opens a Terminal window in the agent dir (when launched from Finder),
# then runs ./run.sh which starts the local web UI and opens your browser.
cd "$(dirname "$0")"
printf '\033]0;sf-initial-setup-agent (running)\007'
exec ./run.sh
