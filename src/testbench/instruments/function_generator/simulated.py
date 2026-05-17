from typing import Dict, Any, List, Optional, Tuple
from ..arb_waveform import load_waveform_csv
from ..simulated_mixin import SimulatedInstrumentMixin, merge_simulated_actions
from .base import FunctionGeneratorBase


class SimulatedFunctionGenerator(FunctionGeneratorBase, SimulatedInstrumentMixin):
    """Simulated function generator for testing without real hardware."""

    ACTIONS = merge_simulated_actions({
        'output_on': 'Enable output',
        'output_off': 'Disable output',
        'set_frequency': 'Set frequency (Hz)',
        'set_amplitude': 'Set amplitude (V)',
        'set_waveform': 'Set waveform (sine|square|triangle|ramp|pulse|arb)',
        'load_arb_csv': 'Load ARB waveform from CSV file path',
        'get_arb': 'Return loaded ARB times and voltages',
        'clear_arb': 'Clear loaded ARB waveform',
    })

    def __init__(self, resource_name: Optional[str] = None):
        super().__init__(resource_name or "SIM_FG_01")
        self._output_on = False
        self._frequency = 1000.0
        self._amplitude = 1.0
        self._offset = 0.0
        self._waveform = 'sine'
        self._burst_enabled = False
        self._burst_count = 1
        self._arb_times: List[float] = []
        self._arb_voltages: List[float] = []
        self._arb_source: Optional[str] = None

    def connect(self, address: Optional[str] = None) -> None:
        self.connected = True
        if address:
            self.resource_name = address
        print(f"[SIMULATED] FunctionGenerator connected to {self.resource_name}")

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
        self.clear_arb()
        self._sim_fault = None
        print(f"[SIMULATED] FunctionGenerator reset")

    def identify(self) -> str:
        return f"SimulatedFunctionGenerator (resource: {self.resource_name})"

    def output_on(self) -> None:
        self.sim_require_connected()
        self._output_on = True
        print(f"[SIMULATED] Output ON - {self._waveform} {self._frequency}Hz @ {self._amplitude}V")

    def output_off(self) -> None:
        self._output_on = False
        print(f"[SIMULATED] Output OFF")

    def set_frequency(self, frequency_hz: float) -> None:
        self.sim_require_connected()
        self._frequency = frequency_hz
        print(f"[SIMULATED] Frequency set to {frequency_hz}Hz")

    def set_amplitude(self, amplitude_v: float) -> None:
        self.sim_require_connected()
        self._amplitude = amplitude_v
        print(f"[SIMULATED] Amplitude set to {amplitude_v}V")

    def set_offset(self, offset_v: float) -> None:
        self.sim_require_connected()
        self._offset = offset_v
        print(f"[SIMULATED] Offset set to {offset_v}V")

    def set_waveform(self, waveform: str) -> None:
        self.sim_require_connected()
        valid = ['sine', 'square', 'triangle', 'ramp', 'pulse', 'arb']
        if waveform not in valid:
            raise ValueError(f"Invalid waveform: {waveform}")
        if waveform == 'arb' and not self._arb_voltages:
            raise ValueError("Load ARB CSV first (load_arb_csv)")
        self._waveform = waveform
        print(f"[SIMULATED] Waveform set to {waveform}")

    def load_arb_csv(self, path: str) -> Dict[str, Any]:
        self.sim_require_connected()
        times, volts = load_waveform_csv(path)
        self._arb_times = times
        self._arb_voltages = volts
        self._arb_source = path
        self._waveform = 'arb'
        print(f"[SIMULATED] ARB loaded: {len(volts)} points from {path}")
        return {'points': len(volts), 'path': path, 'duration_s': times[-1] - times[0] if len(times) > 1 else 0.0}

    def get_arb(self) -> Dict[str, Any]:
        self.sim_require_connected()
        return {
            'times': list(self._arb_times),
            'voltages': list(self._arb_voltages),
            'source': self._arb_source,
            'points': len(self._arb_voltages),
        }

    def clear_arb(self) -> None:
        self._arb_times = []
        self._arb_voltages = []
        self._arb_source = None
        if self._waveform == 'arb':
            self._waveform = 'sine'
        print(f"[SIMULATED] ARB cleared")

    def set_burst_mode(self, enabled: bool, count: Optional[int] = None) -> None:
        self.sim_require_connected()
        self._burst_enabled = enabled
        if count:
            self._burst_count = count
        print(f"[SIMULATED] Burst mode {'enabled' if enabled else 'disabled'} (count: {self._burst_count})")

    def status(self) -> Dict[str, Any]:
        return {
            'resource': self.resource_name,
            'connected': self.connected,
            'output_on': self._output_on,
            'frequency_hz': self._frequency,
            'amplitude_v': self._amplitude,
            'offset_v': self._offset,
            'waveform': self._waveform,
            'burst_enabled': self._burst_enabled,
            'arb_points': len(self._arb_voltages),
            'arb_source': self._arb_source,
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
        self.sim_wait_settling()
        if parameter == 'frequency':
            return self.sim_apply_noise(self._frequency)
        if parameter == 'amplitude':
            return self.sim_apply_noise(self._amplitude)
        raise ValueError(f"Unknown parameter: {parameter}")

    def execute(self, action: str, args: list) -> Any:
        handlers = {
            'output_on': lambda a: self.output_on(),
            'output_off': lambda a: self.output_off(),
            'set_frequency': lambda a: self.set_frequency(float(a[0])),
            'set_amplitude': lambda a: self.set_amplitude(float(a[0])),
            'set_waveform': lambda a: self.set_waveform(str(a[0])),
            'load_arb_csv': lambda a: self.load_arb_csv(str(a[0])),
            'get_arb': lambda a: self.get_arb(),
            'clear_arb': lambda a: self.clear_arb(),
        }
        return self._dispatch_or_raise(action, args, handlers)
