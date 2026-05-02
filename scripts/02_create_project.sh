#!/usr/bin/env bash
# Scaffold an SFDX project at $PROJECT_PARENT_DIR/$ALIAS-metadata.
# Refuses to overwrite an existing project — the agent's repair mode handles
# that case (rename / reuse / abort).
#
# Reads: ALIAS, PROJECT_PARENT_DIR
set -euo pipefail

: "${ALIAS:?required}"
: "${PROJECT_PARENT_DIR:?required}"

target="$PROJECT_PARENT_DIR/$ALIAS-metadata"

if [ -e "$target" ]; then
  echo "ERROR: $target already exists." >&2
  echo "       Pick a new alias, delete the existing folder, or" >&2
  echo "       resume from a later step if this project is already set up." >&2
  exit 1
fi

echo "  Generating SFDX project at $target"
cd "$PROJECT_PARENT_DIR"
sf project generate --name "$ALIAS-metadata" --output-dir "$PROJECT_PARENT_DIR"
echo "  ✅ Project created."
