#!/usr/bin/env python3
"""If the org uses Experience Cloud (Communities), add the relevant types.

The default `--from-org` manifest historically has spotty coverage of
Experience Cloud metadata. This step detects Network presence and adds the
full set of related types explicitly.

Reads: ALIAS, PROJECT_PARENT_DIR (via _lib.env)
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _lib import load_manifest, save_manifest, list_metadata, info  # noqa: E402

EXPERIENCE_TYPES = [
    "Network",
    "ExperienceBundle",
    "CustomSite",
    "SiteDotCom",
    "NavigationMenu",
    "ManagedTopics",
    "Audience",
    "CommunityTemplateDefinition",
    "CommunityThemeDefinition",
    "ContentAsset",
    "BrandingSet",
]


def main():
    networks = list_metadata("Network")
    if not networks:
        info("No Experience Cloud networks detected — skipping.")
        return

    info(f"Detected {len(networks)} Experience Cloud network(s); adding related types.")
    types, version = load_manifest()

    total_added = 0
    for t in EXPERIENCE_TYPES:
        members = {m["fullName"] for m in list_metadata(t) if m.get("fullName")}
        if not members:
            continue
        existing = types.get(t, set())
        new = members - existing
        if new:
            types.setdefault(t, set()).update(new)
            total_added += len(new)
            info(f"+{len(new):>5} {t}")

    save_manifest(types, version)
    info(f"✅ Added {total_added} Experience Cloud member(s).")


if __name__ == "__main__":
    main()
