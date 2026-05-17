from typing import Dict, Any, Optional
from ..simulated_mixin import SimulatedInstrumentMixin, merge_simulated_actions
from .base import PowerSupplyBase


class SimulatedPowerSupply(PowerSupplyBase, SimulatedInstrumentMixin):
    """Simulated power supply for testing without real hardware."""

    ACTIONS = merge_simulated_actions({
        'on': 'Enable power supply',
        'off': 'Disable power supply',
        'setVoltage': 'Set output voltage (V)',
        'set_voltage': 'Set output voltage (V)',
        'setCurrent': 'Set current limit (A)',
        'set_current': 'Set current limit (A)',
        'measure_voltage': 'Measure output voltage (V)',
        'measure_current': 'Measure output current (A)',
        'measure_power': 'Measure output power (W)',
    })

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
        print(f"[SIMULATED] PowerSupply disconnected from {self.resource_name}")

    def reset(self) -> None:
        self._voltage = 0.0
        self._current = 0.0
        self._is_on = False
        self._ocp_enabled = False
        self._sim_fault = None
        print(f"[SIMULATED] PowerSupply reset")

    def identify(self) -> str:
        return f"SimulatedPowerSupply (resource: {self.resource_name})"

    def on(self) -> None:
        self.sim_require_connected()
        self._is_on = True
        print(f"[SIMULATED] PowerSupply ON - V: {self._voltage}V, I: {self._current}A")

    def off(self) -> None:
        self._is_on = False
        print(f"[SIMULATED] PowerSupply OFF")

    def set_voltage(self, voltage: float) -> None:
        self.sim_require_connected()
        self._voltage = voltage
        print(f"[SIMULATED] Voltage set to {voltage}V")

    def set_current(self, current: float) -> None:
        self.sim_require_connected()
        self._current = current
        print(f"[SIMULATED] Current set to {current}A")

    def enable_overcurrent_protection(self, enabled: bool) -> None:
        self.sim_require_connected()
        self._ocp_enabled = enabled
        print(f"[SIMULATED] Overcurrent Protection {'enabled' if enabled else 'disabled'}")

    def measure_voltage(self) -> float:
        self.sim_require_connected()
        self.sim_wait_settling()
        raw = self._voltage if self._is_on else 0.0
        return self.sim_apply_noise(raw)

    def measure_current(self) -> float:
        self.sim_require_connected()
        self.sim_wait_settling()
        raw = self._current if self._is_on else 0.0
        return self.sim_apply_noise(raw)

    def measure_power(self) -> float:
        self.sim_require_connected()
        self.sim_wait_settling()
        raw = (self._voltage * self._current) if self._is_on else 0.0
        return self.sim_apply_noise(raw)

    def status(self) -> Dict[str, Any]:
        return {
            'resource': self.resource_name,
            'connected': self.connected,
            'is_on': self._is_on,
            'voltage_v': self._voltage,
            'current_a': self._current,
            'power_w': (self._voltage * self._current) if self._is_on else 0.0,
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
        if parameter == 'current':
            return self.measure_current()
        if parameter == 'power':
            return self.measure_power()
        raise ValueError(f"Unknown parameter: {parameter}")

    def execute(self, action: str, args: list) -> Any:
        handlers = {
            'on': lambda a: self.on(),
            'off': lambda a: self.off(),
            'setVoltage': lambda a: self.set_voltage(float(a[0])),
            'set_voltage': lambda a: self.set_voltage(float(a[0])),
            'setCurrent': lambda a: self.set_current(float(a[0])),
            'set_current': lambda a: self.set_current(float(a[0])),
            'measure_voltage': lambda a: self.measure_voltage(),
            'measure_current': lambda a: self.measure_current(),
            'measure_power': lambda a: self.measure_power(),
        }
        return self._dispatch_or_raise(action, args, handlers)
