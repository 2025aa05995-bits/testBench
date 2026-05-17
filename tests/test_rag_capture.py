"""Tests for RAG mode sequence capture."""

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from testbench.rag import get_index, retrieve_for_prompt
from testbench.rag_capture import (
    capture_rag_sequence_from_input,
    parse_rag_sequence_input,
    save_rag_sequence,
)


def test_parse_tag_and_commands_multiline():
    tag, cmds = parse_rag_sequence_input(
        "Power Cycle\nbc.ps.off\ndelay 1\nbc.ps.on"
    )
    assert tag == "Power Cycle"
    assert cmds == ["bc.ps.off", "delay 1", "bc.ps.on"]


def test_parse_commands_only_no_tag():
    tag, cmds = parse_rag_sequence_input("bc.ps.off\ndelay 1\nbc.ps.on")
    assert tag is None
    assert len(cmds) == 3


def test_parse_quoted_heading_as_tag_and_command():
    tag, cmds = parse_rag_sequence_input('"Power Cycle"\nbc.ps.off\nbc.ps.on')
    assert tag == "Power Cycle"
    assert cmds[0] == '"Power Cycle"'
    assert "bc.ps.off" in cmds


def test_parse_ignores_non_command_prose():
    tag, cmds = parse_rag_sequence_input(
        "Power Cycle\nbc.ps.off\nThis is an explanation.\nbc.ps.on"
    )
    assert tag == "Power Cycle"
    assert cmds == ["bc.ps.off", "bc.ps.on"]


def test_save_and_retrieve_sequence(tmp_path: Path):
    docs = tmp_path / "rag_docs"
    docs.mkdir()
    cfg = {
        "rag": {
            "enabled": True,
            "dir": str(docs),
            "backend": "tfidf",
        }
    }
    path = save_rag_sequence(
        cfg,
        ["bc.ps.off", "delay 1", "bc.ps.on"],
        tag="Power Cycle",
        root=tmp_path,
    )
    assert path.is_file()
    assert "sequences" in str(path)
    block, hits = retrieve_for_prompt("power cycle supply", cfg, root=tmp_path)
    assert hits
    assert "bc.ps.off" in block or any("bc.ps.off" in h.text for h in hits)


def test_capture_empty_commands_errors():
    out = capture_rag_sequence_from_input("Power Cycle only", cfg={"rag": {"enabled": True}})
    assert out.error
