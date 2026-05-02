#!/usr/bin/env python3
"""Remove managed-package metadata from the manifest.

Strips:
  - The InstalledPackage type entirely.
  - Any member whose name starts with `<namespace>__` for any installed
    managed package's namespace prefix.

Reads: ALIAS, PROJECT_PARENT_DIR (via _lib.env)
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _lib import load_manifest, save_manifest, installed_namespaces, info  # noqa: E402


def is_managed(member_name, namespaces):
    return any(member_name.startswith(ns + "__") for ns in namespaces)


def main():
    namespaces = installed_namespaces()
    if not namespaces:
        info("No installed packages detected — nothing to strip.")
        # Still drop InstalledPackage type if it crept in from --from-org.
    else:
        info(f"Installed packages: {', '.join(sorted(namespaces))}")

    types, version = load_manifest()
    removed = 0

    if "InstalledPackage" in types:
        removed += len(types["InstalledPackage"])
        del types["InstalledPackage"]

    for type_name, members in list(types.items()):
        if not namespaces:
            continue
        kept = {m for m in members if not is_managed(m, namespaces)}
        diff = len(members) - len(kept)
        if diff:
            removed += diff
            types[type_name] = kept

    # Drop types that are now empty.
    for type_name in [t for t, m in types.items() if not m]:
        del types[type_name]

    save_manifest(types, version)
    info(f"✅ Stripped {removed} managed-package member(s).")


if __name__ == "__main__":
    main()
