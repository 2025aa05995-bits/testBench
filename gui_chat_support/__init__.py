"""Support modules for ``gui_chat.py`` (fonts, sequences, command helpers, Qt/Tk backends)."""

from .command_completer import CommandCompleter
from .command_helpers import (
    CHAT_MODE_AGENT,
    CHAT_MODE_PLAN,
    normalize_chat_mode,
    looks_like_direct_command,
    parse_analyze_keyword,
    parse_plan_action,
    parse_rag_keyword,
    try_parse_quoted_heading,
    validate_llm_commands,
)
from .run_command import run_chat_command

__all__ = [
    "CHAT_MODE_AGENT",
    "CHAT_MODE_PLAN",
    "CommandCompleter",
    "looks_like_direct_command",
    "normalize_chat_mode",
    "parse_analyze_keyword",
    "parse_plan_action",
    "parse_rag_keyword",
    "run_chat_command",
    "try_parse_quoted_heading",
    "validate_llm_commands",
]
