from typing import Dict, Any, Optional
from ..base import InstrumentBase


class SourceMeasureUnitBase(InstrumentBase):
    def source_on(self) -> None:
        raise NotImplementedError

    def source_off(self) -> None:
        raise NotImplementedError

    def set_voltage(self, voltage_v: float) -> None:
        raise NotImplementedError

    def set_current(self, current_a: float) -> None:
        raise NotImplementedError

    def set_compliance(self, limit: float) -> None:
        raise NotImplementedError

    def measure_voltage(self) -> float:
        raise NotImplementedError

    def measure_current(self) -> float:
        raise NotImplementedError
