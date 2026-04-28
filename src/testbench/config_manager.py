"""Configuration manager for bench instruments."""

import json
import os
from typing import Dict, Any, Optional


class ConfigManager:
    """Manages instrument configuration from testbenchconfig.json."""

    def __init__(self, config_file: str = "testbenchconfig.json"):
        """Initialize the config manager.

        Args:
            config_file: Path to the configuration JSON file
        """
        self.config_file = config_file
        self.config: Dict[str, Any] = {}
        self.load_config()

    def load_config(self) -> None:
        """Load configuration from JSON file."""
        if not os.path.exists(self.config_file):
            raise FileNotFoundError(f"Configuration file not found: {self.config_file}")

        try:
            with open(self.config_file, 'r') as f:
                self.config = json.load(f)
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON in configuration file: {e}")

    def get_instrument_config(self, category: str) -> Optional[Dict[str, Any]]:
        """Get configuration for a specific instrument.

        Args:
            category: Instrument category (e.g., 'ps', 'osc', 'sg')

        Returns:
            Instrument configuration dictionary or None if not found
        """
        instruments = self.config.get('instruments', {})
        return instruments.get(category)

    def get_all_instruments(self) -> Dict[str, Dict[str, Any]]:
        """Get configuration for all instruments.

        Returns:
            Dictionary of all instrument configurations
        """
        return self.config.get('instruments', {})

    def should_simulate(self, category: str) -> bool:
        """Check if an instrument should be simulated.

        Args:
            category: Instrument category

        Returns:
            True if instrument should be simulated, False otherwise
        """
        # Check global setting first
        global_simulate = self.config.get('global_settings', {}).get('simulate_all', False)
        if global_simulate:
            return True

        # Check instrument-specific setting
        instrument = self.get_instrument_config(category)
        if instrument:
            return instrument.get('simulate', True)

        return True  # Default to simulation

    def get_visa_resource(self, category: str) -> Optional[str]:
        """Get VISA resource name for an instrument.

        Args:
            category: Instrument category

        Returns:
            VISA resource string or None
        """
        instrument = self.get_instrument_config(category)
        if instrument:
            return instrument.get('visa_resource')
        return None

    def get_ip_address(self, category: str) -> Optional[str]:
        """Get IP address for an instrument.

        Args:
            category: Instrument category

        Returns:
            IP address string or None
        """
        instrument = self.get_instrument_config(category)
        if instrument:
            return instrument.get('ip_address')
        return None

    def get_instrument_type(self, category: str) -> Optional[str]:
        """Get instrument type.

        Args:
            category: Instrument category

        Returns:
            Instrument type or None
        """
        instrument = self.get_instrument_config(category)
        if instrument:
            return instrument.get('type')
        return None

    def get_instrument_name(self, category: str) -> Optional[str]:
        """Get human-readable instrument name.

        Args:
            category: Instrument category

        Returns:
            Instrument name or None
        """
        instrument = self.get_instrument_config(category)
        if instrument:
            return instrument.get('name')
        return None

    def get_timeout(self, category: str) -> int:
        """Get connection timeout for an instrument.

        Args:
            category: Instrument category

        Returns:
            Timeout in milliseconds
        """
        instrument = self.get_instrument_config(category)
        if instrument:
            return instrument.get('timeout_ms', 5000)
        return self.config.get('global_settings', {}).get('connection_timeout_ms', 5000)

    def get_global_setting(self, key: str, default: Any = None) -> Any:
        """Get a global setting.

        Args:
            key: Setting key
            default: Default value if key not found

        Returns:
            Setting value or default
        """
        global_settings = self.config.get('global_settings', {})
        return global_settings.get(key, default)

    def print_config(self) -> None:
        """Print the loaded configuration to console (for debugging)."""
        print("=" * 60)
        print("Bench Configuration")
        print("=" * 60)
        print("\nGlobal Settings:")
        for key, value in self.config.get('global_settings', {}).items():
            print(f"  {key}: {value}")

        print("\nInstruments:")
        for category, config in self.config.get('instruments', {}).items():
            simulate_str = "SIM" if config.get('simulate', True) else "REAL"
            print(f"  [{category}] {config.get('name')} ({simulate_str})")
            print(f"      Type: {config.get('type')}")
            print(f"      VISA: {config.get('visa_resource')}")
            print(f"      IP: {config.get('ip_address')}:{config.get('port', 5025)}")

    def save_config(self, output_file: Optional[str] = None) -> None:
        """Save configuration to a JSON file.

        Args:
            output_file: Output file path (defaults to config_file)
        """
        target_file = output_file or self.config_file
        with open(target_file, 'w') as f:
            json.dump(self.config, f, indent=2)
        print(f"Configuration saved to {target_file}")


# Example usage
if __name__ == "__main__":
    config = ConfigManager()
    config.print_config()

    # Example: Check if power supply should be simulated
    print("\n" + "=" * 60)
    print("Example queries:")
    print(f"Power Supply simulated: {config.should_simulate('ps')}")
    print(f"Power Supply VISA resource: {config.get_visa_resource('ps')}")
    print(f"Power Supply IP: {config.get_ip_address('ps')}")
    print(f"Power Supply name: {config.get_instrument_name('ps')}")
