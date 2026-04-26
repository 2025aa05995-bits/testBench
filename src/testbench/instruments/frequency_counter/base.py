from typing import Dict, Any, Optional
from ..base import InstrumentBase


class FrequencyCounterBase(InstrumentBase):
    def measure_frequency(self) -> float:
        raise NotImplementedError

    def measure_period(self) -> float:
        raise NotImplementedError

    def set_gate_time(self, seconds: float) -> None:
        raise NotImplementedError

    def auto_range(self, enabled: bool) -> None:
        raise NotImplementedError
