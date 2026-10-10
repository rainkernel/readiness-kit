from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from readiness_kit.paths import example_path

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def example(tmp_path: Path) -> Path:
    """A fresh copy of the example agent directory (no runs, no split)."""
    dest = tmp_path / "agent"
    shutil.copytree(example_path(), dest, ignore=shutil.ignore_patterns("runs", "split.json", "__pycache__"))
    return dest


@pytest.fixture
def fixtures() -> Path:
    return FIXTURES
