from typing import Dict, Any, Optional
from ..base import InstrumentBase


class FunctionGeneratorBase(InstrumentBase):
    def output_on(self) -> None:
        raise NotImplementedError

    def output_off(self) -> None:
        raise NotImplementedError

    def set_frequency(self, frequency_hz: float) -> None:
        raise NotImplementedError

    def set_amplitude(self, amplitude_v: float) -> None:
        raise NotImplementedError

    def set_offset(self, offset_v: float) -> None:
        raise NotImplementedError

    def set_waveform(self, waveform: str) -> None:
        raise NotImplementedError

    def set_burst_mode(self, enabled: bool, count: Optional[int] = None) -> None:
        raise NotImplementedError
