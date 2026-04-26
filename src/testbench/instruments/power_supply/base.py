from typing import Dict, Any, Optional
from ..base import InstrumentBase


class PowerSupplyBase(InstrumentBase):
    def on(self) -> None:
        raise NotImplementedError

    def off(self) -> None:
        raise NotImplementedError

    def set_voltage(self, voltage: float) -> None:
        raise NotImplementedError

    def set_current(self, current: float) -> None:
        raise NotImplementedError

    def enable_overcurrent_protection(self, enabled: bool) -> None:
        raise NotImplementedError

    def measure_voltage(self) -> float:
        raise NotImplementedError

    def measure_current(self) -> float:
        raise NotImplementedError

    def measure_power(self) -> float:
        raise NotImplementedError

    def status(self) -> Dict[str, Any]:
        return {
            'resource': self.resource_name,
            'connected': self.connected,
        }
