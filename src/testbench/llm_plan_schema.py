"""Structured LLM plan schema: commands, pass/fail checks, and criteria."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class PlanCheck:
    """One assert or limit to run after setup commands."""

    type: str  # assert | limit
    command: str
    expected: Optional[float] = None
    tolerance: Optional[float] = None
    min_value: Optional[float] = None
    max_value: Optional[float] = None
    field: Optional[str] = None
    label: Optional[str] = None


@dataclass
class StructuredPlan:
    """Parsed LLM plan before flattening to executable script lines."""

    commands: List[str] = field(default_factory=list)
    analysis: str = ""
    checks: List[PlanCheck] = field(default_factory=list)
    pass_criteria: List[str] = field(default_factory=list)


def _float_or_none(v: Any) -> Optional[float]:
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def parse_checks(raw: Any) -> List[PlanCheck]:
    if not isinstance(raw, list):
        return []
    out: List[PlanCheck] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        kind = str(item.get("type", "") or "").strip().lower()
        cmd = str(item.get("command", "") or item.get("bench_command", "") or "").strip()
        if kind not in {"assert", "limit"} or not cmd:
            continue
        chk = PlanCheck(
            type=kind,
            command=cmd,
            expected=_float_or_none(item.get("expected")),
            tolerance=_float_or_none(item.get("tolerance")),
            min_value=_float_or_none(item.get("min") if "min" in item else item.get("min_value")),
            max_value=_float_or_none(item.get("max") if "max" in item else item.get("max_value")),
            field=str(item.get("field", "") or "").strip() or None,
            label=str(item.get("label", "") or "").strip() or None,
        )
        if kind == "assert" and chk.expected is None:
            continue
        if kind == "limit" and (chk.min_value is None or chk.max_value is None):
            continue
        out.append(chk)
    return out


def parse_pass_criteria(raw: Any) -> List[str]:
    if not isinstance(raw, list):
        return []
    return [str(x).strip() for x in raw if str(x).strip()]


def check_to_command_line(chk: PlanCheck) -> str:
    """Convert a structured check to an assert/limit script line."""
    cmd = chk.command.strip()
    if chk.type == "assert":
        tol = chk.tolerance if chk.tolerance is not None else 0.0
        exp = chk.expected if chk.expected is not None else 0.0
        if chk.field:
            return f"assert {cmd} expected={exp} tolerance={tol} field={chk.field}"
        return f"assert {cmd} {exp} {tol}"
    vmin = chk.min_value if chk.min_value is not None else 0.0
    vmax = chk.max_value if chk.max_value is not None else 0.0
    if chk.field:
        return f"limit {cmd} field={chk.field} min={vmin} max={vmax}"
    return f"limit {cmd} {vmin} {vmax}"


def checks_to_command_lines(checks: List[PlanCheck]) -> List[str]:
    lines: List[str] = []
    for chk in checks:
        if chk.label:
            lines.append(f'"{chk.label}"')
        lines.append(check_to_command_line(chk))
    return lines


def merge_plan_commands(commands: List[str], checks: List[PlanCheck]) -> List[str]:
    """
    Flatten plan: setup commands first, then generated assert/limit lines.

    Skips exact duplicate lines already present in ``commands``.
    """
    base = [str(c).strip() for c in commands if str(c).strip()]
    seen = {c.lower() for c in base}
    for line in checks_to_command_lines(checks):
        key = line.lower()
        if key not in seen:
            base.append(line)
            seen.add(key)
    return base


def structured_plan_from_payload(payload: Dict[str, Any]) -> StructuredPlan:
    commands_raw = payload.get("commands", [])
    commands: List[str] = []
    if isinstance(commands_raw, list):
        for c in commands_raw:
            s = str(c).strip()
            if s:
                commands.append(s)

    analysis = str(payload.get("analysis", "") or "").strip()
    checks = parse_checks(payload.get("checks"))
    criteria = parse_pass_criteria(payload.get("pass_criteria"))

    return StructuredPlan(
        commands=commands,
        analysis=analysis,
        checks=checks,
        pass_criteria=criteria,
    )


def finalize_plan(plan: StructuredPlan, *, include_checks: bool = True) -> Tuple[List[str], str]:
    """Return executable command list and analysis text (with optional criteria appendix)."""
    commands = list(plan.commands)
    if include_checks and plan.checks:
        commands = merge_plan_commands(commands, plan.checks)

    analysis = plan.analysis
    if plan.pass_criteria:
        crit = "\n".join(f"- {c}" for c in plan.pass_criteria)
        if analysis:
            analysis = f"{analysis}\n\nPass criteria:\n{crit}"
        else:
            analysis = f"Pass criteria:\n{crit}"
    return commands, analysis


def plan_schema_prompt_section() -> str:
    """Extra system-prompt text for structured plans."""
    return (
        'Optional keys (schema v2):\n'
        '- "checks": array of pass/fail steps after setup commands. Each object:\n'
        '  - type: "assert" or "limit"\n'
        '  - command: bench/bc command that returns a number (e.g. bc.mm.measure_voltage)\n'
        '  - assert: "expected" and "tolerance" (numbers)\n'
        '  - limit: "min" and "max" (numbers); optional "field" for dict results\n'
        '  - optional "label": short heading shown before the check\n'
        '- "pass_criteria": array of human-readable acceptance strings (for analysis only)\n'
        "\n"
        "Example check:\n"
        '{"type": "assert", "command": "bc.mm.measure_voltage", "expected": 5.25, "tolerance": 0.1}\n'
        '{"type": "limit", "command": "bc.ps.measure_voltage", "min": 3.0, "max": 3.6}\n'
        "\n"
        "When the user asks for limits, tolerance, pass/fail, or verification, include checks.\n"
        "Checks are converted to assert/limit script lines automatically.\n"
    )
