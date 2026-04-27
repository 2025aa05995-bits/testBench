from typing import Dict, Any, Optional
from .base import FunctionGeneratorBase


class SimulatedFunctionGenerator(FunctionGeneratorBase):
    """Simulated function generator for testing without real hardware."""

    ACTIONS = {
        'output_on': 'Enable output',
        'output_off': 'Disable output',
    }

    def __init__(self, resource_name: Optional[str] = None):
        super().__init__(resource_name or "SIM_FG_01")
        self._output_on = False
        self._frequency = 1000.0
        self._amplitude = 1.0
        self._offset = 0.0
        self._waveform = 'sine'
        self._burst_enabled = False
        self._burst_count = 1

    def connect(self, address: Optional[str] = None) -> None:
        self.connected = True
        if address:
            self.resource_name = address
        print(
            f"[SIMULATED] FunctionGenerator connected to {self.resource_name}")

    def disconnect(self) -> None:
        self.connected = False
        self._output_on = False
        print(f"[SIMULATED] FunctionGenerator disconnected")

    def reset(self) -> None:
        self._output_on = False
        self._frequency = 1000.0
        self._amplitude = 1.0
        self._offset = 0.0
        self._waveform = 'sine'
        self._burst_enabled = False
        print(f"[SIMULATED] FunctionGenerator reset")

    def identify(self) -> str:
        return f"SimulatedFunctionGenerator (resource: {self.resource_name})"

    def output_on(self) -> None:
        if not self.connected:
            raise RuntimeError("Not connected")
        self._output_on = True
        print(
            f"[SIMULATED] Output ON - {self._waveform} {self._frequency}Hz @ {self._amplitude}V")

    def output_off(self) -> None:
        self._output_on = False
        print(f"[SIMULATED] Output OFF")

    def set_frequency(self, frequency_hz: float) -> None:
        if not self.connected:
            raise RuntimeError("Not connected")
        self._frequency = frequency_hz
        print(f"[SIMULATED] Frequency set to {frequency_hz}Hz")

    def set_amplitude(self, amplitude_v: float) -> None:
        if not self.connected:
            raise RuntimeError("Not connected")
        self._amplitude = amplitude_v
        print(f"[SIMULATED] Amplitude set to {amplitude_v}V")

    def set_offset(self, offset_v: float) -> None:
        if not self.connected:
            raise RuntimeError("Not connected")
        self._offset = offset_v
        print(f"[SIMULATED] Offset set to {offset_v}V")

    def set_waveform(self, waveform: str) -> None:
        if not self.connected:
            raise RuntimeError("Not connected")
        valid = ['sine', 'square', 'triangle', 'ramp', 'pulse']
        if waveform not in valid:
            raise ValueError(f"Invalid waveform: {waveform}")
        self._waveform = waveform
        print(f"[SIMULATED] Waveform set to {waveform}")

    def set_burst_mode(self, enabled: bool, count: Optional[int] = None) -> None:
        if not self.connected:
            raise RuntimeError("Not connected")
        self._burst_enabled = enabled
        if count:
            self._burst_count = count
        print(
            f"[SIMULATED] Burst mode {'enabled' if enabled else 'disabled'} (count: {self._burst_count})")

    def status(self) -> Dict[str, Any]:
        return {
            'resource': self.resource_name,
            'connected': self.connected,
            'output_on': self._output_on,
            'frequency': self._frequency,
            'amplitude': self._amplitude,
            'offset': self._offset,
            'waveform': self._waveform,
            'burst_enabled': self._burst_enabled,
        }

    def configure(self, **settings: Any) -> None:
        if 'frequency' in settings:
            self.set_frequency(settings['frequency'])
        if 'amplitude' in settings:
            self.set_amplitude(settings['amplitude'])
        if 'offset' in settings:
            self.set_offset(settings['offset'])
        if 'waveform' in settings:
            self.set_waveform(settings['waveform'])

    def measure(self, parameter: str) -> Any:
        if parameter == 'frequency':
            return self._frequency
        elif parameter == 'amplitude':
            return self._amplitude
        else:
            raise ValueError(f"Unknown parameter: {parameter}")

    def execute(self, action: str, args: list) -> Any:
        if action == 'output_on':
            return self.output_on()
        elif action == 'output_off':
            return self.output_off()
        else:
            raise ValueError(f"Unknown action: {action}")
