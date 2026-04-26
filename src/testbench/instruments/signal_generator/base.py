from typing import Dict, Any, Optional
from ..base import InstrumentBase


class SignalGeneratorBase(InstrumentBase):
    def output_on(self) -> None:
        raise NotImplementedError

    def output_off(self) -> None:
        raise NotImplementedError

    def set_frequency(self, frequency_hz: float) -> None:
        raise NotImplementedError

    def set_amplitude(self, amplitude_v: float) -> None:
        raise NotImplementedError

    def set_waveform(self, waveform: str) -> None:
        raise NotImplementedError

    def modulate(self, mode: str, settings: Dict[str, Any]) -> None:
        raise NotImplementedError

    def status(self) -> Dict[str, Any]:
        return {
            'resource': self.resource_name,
            'connected': self.connected,
        }
