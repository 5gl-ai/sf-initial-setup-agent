#!/usr/bin/env bash
# Verify the user is authenticated as ALIAS, log them in via browser if not,
# then confirm the authenticated username matches USERNAME (case-insensitive).
#
# Reads: ALIAS, USERNAME, SANDBOX (1=sandbox, 0=production)
set -euo pipefail

: "${ALIAS:?required}"
: "${USERNAME:?required}"
: "${SANDBOX:?required}"

instance="https://login.salesforce.com"
[ "$SANDBOX" = "1" ] && instance="https://test.salesforce.com"

echo "  Checking auth for alias '$ALIAS'..."

if sf org display --target-org "$ALIAS" --json >/dev/null 2>&1; then
  echo "  Already authenticated."
else
  echo "  Not authenticated — opening browser for $instance"
  sf org login web --alias "$ALIAS" --instance-url "$instance"
fi

# Confirm the org we're now talking to matches the user's intent.
authed_user=$(sf org display --target-org "$ALIAS" --json | python3 -c \
  'import sys, json; print(json.load(sys.stdin)["result"]["username"])')

if [ "$(echo "$authed_user" | tr "[:upper:]" "[:lower:]")" != \
     "$(echo "$USERNAME" | tr "[:upper:]" "[:lower:]")" ]; then
  echo "ERROR: alias '$ALIAS' is authenticated as '$authed_user'," >&2
  echo "       but you said the username should be '$USERNAME'." >&2
  echo "       Refusing to proceed — wrong org would be a disaster." >&2
  echo "       Fix: run 'sf org logout --target-org $ALIAS' and re-run." >&2
  exit 1
fi

echo "  ✅ Authenticated as $authed_user"
