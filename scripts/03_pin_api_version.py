#!/usr/bin/env python3
"""Pin the SFDX project's sourceApiVersion to the org's max API version.

The default `sf project generate` picks an API version that may lag behind
the org. Pinning to the org's max ensures newer metadata types are visible.

Reads: ALIAS, PROJECT_PARENT_DIR (via _lib.env)
"""
import json, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _lib import env, project_dir, sf_json, info, warn  # noqa: E402


def main():
    alias = env("ALIAS")
    info(f"Querying org '{alias}' for max API version...")

    org = sf_json(["org", "display", "--target-org", alias])
    org_api = org.get("apiVersion")
    if not org_api:
        warn("Could not determine org's API version; leaving project default.")
        return

    sfdx_path = project_dir() / "sfdx-project.json"
    cfg = json.loads(sfdx_path.read_text())
    old = cfg.get("sourceApiVersion", "(unset)")
    cfg["sourceApiVersion"] = org_api
    sfdx_path.write_text(json.dumps(cfg, indent=2) + "\n")
    info(f"sourceApiVersion: {old} → {org_api}")


if __name__ == "__main__":
    main()
