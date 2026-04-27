from typing import Dict, Any, Optional
from .base import FrequencyCounterBase


class SimulatedFrequencyCounter(FrequencyCounterBase):
    """Simulated frequency counter for testing without real hardware."""

    ACTIONS = {
        'measure': 'Measure frequency',
    }

    def __init__(self, resource_name: Optional[str] = None):
        super().__init__(resource_name or "SIM_FC_01")
        self._gate_time = 0.1  # 100ms
        self._auto_range = True

    def connect(self, address: Optional[str] = None) -> None:
        self.connected = True
        if address:
            self.resource_name = address
        print(
            f"[SIMULATED] FrequencyCounter connected to {self.resource_name}")

    def disconnect(self) -> None:
        self.connected = False
        print(f"[SIMULATED] FrequencyCounter disconnected")

    def reset(self) -> None:
        self._gate_time = 0.1
        self._auto_range = True
        print(f"[SIMULATED] FrequencyCounter reset")

    def identify(self) -> str:
        return f"SimulatedFrequencyCounter (resource: {self.resource_name})"

    def measure_frequency(self) -> float:
        if not self.connected:
            raise RuntimeError("Not connected")
        return 1000000.0  # 1MHz

    def measure_period(self) -> float:
        if not self.connected:
            raise RuntimeError("Not connected")
        return 1e-6  # 1us

    def set_gate_time(self, seconds: float) -> None:
        if not self.connected:
            raise RuntimeError("Not connected")
        self._gate_time = seconds
        print(f"[SIMULATED] Gate time set to {seconds}s")

    def auto_range(self, enabled: bool) -> None:
        if not self.connected:
            raise RuntimeError("Not connected")
        self._auto_range = enabled
        print(f"[SIMULATED] Auto-range {'enabled' if enabled else 'disabled'}")

    def status(self) -> Dict[str, Any]:
        return {
            'resource': self.resource_name,
            'connected': self.connected,
            'gate_time': self._gate_time,
            'auto_range': self._auto_range,
        }

    def configure(self, **settings: Any) -> None:
        if 'gate_time' in settings:
            self.set_gate_time(settings['gate_time'])
        if 'auto_range' in settings:
            self.auto_range(settings['auto_range'])

    def measure(self, parameter: str) -> Any:
        if parameter == 'frequency':
            return self.measure_frequency()
        elif parameter == 'period':
            return self.measure_period()
        else:
            raise ValueError(f"Unknown parameter: {parameter}")

    def execute(self, action: str, args: list) -> Any:
        if action == 'measure':
            return self.measure_frequency()
        else:
            raise ValueError(f"Unknown action: {action}")
