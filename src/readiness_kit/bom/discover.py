"""Discover components from configuration on disk: MCP client configs, skill files, prompt files and an
Agentic Radar graph export. Discovery only ever adds what the manifest did not already name.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from readiness_kit.bom.manifest import Component, version_from_command
from readiness_kit.util import KitError, read_json, sha256_file, sha256_json

# Where the common agent clients keep their MCP server lists, relative to the directory scanned.
MCP_CONFIG_FILES = (
    ".mcp.json",
    "mcp.json",
    ".cursor/mcp.json",
    ".vscode/mcp.json",
    ".windsurf/mcp.json",
    ".codeium/windsurf/mcp_config.json",
    ".gemini/settings.json",
    "claude_desktop_config.json",
    ".claude/settings.json",
    ".claude/settings.local.json",
)
SKILL_GLOBS = (".claude/skills/*/SKILL.md", "skills/*/SKILL.md", "skills/**/SKILL.md")
PROMPT_GLOBS = ("prompts/*.md", "prompts/*.txt", "prompts/**/*.md")


def _servers_from_config(data: Any) -> dict[str, dict[str, Any]]:
    if not isinstance(data, dict):
        return {}
    for key in ("mcpServers", "mcp_servers", "servers"):
        v = data.get(key)
        if isinstance(v, dict):
            return {str(k): (vv if isinstance(vv, dict) else {}) for k, vv in v.items()}
    # VS Code style: {"servers": {...}} handled above; Gemini: {"mcpServers": {...}}
    return {}


def discover_mcp_configs(root: Path) -> list[Component]:
    comps: list[Component] = []
    for rel in MCP_CONFIG_FILES:
        p = root / rel
        if not p.is_file():
            continue
        try:
            data = read_json(p)
        except KitError:
            continue
        for name, cfg in _servers_from_config(data).items():
            cmd = cfg.get("command")
            args = cfg.get("args") or []
            full = " ".join([str(cmd), *[str(a) for a in args]]) if cmd else None
            url = cfg.get("url") or cfg.get("serverUrl")
            props = {"rk:config": rel, "rk:transport": "stdio" if cmd else ("http" if url else "unknown")}
            if full:
                props["rk:command"] = full
            if url:
                props["rk:url"] = str(url)
            ver = version_from_command(full)
            comps.append(
                Component("mcp_server", name, ver, hash=sha256_json(cfg), properties=props, source=rel)
            )
    return comps


def discover_skills(root: Path) -> list[Component]:
    comps: list[Component] = []
    seen: set[Path] = set()
    for g in SKILL_GLOBS:
        for p in sorted(root.glob(g)):
            if p in seen or not p.is_file():
                continue
            seen.add(p)
            name = p.parent.name
            h = sha256_file(p)
            comps.append(
                Component(
                    "skill",
                    name,
                    f"sha256:{h[:12]}",
                    hash=h,
                    properties={"rk:path": str(p.relative_to(root))},
                    source="skills",
                )
            )
    return comps


def discover_prompts(root: Path) -> list[Component]:
    comps: list[Component] = []
    seen: set[Path] = set()
    for g in PROMPT_GLOBS:
        for p in sorted(root.glob(g)):
            if p in seen or not p.is_file():
                continue
            seen.add(p)
            h = sha256_file(p)
            comps.append(
                Component(
                    "prompt",
                    p.stem,
                    f"sha256:{h[:12]}",
                    hash=h,
                    properties={"rk:path": str(p.relative_to(root))},
                    source="prompts",
                )
            )
    return comps


def from_radar_graph(path: str | Path) -> list[Component]:
    """Tools and agents from an Agentic Radar ``--export-graph-json`` file."""
    data = read_json(path)
    if not isinstance(data, dict):
        raise KitError(f"{path}: not an Agentic Radar graph export")
    comps: list[Component] = []
    for t in data.get("tools") or []:
        name = t.get("name")
        if not name:
            continue
        props = {
            "rk:radar-type": str(t.get("node_type", "")),
            "rk:description": str(t.get("description") or "")[:200],
        }
        vulns = t.get("vulnerabilities") or []
        if vulns:
            props["rk:radar-vulnerabilities"] = json.dumps(vulns)[:500]
        comps.append(Component("tool", str(name), None, properties=props, source="agentic-radar"))
    for a in data.get("agents") or []:
        name = a.get("name")
        if name:
            comps.append(
                Component(
                    "tool",
                    f"agent:{name}",
                    None,
                    properties={"rk:radar-type": "agent"},
                    source="agentic-radar",
                )
            )
    return comps


def discover(root: str | Path, radar_graph: str | Path | None = None) -> list[Component]:
    r = Path(root)
    if not r.is_dir():
        raise KitError(f"not a directory: {r}")
    comps = discover_mcp_configs(r) + discover_skills(r) + discover_prompts(r)
    if radar_graph:
        comps += from_radar_graph(radar_graph)
    return comps
