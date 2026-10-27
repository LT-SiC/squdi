# -*- coding: utf-8 -*-

"""
Dummy of an NI X-series analog-output scanner for the ScanningProbeInterface (scanning_probe_logic).

It replaces national_instruments_x_series.py for the new scanning_probe_logic when no NI card is available:
there is no PyDAQmx and no hardware, the "analog outputs" are simulated and the fluorescence is calculated from a
simulated sample.

What it simulates
-----------------
* Analog output: target position (m) <-> output voltage with the same linear mapping as the NI module
  (scanner_position_ranges <-> scanner_voltage_ranges). The voltages can be read with get_ao_voltages().
* Axes: x, y, z, a, as many as scanner_ao_channels are configured (like the NI module). x, y, z are in m, a in V.
* Scans (1D and 2D): a worker thread produces the lines in real time (points per second = scan frequency of the
  fast axis), fills the ScanData (NaN where not yet scanned) and goes back to 'idle' when the scan is done.
  The scanner module_state is 'locked' during a scan, which is what the scan logic polls for.
* Signal: fluorescence = background + Gaussian emitters (NVs) in x, y, z, with Poisson noise, in counts/s. If an
  axis 'a' exists the signal is multiplied by a Lorentzian line around the centre of its range (PLE-like).
  The first emitter is placed close to the start position, so that the optimizer has something to find.
  Counter channels give counts/s, analog input channels give a voltage.

Example config (the options of the NI module can stay in the config, they are accepted and ignored):

scanner_dummy:
    module.Class: 'dummy.ni_x_series_scanner_dummy.NiXSeriesScannerDummy'
    options:
        scanner_ao_channels: ['/Dev1/AO0', '/Dev1/AO1', '/Dev1/AO2']        # 1 to 4 -> axes x, y, z, a
        scanner_voltage_ranges: [[-10, 10], [-10, 10], [-10, 10]]
        scanner_position_ranges: [[0e-6, 100e-6], [0e-6, 100e-6], [-50e-6, 50e-6]]
        scanner_counter_channels: ['fluorescence']                           # unit c/s
        scanner_ai_channels: []                                              # unit V
        max_scan_frequency: 1000                                             # points per second, optional
        # optional simulation settings
        emitters: [[50e-6, 50e-6, 0.0]]       # positions of the emitters in m; default: one near the start, others random
        n_random_emitters: 12
        emitter_rate: 1.0e5                   # counts/s in the maximum of an emitter
        background_rate: 2.0e3
        emitter_sigma_xy: 0.4e-6
        emitter_sigma_z: 1.0e-6
        ple_linewidth: 0.5                    # width (V) of the Lorentzian along axis a
        seed: 1
"""

import threading
import time
from collections import OrderedDict
from typing import Dict, List, Optional, Tuple

import numpy as np
from PySide6 import QtCore

from qudi.core.configoption import ConfigOption
from qudi.interface.scanning_probe_interface import (ScanningProbeInterface, ScanConstraints, ScannerAxis,
                                                     ScannerChannel, ScanData, CoordinateTransformMixin)

AXIS_NAMES = ['x', 'y', 'z', 'a']
AXIS_UNITS = {'x': 'm', 'y': 'm', 'z': 'm', 'a': 'V'}


class _NiXSeriesScannerDummyBase(ScanningProbeInterface):
    """Simulated analog-output scanner. See the module docstring."""

    # options of the NI module that are used by the dummy
    _scanner_ao_channels: List[str] = ConfigOption(name='scanner_ao_channels', default=['/Dev1/AO0', '/Dev1/AO1', '/Dev1/AO2'],
                                                   missing='nothing')
    _scanner_voltage_ranges = ConfigOption(name='scanner_voltage_ranges', default=None, missing='nothing')
    _scanner_position_ranges = ConfigOption(name='scanner_position_ranges', default=None, missing='nothing')
    _scanner_counter_channels = ConfigOption(name='scanner_counter_channels', default=['fluorescence'],
                                             missing='nothing')
    _scanner_ai_channels = ConfigOption(name='scanner_ai_channels', default=[], missing='nothing')

    # options of the dummy
    _max_scan_frequency: float = ConfigOption(name='max_scan_frequency', default=1000.0, missing='nothing')
    _max_resolution: int = ConfigOption(name='max_resolution', default=10000, missing='nothing')
    _max_move_velocity: Optional[float] = ConfigOption(name='max_move_velocity', default=None, missing='nothing')
    _emitters = ConfigOption(name='emitters', default=None, missing='nothing')
    _n_random_emitters: int = ConfigOption(name='n_random_emitters', default=12, missing='nothing')
    _emitter_rate: float = ConfigOption(name='emitter_rate', default=1.0e5, missing='nothing')
    _background_rate: float = ConfigOption(name='background_rate', default=2.0e3, missing='nothing')
    _emitter_sigma_xy: float = ConfigOption(name='emitter_sigma_xy', default=0.4e-6, missing='nothing')
    _emitter_sigma_z: float = ConfigOption(name='emitter_sigma_z', default=1.0e-6, missing='nothing')
    _ple_linewidth: float = ConfigOption(name='ple_linewidth', default=0.5, missing='nothing')
    _seed: Optional[int] = ConfigOption(name='seed', default=None, missing='nothing')

    # options of the NI module that are accepted so that its config block can be pasted without editing it
    for _ni_name in ('photon_sources', 'clock_channel', 'default_clock_frequency', 'counter_channels',
                     'counter_ai_channels', 'counter_voltage_range', 'default_scanner_clock_frequency',
                     'scanner_clock_channel', 'pixel_clock_channel', 'odmr_trigger_channel', 'odmr_trigger_line',
                     'odmr_switch_line', 'gate_in_channel', 'default_samples_number', 'max_counts',
                     'read_write_timeout', 'counting_edge_rising', 'rotation_correction', 'scaling_correction_a',
                     'scaling_correction_b', 'scaling_correction_x', 'scaling_correction_y'):
        locals()['_ni_' + _ni_name] = ConfigOption(name=_ni_name, default=None, missing='nothing')
    del _ni_name

    # signal of the old confocal chain that the scanning logic may emit
    sigChangeTemperatureRegime = QtCore.Signal(bool)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._backwards_line_resolution = 50      # set by the scanning logic
        self._data_lock = threading.RLock()
        self._state_lock = threading.RLock()

        self._axes: 'OrderedDict[str, ScannerAxis]' = OrderedDict()
        self._channels: List[ScannerChannel] = []
        self._constraints: Optional[ScanConstraints] = None
        self._voltage_ranges: Dict[str, Tuple[float, float]] = {}
        self._target: Dict[str, float] = {}
        self._ao_voltages: Dict[str, float] = {}

        self._scan_data: Optional[ScanData] = None
        self._scan_settings = None
        self._scan_thread: Optional[threading.Thread] = None
        self._scan_stop_event: Optional[threading.Event] = None

        self._rng = np.random.default_rng()
        self._emitter_positions = np.zeros((0, 3))

    # ----------------------------------------------------------------------------------------------------------
    # qudi module
    # ----------------------------------------------------------------------------------------------------------
    def on_activate(self) -> None:
        self._rng = np.random.default_rng(self._seed)
        self._build_axes_and_channels()
        self._constraints = ScanConstraints(axes=list(self._axes.values()),
                                            channels=list(self._channels),
                                            backscan_configurable=True,
                                            has_position_feedback=False,
                                            square_px_only=False)
        # start in the centre of the ranges, like an analog output that is set to the middle of its range
        self._target = {name: 0.5 * (ax.min_value + ax.max_value) for name, ax in self._axes.items()}
        self._update_voltages()
        self._build_sample()
        self._scan_data = None
        self.log.warning('Using the DUMMY NI scanner: positions and fluorescence are simulated.')

    def on_deactivate(self) -> None:
        self._stop_scan_thread()
        with self._state_lock:
            if self.module_state() == 'locked':
                self.module_state.unlock()

    # ----------------------------------------------------------------------------------------------------------
    # ScanningProbeInterface
    # ----------------------------------------------------------------------------------------------------------
    def get_constraints(self) -> ScanConstraints:
        return self._constraints

    def get_max_move_velocity(self):
        return self._max_move_velocity

    def reset(self) -> None:
        """Hard reset: stop everything and set the outputs to the centre of the ranges."""
        self._stop_scan_thread()
        with self._state_lock:
            if self.module_state() == 'locked':
                self.module_state.unlock()
        self._target = {name: 0.5 * (ax.min_value + ax.max_value) for name, ax in self._axes.items()}
        self._update_voltages()

    def emergency_stop(self) -> None:
        self.log.warning('Emergency stop: scan stopped, outputs stay where they are.')
        self.stop_scan()

    def configure_scan(self, settings):
        """
        @param dict settings: keys 'axes', 'range', 'resolution', 'frequency'
        @return (bool, dict): failure indicator, settings that are really used
        """
        if self.module_state() != 'idle':
            self.log.error('Cannot configure a scan while a scan is running.')
            return True, settings
        try:
            axes_names = tuple(settings['axes'])
            if not 0 < len(axes_names) <= 2 or any(name not in self._axes for name in axes_names):
                raise ValueError('axes {} not valid, available axes are {}'.format(axes_names, list(self._axes)))
            axes = [self._axes[name] for name in axes_names]
            ranges = []
            for ax, (start, stop) in zip(axes, settings['range']):
                ranges.append((ax.clip_value(float(start)), ax.clip_value(float(stop))))
            resolution = tuple(int(ax.clip_resolution(int(res))) for ax, res in zip(axes, settings['resolution']))
            frequency = float(axes[0].clip_frequency(float(settings['frequency'])))
            if frequency <= 0:
                raise ValueError('scan frequency must be positive')
        except Exception as err:
            self.log.error('Invalid scan settings {}: {}'.format(settings, err))
            return True, settings

        with self._data_lock:
            self._scan_data = ScanData(channels=list(self._channels),
                                       scan_axes=axes,
                                       scan_range=tuple(ranges),
                                       scan_resolution=resolution,
                                       scan_frequency=frequency,
                                       target_at_start=self.get_target(),
                                       position_feedback_axes=None)
            self._scan_settings = {'axes': axes_names, 'range': tuple(ranges), 'resolution': resolution,
                                   'frequency': frequency}
        return False, dict(self._scan_settings)

    def start_scan(self):
        """@return int: 0 if the scan was started, -1 on failure"""
        with self._state_lock:
            if self.module_state() != 'idle':
                self.log.error('A scan is already running.')
                return -1
            if self._scan_data is None:
                self.log.error('Scan is not configured.')
                return -1
            self.module_state.lock()
        with self._data_lock:
            self._scan_data.new_scan()
            self._scan_data.retrace_data = self._empty_retrace_data()
        self._scan_stop_event = threading.Event()
        self._scan_thread = threading.Thread(target=self._scan_worker,
                                             args=(self._scan_stop_event, dict(self._scan_settings),
                                                   dict(self._target), self._backwards_line_resolution),
                                             name='ni_scanner_dummy_scan', daemon=True)
        self._scan_thread.start()
        return 0

    def stop_scan(self):
        """@return int: 0 on success"""
        self._stop_scan_thread()
        with self._state_lock:
            if self.module_state() == 'locked':
                self.module_state.unlock()
        return 0

    def get_scan_data(self):
        with self._data_lock:
            return None if self._scan_data is None else self._scan_data.copy()

    def move_absolute(self, position, velocity=None, blocking=False):
        """Set the analog outputs to a new position. Axes that are not given keep their value."""
        if self.module_state() != 'idle':
            self.log.error('Cannot move the scanner while a scan is running.')
            return dict(self._target)
        unknown = [ax for ax in position if ax not in self._axes]
        if unknown:
            self.log.error('Unknown scanner axes {}, available are {}'.format(unknown, list(self._axes)))
            return dict(self._target)
        new_target = dict(self._target)
        for name, value in position.items():
            clipped = self._axes[name].clip_value(float(value))
            if clipped != float(value):
                self.log.warning('Position {:.3e} of axis {} is out of range, clipped to {:.3e}.'.format(
                    float(value), name, clipped))
            new_target[name] = clipped
        velocity = velocity if velocity is not None else self._max_move_velocity
        if blocking and velocity:
            distance = max(abs(new_target[n] - self._target[n]) for n in new_target)
            time.sleep(min(distance / velocity, 5.0))
        self._target = new_target
        self._update_voltages()
        return dict(self._target)

    def move_relative(self, distance, velocity=None, blocking=False):
        if self.module_state() != 'idle':
            self.log.error('Cannot move the scanner while a scan is running.')
            return dict(self._target)
        position = {name: self._target[name] + float(dist) for name, dist in distance.items()
                    if name in self._target}
        return self.move_absolute(position, velocity=velocity, blocking=blocking)

    def get_target(self):
        return dict(self._target)

    def get_position(self):
        """No position feedback: the position is the target."""
        return dict(self._target)

    # ----------------------------------------------------------------------------------------------------------
    # analog output
    # ----------------------------------------------------------------------------------------------------------
    def get_ao_voltages(self) -> Dict[str, float]:
        """Voltages that the (simulated) analog outputs deliver for the current target."""
        return dict(self._ao_voltages)

    def _position_to_voltage(self, name: str, position: float) -> float:
        ax = self._axes[name]
        vmin, vmax = self._voltage_ranges[name]
        span = ax.max_value - ax.min_value
        volt = vmin + (position - ax.min_value) / span * (vmax - vmin) if span != 0 else vmin
        return float(np.clip(volt, min(vmin, vmax), max(vmin, vmax)))

    def _update_voltages(self) -> None:
        self._ao_voltages = {name: self._position_to_voltage(name, pos) for name, pos in self._target.items()}

    # ----------------------------------------------------------------------------------------------------------
    # simulated sample
    # ----------------------------------------------------------------------------------------------------------
    def _build_axes_and_channels(self) -> None:
        n_axes = len(self._scanner_ao_channels)
        if not 1 <= n_axes <= len(AXIS_NAMES):
            raise ValueError('scanner_ao_channels must contain 1 to {} channels.'.format(len(AXIS_NAMES)))
        names = AXIS_NAMES[:n_axes]

        default_pos = {'x': (0.0, 100e-6), 'y': (0.0, 100e-6), 'z': (-50e-6, 50e-6), 'a': (-10.0, 10.0)}
        pos_ranges = self._scanner_position_ranges or [default_pos[n] for n in names]
        volt_ranges = self._scanner_voltage_ranges or [(-10, 10)] * n_axes
        if len(pos_ranges) < n_axes or len(volt_ranges) < n_axes:
            raise ValueError('Specify a position range and a voltage range for each scanner_ao_channel.')

        self._axes = OrderedDict()
        self._voltage_ranges = {}
        for name, prange, vrange in zip(names, pos_ranges, volt_ranges):
            self._axes[name] = ScannerAxis(name=name,
                                           unit=AXIS_UNITS[name],
                                           value_range=tuple(prange),
                                           step_range=(0.0, np.inf),
                                           resolution_range=(1, int(self._max_resolution)),
                                           frequency_range=(0.0, float(self._max_scan_frequency)))
            self._voltage_ranges[name] = (float(vrange[0]), float(vrange[1]))

        counter = list(self._scanner_counter_channels or [])
        ai = list(self._scanner_ai_channels or [])
        if not counter and not ai:
            counter = ['fluorescence']
        self._channels = ([ScannerChannel(name=str(ch), unit='c/s', dtype=np.float64) for ch in counter] +
                          [ScannerChannel(name=str(ch), unit='V', dtype=np.float64) for ch in ai])
        self._counter_names = [str(ch) for ch in counter]
        self._ai_names = [str(ch) for ch in ai]

    def _build_sample(self) -> None:
        """Positions of the emitters (x, y, z)."""
        centre = np.array([0.5 * (self._axes[n].min_value + self._axes[n].max_value) if n in self._axes else 0.0
                           for n in ('x', 'y', 'z')])
        if self._emitters:
            emitters = np.array([list(e) + [0.0] * (3 - len(e)) for e in self._emitters], dtype=float)[:, :3]
        else:
            # one emitter close to the start position (so the optimizer has something to find), the others random
            first = centre + np.array([0.3e-6, -0.2e-6, 0.5e-6])
            lows = np.array([self._axes[n].min_value if n in self._axes else 0.0 for n in ('x', 'y', 'z')])
            highs = np.array([self._axes[n].max_value if n in self._axes else 0.0 for n in ('x', 'y', 'z')])
            others = lows + self._rng.random((int(self._n_random_emitters), 3)) * (highs - lows)
            emitters = np.vstack([first, others])
        self._emitter_positions = emitters

    def _signal_rate(self, coords: Dict[str, np.ndarray]) -> np.ndarray:
        """Noise-free fluorescence rate in counts/s at the given coordinates (arrays of the same length)."""
        n = max(np.size(v) for v in coords.values())
        get = lambda name: np.broadcast_to(np.asarray(coords.get(name, self._target.get(name, 0.0)), dtype=float), (n,))
        x, y, z = get('x'), get('y'), get('z')
        rate = np.full(n, float(self._background_rate))
        s_xy2 = 2 * self._emitter_sigma_xy ** 2
        s_z2 = 2 * self._emitter_sigma_z ** 2
        for ex, ey, ez in self._emitter_positions:
            rate += self._emitter_rate * np.exp(-((x - ex) ** 2 + (y - ey) ** 2) / s_xy2 - (z - ez) ** 2 / s_z2)
        if 'a' in self._axes:
            a = get('a')
            a0 = 0.5 * (self._axes['a'].min_value + self._axes['a'].max_value)
            hw = self._ple_linewidth / 2
            rate = self._background_rate + (rate - self._background_rate) * hw ** 2 / ((a - a0) ** 2 + hw ** 2)
        return rate

    def _measure(self, coords: Dict[str, np.ndarray], dwell: float) -> Dict[str, np.ndarray]:
        """Measured values of all channels for the given points, each measured for 'dwell' seconds."""
        rate = self._signal_rate(coords)
        out = {}
        for ch in self._counter_names:
            out[ch] = self._rng.poisson(rate * dwell) / dwell
        for ch in self._ai_names:
            out[ch] = 0.1 * rate / max(self._emitter_rate, 1.0) + 0.002 * self._rng.normal(size=rate.shape)
        return out

    # ----------------------------------------------------------------------------------------------------------
    # scanning
    # ----------------------------------------------------------------------------------------------------------
    def _empty_retrace_data(self):
        res = self._scan_data.scan_resolution
        back = max(int(self._backwards_line_resolution), 1)
        shape = (back,) if len(res) == 1 else (back, res[1])
        return {ch.name: np.full(shape, np.nan, dtype=ch.dtype) for ch in self._channels}

    def _scan_worker(self, stop_event: threading.Event, settings: dict, start_target: dict,
                     back_resolution: int) -> None:
        """Produces the scan line by line in real time and finishes by unlocking the module state."""
        try:
            axes = settings['axes']
            (r0_start, r0_stop) = settings['range'][0]
            res0 = settings['resolution'][0]
            frequency = settings['frequency']
            dwell = 1.0 / frequency
            line_time = res0 / frequency
            back_res = max(int(back_resolution), 1)
            fast = np.linspace(r0_start, r0_stop, res0)
            fast_back = np.linspace(r0_stop, r0_start, back_res)

            if len(axes) == 1:
                coords = dict(start_target)
                coords[axes[0]] = fast
                values = self._measure(coords, dwell)
                if stop_event.wait(line_time):
                    return
                coords_back = dict(start_target)
                coords_back[axes[0]] = fast_back
                values_back = self._measure(coords_back, dwell)
                with self._data_lock:
                    for ch, vals in values.items():
                        self._scan_data.data[ch][:] = vals
                    for ch, vals in values_back.items():
                        self._scan_data.retrace_data[ch][:] = vals
            else:
                (r1_start, r1_stop) = settings['range'][1]
                res1 = settings['resolution'][1]
                slow = np.linspace(r1_start, r1_stop, res1)
                for j, s in enumerate(slow):
                    coords = dict(start_target)
                    coords[axes[0]] = fast
                    coords[axes[1]] = np.full(res0, s)
                    values = self._measure(coords, dwell)
                    coords_back = dict(start_target)
                    coords_back[axes[0]] = fast_back
                    coords_back[axes[1]] = np.full(back_res, s)
                    values_back = self._measure(coords_back, dwell)
                    if stop_event.wait(line_time):      # also the time of one line passes if the scan is stopped
                        return
                    with self._data_lock:
                        for ch, vals in values.items():
                            self._scan_data.data[ch][:, j] = vals
                        for ch, vals in values_back.items():
                            self._scan_data.retrace_data[ch][:, j] = vals
        except Exception:
            self.log.exception('Error in the simulated scan.')
        finally:
            if not stop_event.is_set():
                # scan finished on its own: back to idle, the scan logic polls for this
                with self._state_lock:
                    if self.module_state() == 'locked':
                        self.module_state.unlock()

    def _stop_scan_thread(self) -> None:
        thread = self._scan_thread
        if self._scan_stop_event is not None:
            self._scan_stop_event.set()
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=5.0)
        self._scan_thread = None
        self._scan_stop_event = None


class NiXSeriesScannerDummy(CoordinateTransformMixin, _NiXSeriesScannerDummyBase):
    """NI X-series analog-output scanner dummy with support for the tilt correction (coordinate transformation)."""
    pass
