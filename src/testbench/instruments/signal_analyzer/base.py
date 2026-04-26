from typing import Dict, Any, Optional
from ..base import InstrumentBase


class SignalAnalyzerBase(InstrumentBase):
    def set_frequency(self, frequency_hz: float) -> None:
        raise NotImplementedError

    def set_span(self, span_hz: float) -> None:
        raise NotImplementedError

    def start_capture(self) -> None:
        raise NotImplementedError

    def stop_capture(self) -> None:
        raise NotImplementedError

    def get_spectrum(self) -> Any:
        raise NotImplementedError

    def measure_power(self, bandwidth_hz: Optional[float] = None) -> float:
        raise NotImplementedError

    def demodulate(self, mode: str) -> Dict[str, Any]:
        raise NotImplementedError
