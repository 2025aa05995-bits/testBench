# Example: Oscilloscope capture SOP

This is an **example** RAG document so the index has something to retrieve
the first time you launch the app. Replace it (or delete it) with your own
internal notes — datasheets, calibration steps, lab rules, etc.

## Capture a sine wave on CH1

1. Configure timebase: `bc.osc.set_timebase 0.001` (1 ms / div).
2. Set CH1 voltage scale: `bc.osc.set_voltage_scale 1 1.0` (1 V / div).
3. Start acquisition: `bc.osc.run`.
4. Fetch the trace: `bc.osc.get_trace 1 1024`.
5. Stop the scope: `bc.osc.stop`.

## Plot the trace

After step 4, plot the captured trace with:

```
plot "CH1 sine" bc.osc.get_trace 1 1024
```

Plots and CSV logs are written under `logs/plot_data/`.
