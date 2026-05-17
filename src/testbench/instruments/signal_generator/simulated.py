from typing import Dict, Any, Optional
from ..simulated_mixin import SimulatedInstrumentMixin, merge_simulated_actions
from .base import SignalGeneratorBase


class SimulatedSignalGenerator(SignalGeneratorBase, SimulatedInstrumentMixin):
    """Simulated signal generator for testing without real hardware."""

    ACTIONS = merge_simulated_actions({
        'output_on': 'Enable signal output',
        'output_off': 'Disable signal output',
        'setFrequency': 'Set frequency (Hz)',
        'set_frequency': 'Set frequency (Hz)',
        'setAmplitude': 'Set amplitude (V)',
        'set_amplitude': 'Set amplitude (V)',
        'measure': 'Read parameter (frequency|amplitude)',
    })

    def __init__(self, resource_name: Optional[str] = None):
        super().__init__(resource_name or "SIM_SG_01")
        self._output_on = False
        self._frequency = 1000.0  # 1kHz
        self._amplitude = 1.0  # 1V
        self._waveform = 'sine'
        self._modulation_mode = None
        self._modulation_settings = {}

    def connect(self, address: Optional[str] = None) -> None:
        self.connected = True
        if address:
            self.resource_name = address
        print(f"[SIMULATED] SignalGenerator connected to {self.resource_name}")

    def disconnect(self) -> None:
        self.connected = False
        self._output_on = False
        print(f"[SIMULATED] SignalGenerator disconnected")

    def reset(self) -> None:
        self._output_on = False
        self._frequency = 1000.0
        self._amplitude = 1.0
        self._waveform = 'sine'
        self._modulation_mode = None
        self._modulation_settings = {}
        print(f"[SIMULATED] SignalGenerator reset")

    def identify(self) -> str:
        return f"SimulatedSignalGenerator (resource: {self.resource_name})"

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

    def set_waveform(self, waveform: str) -> None:
        if not self.connected:
            raise RuntimeError("Not connected")
        valid_waveforms = ['sine', 'square', 'triangle', 'ramp', 'pulse']
        if waveform not in valid_waveforms:
            raise ValueError(f"Invalid waveform: {waveform}")
        self._waveform = waveform
        print(f"[SIMULATED] Waveform set to {waveform}")

    def modulate(self, mode: str, settings: Dict[str, Any]) -> None:
        if not self.connected:
            raise RuntimeError("Not connected")
        self._modulation_mode = mode
        self._modulation_settings = settings
        print(f"[SIMULATED] Modulation mode: {mode}, settings: {settings}")

    def status(self) -> Dict[str, Any]:
        return {
            'resource': self.resource_name,
            'connected': self.connected,
            'output_on': self._output_on,
            'frequency_hz': self._frequency,
            'amplitude_v': self._amplitude,
            'waveform': self._waveform,
            'modulation_mode': self._modulation_mode,
        }

    def configure(self, **settings: Any) -> None:
        if 'frequency' in settings:
            self.set_frequency(settings['frequency'])
        if 'amplitude' in settings:
            self.set_amplitude(settings['amplitude'])
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
        handlers = {
            'output_on': lambda a: self.output_on(),
            'output_off': lambda a: self.output_off(),
            'setFrequency': lambda a: self.set_frequency(float(a[0])),
            'set_frequency': lambda a: self.set_frequency(float(a[0])),
            'setAmplitude': lambda a: self.set_amplitude(float(a[0])),
            'set_amplitude': lambda a: self.set_amplitude(float(a[0])),
            'measure': lambda a: self.sim_apply_noise_optional(
                self.measure((a[0] if a else 'frequency').strip().lower())
            ),
        }
        return self._dispatch_or_raise(action, args, handlers)
