"""Frequency counter instrument category."""

from .base import FrequencyCounterBase
from .simulated import SimulatedFrequencyCounter

__all__ = ['FrequencyCounterBase', 'SimulatedFrequencyCounter']
