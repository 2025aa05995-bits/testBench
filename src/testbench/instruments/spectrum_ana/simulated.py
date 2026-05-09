import math
import random
from typing import Dict, Any, List, Optional
from .base import SpectrumAnalyzerBase


class SimulatedSpectrumAnalyzer(SpectrumAnalyzerBase):
    """Simulated spectrum analyzer for testing without real hardware."""

    ACTIONS = {
        'start_sweep': 'Start frequency sweep',
        'stop_sweep': 'Stop frequency sweep',
        'get_trace': 'Return frequencies (Hz) and data (dBm) for the current sweep',
        'measure_peak': 'Return the peak frequency (Hz) and power (dBm)',
    }

    def __init__(self, resource_name: Optional[str] = None):
        super().__init__(resource_name or "SIM_SA_01")
        self._sweeping = False
        self._center_freq = 1e9  # 1GHz
        self._span = 1e9
        self._rbw = 1e6  # 1MHz

    def connect(self, address: Optional[str] = None) -> None:
        self.connected = True
        if address:
            self.resource_name = address
        print(
            f"[SIMULATED] SpectrumAnalyzer connected to {self.resource_name}")

    def disconnect(self) -> None:
        self.connected = False
        self._sweeping = False
        print(f"[SIMULATED] SpectrumAnalyzer disconnected")

    def reset(self) -> None:
        self._sweeping = False
        self._center_freq = 1e9
        self._span = 1e9
        self._rbw = 1e6
        print(f"[SIMULATED] SpectrumAnalyzer reset")

    def identify(self) -> str:
        return f"SimulatedSpectrumAnalyzer (resource: {self.resource_name})"

    def start_sweep(self) -> None:
        if not self.connected:
            raise RuntimeError("Not connected")
        self._sweeping = True
        print(f"[SIMULATED] Spectrum sweep started")

    def stop_sweep(self) -> None:
        self._sweeping = False
        print(f"[SIMULATED] Spectrum sweep stopped")

    def set_center_frequency(self, frequency_hz: float) -> None:
        if not self.connected:
            raise RuntimeError("Not connected")
        self._center_freq = frequency_hz
        print(f"[SIMULATED] Center frequency set to {frequency_hz}Hz")

    def set_span(self, span_hz: float) -> None:
        if not self.connected:
            raise RuntimeError("Not connected")
        self._span = span_hz
        print(f"[SIMULATED] Span set to {span_hz}Hz")

    def set_resolution_bandwidth(self, rbw_hz: float) -> None:
        if not self.connected:
            raise RuntimeError("Not connected")
        self._rbw = rbw_hz
        print(f"[SIMULATED] Resolution bandwidth set to {rbw_hz}Hz")

    def measure_peak(self) -> Dict[str, Any]:
        if not self.connected:
            raise RuntimeError("Not connected")
        # Small jitter around the configured center frequency / nominal peak power.
        freq_jitter = self._span * 0.001 * random.gauss(0.0, 1.0)
        return {
            'frequency': self._center_freq + freq_jitter,
            'power_dbm': -30.0 + random.gauss(0.0, 0.5),
        }

    def get_trace(self, num_points: int = 256) -> Dict[str, Any]:
        """Simulated spectrum sweep: frequency (Hz) vs power (dBm).

        Builds a noise floor (~-90 dBm with ±2 dBm Gaussian fluctuation) plus a
        Gaussian peak near the configured center frequency. Each call jitters
        the peak frequency, peak height, and per-bin noise so consecutive
        sweeps look like real instrument data.
        """
        if not self.connected:
            raise RuntimeError("Not connected")
        n = max(16, min(int(num_points), 8192))
        f0 = float(self._center_freq)
        span = max(float(self._span), 1.0)
        rbw = max(float(self._rbw), 1.0)
        f_lo = f0 - span / 2.0
        df = span / (n - 1)
        # Per-sweep peak parameters
        peak_freq = f0 + span * 0.001 * random.gauss(0.0, 1.0)
        peak_dbm = -30.0 + random.gauss(0.0, 0.8)
        noise_floor_dbm = -90.0
        # FWHM ≈ 5×RBW (clamped to a reasonable fraction of the span)
        fwhm = max(min(5.0 * rbw, span * 0.2), span * 0.005)
        sigma_f = fwhm / (2.0 * math.sqrt(2.0 * math.log(2.0)))
        amp_db = peak_dbm - noise_floor_dbm
        frequencies: List[float] = []
        data: List[float] = []
        for i in range(n):
            f = f_lo + i * df
            peak_db = amp_db * math.exp(-((f - peak_freq) ** 2) / (2.0 * sigma_f ** 2))
            value = noise_floor_dbm + peak_db + random.gauss(0.0, 2.0)
            frequencies.append(f)
            data.append(value)
        return {
            'center_freq': f0,
            'span': span,
            'rbw': rbw,
            'frequencies': frequencies,
            'data': data,
        }

    def status(self) -> Dict[str, Any]:
        return {
            'resource': self.resource_name,
            'connected': self.connected,
            'sweeping': self._sweeping,
            'center_freq': self._center_freq,
            'span': self._span,
            'rbw': self._rbw,
        }

    def configure(self, **settings: Any) -> None:
        if 'center_freq' in settings:
            self.set_center_frequency(settings['center_freq'])
        if 'span' in settings:
            self.set_span(settings['span'])
        if 'rbw' in settings:
            self.set_resolution_bandwidth(settings['rbw'])

    def measure(self, parameter: str) -> Any:
        if parameter == 'peak':
            return self.measure_peak()
        else:
            raise ValueError(f"Unknown parameter: {parameter}")

    def execute(self, action: str, args: list) -> Any:
        if action == 'start_sweep':
            return self.start_sweep()
        elif action == 'stop_sweep':
            return self.stop_sweep()
        elif action == 'get_trace':
            n = int(args[0]) if args else 256
            return self.get_trace(n)
        elif action == 'measure_peak':
            return self.measure_peak()
        else:
            raise ValueError(f"Unknown action: {action}")
