"""Shared helpers for pipeline scripts. Not invoked directly."""
import os, sys, json, subprocess
import xml.etree.ElementTree as ET
from pathlib import Path

NS = "http://soap.sforce.com/2006/04/metadata"
ET.register_namespace("", NS)


def env(name):
    v = os.environ.get(name)
    if not v:
        print(f"ERROR: required env var {name} is not set", file=sys.stderr)
        sys.exit(2)
    return v


def project_dir():
    return Path(env("PROJECT_PARENT_DIR")) / f"{env('ALIAS')}-metadata"


def manifest_path():
    return project_dir() / "manifest" / "package.xml"


def load_manifest():
    """Return (types_dict, api_version). types_dict maps type_name -> set(members)."""
    tree = ET.parse(manifest_path())
    root = tree.getroot()
    types = {}
    for t in root.findall(f"{{{NS}}}types"):
        name_el = t.find(f"{{{NS}}}name")
        if name_el is None or not name_el.text:
            continue
        members = {m.text for m in t.findall(f"{{{NS}}}members") if m.text}
        types[name_el.text] = members
    version_el = root.find(f"{{{NS}}}version")
    version = version_el.text if version_el is not None else None
    return types, version


def save_manifest(types, version):
    """Write a fresh manifest with the given types dict and version."""
    root = ET.Element(f"{{{NS}}}Package")
    for name in sorted(types.keys()):
        members = sorted(types[name])
        if not members:
            continue
        type_el = ET.SubElement(root, f"{{{NS}}}types")
        for m in members:
            ET.SubElement(type_el, f"{{{NS}}}members").text = m
        ET.SubElement(type_el, f"{{{NS}}}name").text = name
    if version:
        ET.SubElement(root, f"{{{NS}}}version").text = version
    ET.indent(root, space="    ")
    tree = ET.ElementTree(root)
    tree.write(manifest_path(), encoding="utf-8", xml_declaration=True)


def sf_json(args, timeout=600):
    """Run an `sf` command with --json appended; return result['result'] or raise."""
    full = ["sf"] + list(args) + ["--json"]
    r = subprocess.run(full, capture_output=True, text=True, timeout=timeout)
    if r.returncode != 0:
        msg = r.stderr.strip() or r.stdout.strip() or "(no message)"
        try:
            payload = json.loads(r.stdout)
            msg = payload.get("message") or msg
        except Exception:
            pass
        raise RuntimeError(f"sf {' '.join(args)} failed: {msg}")
    try:
        payload = json.loads(r.stdout)
    except json.JSONDecodeError:
        raise RuntimeError(f"sf {' '.join(args)} returned non-JSON: {r.stdout[:500]}")
    return payload.get("result")


def list_metadata(metadata_type, folder=None, alias=None):
    """`sf org list metadata --metadata-type X [--folder Y]` -> list[dict] (possibly empty)."""
    args = ["org", "list", "metadata", "--metadata-type", metadata_type,
            "--target-org", alias or env("ALIAS")]
    if folder:
        args += ["--folder", folder]
    try:
        result = sf_json(args)
    except RuntimeError as e:
        # An unknown/unsupported type in this org is not fatal — return empty.
        if "INVALID_TYPE" in str(e) or "not supported" in str(e).lower():
            return []
        raise
    if result is None:
        return []
    return result if isinstance(result, list) else [result]


def installed_namespaces(alias=None):
    """Return the set of managed-package namespace prefixes installed in the org."""
    pkgs = list_metadata("InstalledPackage", alias=alias)
    return {p["fullName"] for p in pkgs if p.get("fullName")}


def info(msg):
    print(f"  {msg}", flush=True)


def warn(msg):
    print(f"  ⚠️  {msg}", flush=True)
