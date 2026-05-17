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

### SimulatedFunctionGenerator (ARB waveforms)
Located in: `src/testbench/instruments/function_generator/simulated.py`

Load arbitrary waveforms from CSV and play as `arb` waveform:

```text
bc.fg.load_arb_csv scripts/examples/arb_sine.csv
bc.fg.set_waveform arb
bc.fg.output_on
bc.fg.get_arb
```

CSV: one voltage column, or `time_s,voltage_v` columns. See `scripts/examples/arb_sine.csv`.

### Spectrum analyzer (`sa`) vs signal analyzer (`san`)

| Key | Device | Typical use |
|-----|--------|-------------|
| `sa` | Spectrum analyzer | Sweeps, `get_trace`, `measure_peak` |
| `san` | Signal analyzer | Capture, `get_spectrum`, `measure_power` |

## Shared simulated commands

Every simulated driver includes these **bench actions** (via `SimulatedInstrumentMixin`):

| Action | Description |
|--------|-------------|
| `reset` | Reset to defaults |
| `status` | Status dict (+ sim fault/noise fields) |
| `identify` | Simulated ID string |
| `fault_inject` | `disconnect`, `overload`, or `read_error` |
| `fault_clear` | Clear fault |
| `sim_noise_on` / `sim_noise_off` | Toggle Gaussian noise on numeric reads |
| `sim_settling` | Set delay (ms) before next measurement |

**Examples:**
```text
bc.mm.fault_inject disconnect
bc.mm.fault_clear
bc.ps.sim_settling 100
bc.mm.sim_noise_off
bc.mm.measure_voltage
```

## Bind discovered hardware (real mode)

**CLI:**
```text
bc.config.discover
bc.config.bind ps visa GPIB0::1::INSTR
bc.config.bind mm serial COM7
bc.config.bind ps tcp 192.168.1.10:5025
```

**GUI (PyQt):** **Bench → Bind instrument…** — discover, pick address, save to `testbenchconfig.json`.

## Running Tests

```powershell
$env:PYTHONPATH = "src"
pytest tests/test_simulated_instruments.py tests/test_simulated_mixin.py -q
```

## Base Class Implementation

All simulated instruments implement their respective base class methods:
- `connect()` / `disconnect()` - Connection management
- `reset()` - Reset to default state (also exposed as `bc.<cat>.reset`)
- `identify()` - Query instrument info (`bc.<cat>.identify`)
- `status()` - Get current configuration as dict (`bc.<cat>.status`)
- `configure(**settings)` - Bulk configuration
- `measure(parameter)` - Single measurement (where applicable)
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
