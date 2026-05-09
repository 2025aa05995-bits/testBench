"""Persisted test sequences (config/test_sequences.json)."""

import json
import os
from pathlib import Path
from typing import Any, Dict

_REPO_ROOT = Path(__file__).resolve().parent.parent


def test_sequences_file() -> str:
    return str(_REPO_ROOT / "config" / "test_sequences.json")


def _normalize_sequence_name_map(raw: object) -> Dict[str, Any]:
    """Normalize { sequence_name: [command, ...] }."""
    out: Dict[str, Any] = {}
    if not isinstance(raw, dict):
        return out
    for k, v in raw.items():
        if not isinstance(k, str) or not k.strip():
            continue
        if not isinstance(v, list):
            continue
        steps = [str(x).strip() for x in v if str(x).strip()]
        if steps:
            out[k.strip()] = steps
    return out


def _normalize_categories(raw: object) -> Dict[str, Any]:
    """Normalize { category: { sequence_name: [commands] } }."""
    out: Dict[str, Any] = {}
    if not isinstance(raw, dict):
        return out
    for cat, inner in raw.items():
        if not isinstance(cat, str) or not cat.strip():
            continue
        nm = _normalize_sequence_name_map(inner)
        if nm:
            out[cat.strip()] = nm
    return out


def load_test_sequences() -> dict:
    """Load saved test sequences; returns {'categories': {category: {name: [commands]}}}."""
    path = test_sequences_file()
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        data = {}
    categories: Dict[str, Any] = {}
    if isinstance(data, dict):
        if isinstance(data.get("categories"), dict) and data["categories"]:
            categories = _normalize_categories(data["categories"])
        legacy_pc = data.get("power_cycle")
        if isinstance(legacy_pc, dict) and legacy_pc:
            merged = _normalize_sequence_name_map(legacy_pc)
            if merged:
                bucket = categories.setdefault("power_cycle", {})
                for seq_name, cmds in merged.items():
                    if seq_name not in bucket:
                        bucket[seq_name] = cmds
    return {"categories": categories}


def save_test_sequences(store: dict) -> None:
    path = test_sequences_file()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    cats = _normalize_categories(store.get("categories"))
    payload = {"categories": cats}
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
