from typing import Dict, Any, Optional
from .base import SpectrumAnalyzerBase


class SimulatedSpectrumAnalyzer(SpectrumAnalyzerBase):
    """Simulated spectrum analyzer for testing without real hardware."""

    ACTIONS = {
        'start_sweep': 'Start frequency sweep',
        'stop_sweep': 'Stop frequency sweep',
    }

    def __init__(self, resource_name: Optional[str] = None):
        super().__init__(resource_name or "SIM_SA_01")
        self._sweeping = False
        self._center_freq = 1e9  # 1GHz
        self._span = 1e9
        self._rbw = 1e6  # 1MHz

    def connect(self, address: Optional[str] = None) -> None:
        self.connected = True
        if address:
            self.resource_name = address
        print(
            f"[SIMULATED] SpectrumAnalyzer connected to {self.resource_name}")

    def disconnect(self) -> None:
        self.connected = False
        self._sweeping = False
        print(f"[SIMULATED] SpectrumAnalyzer disconnected")

    def reset(self) -> None:
        self._sweeping = False
        self._center_freq = 1e9
        self._span = 1e9
        self._rbw = 1e6
        print(f"[SIMULATED] SpectrumAnalyzer reset")

    def identify(self) -> str:
        return f"SimulatedSpectrumAnalyzer (resource: {self.resource_name})"

    def start_sweep(self) -> None:
        if not self.connected:
            raise RuntimeError("Not connected")
        self._sweeping = True
        print(f"[SIMULATED] Spectrum sweep started")

    def stop_sweep(self) -> None:
        self._sweeping = False
        print(f"[SIMULATED] Spectrum sweep stopped")

    def set_center_frequency(self, frequency_hz: float) -> None:
        if not self.connected:
            raise RuntimeError("Not connected")
        self._center_freq = frequency_hz
        print(f"[SIMULATED] Center frequency set to {frequency_hz}Hz")

    def set_span(self, span_hz: float) -> None:
        if not self.connected:
            raise RuntimeError("Not connected")
        self._span = span_hz
        print(f"[SIMULATED] Span set to {span_hz}Hz")

    def set_resolution_bandwidth(self, rbw_hz: float) -> None:
        if not self.connected:
            raise RuntimeError("Not connected")
        self._rbw = rbw_hz
        print(f"[SIMULATED] Resolution bandwidth set to {rbw_hz}Hz")

    def measure_peak(self) -> Dict[str, Any]:
        if not self.connected:
            raise RuntimeError("Not connected")
        return {
            'frequency': self._center_freq,
            'power_dbm': -30.0,
        }

    def get_trace(self) -> Any:
        if not self.connected:
            raise RuntimeError("Not connected")
        return {
            'center_freq': self._center_freq,
            'span': self._span,
            'rbw': self._rbw,
            'data': [-20, -25, -30, -35, -40],  # Simulated trace
        }

    def status(self) -> Dict[str, Any]:
        return {
            'resource': self.resource_name,
            'connected': self.connected,
            'sweeping': self._sweeping,
            'center_freq': self._center_freq,
            'span': self._span,
            'rbw': self._rbw,
        }

    def configure(self, **settings: Any) -> None:
        if 'center_freq' in settings:
            self.set_center_frequency(settings['center_freq'])
        if 'span' in settings:
            self.set_span(settings['span'])
        if 'rbw' in settings:
            self.set_resolution_bandwidth(settings['rbw'])

    def measure(self, parameter: str) -> Any:
        if parameter == 'peak':
            return self.measure_peak()
        else:
            raise ValueError(f"Unknown parameter: {parameter}")

    def execute(self, action: str, args: list) -> Any:
        if action == 'start_sweep':
            return self.start_sweep()
        elif action == 'stop_sweep':
            return self.stop_sweep()
        else:
            raise ValueError(f"Unknown action: {action}")
