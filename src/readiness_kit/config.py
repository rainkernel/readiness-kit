"""rk.yaml: one file that names the target and the inputs, so every command runs without flags.

    name: ticket-triage-agent
    target:
      type: python            # python | http | openai-chat | command | replay
      module: agent
      function: handle
      max_steps: 40
    eval:
      set: evalset.jsonl
      split: split.json
      target_pass_rate: 0.90
      concurrency: 1
    attack:
      pack: starter           # "starter" = the bundled pack, or a folder/file path
    cost:
      traces: [traces.jsonl]
      prices: prices.yaml
      ceiling_per_task: 0.40
      volume_per_month: 12000
    bom:
      manifest: agent.yaml
      discover: .
    scan:
      tools: [mcp-scanner, snyk-agent-scan, agentic-radar, promptfoo]
      framework: langgraph
    assessment: assessment.yaml
    runs_dir: runs

Paths are relative to the directory that holds rk.yaml. Every command flag overrides the file.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from readiness_kit.util import KitError, read_yaml

DEFAULT_NAME = "rk.yaml"


@dataclass
class Config:
    base_dir: Path
    path: Path | None = None
    name: str = "agent"
    target: dict[str, Any] = field(default_factory=dict)
    eval: dict[str, Any] = field(default_factory=dict)
    attack: dict[str, Any] = field(default_factory=dict)
    cost: dict[str, Any] = field(default_factory=dict)
    bom: dict[str, Any] = field(default_factory=dict)
    scan: dict[str, Any] = field(default_factory=dict)
    assessment: str = "assessment.yaml"
    runs_dir: str = "runs"

    def resolve(self, p: str | Path | None) -> Path | None:
        if p is None:
            return None
        pp = Path(p)
        return pp if pp.is_absolute() else (self.base_dir / pp)

    @property
    def runs(self) -> Path:
        return self.resolve(self.runs_dir) or (self.base_dir / "runs")

    @property
    def max_steps(self) -> int | None:
        v = self.target.get("max_steps")
        return int(v) if v is not None else None


def load_config(path: str | Path | None, required: bool = True) -> Config:
    """Load rk.yaml from ``path`` or the working directory. With ``required=False`` a missing file gives defaults."""
    p = Path(path) if path else Path.cwd() / DEFAULT_NAME
    if not p.exists():
        if required:
            raise KitError(f"{p} not found; run `rk init` here or pass --config")
        return Config(base_dir=Path.cwd())
    data = read_yaml(p) or {}
    if not isinstance(data, dict):
        raise KitError(f"{p}: rk.yaml is a YAML object")
    cfg = Config(base_dir=p.parent.resolve(), path=p.resolve(), name=str(data.get("name") or p.parent.name))
    for key in ("target", "eval", "attack", "cost", "bom", "scan"):
        v = data.get(key) or {}
        if not isinstance(v, dict):
            raise KitError(f"{p}: '{key}' must be an object")
        setattr(cfg, key, v)
    cfg.assessment = str(data.get("assessment") or "assessment.yaml")
    cfg.runs_dir = str(data.get("runs_dir") or "runs")
    return cfg
