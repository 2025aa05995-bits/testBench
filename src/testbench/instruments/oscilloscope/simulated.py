import math
import random
from typing import Dict, Any, Optional, List
from .base import OscilloscopeBase


class SimulatedOscilloscope(OscilloscopeBase):
    """Simulated oscilloscope for testing without real hardware."""

    ACTIONS = {
        'run': 'Start oscilloscope acquisition',
        'stop': 'Stop oscilloscope acquisition',
        'get_trace': 'Return time_s and voltage_v arrays (channel [num_points])',
    }

    def __init__(self, resource_name: Optional[str] = None, num_channels: int = 4):
        super().__init__(resource_name or "SIM_OSC_01")
        self.num_channels = num_channels
        self._running = False
        self._timebase = 0.001  # 1ms/div
        self._channel_settings = {
            i: {'enabled': True, 'volts_per_div': 1.0, 'offset': 0.0}
            for i in range(1, num_channels + 1)
        }

    def connect(self, address: Optional[str] = None) -> None:
        self.connected = True
        if address:
            self.resource_name = address
        print(f"[SIMULATED] Oscilloscope connected to {self.resource_name}")

    def disconnect(self) -> None:
        self.connected = False
        self._running = False
        print(f"[SIMULATED] Oscilloscope disconnected")

    def reset(self) -> None:
        self._running = False
        self._timebase = 0.001
        for ch in self._channel_settings:
            self._channel_settings[ch] = {
                'enabled': True, 'volts_per_div': 1.0, 'offset': 0.0}
        print(f"[SIMULATED] Oscilloscope reset")

    def identify(self) -> str:
        return f"SimulatedOscilloscope {self.num_channels}CH (resource: {self.resource_name})"

    def run(self) -> None:
        if not self.connected:
            raise RuntimeError("Not connected")
        self._running = True
        print(f"[SIMULATED] Oscilloscope running")

    def stop(self) -> None:
        self._running = False
        print(f"[SIMULATED] Oscilloscope stopped")

    def set_timebase(self, seconds_per_div: float) -> None:
        if not self.connected:
            raise RuntimeError("Not connected")
        self._timebase = seconds_per_div
        print(f"[SIMULATED] Timebase set to {seconds_per_div}s/div")

    def set_voltage_scale(self, channel: int, volts_per_div: float) -> None:
        if not self.connected:
            raise RuntimeError("Not connected")
        if channel not in self._channel_settings:
            raise ValueError(f"Invalid channel: {channel}")
        self._channel_settings[channel]['volts_per_div'] = volts_per_div
        print(f"[SIMULATED] CH{channel} voltage scale: {volts_per_div}V/div")

    def set_channel_enabled(self, channel: int, enabled: bool) -> None:
        if not self.connected:
            raise RuntimeError("Not connected")
        if channel not in self._channel_settings:
            raise ValueError(f"Invalid channel: {channel}")
        self._channel_settings[channel]['enabled'] = enabled
        print(
            f"[SIMULATED] CH{channel} {'enabled' if enabled else 'disabled'}")

    def get_trace(self, channel: int = 1, num_points: int = 256) -> Dict[str, List[float]]:
        """Simulated acquisition: time (s) vs voltage (V) for plotting.

        Adds realistic noise to mimic a real scope: per-sample Gaussian noise
        scaled to ~2% of the channel's volts/div, plus tiny per-sweep
        amplitude/offset jitter so consecutive captures differ slightly.
        """
        if not self.connected:
            raise RuntimeError("Not connected")
        if channel not in self._channel_settings:
            raise ValueError(f"Invalid channel: {channel}")
        if not self._running:
            raise RuntimeError("Oscilloscope not running — use bench.osc.run first")
        num_points = max(8, min(int(num_points), 8192))
        # Horizontal span: 10 divisions at current timebase (seconds per division)
        total_time = 10.0 * self._timebase
        dt = total_time / (num_points - 1) if num_points > 1 else total_time
        vdiv = self._channel_settings[channel]['volts_per_div']
        offset = self._channel_settings[channel]['offset']
        # Simulated 1 kHz sine, amplitude ~1 division peak
        freq_hz = 1000.0
        # Per-sweep variability: ±0.5% amplitude, ±0.5% of vdiv DC offset jitter
        amp = vdiv * (1.0 + random.gauss(0.0, 0.005))
        sweep_offset = offset + random.gauss(0.0, 0.005 * vdiv)
        # Per-sample voltage noise: ~2% of vdiv, with a small floor so flat lines
        # also look noisy when vdiv is configured very small.
        noise_sigma = max(0.02 * vdiv, 1e-4)
        time_s: List[float] = []
        voltage_v: List[float] = []
        for i in range(num_points):
            t = i * dt
            v = amp * math.sin(2.0 * math.pi * freq_hz * t) + sweep_offset
            v += random.gauss(0.0, noise_sigma)
            time_s.append(t)
            voltage_v.append(v)
        return {'time_s': time_s, 'voltage_v': voltage_v}

    def capture_waveform(self, channel: int) -> Dict[str, Any]:
        if not self.connected:
            raise RuntimeError("Not connected")
        if channel not in self._channel_settings:
            raise ValueError(f"Invalid channel: {channel}")
        if not self._running:
            raise RuntimeError("Oscilloscope not running")
        return {
            'channel': channel,
            'timebase': self._timebase,
            'volts_per_div': self._channel_settings[channel]['volts_per_div'],
            'points': [0.0, 0.5, 1.0, 0.5, 0.0],  # Simulated waveform
        }

    def measure(self, parameter: str, channel: int = 1) -> Any:
        if not self.connected:
            raise RuntimeError("Not connected")
        if parameter == 'frequency':
            return 1000.0  # 1kHz
        elif parameter == 'amplitude':
            return self._channel_settings[channel]['volts_per_div'] * 4
        elif parameter == 'period':
            return 1e-3  # 1ms
        else:
            raise ValueError(f"Unknown parameter: {parameter}")

    def status(self) -> Dict[str, Any]:
        return {
            'resource': self.resource_name,
            'connected': self.connected,
            'running': self._running,
            'timebase': self._timebase,
            'channels': self._channel_settings,
        }

    def configure(self, **settings: Any) -> None:
        if 'timebase' in settings:
            self.set_timebase(settings['timebase'])
        if 'channels' in settings:
            for ch, cfg in settings['channels'].items():
                if 'volts_per_div' in cfg:
                    self.set_voltage_scale(ch, cfg['volts_per_div'])

    def execute(self, action: str, args: list) -> Any:
        if action == 'run':
            return self.run()
        elif action == 'stop':
            return self.stop()
        elif action == 'get_trace':
            ch = int(args[0]) if args else 1
            n = int(args[1]) if len(args) > 1 else 256
            return self.get_trace(ch, n)
        else:
            raise ValueError(f"Unknown action: {action}")
