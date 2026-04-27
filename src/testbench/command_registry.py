"""Central registry for all available instrument commands."""

from typing import Dict, List, Optional, Any
from .instruments import (
    SimulatedPowerSupply,
    SimulatedOscilloscope,
    SimulatedSignalGenerator,
    SimulatedSpectrumAnalyzer,
    SimulatedMultimeter,
    SimulatedFunctionGenerator,
    SimulatedNetworkAnalyzer,
    SimulatedFrequencyCounter,
    SimulatedElectronicLoad,
    SimulatedSourceMeasureUnit,
    SimulatedTemperatureChamber,
)


class CommandRegistry:
    """Registry of all available instrument commands."""

    def __init__(self):
        """Initialize the registry with all available instruments."""
        self.instruments = {
            'ps': SimulatedPowerSupply(),
            'osc': SimulatedOscilloscope(),
            'sg': SimulatedSignalGenerator(),
            'sa': SimulatedSpectrumAnalyzer(),
            'mm': SimulatedMultimeter(),
            'fg': SimulatedFunctionGenerator(),
            'na': SimulatedNetworkAnalyzer(),
            'fc': SimulatedFrequencyCounter(),
            'el': SimulatedElectronicLoad(),
            'smu': SimulatedSourceMeasureUnit(),
            'tc': SimulatedTemperatureChamber(),
        }
        # Connect all instruments
        for instrument in self.instruments.values():
            if not instrument.connected:
                try:
                    instrument.connect()
                except Exception:
                    pass

    def get_all_commands(self) -> Dict[str, Dict[str, str]]:
        """Get all available commands grouped by instrument.

        Returns:
            Dict mapping instrument category to its available actions and descriptions.
            Format: {
                'ps': {'on': 'Enable power supply', 'off': 'Disable power supply', ...},
                'mm': {'measure_voltage': 'Measure DC voltage', ...},
                ...
            }
        """
        result = {}
        for category, instrument in self.instruments.items():
            if hasattr(instrument, 'ACTIONS'):
                result[category] = instrument.ACTIONS
        return result

    def get_instrument_commands(self, category: str) -> Optional[Dict[str, str]]:
        """Get commands for a specific instrument.

        Args:
            category: Instrument category (e.g., 'ps', 'mm')

        Returns:
            Dict mapping action names to descriptions, or None if category not found.
        """
        if category not in self.instruments:
            return None
        instrument = self.instruments[category]
        if hasattr(instrument, 'ACTIONS'):
            return instrument.ACTIONS
        return None

    def execute(self, category: str, action: str, args: List[str]) -> Any:
        """Execute a command on a specific instrument.

        Args:
            category: Instrument category (e.g., 'ps', 'mm')
            action: Action name (e.g., 'on', 'measure_voltage')
            args: List of arguments for the action

        Returns:
            The result of the action execution

        Raises:
            ValueError: If category or action is not found
        """
        if category not in self.instruments:
            raise ValueError(f"Unknown instrument category: {category}")

        instrument = self.instruments[category]
        try:
            result = instrument.execute(action, args)
            return result
        except Exception as e:
            raise ValueError(f"Error executing {category}.{action}: {str(e)}")

    def get_instrument_name(self, category: str) -> Optional[str]:
        """Get the full name of an instrument by category.

        Args:
            category: Instrument category (e.g., 'ps')

        Returns:
            The full instrument name (e.g., 'Power Supply') or None if not found.
        """
        names = {
            'ps': 'Power Supply',
            'osc': 'Oscilloscope',
            'sg': 'Signal Generator',
            'sa': 'Spectrum Analyzer',
            'mm': 'Multimeter',
            'fg': 'Function Generator',
            'na': 'Network Analyzer',
            'fc': 'Frequency Counter',
            'el': 'Electronic Load',
            'smu': 'Source Measure Unit',
            'tc': 'Temperature Chamber',
        }
        return names.get(category)
