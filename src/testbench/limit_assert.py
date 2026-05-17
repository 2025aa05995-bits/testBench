"""Parse and evaluate ``assert`` / ``limit`` test commands."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple, Union

Number = Union[int, float]


@dataclass
class CheckResult:
    passed: bool
    message: str
    measured: Any
    expected: Optional[Any] = None
    tolerance: Optional[float] = None
    min_value: Optional[float] = None
    max_value: Optional[float] = None
    field: Optional[str] = None


def _split_bench_and_kv(rest: str) -> tuple:
    """Split ``bc.mm.measure field=x min=1 max=2`` into bench command and kwargs."""
    tokens = rest.split()
    bench_parts: List[str] = []
    kv: Dict[str, str] = {}
    for t in tokens:
        if "=" in t:
            k, _, v = t.partition("=")
            kv[k.strip().lower()] = v.strip()
        else:
            bench_parts.append(t)
    return " ".join(bench_parts).strip(), kv


def _float_arg(s: str, label: str) -> float:
    try:
        return float(s)
    except (TypeError, ValueError) as e:
        raise ValueError(f"Invalid {label}: {s!r}") from e


def coerce_numeric(value: Any, field: Optional[str] = None) -> float:
    """Extract a single numeric measurement from a command result."""
    if isinstance(value, bool):
        raise ValueError("Boolean result cannot be used for numeric assert/limit")
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.strip())
        except ValueError as e:
            raise ValueError(f"Result is not numeric: {value!r}") from e
    if isinstance(value, dict):
        if field:
            if field not in value:
                raise ValueError(f"Field {field!r} not in result keys: {list(value.keys())}")
            return coerce_numeric(value[field])
        for key in (
            "value",
            "voltage",
            "voltage_v",
            "current",
            "current_a",
            "power",
            "power_w",
            "frequency",
            "frequency_hz",
            "temperature",
            "temperature_c",
        ):
            if key in value:
                return coerce_numeric(value[key])
        nums = [v for v in value.values() if isinstance(v, (int, float)) and not isinstance(v, bool)]
        if len(nums) == 1:
            return float(nums[0])
        raise ValueError(
            f"Ambiguous dict result for assert/limit; specify field=<key>. Keys: {list(value.keys())}"
        )
    raise ValueError(f"Cannot coerce result type {type(value).__name__} to a number")


def parse_assert_line(line: str) -> Tuple[str, float, float, Optional[str]]:
    """
    ``assert <bench_command> <expected> <tolerance>``
    or ``assert <bench_command> expected=… tolerance=… [field=…]``.
    """
    s = (line or "").strip()
    if not s.lower().startswith("assert "):
        raise ValueError("Not an assert command")
    rest = s[7:].strip()
    if not rest:
        raise ValueError("Usage: assert <bench_command> <expected> <tolerance>")

    if "expected=" in rest.lower() or "tolerance=" in rest.lower():
        bench, kv = _split_bench_and_kv(rest)
        field = kv.get("field")
        if "expected" in kv and "tolerance" in kv:
            if not bench:
                raise ValueError("assert requires a bench/bc command")
            return bench, _float_arg(kv["expected"], "expected"), _float_arg(kv["tolerance"], "tolerance"), field

    # Split: bench command may contain spaces; last two tokens are expected and tolerance
    parts = rest.split()
    field = None
    if len(parts) < 3:
        raise ValueError("Usage: assert <bench_command> <expected> <tolerance>")
    tolerance = _float_arg(parts[-1], "tolerance")
    expected = _float_arg(parts[-2], "expected")
    bench = " ".join(parts[:-2]).strip()
    if not bench:
        raise ValueError("assert requires a bench/bc command")
    return bench, expected, tolerance, field


def parse_limit_line(line: str) -> Tuple[str, float, float, Optional[str]]:
    """
    ``limit <bench_command> <min> <max>``
    or ``limit <bench_command> min=… max=… [field=…]``.
    """
    s = (line or "").strip()
    if not s.lower().startswith("limit "):
        raise ValueError("Not a limit command")
    rest = s[6:].strip()
    if not rest:
        raise ValueError("Usage: limit <bench_command> <min> <max>")

    if "min=" in rest.lower() or "max=" in rest.lower():
        bench, kv = _split_bench_and_kv(rest)
        field = kv.get("field")
        if "min" in kv and "max" in kv:
            if not bench:
                raise ValueError("limit requires a bench/bc command")
            return bench, _float_arg(kv["min"], "min"), _float_arg(kv["max"], "max"), field

    parts = rest.split()
    field = None
    if len(parts) < 3:
        raise ValueError("Usage: limit <bench_command> <min> <max>")
    vmax = _float_arg(parts[-1], "max")
    vmin = _float_arg(parts[-2], "min")
    bench = " ".join(parts[:-2]).strip()
    if not bench:
        raise ValueError("limit requires a bench/bc command")
    return bench, vmin, vmax, field


def evaluate_assert(measured: Any, expected: float, tolerance: float, field: Optional[str] = None) -> CheckResult:
    try:
        actual = coerce_numeric(measured, field)
    except ValueError as e:
        return CheckResult(False, str(e), measured, expected=expected, tolerance=tolerance, field=field)

    if tolerance < 0:
        return CheckResult(False, "Tolerance must be non-negative", measured, expected, tolerance, field)

    ok = abs(actual - expected) <= tolerance
    msg = (
        f"PASS: {actual} within {expected} ± {tolerance}"
        if ok
        else f"FAIL: {actual} not within {expected} ± {tolerance} (delta={abs(actual - expected):.6g})"
    )
    return CheckResult(ok, msg, actual, expected=expected, tolerance=tolerance, field=field)


def evaluate_limit(measured: Any, vmin: float, vmax: float, field: Optional[str] = None) -> CheckResult:
    try:
        actual = coerce_numeric(measured, field)
    except ValueError as e:
        return CheckResult(False, str(e), measured, min_value=vmin, max_value=vmax, field=field)

    if vmin > vmax:
        return CheckResult(False, f"min ({vmin}) > max ({vmax})", measured, min_value=vmin, max_value=vmax, field=field)

    ok = vmin <= actual <= vmax
    msg = (
        f"PASS: {actual} in [{vmin}, {vmax}]"
        if ok
        else f"FAIL: {actual} outside [{vmin}, {vmax}]"
    )
    return CheckResult(ok, msg, actual, min_value=vmin, max_value=vmax, field=field)


def is_assert_line(line: str) -> bool:
    return (line or "").strip().lower().startswith("assert ")


def is_limit_line(line: str) -> bool:
    return (line or "").strip().lower().startswith("limit ")


def serialize_check(check: CheckResult) -> Dict[str, Any]:
    d: Dict[str, Any] = {
        "passed": check.passed,
        "message": check.message,
        "measured": check.measured,
    }
    if check.expected is not None:
        d["expected"] = check.expected
    if check.tolerance is not None:
        d["tolerance"] = check.tolerance
    if check.min_value is not None:
        d["min"] = check.min_value
    if check.max_value is not None:
        d["max"] = check.max_value
    if check.field:
        d["field"] = check.field
    return d
