from typing import Dict, Any, Optional
from .base import TemperatureChamberBase


class SimulatedTemperatureChamber(TemperatureChamberBase):
    """Simulated temperature chamber for testing without real hardware."""

    ACTIONS = {
        'get_temp': 'Get current temperature',
    }

    def __init__(self, resource_name: Optional[str] = None):
        super().__init__(resource_name or "SIM_TC_01")
        self._current_temp = 25.0  # Room temperature
        self._target_temp = 25.0
        self._ramping = False
        self._ramp_rate = 5.0  # C/min
        self._humidity = 50.0

    def connect(self, address: Optional[str] = None) -> None:
        self.connected = True
        if address:
            self.resource_name = address
        print(
            f"[SIMULATED] TemperatureChamber connected to {self.resource_name}")

    def disconnect(self) -> None:
        self.connected = False
        self._ramping = False
        print(f"[SIMULATED] TemperatureChamber disconnected")

    def reset(self) -> None:
        self._current_temp = 25.0
        self._target_temp = 25.0
        self._ramping = False
        self._ramp_rate = 5.0
        self._humidity = 50.0
        print(f"[SIMULATED] TemperatureChamber reset")

    def identify(self) -> str:
        return f"SimulatedTemperatureChamber (resource: {self.resource_name})"

    def set_temperature(self, temperature_c: float) -> None:
        if not self.connected:
            raise RuntimeError("Not connected")
        self._target_temp = temperature_c
        self._ramping = True
        print(
            f"[SIMULATED] Target temperature set to {temperature_c}°C (ramping...)")

    def get_temperature(self) -> float:
        if not self.connected:
            raise RuntimeError("Not connected")
        # Simulate gradual temperature change
        if self._ramping:
            diff = self._target_temp - self._current_temp
            if abs(diff) > 0.1:
                step = self._ramp_rate / 60  # Convert per-minute to per-check rate
                self._current_temp += (step if diff > 0 else -step)
            else:
                self._current_temp = self._target_temp
                self._ramping = False
        return self._current_temp

    def wait_for_temperature(self, temperature_c: float, timeout_s: Optional[float] = None) -> None:
        if not self.connected:
            raise RuntimeError("Not connected")
        self.set_temperature(temperature_c)
        print(
            f"[SIMULATED] Waiting for {temperature_c}°C (timeout: {timeout_s}s)")

    def set_ramp_rate(self, rate_c_per_min: float) -> None:
        if not self.connected:
            raise RuntimeError("Not connected")
        self._ramp_rate = rate_c_per_min
        print(f"[SIMULATED] Ramp rate set to {rate_c_per_min}°C/min")

    def set_humidity(self, humidity_pct: float) -> None:
        if not self.connected:
            raise RuntimeError("Not connected")
        if not 0 <= humidity_pct <= 100:
            raise ValueError("Humidity must be 0-100%")
        self._humidity = humidity_pct
        print(f"[SIMULATED] Humidity set to {humidity_pct}%")

    def status(self) -> Dict[str, Any]:
        return {
            'resource': self.resource_name,
            'connected': self.connected,
            'current_temp': self.get_temperature(),
            'target_temp': self._target_temp,
            'ramping': self._ramping,
            'ramp_rate': self._ramp_rate,
            'humidity': self._humidity,
        }

    def configure(self, **settings: Any) -> None:
        if 'temperature' in settings:
            self.set_temperature(settings['temperature'])
        if 'ramp_rate' in settings:
            self.set_ramp_rate(settings['ramp_rate'])
        if 'humidity' in settings:
            self.set_humidity(settings['humidity'])

    def measure(self, parameter: str) -> Any:
        if parameter == 'temperature':
            return self.get_temperature()
        elif parameter == 'humidity':
            return self._humidity
        else:
            raise ValueError(f"Unknown parameter: {parameter}")

    def execute(self, action: str, args: list) -> Any:
        if action == 'get_temp':
            return self.get_temperature()
        else:
            raise ValueError(f"Unknown action: {action}")
