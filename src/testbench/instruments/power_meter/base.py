from typing import Dict, Any, Optional
from ..base import InstrumentBase


class PowerMeterBase(InstrumentBase):
    def measure_power(self) -> float:
        raise NotImplementedError

    def measure_energy(self) -> float:
        raise NotImplementedError

    def set_wavelength(self, wavelength_nm: float) -> None:
        raise NotImplementedError

    def set_average(self, enabled: bool) -> None:
        raise NotImplementedError
