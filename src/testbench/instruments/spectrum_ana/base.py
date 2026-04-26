from typing import Dict, Any, Optional
from ..base import InstrumentBase


class SpectrumAnalyzerBase(InstrumentBase):
    def start_sweep(self) -> None:
        raise NotImplementedError

    def stop_sweep(self) -> None:
        raise NotImplementedError

    def set_center_frequency(self, frequency_hz: float) -> None:
        raise NotImplementedError

    def set_span(self, span_hz: float) -> None:
        raise NotImplementedError

    def set_resolution_bandwidth(self, rbw_hz: float) -> None:
        raise NotImplementedError

    def measure_peak(self) -> Dict[str, Any]:
        raise NotImplementedError

    def get_trace(self) -> Any:
        raise NotImplementedError
