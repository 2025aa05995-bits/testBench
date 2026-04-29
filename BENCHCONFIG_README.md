# Bench Configuration Guide

## Overview

The `testbenchconfig.json` file allows you to configure all instruments in the test bench with the following properties:

- **simulate**: Boolean flag to enable/disable simulation mode
- **protocol**: Transport protocol for real instruments (e.g. `VISA`, `TCP/IP`, `Serial`)
- **visa_resource**: VISA resource name (e.g., "GPIB0::1::INSTR")
- **ip_address**: Network IP address for TCP/IP connections
- **port**: Network port (default: 5025)
- **serial_port**: Serial port device path for serial instruments
- **baudrate**: Serial baud rate (default: 9600)
- **type**: Instrument type
- **timeout_ms**: Connection timeout in milliseconds

## Configuration Structure

```json
{
  "instruments": {
    "ps": {
      "name": "Power Supply",
      "simulate": true,
      "type": "PowerSupply",
      "visa_resource": "GPIB0::1::INSTR",
      "ip_address": "192.168.1.10",
      "port": 5025,
      "timeout_ms": 5000,
      "description": "Programmable DC power supply"
    },
    ...
  },
  "global_settings": {
    "simulate_all": false,
    "connection_timeout_ms": 5000,
    "auto_connect": true,
    "log_level": "INFO",
    "enable_cache": true
  }
}
```

## Using ConfigManager in Code

### Basic Usage

```python
from testbench.config_manager import ConfigManager

# Load configuration
config = ConfigManager('testbenchconfig.json')

# Check if an instrument should be simulated
if config.should_simulate('ps'):
    print("Using simulated power supply")
else:
    print("Using real power supply")

# Get VISA resource for an instrument
visa_resource = config.get_visa_resource('ps')
print(f"VISA Resource: {visa_resource}")

# Get IP address
ip = config.get_ip_address('ps')
print(f"IP Address: {ip}")

# Print all configuration
config.print_config()
```

### Querying Configuration

```python
config = ConfigManager()

# Get instrument configuration
ps_config = config.get_instrument_config('ps')

# Get all instruments
all_instruments = config.get_all_instruments()

# Get specific properties
```

## Runtime instrument mode and discovery

The registry also supports runtime mode switching and device discovery via the `config` command category:

- `bench.config.show` — display loaded instrument configuration
- `bench.config.discover` — discover available VISA, serial, and TCP/IP devices
- `bench.config.set_simulation ps false` — switch the `ps` instrument to real mode
- `bench.config.set_simulation ps true` — switch the `ps` instrument back to simulation
- `bench.config.status ps` — show the current connection status of the `ps` instrument

```python
config = ConfigManager()
print(config.discover_available_devices())
```

### Get specific properties
name = config.get_instrument_name('ps')
type_name = config.get_instrument_type('ps')
timeout = config.get_timeout('ps')

# Get global settings
log_level = config.get_global_setting('log_level', 'INFO')
auto_connect = config.get_global_setting('auto_connect', True)
```

## Configuration Examples

### All Instruments Simulated (Default)

```json
{
  "instruments": {
    "ps": {
      "name": "Power Supply",
      "simulate": true,
      ...
    },
    "osc": {
      "name": "Oscilloscope",
      "simulate": true,
      ...
    }
  },
  "global_settings": {
    "simulate_all": false
  }
}
```

### Mix of Real and Simulated Instruments

```json
{
  "instruments": {
    "ps": {
      "name": "Power Supply",
      "simulate": false,
      "visa_resource": "GPIB0::1::INSTR"
    },
    "osc": {
      "name": "Oscilloscope",
      "simulate": true
    }
  }
}
```

### All Instruments Real (Global Setting)

```json
{
  "global_settings": {
    "simulate_all": false
  },
  "instruments": {
    "ps": {
      "name": "Power Supply",
      "visa_resource": "GPIB0::1::INSTR",
      "ip_address": "192.168.1.10"
    }
  }
}
```

## Instrument Categories and Types

| Category | Instrument Type | VISA Default |
|----------|-----------------|--------------|
| ps | PowerSupply | GPIB0::1::INSTR |
| osc | Oscilloscope | GPIB0::2::INSTR |
| sg | SignalGenerator | GPIB0::3::INSTR |
| sa | SpectrumAnalyzer | GPIB0::4::INSTR |
| mm | Multimeter | GPIB0::5::INSTR |
| fg | FunctionGenerator | GPIB0::6::INSTR |
| na | NetworkAnalyzer | GPIB0::7::INSTR |
| fc | FrequencyCounter | GPIB0::8::INSTR |
| el | ElectronicLoad | GPIB0::9::INSTR |
| smu | SourceMeasureUnit | GPIB0::10::INSTR |
| tc | TemperatureChamber | GPIB0::11::INSTR |
| pm | PowerMeter | GPIB0::12::INSTR |

## Global Settings

| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| simulate_all | bool | false | Force all instruments to use simulation |
| connection_timeout_ms | int | 5000 | Default timeout for all instruments |
| auto_connect | bool | true | Automatically connect on startup |
| log_level | string | INFO | Logging level (DEBUG, INFO, WARNING, ERROR) |
| enable_cache | bool | true | Cache instrument responses |

## Integration with Command Registry

The `CommandRegistry` can be updated to use `ConfigManager` to dynamically choose between simulated and real instruments:

```python
from testbench.config_manager import ConfigManager
from testbench.command_registry import CommandRegistry

config = ConfigManager()
registry = CommandRegistry(config)

# Instruments will be created based on simulate flag
if registry.should_simulate('ps'):
    ps = SimulatedPowerSupply()
else:
    ps = RealPowerSupply(visa_resource=config.get_visa_resource('ps'))
```

## Tips and Best Practices

1. **Start with Simulation**: Begin development with `simulate: true` to test without hardware
2. **Use IP for Network Instruments**: For instruments with Ethernet, specify `ip_address` and `port`
3. **Keep Defaults**: Leave `timeout_ms` at 5000 unless you have specific needs
4. **Document Changes**: Keep comments in JSON explaining custom configurations
5. **Version Control**: Track `testbenchconfig.json` in git for reproducible tests
6. **Environment Specific**: Create different config files for different test environments:
   - `testbenchconfig.dev.json` - Development (simulated)
   - `testbenchconfig.test.json` - Test lab (real instruments)
   - `testbenchconfig.prod.json` - Production (real instruments)

## Troubleshooting

### ModuleNotFoundError when importing ConfigManager
Add src to Python path:
```python
import sys
sys.path.insert(0, 'src')
from testbench.config_manager import ConfigManager
```

### Configuration file not found
Ensure `testbenchconfig.json` is in the current working directory or provide the full path:
```python
config = ConfigManager('testbenchconfig.json')
```

### Invalid JSON
Validate your JSON using:
- Online JSON validator: https://jsonlint.com/
- Python: `python -m json.tool testbenchconfig.json`

### Connection timeouts
Increase `timeout_ms` in the configuration for slow instruments:
```json
"ps": {
  "timeout_ms": 10000
}
```
