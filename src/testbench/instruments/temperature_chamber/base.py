from typing import Dict, Any, Optional
from ..base import InstrumentBase


class TemperatureChamberBase(InstrumentBase):
    def set_temperature(self, temperature_c: float) -> None:
        raise NotImplementedError

    def get_temperature(self) -> float:
        raise NotImplementedError

    def wait_for_temperature(self, temperature_c: float, timeout_s: Optional[float] = None) -> None:
        raise NotImplementedError

    def set_ramp_rate(self, rate_c_per_min: float) -> None:
        raise NotImplementedError

    def set_humidity(self, humidity_pct: float) -> None:
        raise NotImplementedError
