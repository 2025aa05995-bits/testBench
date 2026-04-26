from typing import Dict, Any, Optional
from ..base import InstrumentBase


class OscilloscopeBase(InstrumentBase):
    def run(self) -> None:
        raise NotImplementedError

    def stop(self) -> None:
        raise NotImplementedError

    def set_timebase(self, seconds_per_div: float) -> None:
        raise NotImplementedError

    def set_voltage_scale(self, channel: int, volts_per_div: float) -> None:
        raise NotImplementedError

    def set_channel_enabled(self, channel: int, enabled: bool) -> None:
        raise NotImplementedError

    def capture_waveform(self, channel: int) -> Any:
        raise NotImplementedError

    def measure(self, parameter: str, channel: int) -> Any:
        raise NotImplementedError
