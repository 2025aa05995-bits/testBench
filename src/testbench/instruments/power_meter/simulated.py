from typing import Dict, Any, Optional
from .base import PowerMeterBase


class SimulatedPowerMeter(PowerMeterBase):
    """Simulated optical power meter for testing without real hardware."""

    ACTIONS = {
        'measure': 'Measure optical power',
    }

    def __init__(self, resource_name: Optional[str] = None):
        super().__init__(resource_name or "SIM_PM_01")
        self._wavelength = 1550.0  # nm
        self._power_dbm = -30.0
        self._averaging = False

    def connect(self, address: Optional[str] = None) -> None:
        self.connected = True
        if address:
            self.resource_name = address
        print(f"[SIMULATED] PowerMeter connected to {self.resource_name}")

    def disconnect(self) -> None:
        self.connected = False
        print(f"[SIMULATED] PowerMeter disconnected")

    def reset(self) -> None:
        self._wavelength = 1550.0
        self._power_dbm = -30.0
        self._averaging = False
        print(f"[SIMULATED] PowerMeter reset")

    def identify(self) -> str:
        return f"SimulatedPowerMeter (resource: {self.resource_name})"

    def measure_power(self) -> float:
        if not self.connected:
            raise RuntimeError("Not connected")
        return self._power_dbm

    def measure_energy(self) -> float:
        if not self.connected:
            raise RuntimeError("Not connected")
        return 0.001  # Simulated energy in Joules

    def set_wavelength(self, wavelength_nm: float) -> None:
        if not self.connected:
            raise RuntimeError("Not connected")
        self._wavelength = wavelength_nm
        print(f"[SIMULATED] Wavelength set to {wavelength_nm}nm")

    def set_average(self, enabled: bool) -> None:
        if not self.connected:
            raise RuntimeError("Not connected")
        self._averaging = enabled
        print(f"[SIMULATED] Averaging {'enabled' if enabled else 'disabled'}")

    def status(self) -> Dict[str, Any]:
        return {
            'resource': self.resource_name,
            'connected': self.connected,
            'wavelength': self._wavelength,
            'power_dbm': self._power_dbm,
            'averaging': self._averaging,
        }

    def configure(self, **settings: Any) -> None:
        if 'wavelength' in settings:
            self.set_wavelength(settings['wavelength'])
        if 'averaging' in settings:
            self.set_average(settings['averaging'])

    def measure(self, parameter: str) -> Any:
        if parameter == 'power':
            return self.measure_power()
        elif parameter == 'energy':
            return self.measure_energy()
        else:
            raise ValueError(f"Unknown parameter: {parameter}")

    def execute(self, action: str, args: list) -> Any:
        if action == 'measure':
            return self.measure_power()
        else:
            raise ValueError(f"Unknown action: {action}")
