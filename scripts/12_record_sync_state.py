#!/usr/bin/env python3
"""Write .5gl-sync-state.json so a future monitoring agent knows the
last time this org was synced and can diff SetupAuditTrail from there.

Reads: ALIAS, USERNAME, PROJECT_PARENT_DIR (via _lib.env), AGENT_VERSION
"""
import os, sys, json, hashlib
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _lib import env, project_dir, manifest_path, sf_json, info  # noqa: E402

AGENT_NAME = "sf-initial-setup-agent"


def main():
    alias = env("ALIAS")
    username = env("USERNAME")
    agent_version = os.environ.get("AGENT_VERSION", "unknown")

    org = sf_json(["org", "display", "--target-org", alias])
    org_id = org.get("id")

    manifest_bytes = manifest_path().read_bytes()
    manifest_hash = "sha256:" + hashlib.sha256(manifest_bytes).hexdigest()

    file_count = sum(1 for _ in (project_dir() / "force-app").rglob("*") if _.is_file())

    state = {
        "alias": alias,
        "org_id": org_id,
        "username": username,
        "synced_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "synced_by_agent": AGENT_NAME,
        "synced_by_version": agent_version,
        "manifest_hash": manifest_hash,
        "file_count": file_count,
    }

    state_path = project_dir() / ".5gl-sync-state.json"
    state_path.write_text(json.dumps(state, indent=2) + "\n")
    info(f"Wrote sync state to {state_path}")


if __name__ == "__main__":
    main()
