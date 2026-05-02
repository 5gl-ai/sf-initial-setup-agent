#!/usr/bin/env bash
# Retrieve all metadata in the manifest. Long --wait because v0.2.0
# manifests can be large (profile completion alone can grow the manifest
# 10-100x for mature orgs).
#
# If the retrieve times out, the CLI emits a job id. The agent's repair
# mode handles `sf project retrieve resume --job-id <id>` from there.
#
# Reads: ALIAS, PROJECT_DIR
set -euo pipefail

: "${ALIAS:?required}"
: "${PROJECT_DIR:?required}"

cd "$PROJECT_DIR"

manifest_size=$(wc -l < manifest/package.xml | tr -d ' ')
echo "  Manifest is $manifest_size lines."
echo "  Starting retrieve (--wait 3600). This can take a while on large orgs."

sf project retrieve start \
  --manifest manifest/package.xml \
  --target-org "$ALIAS" \
  --wait 3600

echo "  ✅ Retrieve complete."
