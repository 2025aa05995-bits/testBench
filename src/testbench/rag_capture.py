"""Capture manual bench command sequences into ``rag_docs`` for RAG retrieval."""

from __future__ import annotations

import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from testbench._paths import repo_root
from testbench.command_parser import try_parse_quoted_heading
from testbench.rag import RagConfig, _resolve_dir, reload_index


_LINE_SPLIT_RE = re.compile(r"[\n\r;]+")


def _is_command_line(line: str) -> bool:
    s = (line or "").strip()
    if not s:
        return False
    if try_parse_quoted_heading(s) is not None:
        return True
    low = s.lower()
    if low.startswith(("bench.", "bc.")):
        return True
    if low.startswith(("delay ", "plot ", "assert ", "limit ", "help", "set ")):
        return True
    if low in {"endfor", "end"}:
        return True
    if low.startswith("for "):
        return True
    return False


def parse_rag_sequence_input(text: str) -> Tuple[Optional[str], List[str]]:
    """Split chat input into an optional text tag and bench command lines.

    The first line may be a human-readable tag (e.g. ``Power Cycle``) when it
    is not a bench command. A quoted heading (``"Power Cycle"``) sets the tag
    and is kept as the first command line. Lines that are not commands are
    skipped. If there is no tag, ``None`` is returned and the sequence is still
    valid.
    """
    lines = [ln.strip() for ln in _LINE_SPLIT_RE.split(text or "") if ln.strip()]
    if not lines:
        return None, []

    tag: Optional[str] = None
    commands: List[str] = []

    for i, ln in enumerate(lines):
        heading = try_parse_quoted_heading(ln)
        if heading is not None:
            if tag is None:
                tag = heading
            commands.append(ln)
            continue
        if i == 0 and tag is None and not _is_command_line(ln):
            tag = ln.strip().strip('"').strip("'")
            continue
        if _is_command_line(ln):
            commands.append(ln)
        # Non-command prose after the tag line is ignored.

    return tag, commands


def _slugify(label: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "_", (label or "").lower()).strip("_")
    return s[:80] if s else ""


def format_sequence_markdown(tag: Optional[str], commands: List[str]) -> str:
    title = (tag or "").strip() or "Bench sequence"
    lines = [
        f"# {title}",
        "",
        "Type: captured bench sequence (RAG mode)",
        "",
    ]
    if tag:
        lines.append(f"Keywords: {tag}")
        lines.append("")
    lines.append("Commands:")
    lines.append("")
    lines.extend(commands)
    lines.append("")
    return "\n".join(lines)


def save_rag_sequence(
    cfg: Optional[Dict[str, Any]],
    commands: List[str],
    *,
    tag: Optional[str] = None,
    root: Optional[Path] = None,
) -> Path:
    """Write a sequence markdown file under ``rag_docs/sequences/`` and refresh the index."""
    if not commands:
        raise ValueError("No commands to save for RAG.")

    rag_cfg = RagConfig.from_config(cfg)
    if not rag_cfg.enabled:
        raise RuntimeError("RAG is disabled in config (rag.enabled).")

    base = Path(root) if root is not None else repo_root()
    docs_dir = _resolve_dir(rag_cfg, base)
    seq_dir = docs_dir / "sequences"
    seq_dir.mkdir(parents=True, exist_ok=True)

    slug = _slugify(tag) if tag else ""
    if not slug:
        slug = f"sequence_{int(time.time())}"
    path = seq_dir / f"{slug}.md"
    if path.exists():
        path = seq_dir / f"{slug}_{int(time.time())}.md"

    path.write_text(format_sequence_markdown(tag, commands), encoding="utf-8")
    reload_index(cfg, root=base)
    return path


@dataclass(frozen=True)
class RagCaptureOutcome:
    tag: Optional[str]
    commands: List[str]
    saved_path: Optional[Path] = None
    error: Optional[str] = None


def capture_rag_sequence_from_input(
    text: str,
    cfg: Optional[Dict[str, Any]],
    *,
    root: Optional[Path] = None,
) -> RagCaptureOutcome:
    """Parse input, persist to RAG docs. Does not run commands."""
    tag, commands = parse_rag_sequence_input(text)
    if not commands:
        return RagCaptureOutcome(
            tag=tag,
            commands=[],
            error="No bench commands found. Enter a tag line (optional) then bc.* / bench.* lines.",
        )
    try:
        path = save_rag_sequence(cfg, commands, tag=tag, root=root)
    except Exception as exc:
        return RagCaptureOutcome(tag=tag, commands=commands, error=str(exc))
    return RagCaptureOutcome(tag=tag, commands=commands, saved_path=path)
