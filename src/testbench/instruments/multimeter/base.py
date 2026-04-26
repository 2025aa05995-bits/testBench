from typing import Dict, Any, Optional
from ..base import InstrumentBase


class MultimeterBase(InstrumentBase):
    def measure_voltage(self, dc: bool = True) -> float:
        raise NotImplementedError

    def measure_current(self, dc: bool = True) -> float:
        raise NotImplementedError

    def measure_resistance(self) -> float:
        raise NotImplementedError

    def measure_continuity(self) -> bool:
        raise NotImplementedError

    def set_range(self, measurement: str, value: Optional[float] = None) -> None:
        raise NotImplementedError

    def auto_range(self, enabled: bool) -> None:
        raise NotImplementedError
