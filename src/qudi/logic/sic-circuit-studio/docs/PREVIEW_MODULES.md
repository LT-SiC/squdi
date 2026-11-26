# Preview modules in v0.3.1

## Pulse sequence preview (Circuit Editor > expandable panel)

- This is a **qualitative display**, not a pulse compiler. It is based on the currently placed logical gates.
- The horizontal direction shows operation ordering, **not actual gate durations**.
- For demonstration, q0 single-spin rotations are drawn on an MW channel and higher-numbered wires on a single RF channel. This is a deliberately provisional convention, not an experimental requirement.
- DDRF is represented by four schematic MW echo markers and an RF envelope. These marks do not encode an actual DDRF sequence, microwave phase cycling, pulse calibration, or conditional state control.
- Rectangular, Gaussian and edge-smoothed rectangular envelopes affect only the drawing. There is **no pulse optimizer or GRAPE implementation** in this version.
- Sign-convention warning icons on DDRF gates are reminders to verify spin-basis and sign mapping with Erik.

## Measurement & Analysis

- The separate page is inspired by `confocal_gui`/`scanning_probe_logic`/`scanning_data_logic`/`scanning_optimize_logic`/`scanner_dummy` from Erik's `erik_testing.cfg`.
- The XY scan displays an artificial 2D fluorescence pattern (Gaussian spots and deterministic texture). Position, resolution and sample selection affect the display.
- The "Simulate scan" action redraws the synthetic data line by line. Crosshair clicks update X and Y profiles.
- The dwell-time dropdown changes the on-screen **demonstration animation speed**, but does not represent acquisition timing and cannot control any device.
- No qudi/squdi process or instrument is accessed. The page is not the native confocal GUI and not a faithful replica of its controls.

## Future integration

A real pulse compiler needs a supported hardware gate inventory, Hilbert-space and sign conventions, oscillator frequencies, pulse timing and amplitude limits, calibrated optimization objective, scheduler/queue logic and experiment permissions. Do not replace the preview output with hardware commands without group review.


## v0.3.2 clarifications

The independent per-wire pulse preview is schematic: MW control is assumed on the central electron (q0), RF on the nuclear wires, and DDRF uses illustrative MW echo shapes. Identical drawing widths do not imply experimentally identical gate durations, and gates in a shared column are only notionally simultaneous.

The 25-nucleus register viewer displays **fictional coordinates** in arbitrary lattice units and proximity links. These are not the measured spatial coordinates or dipolar couplings published by the PI3 group. It provides XY/XZ/YZ projections, rotatable 3D, zoom, and per-spin selection. The fluorescence height surface uses the same generated confocal dummy values as the XY plot.

The compact measurement code pane displays the current editor circuit and cannot control instruments.
