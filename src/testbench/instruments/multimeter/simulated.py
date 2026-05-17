from typing import Dict, Any, Optional
from ..simulated_mixin import SimulatedInstrumentMixin, merge_simulated_actions
from .base import MultimeterBase


class SimulatedMultimeter(MultimeterBase, SimulatedInstrumentMixin):
    """Simulated multimeter for testing without real hardware."""

    ACTIONS = merge_simulated_actions({
        'measure_voltage': 'Measure DC voltage',
        'measure_current': 'Measure DC current',
        'measure_resistance': 'Measure resistance (ohms)',
        'measure_continuity': 'Measure continuity (true/false)',
    })

    def __init__(self, resource_name: Optional[str] = None):
        super().__init__(resource_name or "SIM_MM_01")
        self._auto_range_enabled = True
        self._range = None
        self._measurement_type = 'voltage_dc'

    def connect(self, address: Optional[str] = None) -> None:
        self.connected = True
        if address:
            self.resource_name = address
        print(f"[SIMULATED] Multimeter connected to {self.resource_name}")

    def disconnect(self) -> None:
        self.connected = False
        print(f"[SIMULATED] Multimeter disconnected")

    def reset(self) -> None:
        self._auto_range_enabled = True
        self._range = None
        self._measurement_type = 'voltage_dc'
        self._sim_fault = None
        print(f"[SIMULATED] Multimeter reset")

    def identify(self) -> str:
        return f"SimulatedMultimeter (resource: {self.resource_name})"

    def measure_voltage(self, dc: bool = True) -> float:
        self.sim_require_connected()
        self.sim_wait_settling()
        raw = 5.25 if dc else 2.5
        return self.sim_apply_noise(raw)

    def measure_current(self, dc: bool = True) -> float:
        self.sim_require_connected()
        self.sim_wait_settling()
        raw = 0.125 if dc else 0.05
        return self.sim_apply_noise(raw)

    def measure_resistance(self) -> float:
        self.sim_require_connected()
        self.sim_wait_settling()
        return self.sim_apply_noise(1000.0)

    def measure_continuity(self) -> bool:
        self.sim_require_connected()
        self.sim_wait_settling()
        return True

    def set_range(self, measurement: str, value: Optional[float] = None) -> None:
        self.sim_require_connected()
        self._measurement_type = measurement
        self._range = value
        print(f"[SIMULATED] Range set: {measurement} = {value}")

    def auto_range(self, enabled: bool) -> None:
        self.sim_require_connected()
        self._auto_range_enabled = enabled
        print(f"[SIMULATED] Auto-range {'enabled' if enabled else 'disabled'}")

    def status(self) -> Dict[str, Any]:
        return {
            'resource': self.resource_name,
            'connected': self.connected,
            'auto_range': self._auto_range_enabled,
            'range': self._range,
            'measurement_type': self._measurement_type,
        }

    def configure(self, **settings: Any) -> None:
        if 'auto_range' in settings:
            self.auto_range(settings['auto_range'])
        if 'range' in settings:
            self.set_range(settings.get('measurement', 'voltage'), settings['range'])

    def measure(self, parameter: str) -> Any:
        if parameter == 'voltage':
            return self.measure_voltage()
        if parameter == 'current':
            return self.measure_current()
        if parameter == 'resistance':
            return self.measure_resistance()
        raise ValueError(f"Unknown parameter: {parameter}")

    def execute(self, action: str, args: list) -> Any:
        handlers = {
            'measure_voltage': lambda a: self.measure_voltage(),
            'measure_current': lambda a: self.measure_current(),
            'measure_resistance': lambda a: self.measure_resistance(),
            'measure_continuity': lambda a: self.measure_continuity(),
        }
        return self._dispatch_or_raise(action, args, handlers)
