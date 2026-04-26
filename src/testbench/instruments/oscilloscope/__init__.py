"""Oscilloscope instrument category."""

from .base import OscilloscopeBase
from .simulated import SimulatedOscilloscope

__all__ = ['OscilloscopeBase', 'SimulatedOscilloscope']
