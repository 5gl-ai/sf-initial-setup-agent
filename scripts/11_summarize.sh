#!/usr/bin/env bash
# Print a brief summary of what was retrieved.
#
# Reads: ALIAS, PROJECT_DIR
set -euo pipefail

: "${ALIAS:?required}"
: "${PROJECT_DIR:?required}"

cd "$PROJECT_DIR"

file_count=$(find force-app -type f 2>/dev/null | wc -l | tr -d ' ')
type_count=$(grep -c '<name>' manifest/package.xml || echo 0)

echo ""
echo "  ────────────────────────────────────────"
echo "  Retrieve summary for org '$ALIAS'"
echo "  ────────────────────────────────────────"
echo "  Project:     $PROJECT_DIR"
echo "  Files:       $file_count"
echo "  Type entries: $type_count"
echo "  Manifest:    $PROJECT_DIR/manifest/package.xml"
echo ""
