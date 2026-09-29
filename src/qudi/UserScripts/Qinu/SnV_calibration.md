# SnV transition tracking and calibration

Restart Qudi with `configs/QINU.cfg` after these changes. The transition tracker
has `electron_spin: 0.5`; its electron states are **e1** and **e2**. The older
spin-3/2 behavior remains available to other configurations. Internally, e1 and
e2 label the +1/2 and -1/2 basis states, respectively; this is the software basis
convention, not an experimentally established assignment of optical lines.

The NuclearOps queue window contains two permanent, tabbed docks. Drag a tab out
to float it as a separate window. Results stay visible after a run finishes.

The bottom progress bar counts down readouts remaining in the current acquisition
block and shows its percentage complete. It resets for each block, then displays
"Readouts complete; processing data" until NuclearOps publishes "New data arrived".
It uses the same filled-entry estimate as the terminal, independently of live
plot analysis. The `~` marker means progress is approximate: trailing zero-count
readouts can make the estimate lag until the counters confirm completion.
Refocus/sequence setup, stopping, and failure are shown separately; this is not
an elapsed-time countdown or progress through the whole calibration.

Queue calibration reports acceptance, waiting behind another measurement,
startup, or the actual validation/import error in the panel. A pending stop from
an already finished run is cleared before accepting new calibration work. If
the previous measurement is still stopping, wait for it to finish and retry.

1. **SnV ODMR refocus**: choose an OPX intermediate-frequency window, pulse
   duration and amplitude, then queue the calibration. The scan uses the existing
   CRC, electron initialization, SSR and CSR pulse helpers. A resolved
   Lorentzian peak or dip updates the tracked e1/e2
   intermediate frequency. The ODMR fit does not retune the SMIQ local oscillator.
2. **SnV Rabi calibration**: enter fixed amplitudes in percent and a duration
   start, end and step in ns. Pulse duration is the fast OPX sweep; amplitude and
   all other parameters are slow. The default is 20–2000 ns in 20 ns steps at
   20%, 40%, 60%, 80% and 100% amplitude. Durations must be multiples of 4 ns,
   at least 20 ns, with at least 12 time points and two positive amplitudes.
   The program converts amplitude percent to the OPX scale factor once.
3. Each time trace gets an independent sine/cosine fit. The lower plot shows the measured
   frequency versus amplitude and the existing `RabiParametersStatic` linear
   interpolation. Accepted results replace the measured calibration and archive
   its predecessor. Stop, incomplete scans, invalid points and rejected fits do
   not publish a new calibration. **Stop queue** also cancels pending queue work.

The default checkbox uses the latest tracked frequency when execution starts,
so queueing ODMR followed by Rabi uses the new ODMR result. Uncheck it to use an
explicit frequency. These are finite calibration runs; the windows persist,
but the measurements do not repeat forever.

Both calibrations first run the standard A1 PLE refocus, then lock the laser to
the wavemeter wavelength measured after refocusing. They use the normal
tracker `ple_refocus` settings and NuclearOps lock/settling routine. PLE refocus repeats
between measurement blocks when due: every 60 seconds for ODMR and 180 seconds
for Rabi, matching the existing standalone measurement scripts. Every queued run
starts with a fresh refocus, even if the same calibration was just run. The normal
NuclearOps cleanup stops the laser lock at the end. Confocal refocus stays disabled.

## What the queue button runs

The button adds `SnV_ODMR_refocus.py` or `SnV_Rabi_calibration.py` to the normal
NuclearOps queue. Their `run_fun` calls `SnVCalibration.start_calibration` in
`logic/snv_calibration_nops.py`. NuclearOps performs PLE refocus and starts the
laser lock before the measurement block. Its `sequence` method builds the QUA program
inside `qua.program()`. For every scan point it runs CRC, electron initialization,
an initial SSR, the MW pulse, final SSR, CSR and cooldown. The OPX repeats its
fast sweep in a QUA infinite loop while the host acquires a finite measurement
block. NuclearOps advances slow parameters and stops the program when done or
aborted. `hardware/OPX/program_container.py` submits it via `qm.execute`.

The fixed SMIQ LO and power now come from the transition tracker's **OPX setup
parameters / SMIQ** tab (migration defaults: 4.0 GHz, -14 dBm).
`NuclearOPs.ensure_smiq_cw` applies the experiment's captured values and enables
CW output at startup. An explicit `smiq_freq` scan overrides this default.
The **SMIQ LO (MHz)** readout shows the last applied frequency; changing a GUI
default does not immediately command hardware. OPX IQ frequency is separate and
is updated by accepted ODMR fits. The microwave sideband is LO +/- IF according
to the configured IQ sideband.

## Meaning of the time-trace fit

For each fixed OPX amplitude `A`, fit
`P(t) = c + b cos(2π f_R(A) t + φ)`, with `t` in microseconds. Each fitted
frequency supplies one calibration point. The existing `RabiParametersStatic`
interpolates between those measured points; Ω(A) need not be proportional to A.
Choose the duration span and step to resolve several oscillations at all amplitudes.

Zero amplitude is excluded because it has no driven oscillation to fit. No
artificial zero-frequency point is added. Frequencies must increase with amplitude
so inverse interpolation remains unambiguous. Use the ODMR-refocused frequency
for resonant calibration; detuning changes the observed oscillation frequency.
The tracker's historical `omega` field is **f_R = Ω/(2π) in MHz**, with period in
microseconds; it is not angular frequency in rad/s. Fit summaries are keyed by
amplitude percent and contain `frequency_mhz`, `error_mhz` and `r_squared`.

## Files and access

The default log folder is `<qudi source>/log/transition_tracker_log`; it can be
overridden with the tracker's `log_folder` config option.

- `snv_e1_e2_dummy_rabi.dat`: explicitly synthetic, with `omega = 5*A` MHz.
  The **Preview synthetic calibration** button plots it without running hardware.
  It is never used as the measured calibration. Because runtime logs are ignored
  by Git, startup recreates this fixture if absent, without overwriting it.
- `13c5 e1_dummy_rabi.dat` and `13c5 e2_dummy_rabi.dat`: matching synthetic
  fixtures for the currently configured nucleus. They are exposed under keys
  ending in `_dummy`, independently of any measured nuclear calibration.
- `snv_e1_e2_rabi.dat`: created after an accepted measured Rabi calibration.
- `snv_odmr_frequency.dat`: history of accepted OPX frequencies in MHz.
- `rabi_parameters_archive/snv_e1_e2_rabi/`: previous measured calibrations.
- `snv_calibration_runs/odmr/` and `snv_calibration_runs/rabi/`: raw NuclearOps
  measurements, traces, settings and `calibration_fit.json` fit summaries.

```python
frequency_hz = round(queue.tt.snv_frequency_mhz * 1e6)
rp = queue.tt.rp("snv_e1_e2")
frequency_mhz = rp.omega(amplitude=[0.25, 0.5])
amplitude_scale = rp.amplitude(omega=[1.0])
pi_duration_ns = 1000 * rp.pi(amplitude=[0.5])
```

Lookup is limited to the calibrated range. Round any requested pulse duration to
the OPX clock grid before programming it. Qinu fixed-frequency Rabi, Ramsey and T1 scripts now use the tracker IQ frequency.
Explicit frequency scans and scan-specific amplitude/power values still override defaults.
The standalone scripts are `SnV_ODMR_refocus.py` and `SnV_Rabi_calibration.py`.
Their queue parameters mirror the dock controls (`amplitudes_percent`,
`durations_ns`, `frequency_mhz`, `sweeps`, `repetitions`, `init_state`; ODMR also
accepts `span_mhz`, `points`, `duration_ns`, `amplitude_percent`).

Nuclear transition labels become e.g. `13c5 e1` and `13c5 e2`. Existing spin-3/2
calibrations are not relabeled or reused as SnV measurements. Nuclear frequencies
display `nan` until an independently measured `snv_magnetic_field` (Cartesian
tesla) is configured. The optional calculation uses the existing effective-spin
Hamiltonian with two electron levels, not a full SnV orbital Hamiltonian. An OPX
intermediate frequency alone cannot determine the magnetic field.

Hardware-free verification:

```powershell
& 'C:/Users/yy3/anaconda3/envs/squdi/python.exe' -m unittest discover -s tests -p 'test_snv_calibration*.py'
```

These tests cover fitting, interpolation/archive behavior, two-level labels,
tracker activation, scan grouping, offscreen plots and QUA program construction.
Actual OPX execution and the current optical readout settings need validation
on the instrument.

## Editing setup parameters

Open the transition tracker and its **OPX setup parameters** dock (also available
under **View**). The tabs cover GENERAL, SMIQ, ELECTRON, CRC, CSR, SSR,
ELECTRON INIT, PLE REFOCUS and OPTICAL PI PULSE. Units are shown beside each field.
**Apply and save** validates and writes all edited fields together; **Discard
edits** restores the saved values. Calibration updates refresh untouched fields
without discarding pending edits.

Settings are stored as UTF-8 JSON at `<log_folder>/setup_parameters.json`.
On the first activation, migration seeds preserve the previous snippet defaults,
including 208 ns at 100% gate amplitude and the fixed SMIQ settings. An existing
ODMR history initializes the IQ frequency. Once created, the JSON is authoritative
and survives restarts. Invalid files produce an error rather than silently
reverting to defaults. The schema/default seeds live in
`logic/transition_tracker_settings.py`; snippets contain pulse operations only.

Every Qinu `run_fun` captures the tracker settings before `settings()` builds scan
parameters. The helpers, PLE refocus and SMIQ setup use that same snapshot for the
whole run. The run's `setup_parameters.json` records its defaults; the saved scan
data/script record explicit overrides. An edit takes effect in the next queued
experiment, not halfway through the current experiment.

Accepted ODMR fits update `electron.IQ_freq`. Accepted Rabi fits also set
`electron.electron_rabi_period` using the measured interpolation at
`electron.electron_rabi_opx_amp`, when that amplitude is covered by the fit.
The period is rounded to 16 ns so pi and pi/2 pulses are on the 4 ns OPX clock;
periods below 80 ns are rejected because pi/2 would be shorter than 20 ns.
The unrounded measured curve remains available in `RabiParametersStatic`.
After manually changing gate amplitude, click **Use measured Rabi period** or
enter a period explicitly. There is no extrapolation or synthetic fallback;
if a new calibration cannot supply the selected amplitude, its measured curve
is saved and the previous gate period is retained with a log message.

In **GENERAL**, **Use general A1/B2 powers for all groups** is enabled by
default, including when loading an older settings file. It resolves CRC, CSR,
SSR, electron-initialization and PLE-refocus A1/B2 powers to the general values.
The individual values remain stored and are greyed out in the editor while the
override is checked. Unchecking restores those values; repump and optical-pi
powers are always separate. PLE's explicit `use_gui_powers` option still uses
the external power-control setpoints when enabled.

Qinu scripts (including the queued ODMR/Rabi calibrations) now call
`sna.setup_laser_powers(mcas)` once after `ou.init_program()` and **before** the
QUA repetition loops. This sets A1, B2 and CRC repump power, then applies the
configured settling pause once. Optical scripts set their separate optical-pi
power at startup too. Explicit laser-power scans use slow blocks, so each new
power is set when its corresponding QUA program starts.

CRC, CSR, SSR, electron initialization and optical-pi helpers default to
`set_laser_power=False`: they emit the pulses without reapplying powers or
adding power-setting pauses. Unchecking the tracker override does not itself
insert per-pulse power changes. A script needing a different operation power
must explicitly set it or pass `set_laser_power=True` to that helper. Explicit
call-local powers/scan values still override tracker defaults. For example:

```python
with qua.program() as program:
    ou.init_program()
    sna.setup_laser_powers(mcas)
    with qua.infinite_loop_():
        sna.crc(mcas)             # no power setting
        sna.electron_init(mcas)   # no power setting
        sna.ssr(mcas)             # no power setting
        sna.csr(mcas)             # no power setting
```

In the tracker's **SSR** tab, **Init SSR threshold** controls initialization
postselection and **SSR threshold** controls final spin readout. Both default
to 1 count. In **CSR**, **CSR threshold** defaults to 7 counts. Check **Use CRC
threshold** to use the CRC threshold instead; unchecking restores the stored
independent CSR value. Click **Apply and save** for the next experiment.

Qinu scripts and queued SnV calibrations read these thresholds from
`nuclear.setup_parameters.ssr.init_threshold`, `.ssr.threshold`, and
`.csr.csr_threshold` when constructing their analysis sequence. The CSR value
automatically resolves the CRC link in the experiment's snapshot. Existing
comparison operators, photon-detection thresholds and exclusion zones are
preserved. The shared defaults replace the previously different per-script
spin/CSR thresholds, so select the desired values before the next run.

In **CRC**, select **CRC repump laser** (`Laser_520` or `Laser_450`). The
**520 nm repump power** and **450 nm repump power** are independent, in nW.
Existing settings keep 520 nm selected. The new 450 nm power starts at 0 nW;
enter the desired calibrated power before selecting 450 nm, then apply/save.
Both choices use the existing CRC repump duration, threshold and waits.
Qinu's startup helper sets the 450 nm power once when selected; CRC then
pulses that laser without repeating power writes. PLE's green repump remains
separate. Running experiments retain their captured settings.
The optical helper previously ignored its dataclass's 30 ns counting default;
migration preserves the effective 16 ns call default and its 50 ns pulse request
(the existing OPX conversion truncates that pulse to 48 ns).

New scripts should call `nuclear.capture_setup_parameters()` after assigning the
queue and before building settings, then use e.g.
`nuclear.setup_parameters.electron.IQ_freq` in scan definitions. Within a sequence,
use `mcas.ou.setup_parameters.crc.probe_len`. Local helper arguments still accept
scan keys/QUA expressions and do not mutate the stored settings.
