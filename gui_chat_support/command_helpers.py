"""Parsing helpers for chat input, LLM plans, and direct-command detection."""

import re
from typing import List, Optional, Tuple

from testbench.command_parser import normalize_llm_command_prefix, try_parse_quoted_heading

CHAT_MODE_AGENT = "agent"
CHAT_MODE_PLAN = "plan"
_PLAN_RUN_WORDS = {"run", "go", "execute", "run plan"}
_PLAN_DISCARD_WORDS = {"discard", "cancel", "discard plan", "cancel plan"}

# Script variables: set $Vnom 3.3 | set VNOM 3.3 | set v_nom 3.3 — not prose "Set the supply..."
_SET_VARIABLE_RE = re.compile(
    r"^(?i:set)\s+(?:\$[A-Za-z_]\w*|[A-Z][A-Z0-9_]*|[a-z_][a-z0-9_]*_[a-z0-9_]+)\s+\S",
)


def normalize_chat_mode(value) -> str:
    s = str(value or "").strip().lower()
    return CHAT_MODE_PLAN if s == CHAT_MODE_PLAN else CHAT_MODE_AGENT


def looks_like_direct_command(text: str) -> bool:
    """
    Heuristic: treat as direct commands if the last fragment begins with bench./bc.
    or the line is an existing chat keyword (help/plot/delay/analyze/rag) or a quoted heading.
    """
    t = (text or "").strip()
    if not t:
        return True
    if try_parse_quoted_heading(t) is not None:
        return True
    tl = t.lower()
    if tl == "help" or tl.startswith("help "):
        return True
    if tl.startswith("plot "):
        return True
    if tl.startswith("delay "):
        return True
    if tl.startswith("assert ") or tl.startswith("limit "):
        return True
    if _SET_VARIABLE_RE.match(t):
        return True
    if tl == "analyze" or tl.startswith("analyze "):
        return True
    if tl == "repair" or tl.startswith("repair "):
        return True
    if tl in {"clear llm", "clear context", "clear history"}:
        return True
    if tl == "rag" or tl.startswith("rag "):
        return True
    last_fragment = re.split(r"[;\n\r]+", t)[-1].strip().lower()
    return last_fragment.startswith(("bench.", "bc."))


def parse_plan_action(text: str) -> Optional[str]:
    """
    Return ``"run"`` / ``"discard"`` for plan action keywords, else ``None``.
    """
    s = (text or "").strip().lower()
    if not s:
        return None
    if s in _PLAN_RUN_WORDS:
        return "run"
    if s in _PLAN_DISCARD_WORDS:
        return "discard"
    return None


def validate_llm_commands(commands, parser) -> Tuple[List[str], Optional[str]]:
    """
    Validate a list of LLM-generated command strings.

    Returns ``(safe_commands, error_message_or_None)``.
    """
    safe: List[str] = []
    for c in commands or []:
        c = normalize_llm_command_prefix((c or "").strip())
        if not c:
            continue
        cl = c.lower()
        if cl.startswith("delay ") or cl == "help" or cl.startswith("help "):
            safe.append(c)
            continue
        if cl.startswith("assert ") or cl.startswith("limit ") or cl.startswith("set "):
            safe.append(c)
            continue
        if cl.startswith("for ") or cl in {"endfor", "end"}:
            safe.append(c)
            continue
        if cl.startswith("plot "):
            safe.append(c)
            continue
        if try_parse_quoted_heading(c) is not None:
            safe.append(c)
            continue
        parsed = parser.parse(c)
        if not parsed:
            return [], f"LLM produced invalid command: {c}"
        if parsed.get("category") == "config" or parsed.get("action") == "raw":
            return (
                [],
                f"Blocked potentially unsafe command (config/raw). Please run explicitly:\n{c}",
            )
        safe.append(c)
    return safe, None


def parse_repair_keyword(text: str):
    """
    Return optional operator hint for ``repair``, or ``""`` for bare ``repair``.

    Returns ``None`` if the line is not a repair keyword.
    """
    s = (text or "").strip()
    if not s:
        return None
    parts = s.split(None, 1)
    if not parts or parts[0].lower() != "repair":
        return None
    return parts[1].strip() if len(parts) > 1 else ""


def parse_clear_llm_context_keyword(text: str) -> bool:
    s = (text or "").strip().lower()
    return s in {"clear llm", "clear context", "clear history", "clear llm context"}


def parse_analyze_keyword(text: str):
    """
    Return optional extra-prompt text for ``analyze``, or ``None`` if not an analyze keyword.
    """
    s = (text or "").strip()
    if not s:
        return None
    parts = s.split(None, 1)
    if not parts or parts[0].lower() != "analyze":
        return None
    return parts[1].strip() if len(parts) > 1 else ""


def parse_rag_keyword(text: str):
    """Return ``("status", "")`` / ``("reload", "")`` / ``("query", q)`` for ``rag …`` lines.

    Returns ``None`` if the line does not start with the ``rag`` keyword.
    """
    s = (text or "").strip()
    if not s:
        return None
    parts = s.split(None, 1)
    if not parts or parts[0].lower() != "rag":
        return None
    if len(parts) == 1:
        return ("status", "")
    arg = parts[1].strip()
    low = arg.lower()
    if low in {"status", "info"}:
        return ("status", "")
    if low in {"reload", "refresh", "reindex"}:
        return ("reload", "")
    return ("query", arg)
