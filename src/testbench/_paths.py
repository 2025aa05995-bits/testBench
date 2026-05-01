"""Repository-root paths (package lives in ``src/testbench``)."""

from pathlib import Path


def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def default_config_file() -> Path:
    return repo_root() / "config" / "testbenchconfig.json"
