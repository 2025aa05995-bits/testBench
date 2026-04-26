from typing import Dict, Any, Optional
from .base import OscilloscopeBase


class SimulatedOscilloscope(OscilloscopeBase):
    """Simulated oscilloscope for testing without real hardware."""

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
        else:
            raise ValueError(f"Unknown action: {action}")
