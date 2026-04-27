"""Electronic load instrument category."""

from .base import ElectronicLoadBase
from .simulated import SimulatedElectronicLoad

__all__ = ['ElectronicLoadBase', 'SimulatedElectronicLoad']
