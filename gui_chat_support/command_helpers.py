"""Parsing helpers for chat input, LLM plans, and direct-command detection."""

import re
from typing import List, Optional, Tuple

from testbench.command_parser import normalize_llm_command_prefix

CHAT_MODE_AGENT = "agent"
CHAT_MODE_PLAN = "plan"
_PLAN_RUN_WORDS = {"run", "go", "execute", "run plan"}
_PLAN_DISCARD_WORDS = {"discard", "cancel", "discard plan", "cancel plan"}


def normalize_chat_mode(value) -> str:
    s = str(value or "").strip().lower()
    return CHAT_MODE_PLAN if s == CHAT_MODE_PLAN else CHAT_MODE_AGENT


def try_parse_quoted_heading(command: str):
    """Heading only when the whole line is wrapped in double quotes."""
    s = (command or "").strip()
    m = re.match(r'^"(.*)"\s*$', s, re.DOTALL)
    if not m:
        return None
    inner = (m.group(1) or "").strip()
    return inner if inner else None


def looks_like_direct_command(text: str) -> bool:
    """
    Heuristic: treat as direct commands if the last fragment begins with bench./bc.
    or the line is an existing chat keyword (help/plot/delay/analyze) or a quoted heading.
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
    if tl == "analyze" or tl.startswith("analyze "):
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
