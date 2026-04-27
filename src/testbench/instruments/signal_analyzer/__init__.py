"""Signal analyzer instrument category."""

from .base import SignalAnalyzerBase
from .simulated import SimulatedSignalAnalyzer

__all__ = ['SignalAnalyzerBase', 'SimulatedSignalAnalyzer']
