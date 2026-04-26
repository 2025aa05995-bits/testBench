"""Test script for simulated instruments."""

from testbench.instruments.signal_generator.simulated import SimulatedSignalGenerator
from testbench.instruments.oscilloscope.simulated import SimulatedOscilloscope
from testbench.instruments.power_supply.simulated import SimulatedPowerSupply
import sys
sys.path.insert(0, 'src')


def test_power_supply():
    print("\n=== Testing Simulated Power Supply ===")
    ps = SimulatedPowerSupply()
    ps.connect('GPIB0::1::INSTR')
    print(f"Identify: {ps.identify()}")

    ps.set_voltage(12.0)
    ps.set_current(2.5)
    ps.enable_overcurrent_protection(True)
    ps.on()

    print(f"Voltage: {ps.measure_voltage()}V")
    print(f"Current: {ps.measure_current()}A")
    print(f"Power: {ps.measure_power()}W")
    print(f"Status: {ps.status()}")

    ps.off()
    ps.disconnect()


def test_oscilloscope():
    print("\n=== Testing Simulated Oscilloscope ===")
    osc = SimulatedOscilloscope(num_channels=4)
    osc.connect('USB::0::0::INSTR')
    print(f"Identify: {osc.identify()}")

    osc.set_timebase(0.001)
    osc.set_voltage_scale(1, 2.0)
    osc.set_voltage_scale(2, 5.0)
    osc.set_channel_enabled(3, False)

    osc.run()
    waveform = osc.capture_waveform(1)
    print(f"Waveform captured: {waveform}")
    print(f"Frequency measurement: {osc.measure('frequency')}Hz")
    print(f"Status: {osc.status()}")

    osc.stop()
    osc.disconnect()


def test_signal_generator():
    print("\n=== Testing Simulated Signal Generator ===")
    sg = SimulatedSignalGenerator()
    sg.connect('COM3')
    print(f"Identify: {sg.identify()}")

    sg.set_frequency(5000.0)
    sg.set_amplitude(2.5)
    sg.set_waveform('square')
    sg.output_on()

    print(f"Frequency: {sg.measure('frequency')}Hz")
    print(f"Amplitude: {sg.measure('amplitude')}V")
    print(f"Status: {sg.status()}")

    sg.output_off()
    sg.disconnect()


if __name__ == '__main__':
    try:
        test_power_supply()
        test_oscilloscope()
        test_signal_generator()
        print("\n✓ All simulated instrument tests passed!")
    except Exception as e:
        print(f"\n✗ Error: {e}")
        import traceback
        traceback.print_exc()
