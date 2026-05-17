"""Shared behavior for simulated instruments: common actions, noise, faults, settling."""

from __future__ import annotations

import random
import time
from typing import Any, Dict, List, Optional

_NOT_HANDLED = object()

SIMULATED_COMMON_ACTIONS: Dict[str, str] = {
    "reset": "Reset instrument to default state",
    "status": "Return instrument status dict",
    "identify": "Return simulated identity string",
    "fault_inject": "Inject fault: disconnect | overload | read_error",
    "fault_clear": "Clear injected fault",
    "sim_noise_on": "Enable measurement noise (default on)",
    "sim_noise_off": "Disable measurement noise",
    "sim_settling": "Set settling delay in ms before next measurement (sim_settling 50)",
}


def merge_simulated_actions(specific: Dict[str, str]) -> Dict[str, str]:
    """Merge device-specific ACTIONS with shared simulated commands."""
    out = dict(SIMULATED_COMMON_ACTIONS)
    out.update(specific)
    return out


class SimulatedInstrumentMixin:
    """
    Mixin for simulated drivers.

    Provides fault injection, optional Gaussian noise on numeric reads,
    settling delay, and standard bench actions (reset/status/identify).
    """

    _sim_fault: Optional[str] = None
    _sim_noise_enabled: bool = True
    _sim_noise_percent: float = 0.5
    _sim_settling_ms: float = 0.0

    def sim_require_connected(self) -> None:
        fault = getattr(self, "_sim_fault", None)
        if fault == "disconnect":
            raise RuntimeError("Simulated fault: instrument disconnected")
        if fault == "read_error":
            raise RuntimeError("Simulated fault: read error")
        if fault == "overload":
            raise RuntimeError("Simulated fault: overload")
        if not getattr(self, "connected", False):
            raise RuntimeError("Not connected")

    def sim_apply_noise(self, value: float) -> float:
        if not self._sim_noise_enabled:
            return value
        pct = max(0.0, float(self._sim_noise_percent))
        if pct <= 0:
            return value
        return float(value) * (1.0 + random.gauss(0.0, pct / 100.0))

    def sim_apply_noise_optional(self, value: Any) -> Any:
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return self.sim_apply_noise(float(value))
        return value

    def sim_wait_settling(self) -> None:
        ms = float(getattr(self, "_sim_settling_ms", 0.0) or 0.0)
        if ms > 0:
            time.sleep(min(ms, 60_000.0) / 1000.0)

    def sim_status_extras(self) -> Dict[str, Any]:
        return {
            "sim_fault": self._sim_fault,
            "sim_noise_enabled": self._sim_noise_enabled,
            "sim_noise_percent": self._sim_noise_percent,
            "sim_settling_ms": self._sim_settling_ms,
        }

    def dispatch_simulated_common(self, action: str, args: List[str]) -> Any:
        """
        Handle shared simulated actions.

        Returns ``_NOT_HANDLED`` if the action is device-specific.
        """
        if action == "reset":
            self.reset()
            return "OK"
        if action == "status":
            st = self.status()
            if isinstance(st, dict):
                st = dict(st)
                st.update(self.sim_status_extras())
            return st
        if action == "identify":
            return self.identify()
        if action == "fault_inject":
            if not args:
                raise ValueError("Usage: fault_inject <disconnect|overload|read_error>")
            kind = args[0].lower()
            if kind not in {"disconnect", "overload", "read_error"}:
                raise ValueError(f"Unknown fault type: {kind}")
            self._sim_fault = kind
            if kind == "disconnect":
                self.connected = False
            return f"Fault injected: {kind}"
        if action == "fault_clear":
            self._sim_fault = None
            return "Fault cleared"
        if action == "sim_noise_on":
            self._sim_noise_enabled = True
            return "Simulated measurement noise enabled"
        if action == "sim_noise_off":
            self._sim_noise_enabled = False
            return "Simulated measurement noise disabled"
        if action == "sim_settling":
            if not args:
                raise ValueError("Usage: sim_settling <milliseconds>")
            self._sim_settling_ms = float(args[0])
            return f"Settling delay set to {self._sim_settling_ms} ms"
        return _NOT_HANDLED

    def _dispatch_or_raise(self, action: str, args: List[str], handlers: Dict[str, Any]) -> Any:
        """Try common dispatch, then ``handlers`` map of action -> callable."""
        common = self.dispatch_simulated_common(action, args)
        if common is not _NOT_HANDLED:
            return common
        if action in handlers:
            return handlers[action](args)
        raise ValueError(f"Unknown action: {action}")
