from typing import Dict, Any, Optional
from .base import MultimeterBase


class SimulatedMultimeter(MultimeterBase):
    """Simulated multimeter for testing without real hardware."""

    ACTIONS = {
        'measure_voltage': 'Measure DC voltage',
        'measure_current': 'Measure DC current',
    }

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
        print(f"[SIMULATED] Multimeter reset")

    def identify(self) -> str:
        return f"SimulatedMultimeter (resource: {self.resource_name})"

    def measure_voltage(self, dc: bool = True) -> float:
        if not self.connected:
            raise RuntimeError("Not connected")
        return 5.25 if dc else 2.5

    def measure_current(self, dc: bool = True) -> float:
        if not self.connected:
            raise RuntimeError("Not connected")
        return 0.125 if dc else 0.05

    def measure_resistance(self) -> float:
        if not self.connected:
            raise RuntimeError("Not connected")
        return 1000.0

    def measure_continuity(self) -> bool:
        if not self.connected:
            raise RuntimeError("Not connected")
        return True

    def set_range(self, measurement: str, value: Optional[float] = None) -> None:
        if not self.connected:
            raise RuntimeError("Not connected")
        self._measurement_type = measurement
        self._range = value
        print(f"[SIMULATED] Range set: {measurement} = {value}")

    def auto_range(self, enabled: bool) -> None:
        if not self.connected:
            raise RuntimeError("Not connected")
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
            self.set_range(settings.get(
                'measurement', 'voltage'), settings['range'])

    def measure(self, parameter: str) -> Any:
        if parameter == 'voltage':
            return self.measure_voltage()
        elif parameter == 'current':
            return self.measure_current()
        elif parameter == 'resistance':
            return self.measure_resistance()
        else:
            raise ValueError(f"Unknown parameter: {parameter}")

    def execute(self, action: str, args: list) -> Any:
        if action == 'measure_voltage':
            return self.measure_voltage()
        elif action == 'measure_current':
            return self.measure_current()
        else:
            raise ValueError(f"Unknown action: {action}")
