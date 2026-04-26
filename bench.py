from typing import Any, Dict, List, Optional, Type


class InstrumentBase:
    """Base class for all lab instruments.

    This class defines the most common methods expected for instrument
    control, including connection management, status, identification, and
    generic action execution.
    """

    def __init__(self, resource_name: Optional[str] = None):
        self.resource_name = resource_name
        self.connected = False

    def connect(self, address: Optional[str] = None) -> None:
        raise NotImplementedError

    def disconnect(self) -> None:
        raise NotImplementedError

    def reset(self) -> None:
        raise NotImplementedError

    def identify(self) -> str:
        raise NotImplementedError

    def status(self) -> Dict[str, Any]:
        raise NotImplementedError

    def configure(self, **settings: Any) -> None:
        raise NotImplementedError

    def measure(self, parameter: str) -> Any:
        raise NotImplementedError

    def execute(self, action: str, args: List[str]) -> Any:
        raise NotImplementedError


class PowerSupplyBase(InstrumentBase):
    def on(self, state: bool) -> None:
        raise NotImplementedError

    def set_voltage(self, voltage: float) -> None:
        raise NotImplementedError

    def status(self) -> Dict[str, Any]:
        return {
            'resource': self.resource_name,
            'connected': self.connected,
        }

    def execute(self, action: str, args: List[str]) -> Any:
        if action == 'on':
            return self.on(args[0].lower() == 'true')
        elif action in {'setVoltage', 'set_voltage'}:
            return self.set_voltage(float(args[0]))
        else:
            raise ValueError(f"Unknown action: {action}")


class PowerSupplyFactory:
    _registry: Dict[str, Type[PowerSupplyBase]] = {}

    @classmethod
    def register(cls, name: str, ps_cls: Type[PowerSupplyBase]):
        cls._registry[name] = ps_cls

    @classmethod
    def create(cls, name: str, *args, **kwargs) -> PowerSupplyBase:
        if name not in cls._registry:
            raise ValueError(f"Unknown power supply: {name}")
        return cls._registry[name](*args, **kwargs)


class DummyPS(PowerSupplyBase):
    def connect(self, address: Optional[str] = None) -> None:
        self.connected = True
        self.resource_name = address or 'dummy'
        print(f"DummyPS connected to {self.resource_name}")

    def disconnect(self) -> None:
        self.connected = False
        print("DummyPS disconnected")

    def reset(self) -> None:
        print("DummyPS reset")

    def identify(self) -> str:
        return "DummyPS v1.0"

    def on(self, state: bool) -> None:
        print(f"DummyPS Power {'ON' if state else 'OFF'}")

    def set_voltage(self, voltage: float) -> None:
        print(f"DummyPS Voltage set to {voltage}V")


PowerSupplyFactory.register('dummy', DummyPS)


if __name__ == "__main__":
    ps = PowerSupplyFactory.create('dummy')
    ps.connect('USB::DUMMY::1')
    print(ps.identify())
    ps.execute('on', ['True'])
    ps.execute('setVoltage', ['12'])
    ps.disconnect()
