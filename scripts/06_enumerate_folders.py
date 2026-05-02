#!/usr/bin/env python3
"""Enumerate folder-based metadata so subfolders are not silently dropped.

For each folder-typed metadata (Report, Dashboard, Document, EmailTemplate),
list every folder in the org and add each folder's contents to the manifest
explicitly. The default `--from-org` manifest often misses subfolders.

Reads: ALIAS, PROJECT_PARENT_DIR (via _lib.env)
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _lib import load_manifest, save_manifest, list_metadata, info  # noqa: E402

# Each entry: (item_type, folder_type). Folder type is what `sf org list
# metadata --metadata-type X` returns when X is a *Folder type.
FOLDERED = [
    ("Report", "ReportFolder"),
    ("Dashboard", "DashboardFolder"),
    ("Document", "DocumentFolder"),
    ("EmailTemplate", "EmailFolder"),
]


def main():
    types, version = load_manifest()
    total_added = 0

    for item_type, folder_type in FOLDERED:
        folders = list_metadata(folder_type)
        if not folders:
            continue
        # Always include the folder itself so folder permissions are retrieved.
        types.setdefault(item_type, set())
        for folder in folders:
            folder_name = folder.get("fullName")
            if not folder_name:
                continue
            types[item_type].add(folder_name)  # the folder itself
            items = list_metadata(item_type, folder=folder_name)
            for item in items:
                full_name = item.get("fullName")
                if full_name:
                    if full_name not in types[item_type]:
                        total_added += 1
                    types[item_type].add(full_name)
        info(f"{item_type}: enumerated {len(folders)} folder(s)")

    save_manifest(types, version)
    info(f"✅ Added {total_added} folder-scoped member(s).")


if __name__ == "__main__":
    main()
