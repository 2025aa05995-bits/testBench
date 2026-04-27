from typing import Dict, Any, Optional
from .base import ElectronicLoadBase


class SimulatedElectronicLoad(ElectronicLoadBase):
    """Simulated electronic load for testing without real hardware."""

    ACTIONS = {
        'enable': 'Enable electronic load',
        'disable': 'Disable electronic load',
    }

    def __init__(self, resource_name: Optional[str] = None):
        super().__init__(resource_name or "SIM_EL_01")
        self._enabled = False
        self._current = 0.0
        self._voltage = 0.0
        self._power = 0.0
        self._mode = 'CC'  # CC, CV, CP, CR

    def connect(self, address: Optional[str] = None) -> None:
        self.connected = True
        if address:
            self.resource_name = address
        print(f"[SIMULATED] ElectronicLoad connected to {self.resource_name}")

    def disconnect(self) -> None:
        self.connected = False
        self._enabled = False
        print(f"[SIMULATED] ElectronicLoad disconnected")

    def reset(self) -> None:
        self._enabled = False
        self._current = 0.0
        self._voltage = 0.0
        self._power = 0.0
        self._mode = 'CC'
        print(f"[SIMULATED] ElectronicLoad reset")

    def identify(self) -> str:
        return f"SimulatedElectronicLoad (resource: {self.resource_name})"

    def enable(self) -> None:
        if not self.connected:
            raise RuntimeError("Not connected")
        self._enabled = True
        print(f"[SIMULATED] ElectronicLoad enabled (Mode: {self._mode})")

    def disable(self) -> None:
        self._enabled = False
        print(f"[SIMULATED] ElectronicLoad disabled")

    def set_current(self, current_a: float) -> None:
        if not self.connected:
            raise RuntimeError("Not connected")
        self._current = current_a
        print(f"[SIMULATED] Current set to {current_a}A")

    def set_voltage(self, voltage_v: float) -> None:
        if not self.connected:
            raise RuntimeError("Not connected")
        self._voltage = voltage_v
        print(f"[SIMULATED] Voltage set to {voltage_v}V")

    def set_power(self, power_w: float) -> None:
        if not self.connected:
            raise RuntimeError("Not connected")
        self._power = power_w
        print(f"[SIMULATED] Power set to {power_w}W")

    def set_mode(self, mode: str) -> None:
        if not self.connected:
            raise RuntimeError("Not connected")
        valid_modes = ['CC', 'CV', 'CP', 'CR']
        if mode not in valid_modes:
            raise ValueError(f"Invalid mode: {mode}")
        self._mode = mode
        print(f"[SIMULATED] Mode set to {mode}")

    def measure_voltage(self) -> float:
        if not self.connected:
            raise RuntimeError("Not connected")
        return self._voltage if self._enabled else 0.0

    def measure_current(self) -> float:
        if not self.connected:
            raise RuntimeError("Not connected")
        return self._current if self._enabled else 0.0

    def status(self) -> Dict[str, Any]:
        return {
            'resource': self.resource_name,
            'connected': self.connected,
            'enabled': self._enabled,
            'mode': self._mode,
            'voltage': self._voltage,
            'current': self._current,
            'power': self._power,
        }

    def configure(self, **settings: Any) -> None:
        if 'mode' in settings:
            self.set_mode(settings['mode'])
        if 'current' in settings:
            self.set_current(settings['current'])
        if 'voltage' in settings:
            self.set_voltage(settings['voltage'])

    def measure(self, parameter: str) -> Any:
        if parameter == 'voltage':
            return self.measure_voltage()
        elif parameter == 'current':
            return self.measure_current()
        else:
            raise ValueError(f"Unknown parameter: {parameter}")

    def execute(self, action: str, args: list) -> Any:
        if action == 'enable':
            return self.enable()
        elif action == 'disable':
            return self.disable()
        else:
            raise ValueError(f"Unknown action: {action}")
