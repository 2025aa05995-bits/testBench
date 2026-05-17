"""Central registry for all available instrument commands."""

from typing import Any, Dict, List, Optional

from ._paths import default_config_file
from .config_manager import ConfigManager
from .instruments import (
    RealInstrumentAdapter,
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
    SimulatedPowerMeter,
    SimulatedSignalAnalyzer,
)


class ConfigInterface:
    """Configuration command helper for runtime toggles and discovery."""

    ACTIONS = {
        'reload': 'Reload configuration from config file',
        'show': 'Show the current configuration and instrument modes',
        'discover': 'Discover available VISA, serial, and TCP/IP devices',
        'set_simulation': 'Toggle simulation/real mode for an instrument',
        'status': 'Show connection status for a specific instrument',
    }

    def __init__(self, config_manager: ConfigManager, registry: 'CommandRegistry'):
        self.config_manager = config_manager
        self.registry = registry

    def execute(self, action: str, args: List[str]) -> Any:
        if action == 'reload':
            self.config_manager.load_config()
            self.registry.reload_instruments()
            return 'Configuration reloaded.'

        if action == 'show':
            return self._format_config()

        if action == 'discover':
            devices = self.config_manager.discover_available_devices()
            return self._format_discovery(devices)

        if action == 'set_simulation':
            if len(args) < 2:
                raise ValueError('Usage: bench.config.set_simulation <category> <true|false>')
            category = args[0]
            simulate = args[1].lower() not in {'false', '0', 'no', 'off', 'real'}
            self.config_manager.set_simulation(category, simulate)
            self.registry.reload_instruments()
            mode = 'SIMULATED' if simulate else 'REAL'
            return f'{category} set to {mode} mode.'

        if action == 'status':
            if len(args) == 0:
                return self.registry.get_status_summary()
            category = args[0]
            if category not in self.registry.instruments:
                raise ValueError(f'Unknown category: {category}')
            instrument = self.registry.instruments[category]
            if hasattr(instrument, 'status'):
                return instrument.status()
            return {'connected': getattr(instrument, 'connected', False)}

        raise ValueError(f'Unknown config action: {action}')

    def _format_config(self) -> str:
        lines = ['Configuration:']
        for category, cfg in self.config_manager.get_all_instruments().items():
            mode = 'SIMULATED' if self.config_manager.should_simulate(category) else 'REAL'
            lines.append(f"{category}: {cfg.get('name')} ({mode}) protocol={self.config_manager.get_protocol(category)}")
        return '\n'.join(lines)

    def _format_discovery(self, devices: Dict[str, Any]) -> str:
        lines = ['Device discovery results:']
        for section, entries in devices.items():
            lines.append(f"{section}:")
            if not entries:
                lines.append('  none found')
                continue
            for entry in entries:
                lines.append(f'  {entry}')
        return '\n'.join(lines)


class CommandRegistry:
    """Registry of all available instrument commands."""

    INSTRUMENT_FACTORIES = {
        'ps': SimulatedPowerSupply,
        'osc': SimulatedOscilloscope,
        'sg': SimulatedSignalGenerator,
        'sa': SimulatedSpectrumAnalyzer,
        'mm': SimulatedMultimeter,
        'fg': SimulatedFunctionGenerator,
        'na': SimulatedNetworkAnalyzer,
        'fc': SimulatedFrequencyCounter,
        'el': SimulatedElectronicLoad,
        'smu': SimulatedSourceMeasureUnit,
        'tc': SimulatedTemperatureChamber,
        'pm': SimulatedPowerMeter,
        'san': SimulatedSignalAnalyzer,
    }

    def __init__(self, config_file: Optional[str] = None):
        """Initialize the registry with all available instruments."""
        path = str(default_config_file()) if config_file is None else config_file
        self.config_manager = ConfigManager(path)
        self.instruments = self._build_instruments()
        self.instruments['config'] = ConfigInterface(self.config_manager, self)
        self._auto_connect_instruments()

    def _build_instruments(self) -> Dict[str, Any]:
        instruments: Dict[str, Any] = {}
        for category, factory in self.INSTRUMENT_FACTORIES.items():
            if not self.config_manager.should_simulate(category):
                instruments[category] = RealInstrumentAdapter(category, self.config_manager)
            else:
                resource_name = self.config_manager.get_visa_resource(category) or self.config_manager.get_ip_address(category)
                instruments[category] = factory(resource_name)
        return instruments

    def _auto_connect_instruments(self) -> None:
        if not self.config_manager.get_global_setting('auto_connect', True):
            return
        for instrument in self.instruments.values():
            if hasattr(instrument, 'connected') and not instrument.connected:
                try:
                    instrument.connect()
                except Exception:
                    pass

    def reload_instruments(self) -> None:
        self.instruments = self._build_instruments()
        self.instruments['config'] = ConfigInterface(self.config_manager, self)
        self._auto_connect_instruments()

    def get_all_commands(self) -> Dict[str, Dict[str, str]]:
        """Get all available commands grouped by instrument."""
        result = {}
        for category, instrument in self.instruments.items():
            if hasattr(instrument, 'ACTIONS'):
                result[category] = instrument.ACTIONS
        return result

    def get_instrument_commands(self, category: str) -> Optional[Dict[str, str]]:
        """Get commands for a specific instrument."""
        if category not in self.instruments:
            return None
        instrument = self.instruments[category]
        if hasattr(instrument, 'ACTIONS'):
            return instrument.ACTIONS
        return None

    def execute(self, category: str, action: str, args: List[str]) -> Any:
        """Execute a command on a specific instrument."""
        if category not in self.instruments:
            raise ValueError(f"Unknown instrument category: {category}")

        instrument = self.instruments[category]
        try:
            return instrument.execute(action, args)
        except Exception as e:
            raise ValueError(f"Error executing {category}.{action}: {str(e)}")

    def get_instrument_name(self, category: str) -> Optional[str]:
        """Get the full name of an instrument by category."""
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
            'pm': 'Power Meter',
            'san': 'Signal Analyzer',
            'config': 'Configuration Controls',
        }
        return names.get(category)

    def get_status_summary(self) -> Dict[str, Any]:
        status = {}
        for category, instrument in self.instruments.items():
            if category == 'config':
                continue
            status[category] = instrument.status() if hasattr(instrument, 'status') else {'connected': getattr(instrument, 'connected', False)}
        return status
