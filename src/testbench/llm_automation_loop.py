"""Automation loop helpers: multi-turn planning, repair plans, failure detection."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional


@dataclass(frozen=True)
class AutomationLoopConfig:
    """Settings under ``llm`` in bench JSON."""

    enabled: bool = True
    max_iterations: int = 3
    auto_repair_on_fail: bool = True
    closed_loop_agent: bool = True
    multi_turn_history: int = 8

    @classmethod
    def from_config(cls, cfg: Optional[Dict[str, Any]]) -> "AutomationLoopConfig":
        llm = (cfg or {}).get("llm") if isinstance(cfg, dict) else None
        if not isinstance(llm, dict):
            return cls()
        loop = llm.get("automation_loop")
        if isinstance(loop, dict):
            return cls(
                enabled=_bool(loop.get("enabled"), True),
                max_iterations=_int_clamp(loop.get("max_iterations"), 3, 1, 10),
                auto_repair_on_fail=_bool(loop.get("auto_repair_on_fail"), True),
                closed_loop_agent=_bool(loop.get("closed_loop_agent"), True),
                multi_turn_history=_int_clamp(loop.get("multi_turn_history"), 8, 0, 32),
            )
        return cls(
            enabled=_bool(llm.get("automation_loop_enabled"), True),
            max_iterations=_int_clamp(llm.get("automation_max_iterations"), 3, 1, 10),
            auto_repair_on_fail=_bool(llm.get("auto_repair_on_fail"), True),
            closed_loop_agent=_bool(llm.get("closed_loop_agent"), True),
            multi_turn_history=_int_clamp(llm.get("multi_turn_history"), 8, 0, 32),
        )


def _bool(v: Any, default: bool) -> bool:
    if isinstance(v, bool):
        return v
    if isinstance(v, str):
        return v.strip().lower() not in {"false", "0", "no", "off"}
    if v is None:
        return default
    return bool(v)


def _int_clamp(v: Any, default: int, lo: int, hi: int) -> int:
    try:
        n = int(v) if v is not None and str(v).strip() != "" else default
    except (TypeError, ValueError):
        n = default
    return max(lo, min(hi, n))


def results_need_repair(results: List[Dict[str, Any]]) -> bool:
    """True when any captured step failed (error, FAIL message, or check.passed is false)."""
    for item in results or []:
        if not isinstance(item, dict):
            continue
        err = item.get("error")
        if err is not None and str(err).strip():
            return True
        res = item.get("result")
        if isinstance(res, dict) and res.get("passed") is False:
            return True
        if isinstance(res, dict):
            msg = str(res.get("message", "") or "")
            if msg.upper().startswith("FAIL:"):
                return True
    return False


def summarize_results_outcome(results: List[Dict[str, Any]]) -> str:
    """One-line PASS/FAIL summary for conversation history."""
    if not results:
        return "no steps recorded"
    fails = 0
    for item in results:
        if not isinstance(item, dict):
            continue
        if item.get("error"):
            fails += 1
            continue
        res = item.get("result")
        if isinstance(res, dict):
            if res.get("passed") is False:
                fails += 1
            elif str(res.get("message", "")).upper().startswith("FAIL:"):
                fails += 1
    if fails:
        return f"FAIL ({fails} of {len(results)} step(s) failed or errored)"
    return f"PASS ({len(results)} step(s) ok)"


def trim_conversation_turns(
    turns: List[Dict[str, Any]], max_turns: int
) -> List[Dict[str, Any]]:
    if max_turns <= 0:
        return []
    if len(turns) <= max_turns:
        return list(turns)
    return list(turns[-max_turns:])


def format_conversation_for_plan(turns: List[Dict[str, Any]]) -> str:
    """Compact prior-turn block for the plan prompt."""
    if not turns:
        return ""
    lines: List[str] = ["PRIOR TURNS:"]
    for i, turn in enumerate(turns, 1):
        user = str(turn.get("user", "") or "").strip()
        cmds = turn.get("commands") or []
        analysis = str(turn.get("analysis", "") or "").strip()
        outcome = str(turn.get("outcome", "") or "").strip()
        lines.append(f"{i}. User: {user}")
        if cmds:
            lines.append("   Commands run:")
            for c in cmds[:24]:
                lines.append(f"     - {c}")
            if len(cmds) > 24:
                lines.append(f"     … ({len(cmds) - 24} more)")
        if analysis:
            lines.append(f"   Plan notes: {analysis[:400]}")
        if outcome:
            lines.append(f"   Outcome: {outcome}")
    lines.append("")
    return "\n".join(lines)


def _results_block(results: List[Dict[str, Any]]) -> str:
    from testbench.llm_chat import _format_results_for_prompt

    return _format_results_for_prompt(results)


def build_plan_user_content(
    user_text: str,
    allowed: str,
    rag_block: str,
    *,
    conversation_turns: Optional[List[Dict[str, Any]]] = None,
    last_results: Optional[List[Dict[str, Any]]] = None,
    last_commands: Optional[List[str]] = None,
) -> str:
    """Assemble the user message for ``llm_chat_to_plan``."""
    parts: List[str] = []
    if rag_block:
        parts.append(f"CONTEXT:\n{rag_block}\n")
    conv = format_conversation_for_plan(conversation_turns or [])
    if conv:
        parts.append(conv)
    if last_results:
        parts.append(
            "LAST RUN (most recent execution before this request):\n"
            f"{_results_block(last_results)}\n"
        )
    if last_commands:
        parts.append("LAST COMMANDS EXECUTED:\n" + "\n".join(f"- {c}" for c in last_commands) + "\n")
    parts.append(f"ALLOWED:\n{allowed}\n\nREQUEST:\n{(user_text or '').strip()}")
    return "\n".join(parts)


def repair_system_prompt() -> str:
    return (
        "You repair a failed TestBench command sequence.\n"
        "Return ONLY raw JSON (no markdown fences) with keys:\n"
        '- "commands": array of strings — MINIMAL fix steps only (do not repeat the full original plan)\n'
        '- "analysis": string — brief explanation of what failed and what you changed\n'
        "\n"
        "Rules:\n"
        "- Use only commands from ALLOWED.\n"
        "- Prefer small adjustments: different setpoints, extra delay, remeasure, updated assert/limit.\n"
        "- Do NOT invent categories/actions.\n"
        "- Do NOT use config or raw unless the user explicitly needed it in the original request.\n"
        "- If the failure is environmental and not fixable by bench commands, return empty commands "
        'and explain in "analysis".\n'
        "- Include assert/limit checks when verifying a fix.\n"
    )


def build_repair_user_content(
    user_text: str,
    results: List[Dict[str, Any]],
    allowed: str,
    rag_block: str,
    *,
    last_commands: Optional[List[str]] = None,
    conversation_turns: Optional[List[Dict[str, Any]]] = None,
) -> str:
    parts: List[str] = []
    if rag_block:
        parts.append(f"CONTEXT:\n{rag_block}\n")
    conv = format_conversation_for_plan(conversation_turns or [])
    if conv:
        parts.append(conv)
    if last_commands:
        parts.append("COMMANDS ALREADY RUN (do not repeat unless required):\n")
        parts.extend(f"- {c}" for c in last_commands)
        parts.append("")
    parts.append(f"ALLOWED:\n{allowed}\n")
    parts.append(f"ORIGINAL REQUEST:\n{(user_text or '').strip() or '(none)'}\n")
    parts.append(f"FAILED RESULTS:\n{_results_block(results)}")
    repair_hint = (user_text or "").strip()
    if repair_hint and repair_hint.lower() not in {"repair", "fix"}:
        parts.append(f"\nOPERATOR HINT:\n{repair_hint}")
    return "\n".join(parts)


def make_conversation_turn(
    user: str,
    commands: List[str],
    results: List[Dict[str, Any]],
    *,
    analysis: str = "",
) -> Dict[str, Any]:
    return {
        "user": (user or "").strip(),
        "commands": list(commands or []),
        "analysis": (analysis or "").strip(),
        "outcome": summarize_results_outcome(results),
    }
