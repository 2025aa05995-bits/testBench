from typing import Any, Dict, List, Optional


class InstrumentBase:
    """Common base class for all lab instruments."""

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
