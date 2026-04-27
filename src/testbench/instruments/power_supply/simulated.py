from typing import Dict, Any, Optional
from .base import PowerSupplyBase


class SimulatedPowerSupply(PowerSupplyBase):
    """Simulated power supply for testing without real hardware."""

    ACTIONS = {
        'on': 'Enable power supply',
        'off': 'Disable power supply',
        'setVoltage': 'Set output voltage (V)',
        'set_voltage': 'Set output voltage (V)',
        'setCurrent': 'Set current limit (A)',
        'set_current': 'Set current limit (A)',
    }

    def __init__(self, resource_name: Optional[str] = None):
        super().__init__(resource_name or "SIM_PS_01")
        self._voltage = 0.0
        self._current = 0.0
        self._is_on = False
        self._ocp_enabled = False

    def connect(self, address: Optional[str] = None) -> None:
        self.connected = True
        if address:
            self.resource_name = address
        print(f"[SIMULATED] PowerSupply connected to {self.resource_name}")

    def disconnect(self) -> None:
        self.connected = False
        self._is_on = False
        print(
            f"[SIMULATED] PowerSupply disconnected from {self.resource_name}")

    def reset(self) -> None:
        self._voltage = 0.0
        self._current = 0.0
        self._is_on = False
        self._ocp_enabled = False
        print(f"[SIMULATED] PowerSupply reset")

    def identify(self) -> str:
        return f"SimulatedPowerSupply (resource: {self.resource_name})"

    def on(self) -> None:
        if not self.connected:
            raise RuntimeError("Not connected")
        self._is_on = True
        print(
            f"[SIMULATED] PowerSupply ON - V: {self._voltage}V, I: {self._current}A")

    def off(self) -> None:
        self._is_on = False
        print(f"[SIMULATED] PowerSupply OFF")

    def set_voltage(self, voltage: float) -> None:
        if not self.connected:
            raise RuntimeError("Not connected")
        self._voltage = voltage
        print(f"[SIMULATED] Voltage set to {voltage}V")

    def set_current(self, current: float) -> None:
        if not self.connected:
            raise RuntimeError("Not connected")
        self._current = current
        print(f"[SIMULATED] Current set to {current}A")

    def enable_overcurrent_protection(self, enabled: bool) -> None:
        if not self.connected:
            raise RuntimeError("Not connected")
        self._ocp_enabled = enabled
        print(
            f"[SIMULATED] Overcurrent Protection {'enabled' if enabled else 'disabled'}")

    def measure_voltage(self) -> float:
        if not self.connected:
            raise RuntimeError("Not connected")
        return self._voltage if self._is_on else 0.0

    def measure_current(self) -> float:
        if not self.connected:
            raise RuntimeError("Not connected")
        return self._current if self._is_on else 0.0

    def measure_power(self) -> float:
        if not self.connected:
            raise RuntimeError("Not connected")
        return (self._voltage * self._current) if self._is_on else 0.0

    def status(self) -> Dict[str, Any]:
        return {
            'resource': self.resource_name,
            'connected': self.connected,
            'is_on': self._is_on,
            'voltage_v': self._voltage,
            'current_a': self._current,
            'power_w': self.measure_power(),
            'ocp_enabled': self._ocp_enabled,
        }

    def configure(self, **settings: Any) -> None:
        if 'voltage' in settings:
            self.set_voltage(settings['voltage'])
        if 'current' in settings:
            self.set_current(settings['current'])
        if 'ocp' in settings:
            self.enable_overcurrent_protection(settings['ocp'])

    def measure(self, parameter: str) -> Any:
        if parameter == 'voltage':
            return self.measure_voltage()
        elif parameter == 'current':
            return self.measure_current()
        elif parameter == 'power':
            return self.measure_power()
        else:
            raise ValueError(f"Unknown parameter: {parameter}")

    def execute(self, action: str, args: list) -> Any:
        if action == 'on':
            return self.on()
        elif action == 'off':
            return self.off()
        elif action in {'setVoltage', 'set_voltage'}:
            return self.set_voltage(float(args[0]))
        elif action in {'setCurrent', 'set_current'}:
            return self.set_current(float(args[0]))
        else:
            raise ValueError(f"Unknown action: {action}")
