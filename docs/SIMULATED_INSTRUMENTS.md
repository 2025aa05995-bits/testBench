# Simulated Instruments

The testBench framework includes simulated (virtual) instrument implementations for testing and development without connecting to actual hardware.

## Available Simulated Instruments

### SimulatedPowerSupply
Located in: `src/testbench/instruments/power_supply/simulated.py`

Simulates a programmable power supply with:
- Voltage and current control (0-30V, 0-10A range)
- Overcurrent protection (OCP) enable/disable
- Power measurement
- Connection/disconnection management

**Example:**
```python
from testbench.instruments.power_supply import SimulatedPowerSupply

ps = SimulatedPowerSupply()
ps.connect('GPIB0::1::INSTR')
ps.set_voltage(12.0)
ps.set_current(2.5)
ps.on()
print(ps.status())  # View current settings
ps.off()
ps.disconnect()
```

### SimulatedOscilloscope
Located in: `src/testbench/instruments/oscilloscope/simulated.py`

Simulates a multi-channel oscilloscope with:
- Configurable number of channels (default 4)
- Timebase and voltage scale settings
- Waveform capture simulation
- Run/stop control

**Example:**
```python
from testbench.instruments.oscilloscope import SimulatedOscilloscope

osc = SimulatedOscilloscope(num_channels=4)
osc.connect('USB::0::0::INSTR')
osc.set_timebase(0.001)  # 1ms/div
osc.set_voltage_scale(1, 2.0)  # CH1: 2V/div
osc.run()
waveform = osc.capture_waveform(1)
osc.stop()
osc.disconnect()
```

### SimulatedSignalGenerator
Located in: `src/testbench/instruments/signal_generator/simulated.py`

Simulates a signal generator with:
- Frequency control (1Hz to 10MHz)
- Amplitude control (0-10V)
- Waveform selection (sine, square, triangle, ramp, pulse)
- Modulation support
- Output on/off control

**Example:**
```python
from testbench.instruments.signal_generator import SimulatedSignalGenerator

sg = SimulatedSignalGenerator()
sg.connect('COM3')
sg.set_frequency(5000.0)  # 5kHz
sg.set_amplitude(2.5)  # 2.5V
sg.set_waveform('square')
sg.output_on()
print(sg.status())
sg.output_off()
sg.disconnect()
```

## Running Tests

Execute the test suite:
```bash
python test_simulated_instruments.py
```

This runs comprehensive tests for all three simulated instruments and displays their status and measurements.

## Base Class Implementation

All simulated instruments implement their respective base class methods:
- `connect()` / `disconnect()` - Connection management
- `reset()` - Reset to default state
- `identify()` - Query instrument info
- `status()` - Get current configuration as dict
- `configure(**settings)` - Bulk configuration
- `measure(parameter)` - Single measurement
- `execute(action, args)` - Command execution

## Extending with Real Instruments

To replace a simulated instrument with a real one:

1. Create a new class inheriting from the base class (e.g., `PowerSupplyBase`)
2. Implement all abstract methods
3. Handle actual communication (GPIB, USB, serial, etc.)
4. Export from the category `__init__.py`

Example structure:
```python
from .base import PowerSupplyBase

class RealPowerSupply(PowerSupplyBase):
    def connect(self, address):
        # Real GPIB/USB connection code
        pass
    # ... implement all other methods
```
