"""Emit the Agent BOM as CycloneDX 1.6 JSON, plus the Kit's own summary (``rk.bom``) that `rk score` reads.

Component types used (CycloneDX 1.6 ``component.type``):
  model → machine-learning-model · prompt, skill → file · tool, mcp_server → library · data source → data
Kit-specific facts travel as ``properties`` with an ``rk:`` prefix, so any CycloneDX tool can read the BOM and
any Kit-aware tool can read the rest.
"""

from __future__ import annotations

import uuid
from typing import Any

from readiness_kit import __version__
from readiness_kit.bom.manifest import Component, Manifest
from readiness_kit.util import now_iso

CDX_TYPES = {
    "model": "machine-learning-model",
    "prompt": "file",
    "skill": "file",
    "tool": "library",
    "mcp_server": "library",
    "data": "data",
}


def _component(c: Component) -> dict[str, Any]:
    d: dict[str, Any] = {
        "type": CDX_TYPES[c.kind],
        "bom-ref": c.ref,
        "name": c.name,
        "version": c.version or "unversioned",
    }
    if c.hash:
        d["hashes"] = [{"alg": "SHA-256", "content": c.hash}]
    props = [{"name": "rk:kind", "value": c.kind}, {"name": "rk:source", "value": c.source}]
    if c.unversioned:
        props.append({"name": "rk:unversioned", "value": "true"})
    for k, v in sorted(c.properties.items()):
        props.append({"name": k if k.startswith("rk:") else f"rk:{k}", "value": v})
    d["properties"] = props
    return d


def emit_cyclonedx(manifest: Manifest, serial: str | None = None) -> dict[str, Any]:
    serial = serial or f"urn:uuid:{uuid.uuid4()}"
    comps = [_component(c) for c in manifest.components]
    app_ref = f"rk:agent:{manifest.name}"
    bom: dict[str, Any] = {
        "$schema": "http://cyclonedx.org/schema/bom-1.6.schema.json",
        "bomFormat": "CycloneDX",
        "specVersion": "1.6",
        "serialNumber": serial,
        "version": 1,
        "metadata": {
            "timestamp": now_iso(),
            "tools": {
                "components": [
                    {
                        "type": "application",
                        "name": "readiness-kit",
                        "version": __version__,
                        "supplier": {"name": "Rainkernel Technologies Private Limited"},
                    }
                ]
            },
            "component": {
                "type": "application",
                "bom-ref": app_ref,
                "name": manifest.name,
                "version": manifest.version or "unversioned",
                **({"description": manifest.description} if manifest.description else {}),
                "properties": [
                    {"name": "rk:kind", "value": "agent"},
                    *([{"name": "rk:owner", "value": manifest.owner}] if manifest.owner else []),
                ],
            },
        },
        "components": comps,
        "dependencies": [{"ref": app_ref, "dependsOn": [c["bom-ref"] for c in comps]}],
    }
    # a tool provided by an MCP server depends on that server
    servers = {c.name.lower(): c.ref for c in manifest.components if c.kind == "mcp_server"}
    for c in manifest.components:
        if c.kind == "tool":
            srv = (c.properties.get("server") or c.properties.get("rk:server") or "").lower()
            if srv in servers:
                bom["dependencies"].append({"ref": c.ref, "dependsOn": [servers[srv]]})
    return bom


def summarise(manifest: Manifest, bom: dict[str, Any], bom_path: str | None = None) -> dict[str, Any]:
    by_kind: dict[str, int] = {}
    for c in manifest.components:
        by_kind[c.kind] = by_kind.get(c.kind, 0) + 1
    unversioned = [{"kind": c.kind, "name": c.name} for c in manifest.components if c.unversioned]
    unpinned = [c.name for c in manifest.components if c.properties.get("rk:unpinned-source") == "true"]
    missing = [c.name for c in manifest.components if c.properties.get("rk:missing") == "true"]
    data_sources = [
        {"name": c.name, "managed": c.properties.get("rk:managed") == "true"}
        for c in manifest.components
        if c.kind == "data"
    ]
    return {
        "kind": "rk.bom",
        "kit_version": __version__,
        "created": bom["metadata"]["timestamp"],
        "summary": {
            "agent": {"name": manifest.name, "version": manifest.version, "owner": manifest.owner},
            "components": len(manifest.components),
            "by_kind": by_kind,
            "unversioned": unversioned,
            "unpinned_sources": unpinned,
            "missing_files": missing,
            "data_sources": data_sources,
            "bom_path": bom_path,
            "serial": bom["serialNumber"],
        },
    }
