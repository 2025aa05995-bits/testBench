from typing import Dict, Any, Optional
from ..simulated_mixin import SimulatedInstrumentMixin, merge_simulated_actions
from .base import SourceMeasureUnitBase


class SimulatedSourceMeasureUnit(SourceMeasureUnitBase, SimulatedInstrumentMixin):
    """Simulated source measure unit (SMU) for testing without real hardware."""

    ACTIONS = merge_simulated_actions({
        'source_on': 'Enable source output',
        'source_off': 'Disable source output',
        'measure_voltage': 'Measure voltage (V)',
        'measure_current': 'Measure current (A)',
    })

    def __init__(self, resource_name: Optional[str] = None):
        super().__init__(resource_name or "SIM_SMU_01")
        self._sourcing = False
        self._voltage = 0.0
        self._current = 0.0
        self._compliance = 1.0
        self._source_mode = 'voltage'  # 'voltage' or 'current'

    def connect(self, address: Optional[str] = None) -> None:
        self.connected = True
        if address:
            self.resource_name = address
        print(
            f"[SIMULATED] SourceMeasureUnit connected to {self.resource_name}")

    def disconnect(self) -> None:
        self.connected = False
        self._sourcing = False
        print(f"[SIMULATED] SourceMeasureUnit disconnected")

    def reset(self) -> None:
        self._sourcing = False
        self._voltage = 0.0
        self._current = 0.0
        self._compliance = 1.0
        self._source_mode = 'voltage'
        print(f"[SIMULATED] SourceMeasureUnit reset")

    def identify(self) -> str:
        return f"SimulatedSourceMeasureUnit (resource: {self.resource_name})"

    def source_on(self) -> None:
        if not self.connected:
            raise RuntimeError("Not connected")
        self._sourcing = True
        print(f"[SIMULATED] Source ON (Mode: {self._source_mode})")

    def source_off(self) -> None:
        self._sourcing = False
        print(f"[SIMULATED] Source OFF")

    def set_voltage(self, voltage_v: float) -> None:
        if not self.connected:
            raise RuntimeError("Not connected")
        self._voltage = voltage_v
        self._source_mode = 'voltage'
        print(f"[SIMULATED] Voltage source set to {voltage_v}V")

    def set_current(self, current_a: float) -> None:
        if not self.connected:
            raise RuntimeError("Not connected")
        self._current = current_a
        self._source_mode = 'current'
        print(f"[SIMULATED] Current source set to {current_a}A")

    def set_compliance(self, limit: float) -> None:
        if not self.connected:
            raise RuntimeError("Not connected")
        self._compliance = limit
        print(f"[SIMULATED] Compliance limit set to {limit}")

    def measure_voltage(self) -> float:
        if not self.connected:
            raise RuntimeError("Not connected")
        return self._voltage if self._sourcing else 0.0

    def measure_current(self) -> float:
        if not self.connected:
            raise RuntimeError("Not connected")
        return self._current if self._sourcing else 0.0

    def status(self) -> Dict[str, Any]:
        return {
            'resource': self.resource_name,
            'connected': self.connected,
            'sourcing': self._sourcing,
            'source_mode': self._source_mode,
            'voltage': self._voltage,
            'current': self._current,
            'compliance': self._compliance,
        }

    def configure(self, **settings: Any) -> None:
        if 'voltage' in settings:
            self.set_voltage(settings['voltage'])
        if 'current' in settings:
            self.set_current(settings['current'])
        if 'compliance' in settings:
            self.set_compliance(settings['compliance'])

    def measure(self, parameter: str) -> Any:
        if parameter == 'voltage':
            return self.measure_voltage()
        elif parameter == 'current':
            return self.measure_current()
        else:
            raise ValueError(f"Unknown parameter: {parameter}")

    def execute(self, action: str, args: list) -> Any:
        handlers = {
            'source_on': lambda a: self.source_on(),
            'source_off': lambda a: self.source_off(),
            'measure_voltage': lambda a: self.sim_apply_noise_optional(self.measure_voltage()),
            'measure_current': lambda a: self.sim_apply_noise_optional(self.measure_current()),
        }
        return self._dispatch_or_raise(action, args, handlers)
