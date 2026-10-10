"""The agent manifest (agent.yaml): the declared inventory the BOM starts from.

    name: ticket-triage-agent
    version: 0.3.0
    owner: platform-team@example.com
    models:       [{name, provider, version}]
    prompts:      [{name, path, version}]            # path is hashed
    tools:        [{name, server, kind}]             # kind: read | write | send | execute
    mcp_servers:  [{name, transport, command|url, version, tools: [..]}]
    skills:       [{name, path, source, pinned}]     # path is hashed; unpinned remote sources are flagged
    data_sources: [{name, kind, owner, refresh}]     # an owner or a refresh policy makes a source "managed"

Every component ends up with a version or the word ``unversioned`` and a flag; the BOM never invents a version.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from readiness_kit.util import KitError, read_yaml, sha256_file, sha256_json

KINDS = ("model", "prompt", "tool", "mcp_server", "skill", "data")

_VER_RE = re.compile(r"@(v?\d+\.\d+(?:\.\d+)?(?:[-+][0-9A-Za-z.]+)?)(?:\s|$)")
_DIGEST_RE = re.compile(r"@sha256:[0-9a-f]{64}")


@dataclass
class Component:
    kind: str
    name: str
    version: str | None = None
    hash: str | None = None
    properties: dict[str, str] = field(default_factory=dict)
    source: str = "manifest"

    @property
    def unversioned(self) -> bool:
        return not self.version

    @property
    def ref(self) -> str:
        slug = re.sub(r"[^a-z0-9]+", "-", self.name.lower()).strip("-")
        return f"rk:{self.kind}:{slug}"


@dataclass
class Manifest:
    name: str
    version: str | None
    owner: str | None
    components: list[Component]
    path: str | None = None
    description: str = ""

    def by_kind(self, kind: str) -> list[Component]:
        return [c for c in self.components if c.kind == kind]

    def merge(self, extra: list[Component]) -> None:
        """Add discovered components the manifest does not already name (manifest entries win)."""
        have = {(c.kind, c.name.lower()) for c in self.components}
        hashes = {(c.kind, c.hash) for c in self.components if c.hash}
        for c in extra:
            if (c.kind, c.name.lower()) in have or (c.hash and (c.kind, c.hash) in hashes):
                continue  # already declared, by name or by content
            self.components.append(c)
            have.add((c.kind, c.name.lower()))
            if c.hash:
                hashes.add((c.kind, c.hash))


def version_from_command(cmd: str | None) -> str | None:
    if not cmd:
        return None
    m = _DIGEST_RE.search(cmd)
    if m:
        return m.group(0)[1:]
    m = _VER_RE.search(cmd + " ")
    return m.group(1) if m else None


def _hash_path(base: Path, rel: str | None) -> tuple[str | None, bool]:
    if not rel:
        return None, False
    p = Path(rel)
    p = p if p.is_absolute() else base / p
    if p.exists() and p.is_file():
        return sha256_file(p), True
    return None, False


def load_manifest(path: str | Path) -> Manifest:
    p = Path(path)
    if not p.exists():
        raise KitError(f"agent manifest not found: {p}")
    data = read_yaml(p) or {}
    if not isinstance(data, dict) or "name" not in data:
        raise KitError(f"{p}: the manifest is a YAML object with at least 'name'")
    base = p.parent
    comps: list[Component] = []

    def s(v: Any) -> str | None:
        return None if v is None else str(v)

    for m in data.get("models") or []:
        comps.append(
            Component(
                "model",
                str(m["name"]),
                s(m.get("version")),
                properties={
                    k: str(v) for k, v in m.items() if k not in ("name", "version") and v is not None
                },
            )
        )
    for pr in data.get("prompts") or []:
        h, ok = _hash_path(base, pr.get("path"))
        props = {"rk:path": str(pr.get("path"))} if pr.get("path") else {}
        if pr.get("path") and not ok:
            props["rk:missing"] = "true"
        comps.append(
            Component(
                "prompt",
                str(pr.get("name") or pr.get("path")),
                s(pr.get("version")) or (f"sha256:{h[:12]}" if h else None),
                hash=h,
                properties=props,
            )
        )
    servers: dict[str, str | None] = {}
    for srv in data.get("mcp_servers") or []:
        ver = s(srv.get("version")) or version_from_command(s(srv.get("command")))
        servers[str(srv["name"]).lower()] = ver
        props = {k: str(v) for k, v in srv.items() if k not in ("name", "version", "tools") and v is not None}
        if srv.get("tools"):
            props["rk:mcp-tools"] = ",".join(str(x) for x in srv["tools"])
        comps.append(Component("mcp_server", str(srv["name"]), ver, hash=sha256_json(srv), properties=props))
    agent_version = s(data.get("version"))
    for t in data.get("tools") or []:
        props = {k: str(v) for k, v in t.items() if k not in ("name", "version") and v is not None}
        ver = s(t.get("version"))
        server = str(t.get("server") or "").lower()
        if ver is None and server in servers and servers[server]:
            ver = servers[server]  # a tool is as versioned as the server that provides it
            props["rk:version-from"] = "server"
        elif ver is None and server in ("internal", "agent", "builtin") and agent_version:
            ver = agent_version  # an internal tool ships with the agent
            props["rk:version-from"] = "agent"
        comps.append(Component("tool", str(t["name"]), ver, properties=props))
    for sk in data.get("skills") or []:
        h, ok = _hash_path(base, sk.get("path"))
        props = {k: str(v) for k, v in sk.items() if k not in ("name", "version", "pinned") and v is not None}
        pinned = s(sk.get("pinned"))
        if sk.get("source") and not pinned:
            props["rk:unpinned-source"] = "true"
        if sk.get("path") and not ok:
            props["rk:missing"] = "true"
        comps.append(
            Component(
                "skill",
                str(sk.get("name") or sk.get("path")),
                pinned
                or s(sk.get("version"))
                or (f"sha256:{h[:12]}" if h and not sk.get("source") else None),
                hash=h,
                properties=props,
            )
        )
    for d in data.get("data_sources") or []:
        props = {k: str(v) for k, v in d.items() if k not in ("name", "version") and v is not None}
        managed = bool(d.get("owner") or d.get("refresh"))
        props["rk:managed"] = "true" if managed else "false"
        # a data source is "live" unless it carries a version or a refresh cadence; management, not versioning, is its finding
        comps.append(
            Component(
                "data",
                str(d["name"]),
                s(d.get("version")) or (str(d.get("refresh")) if d.get("refresh") else "live"),
                properties=props,
            )
        )
    return Manifest(
        name=str(data["name"]),
        version=s(data.get("version")),
        owner=s(data.get("owner")),
        components=comps,
        path=str(p),
        description=str(data.get("description") or ""),
    )
