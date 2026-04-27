"""Spectrum analyzer instrument category."""

from .base import SpectrumAnalyzerBase
from .simulated import SimulatedSpectrumAnalyzer

__all__ = ['SpectrumAnalyzerBase', 'SimulatedSpectrumAnalyzer']
