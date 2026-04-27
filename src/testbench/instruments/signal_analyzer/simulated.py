from typing import Dict, Any, Optional
from .base import SignalAnalyzerBase


class SimulatedSignalAnalyzer(SignalAnalyzerBase):
    """Simulated signal analyzer for testing without real hardware."""

    ACTIONS = {
        'start': 'Start signal capture',
        'stop': 'Stop signal capture',
    }

    def __init__(self, resource_name: Optional[str] = None):
        super().__init__(resource_name or "SIM_SAN_01")
        self._frequency = 1e9
        self._span = 100e6
        self._capturing = False
        self._spectrum = []

    def connect(self, address: Optional[str] = None) -> None:
        self.connected = True
        if address:
            self.resource_name = address
        print(f"[SIMULATED] SignalAnalyzer connected to {self.resource_name}")

    def disconnect(self) -> None:
        self.connected = False
        self._capturing = False
        print(f"[SIMULATED] SignalAnalyzer disconnected")

    def reset(self) -> None:
        self._frequency = 1e9
        self._span = 100e6
        self._capturing = False
        self._spectrum = []
        print(f"[SIMULATED] SignalAnalyzer reset")

    def identify(self) -> str:
        return f"SimulatedSignalAnalyzer (resource: {self.resource_name})"

    def set_frequency(self, frequency_hz: float) -> None:
        if not self.connected:
            raise RuntimeError("Not connected")
        self._frequency = frequency_hz
        print(f"[SIMULATED] Frequency set to {frequency_hz}Hz")

    def set_span(self, span_hz: float) -> None:
        if not self.connected:
            raise RuntimeError("Not connected")
        self._span = span_hz
        print(f"[SIMULATED] Span set to {span_hz}Hz")

    def start_capture(self) -> None:
        if not self.connected:
            raise RuntimeError("Not connected")
        self._capturing = True
        self._spectrum = [-20, -25, -30, -35, -40]  # Simulated spectrum
        print(f"[SIMULATED] Capture started")

    def stop_capture(self) -> None:
        self._capturing = False
        print(f"[SIMULATED] Capture stopped")

    def get_spectrum(self) -> Any:
        if not self.connected:
            raise RuntimeError("Not connected")
        return {
            'frequency': self._frequency,
            'span': self._span,
            'data': self._spectrum,
        }

    def measure_power(self, bandwidth_hz: Optional[float] = None) -> float:
        if not self.connected:
            raise RuntimeError("Not connected")
        return -30.0

    def demodulate(self, mode: str) -> Dict[str, Any]:
        if not self.connected:
            raise RuntimeError("Not connected")
        return {
            'mode': mode,
            'iq': [0.5, 0.3],
            'error_rate': 0.001,
        }

    def status(self) -> Dict[str, Any]:
        return {
            'resource': self.resource_name,
            'connected': self.connected,
            'frequency': self._frequency,
            'span': self._span,
            'capturing': self._capturing,
        }

    def configure(self, **settings: Any) -> None:
        if 'frequency' in settings:
            self.set_frequency(settings['frequency'])
        if 'span' in settings:
            self.set_span(settings['span'])

    def measure(self, parameter: str) -> Any:
        if parameter == 'power':
            return self.measure_power()
        elif parameter == 'spectrum':
            return self.get_spectrum()
        else:
            raise ValueError(f"Unknown parameter: {parameter}")

    def execute(self, action: str, args: list) -> Any:
        if action == 'start':
            return self.start_capture()
        elif action == 'stop':
            return self.stop_capture()
        else:
            raise ValueError(f"Unknown action: {action}")
