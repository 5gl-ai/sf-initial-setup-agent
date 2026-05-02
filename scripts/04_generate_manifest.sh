#!/usr/bin/env bash
# Generate the initial manifest from the org. Subsequent steps fill in the
# gaps (profile parent types, folder contents, Experience Cloud, etc.).
#
# Reads: ALIAS, PROJECT_DIR
set -euo pipefail

: "${ALIAS:?required}"
: "${PROJECT_DIR:?required}"

echo "  Generating manifest from org '$ALIAS'..."
cd "$PROJECT_DIR"
sf project generate manifest \
  --from-org "$ALIAS" \
  --output-dir manifest \
  --name package
echo "  ✅ Wrote $PROJECT_DIR/manifest/package.xml"
