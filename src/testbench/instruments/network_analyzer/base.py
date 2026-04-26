from typing import Dict, Any, Optional
from ..base import InstrumentBase


class NetworkAnalyzerBase(InstrumentBase):
    def set_start_frequency(self, frequency_hz: float) -> None:
        raise NotImplementedError

    def set_stop_frequency(self, frequency_hz: float) -> None:
        raise NotImplementedError

    def set_power(self, power_dbm: float) -> None:
        raise NotImplementedError

    def measure_s_parameters(self) -> Dict[str, Any]:
        raise NotImplementedError

    def calibrate(self, calibration_type: str = 'full') -> None:
        raise NotImplementedError
