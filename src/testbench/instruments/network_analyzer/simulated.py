from typing import Dict, Any, Optional
from .base import NetworkAnalyzerBase


class SimulatedNetworkAnalyzer(NetworkAnalyzerBase):
    """Simulated network analyzer for testing without real hardware."""

    ACTIONS = {
        'calibrate': 'Run calibration (full, isolation, or through)',
        'cal': 'Run calibration (full, isolation, or through)',
    }

    def __init__(self, resource_name: Optional[str] = None):
        super().__init__(resource_name or "SIM_NA_01")
        self._start_freq = 1e6  # 1MHz
        self._stop_freq = 1e9  # 1GHz
        self._power = 0.0  # dBm
        self._calibrated = False

    def connect(self, address: Optional[str] = None) -> None:
        self.connected = True
        if address:
            self.resource_name = address
        print(f"[SIMULATED] NetworkAnalyzer connected to {self.resource_name}")

    def disconnect(self) -> None:
        self.connected = False
        print(f"[SIMULATED] NetworkAnalyzer disconnected")

    def reset(self) -> None:
        self._start_freq = 1e6
        self._stop_freq = 1e9
        self._power = 0.0
        self._calibrated = False
        print(f"[SIMULATED] NetworkAnalyzer reset")

    def identify(self) -> str:
        return f"SimulatedNetworkAnalyzer (resource: {self.resource_name})"

    def set_start_frequency(self, frequency_hz: float) -> None:
        if not self.connected:
            raise RuntimeError("Not connected")
        self._start_freq = frequency_hz
        print(f"[SIMULATED] Start frequency set to {frequency_hz}Hz")

    def set_stop_frequency(self, frequency_hz: float) -> None:
        if not self.connected:
            raise RuntimeError("Not connected")
        self._stop_freq = frequency_hz
        print(f"[SIMULATED] Stop frequency set to {frequency_hz}Hz")

    def set_power(self, power_dbm: float) -> None:
        if not self.connected:
            raise RuntimeError("Not connected")
        self._power = power_dbm
        print(f"[SIMULATED] RF Power set to {power_dbm}dBm")

    def measure_s_parameters(self) -> Dict[str, Any]:
        if not self.connected:
            raise RuntimeError("Not connected")
        return {
            'S11': -15.5,  # Return loss
            'S21': -0.5,   # Insertion loss
            'S12': -0.5,
            'S22': -20.0,
        }

    def calibrate(self, calibration_type: str = 'full') -> None:
        if not self.connected:
            raise RuntimeError("Not connected")
        self._calibrated = True
        print(f"[SIMULATED] Calibration ({calibration_type}) completed")

    def status(self) -> Dict[str, Any]:
        return {
            'resource': self.resource_name,
            'connected': self.connected,
            'start_freq': self._start_freq,
            'stop_freq': self._stop_freq,
            'power_dbm': self._power,
            'calibrated': self._calibrated,
        }

    def configure(self, **settings: Any) -> None:
        if 'start_freq' in settings:
            self.set_start_frequency(settings['start_freq'])
        if 'stop_freq' in settings:
            self.set_stop_frequency(settings['stop_freq'])
        if 'power' in settings:
            self.set_power(settings['power'])

    def measure(self, parameter: str) -> Any:
        if parameter == 's_parameters':
            return self.measure_s_parameters()
        else:
            raise ValueError(f"Unknown parameter: {parameter}")

    def execute(self, action: str, args: list) -> Any:
        if action in {'calibrate', 'cal'}:
            return self.calibrate(args[0] if args else 'full')
        else:
            raise ValueError(f"Unknown action: {action}")
