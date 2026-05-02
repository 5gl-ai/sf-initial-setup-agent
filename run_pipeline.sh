#!/usr/bin/env bash
# Orchestrator for the metadata bootstrap pipeline.
#
# Runs scripts/NN_*.{sh,py} in numeric order. Each script's combined
# stdout/stderr is tee'd to logs/NN_<name>.log under the project directory.
# On the first nonzero exit, prints which step failed and the log path,
# then exits nonzero so the calling agent (or human) can act.
#
# Required env vars:
#   ALIAS                 — Salesforce org alias
#   USERNAME              — expected Salesforce username (sanity-checked in 01_auth)
#   SANDBOX               — 1 (sandbox) or 0 (production)
#   PROJECT_PARENT_DIR    — directory in which $ALIAS-metadata will be created
#
# Optional env vars:
#   AGENT_VERSION         — recorded in .5gl-sync-state.json (default: "unknown")
#   START_FROM=<step>     — skip everything alphabetically before this step name
#                           (e.g., START_FROM=05_complete_profiles.py)
#   ONLY=<step>           — run exactly this one step
set -uo pipefail

: "${ALIAS:?required}"
: "${USERNAME:?required}"
: "${SANDBOX:?required}"
: "${PROJECT_PARENT_DIR:?required}"

# Derived. Available to all steps.
export PROJECT_DIR="$PROJECT_PARENT_DIR/$ALIAS-metadata"
export AGENT_VERSION="${AGENT_VERSION:-unknown}"

repo_root="$(cd "$(dirname "$0")" && pwd)"
scripts_dir="$repo_root/scripts"

# Logs go inside the project dir once it exists. Before that (steps 01-02),
# log to a temp dir under the project parent so we still capture output.
if [ -d "$PROJECT_DIR" ]; then
  log_dir="$PROJECT_DIR/logs"
else
  log_dir="$PROJECT_PARENT_DIR/$ALIAS-metadata-logs"
fi
mkdir -p "$log_dir"

echo ""
echo "  ════════════════════════════════════════════════════════════"
echo "  5GL SF Metadata Bootstrap Pipeline (agent v$AGENT_VERSION)"
echo "  ════════════════════════════════════════════════════════════"
echo "  Org alias:    $ALIAS"
echo "  Username:     $USERNAME"
echo "  Environment:  $([ "$SANDBOX" = "1" ] && echo SANDBOX || echo PRODUCTION)"
echo "  Project dir:  $PROJECT_DIR"
echo "  Logs dir:     $log_dir"
echo ""

# After step 02 succeeds the project dir exists, so move the logs in.
relocate_logs_if_needed() {
  if [ -d "$PROJECT_DIR" ] && [ "$log_dir" != "$PROJECT_DIR/logs" ]; then
    mkdir -p "$PROJECT_DIR/logs"
    mv "$log_dir"/* "$PROJECT_DIR/logs/" 2>/dev/null || true
    rmdir "$log_dir" 2>/dev/null || true
    log_dir="$PROJECT_DIR/logs"
  fi
}

run_step() {
  local script="$1"
  local name
  name="$(basename "$script")"
  local log="$log_dir/${name%.*}.log"

  echo "  ──────────────────────────────────────────"
  echo "  ▶ $name"
  echo "  ──────────────────────────────────────────"

  set +e
  "$script" 2>&1 | tee "$log"
  local rc=${PIPESTATUS[0]}
  set -e

  if [ "$rc" -ne 0 ]; then
    echo ""
    echo "  ❌ FAILED: $name (exit $rc)"
    echo "     Log: $log"
    return "$rc"
  fi

  relocate_logs_if_needed
  return 0
}

# Discover steps by sorted filename. Skips _lib.py and any underscore-prefixed
# file. Uses while-read instead of mapfile because macOS ships bash 3.2.
steps=()
while IFS= read -r line; do
  steps+=("$line")
done < <(find "$scripts_dir" -maxdepth 1 -type f \
  \( -name '[0-9][0-9]_*.sh' -o -name '[0-9][0-9]_*.py' \) | sort)

# Filter by START_FROM / ONLY if set.
filtered=()
for s in "${steps[@]}"; do
  name="$(basename "$s")"
  if [ -n "${ONLY:-}" ] && [ "$name" != "$ONLY" ]; then
    continue
  fi
  if [ -n "${START_FROM:-}" ] && [ "$name" \< "$START_FROM" ]; then
    continue
  fi
  filtered+=("$s")
done

if [ "${#filtered[@]}" -eq 0 ]; then
  echo "  ERROR: no steps matched START_FROM='${START_FROM:-}' / ONLY='${ONLY:-}'" >&2
  exit 2
fi

for step in "${filtered[@]}"; do
  if ! run_step "$step"; then
    exit 1
  fi
done

echo ""
echo "  ════════════════════════════════════════════════════════════"
echo "  ✅ Pipeline complete."
echo "  ════════════════════════════════════════════════════════════"
