#!/usr/bin/env python3
"""Detect OmniStudio / Vlocity / Industry Cloud and warn the user.

These use metadata systems not covered by the standard Metadata API. We
don't try to handle them — we tell the user explicitly so they don't
assume the retrieve was complete.

Reads: ALIAS (via _lib.env)
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _lib import installed_namespaces, info, warn  # noqa: E402

# Namespace -> friendly label and what the user needs to retrieve it.
SPECIAL_PACKAGES = {
    "vlocity_cmt":   ("Vlocity Communications",        "Vlocity Build CLI (npm install -g vlocity)"),
    "vlocity_ins":   ("Vlocity Insurance",             "Vlocity Build CLI (npm install -g vlocity)"),
    "vlocity_ps":    ("Vlocity Public Sector",         "Vlocity Build CLI (npm install -g vlocity)"),
    "omnistudio":    ("Salesforce OmniStudio",         "OmniStudio Migration Tool"),
    "industries":    ("Salesforce Industries",         "Industry-specific migration tooling"),
    "FinServ":       ("Financial Services Cloud",      "FSC-specific data packs (mostly standard MD-API)"),
    "HealthCloudGA": ("Health Cloud",                  "Health Cloud-specific data packs (mostly standard MD-API)"),
}


def main():
    namespaces = installed_namespaces()
    found = [(ns, *SPECIAL_PACKAGES[ns]) for ns in namespaces if ns in SPECIAL_PACKAGES]

    if not found:
        info("No OmniStudio / Industry Cloud accelerators detected.")
        return

    print("")
    warn("Detected packages with metadata NOT covered by the Metadata API:")
    for ns, label, tool in found:
        print(f"     • {label} ({ns}__)")
        print(f"       To retrieve, use: {tool}")
    print("")
    print("     This agent will continue with standard metadata retrieval.")
    print("     The above components must be retrieved separately.")
    print("")


if __name__ == "__main__":
    main()
