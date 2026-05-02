#!/usr/bin/env python3
"""Add the parent types that Profiles and PermissionSets reference.

If Profile or PermissionSet are in the manifest WITHOUT the types they grant
permissions on, they retrieve as gutted shells (no FLS, no object perms, no
Apex class access, etc.). This step ensures every parent type is present.

Reads: ALIAS, PROJECT_PARENT_DIR (via _lib.env)
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _lib import load_manifest, save_manifest, list_metadata, info  # noqa: E402

# Types that Profile / PermissionSet grant permissions on. Without these in
# the manifest, the retrieved Profile/PermissionSet XML has no permissions.
PARENT_TYPES = [
    "ApexClass",
    "ApexPage",
    "CustomApplication",
    "CustomMetadata",
    "CustomObject",
    "CustomPermission",
    "CustomTab",
    "ExternalDataSource",
    "FlexiPage",
    "Layout",
    "RecordType",
]


def main():
    types, version = load_manifest()

    if "Profile" not in types and "PermissionSet" not in types:
        info("No Profile or PermissionSet in manifest — nothing to complete.")
        return

    added_count = 0
    for t in PARENT_TYPES:
        existing = types.get(t, set())
        members = {m["fullName"] for m in list_metadata(t) if m.get("fullName")}
        new = members - existing
        if new:
            info(f"+{len(new):>5} {t}")
            types.setdefault(t, set()).update(new)
            added_count += len(new)

    save_manifest(types, version)
    info(f"✅ Added {added_count} member(s) across {len(PARENT_TYPES)} parent types.")


if __name__ == "__main__":
    main()
