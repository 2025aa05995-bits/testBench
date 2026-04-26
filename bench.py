from typing import Dict, Type


class InstrumentBase:
    def execute(self, action: str, args: list):
        raise NotImplementedError


class PowerSupplyBase(InstrumentBase):
    def on(self, state: bool):
        raise NotImplementedError

    def setVoltage(self, voltage: float):
        raise NotImplementedError

    def execute(self, action: str, args: list):
        if action == 'on':
            return self.on(args[0].lower() == 'true')
        elif action == 'setVoltage':
            return self.setVoltage(float(args[0]))
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

# Example instrument implementation


class DummyPS(PowerSupplyBase):
    def on(self, state: bool):
        print(f"DummyPS Power {'ON' if state else 'OFF'}")

    def setVoltage(self, voltage: float):
        print(f"DummyPS Voltage set to {voltage}V")


PowerSupplyFactory.register('dummy', DummyPS)

# Example usage
if __name__ == "__main__":
    ps = PowerSupplyFactory.create('dummy')
    ps.execute('on', ['True'])
    ps.execute('setVoltage', ['12'])
