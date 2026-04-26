from typing import Dict, Any, Optional
from ..base import InstrumentBase


class ElectronicLoadBase(InstrumentBase):
    def enable(self) -> None:
        raise NotImplementedError

    def disable(self) -> None:
        raise NotImplementedError

    def set_current(self, current_a: float) -> None:
        raise NotImplementedError

    def set_voltage(self, voltage_v: float) -> None:
        raise NotImplementedError

    def set_power(self, power_w: float) -> None:
        raise NotImplementedError

    def set_mode(self, mode: str) -> None:
        raise NotImplementedError

    def measure_voltage(self) -> float:
        raise NotImplementedError

    def measure_current(self) -> float:
        raise NotImplementedError
