# -*- coding: utf-8 -*-

"""
Qudi hardware module of a National Instruments X series card as scanner for the ScanningProbeInterface
(scanning_probe_logic, scanner GUI, optimizer).

Rewrite of the legacy module (SlowCounterInterface + ConfocalScannerInterface + ODMRCounterInterface). Only the part
that the confocal scanner used is kept: the analog outputs (galvo / piezo positions), the scanner clock, the
photon counters and the optional analog inputs. Slow counter, ODMR counter, gated counter and digital switches
were removed.

!!!!!! NI USB 63XX, NI PCIe 63XX and NI PXIe 63XX DEVICES ONLY !!!!!!

How it works
------------
* The analog outputs are always on. move_absolute / move_relative write the voltages of a new position (with a short
  ramp, see ramp_time_full_range) and keep the target. There is no position feedback, the position is the target.
* A scan runs in a worker thread: for every line the scanner ramps to the start of the line, then the line is scanned
  with the hardware-timed analog output and the counters (as the legacy scan_line did), then the line is scanned
  backwards (retrace, _backwards_line_resolution points). The scan data is filled line by line. The module state is
  'locked' during the scan and 'idle' afterwards, which is what the scan logic polls for. At the end the scanner
  returns to the position where it was before the scan.
* Axes are x, y, z, a, as many as scanner_ao_channels are configured (x, y, z in m, a in V). The tilt
  correction (coordinate transformation) of the scan logic is supported.

Example config for copy-paste (the options of the legacy module that are not needed any more are accepted and ignored):

nicard_6343:
    module.Class: 'national_instruments_x_series.NationalInstrumentsXSeries'
    options:
        photon_sources:
            - '/Dev1/PFI8'
        scanner_clock_channel: '/Dev1/Ctr2'
        pixel_clock_channel: '/Dev1/PFI6'          # optional, together with output_pixel_clock: True
        default_scanner_clock_frequency: 100       # optional, in Hz
        scanner_ao_channels:
            - '/Dev1/AO0'
            - '/Dev1/AO1'
            - '/Dev1/AO2'
            - '/Dev1/AO3'
        scanner_counter_channels:
            - '/Dev1/Ctr3'
        scanner_ai_channels: []                     # optional analog inputs, e.g. ['/Dev1/AI1']
        counter_voltage_range: [-10, 10]            # range of the analog inputs
        scanner_voltage_ranges:
            - [-10, 10]
            - [-10, 10]
            - [-10, 10]
            - [-10, 10]
        scanner_position_ranges:
            - [0e-6, 200e-6]
            - [0e-6, 200e-6]
            - [-100e-6, 100e-6]
            - [-10, 10]
        scanner_channel_names: ['fluorescence']     # optional, names of the counter and analog input channels
        max_scan_frequency: 1000                    # optional, Hz
        ramp_time_full_range: 0.1                   # optional, s for a move over the full range of an axis
        max_counts: 3.0e7
        read_write_timeout: 10
"""

import re
import threading
import time
from collections import OrderedDict
from typing import List

import numpy as np
import PyDAQmx as daq
from PySide6 import QtCore

from qudi.core.configoption import ConfigOption
from qudi.interface.scanning_probe_interface import (ScanningProbeInterface, ScanConstraints, ScannerAxis,
                                                     ScannerChannel, ScanData, CoordinateTransformMixin)
from qudi.interface.slow_counter_interface import SlowCounterConstraints
from qudi.interface.slow_counter_interface import CountingMode

AXIS_NAMES = ['x', 'y', 'z', 'a']
AXIS_UNITS = {'x': 'm', 'y': 'm', 'z': 'm', 'a': 'V'}


def _number(value):
    """Numbers of the correction options may be given as numbers or as expressions like 'np.pi/4'."""
    if isinstance(value, str):
        return float(eval(value, {'np': np, 'pi': np.pi}))
    return float(value)


class _NationalInstrumentsXSeriesBase(ScanningProbeInterface):
    """ A National Instruments X series card as scanner. See the module docstring. """

    # --- scanner ---
    _photon_sources: List[str] = ConfigOption('photon_sources', list(), missing='warn')
    _default_scanner_clock_frequency = ConfigOption('default_scanner_clock_frequency', 100, missing='info')
    _scanner_clock_channel = ConfigOption('scanner_clock_channel', missing='error')
    _pixel_clock_channel = ConfigOption('pixel_clock_channel', None)
    _scanner_ao_channels = ConfigOption('scanner_ao_channels', missing='error')
    _scanner_ai_channels = ConfigOption('scanner_ai_channels', list(), missing='info')
    _scanner_counter_channels = ConfigOption('scanner_counter_channels', list(), missing='warn')
    _scanner_voltage_ranges = ConfigOption('scanner_voltage_ranges', missing='error')
    _scanner_position_ranges = ConfigOption('scanner_position_ranges', missing='error')
    _counter_voltage_range = ConfigOption('counter_voltage_range', [-10, 10], missing='info')   # of the analog inputs
    _max_counts = ConfigOption('max_counts', default=3e7)
    _RWTimeout = ConfigOption('read_write_timeout', default=10)

    # --- corrections of a distorted scan (as in the legacy module) ---
    _trapezoid_rotation_correction = ConfigOption('trapezoid_rotation_correction', 0)
    _rotation_correction = ConfigOption('rotation_correction', 0)
    _scaling_correction_a = ConfigOption('scaling_correction_a', 1)
    _scaling_correction_b = ConfigOption('scaling_correction_b', 1)
    _scaling_correction_x = ConfigOption('scaling_correction_x', 1)
    _scaling_correction_y = ConfigOption('scaling_correction_y', 1)

    # --- new options of the scanning probe version ---
    _scanner_channel_names = ConfigOption('scanner_channel_names', None, missing='nothing')
    _max_scan_frequency = ConfigOption('max_scan_frequency', 1000.0, missing='nothing')     # Hz
    _max_resolution = ConfigOption('max_resolution', 10000, missing='nothing')
    _ramp_time_full_range = ConfigOption('ramp_time_full_range', 0.1, missing='nothing')    # s
    _output_pixel_clock = ConfigOption('output_pixel_clock', False, missing='nothing')
    _initial_position = ConfigOption('initial_position', None, missing='nothing')           # {'x': .., 'y': ..} or None
    # optional voltage / position ranges that are switched with change_temperature_regime
    _scanner_voltage_ranges_lt = ConfigOption('scanner_voltage_ranges_lt', None, missing='nothing')
    _scanner_voltage_ranges_rt = ConfigOption('scanner_voltage_ranges_rt', None, missing='nothing')
    _scanner_position_ranges_lt = ConfigOption('scanner_position_ranges_lt', None, missing='nothing')
    _scanner_position_ranges_rt = ConfigOption('scanner_position_ranges_rt', None, missing='nothing')

    # options of the legacy module (slow counter, ODMR, gated counter) that are accepted and ignored
    for _legacy_name in ('clock_channel', 'default_clock_frequency', 'counter_channels', 'counter_ai_channels',
                         'odmr_trigger_channel', 'odmr_trigger_line', 'odmr_switch_line', 'gate_in_channel',
                         'default_samples_number', 'counting_edge_rising'):
        locals()['_legacy_' + _legacy_name] = ConfigOption(_legacy_name, None, missing='nothing')
    del _legacy_name

    sigLimitsChanged = QtCore.Signal()
    sigChangeTemperatureRegime = QtCore.Signal(bool)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._backwards_line_resolution = 50      # set by the scanning logic
        self._data_lock = threading.RLock()       # scan data
        self._ao_lock = threading.RLock()         # analog output
        self._state_lock = threading.RLock()      # module state

        self._axes: 'OrderedDict[str, ScannerAxis]' = OrderedDict()
        self._channels: List[ScannerChannel] = []
        self._constraints = None
        self._position_ranges: List[List[float]] = []
        self._voltage_ranges: List[List[float]] = []
        self._current_position = np.zeros(0)      # where the scanner physically is (also during a scan)
        self._target_position = np.zeros(0)       # the target: only changes with a move or after a scan

        self._scan_data = None
        self._scan_settings = None
        self._scan_thread = None
        self._scan_stop_event = None

        # DAQmx tasks
        self._scanner_ao_task = None
        self._scanner_clock_daq_task = None
        self._scanner_counter_daq_tasks = []
        self._scanner_analog_daq_task = None
        self._scanner_clock_frequency = None
        self._line_length = None

    # ----------------------------------------------------------------------------------------------------------
    # qudi module
    # ----------------------------------------------------------------------------------------------------------
    def on_activate(self):
        self._photon_sources = self._photon_sources if self._photon_sources is not None else list()
        self._scanner_counter_channels = self._scanner_counter_channels or list()
        print("counter channels")
        print(self._scanner_counter_channels)
        self._scanner_ai_channels = self._scanner_ai_channels or list()
        print("ai channels")
        print(self._scanner_ai_channels)
        self._corrections = {
            'trapezoid': _number(self._trapezoid_rotation_correction),
            'rotation': _number(self._rotation_correction),
            'a': _number(self._scaling_correction_a),
            'b': _number(self._scaling_correction_b),
            'x': _number(self._scaling_correction_x),
            'y': _number(self._scaling_correction_y),
        }
        self._scanner_ao_channels = list(self._scanner_ao_channels)
        self._position_ranges = [list(r) for r in self._scanner_position_ranges]
        self._voltage_ranges = [list(r) for r in self._scanner_voltage_ranges]
        if len(self._scanner_ao_channels) > len(self._voltage_ranges):
            raise ValueError('Specify at least as many scanner_voltage_ranges as scanner_ao_channels!')
        if len(self._scanner_ao_channels) > len(self._position_ranges):
            raise ValueError('Specify at least as many scanner_position_ranges as scanner_ao_channels!')
        if len(self._scanner_counter_channels) + len(self._scanner_ai_channels) < 1:
            raise ValueError('Specify at least one counter or analog input channel for the scanner!')
        if len(self._photon_sources) < len(self._scanner_counter_channels):
            raise ValueError('You have given {0} photon_sources but {1} scanner_counter_channels.'.format(
                len(self._photon_sources), len(self._scanner_counter_channels)))

        self._build_axes_and_channels()
        initial = self._initial_position or {}
        self._current_position = np.array(
            [self._axes[name].clip_value(float(initial.get(name, 0.0))) for name in self._axes])
        self._target_position = self._current_position.copy()

        self.sigChangeTemperatureRegime.connect(self.set_temperature_regime)
        # The analog output is always needed and does not interfere with the rest: start it and leave it running.
        # (Like in the legacy module nothing is written at activation, the first move sets the outputs.)
        if self._start_analog_output() < 0:
            raise Exception('Failed to start NI card module due to analog output failure.')

    def on_deactivate(self):
        self._stop_scan_thread()
        with self._state_lock:
            if self.module_state() == 'locked':
                self.module_state.unlock()
        try:
            self.sigChangeTemperatureRegime.disconnect(self.set_temperature_regime)
        except Exception:
            pass
        self._stop_analog_output()
        try:
            daq.DAQmxClearTask(self._scanner_ao_task)
            self._scanner_ao_task = None
        except Exception:
            self.log.exception('Could not clear AO task.')
        self.reset_hardware()

    # ----------------------------------------------------------------------------------------------------------
    # ScanningProbeInterface
    # ----------------------------------------------------------------------------------------------------------
    def get_constraints(self) -> ScanConstraints:
        return self._constraints

    def get_max_move_velocity(self):
        return None

    def reset(self):
        """Stop the scan and reset the device. The analog outputs are at 0 V afterwards."""
        self._stop_scan_thread()
        with self._state_lock:
            if self.module_state() == 'locked':
                self.module_state.unlock()
        self.reset_hardware()
        self._start_analog_output()
        # position of 0 V
        zero_position = []
        for name, (pmin, pmax), (vmin, vmax) in zip(self._axes, self._position_ranges, self._voltage_ranges):
            pos = pmin + (0.0 - vmin) / (vmax - vmin) * (pmax - pmin)
            zero_position.append(self._axes[name].clip_value(pos))
        self._current_position = np.array(zero_position)
        self._target_position = self._current_position.copy()

    def emergency_stop(self):
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
            ranges = tuple((ax.clip_value(float(start)), ax.clip_value(float(stop)))
                           for ax, (start, stop) in zip(axes, settings['range']))
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
                                       scan_range=ranges,
                                       scan_resolution=resolution,
                                       scan_frequency=frequency,
                                       target_at_start=self.get_target(),
                                       position_feedback_axes=None)
            self._scan_settings = {'axes': axes_names, 'range': ranges, 'resolution': resolution,
                                   'frequency': frequency}
        return False, dict(self._scan_settings)

    def start_scan(self):
        """@return int: 0 if the scan was started, -1 on failure (the scan logic checks for < 0)"""
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
        self._scan_thread = threading.Thread(
            target=self._scan_worker,
            args=(self._scan_stop_event, dict(self._scan_settings), self._target_position.copy(),
                  int(self._backwards_line_resolution)),
            name='ni_scanner_scan', daemon=True)
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
        """Set the analog outputs to a new position (ramped). Axes that are not given keep their value."""
        if self.module_state() != 'idle':
            self.log.error('Cannot move the scanner while a scan is running.')
            return self.get_target()
        unknown = [name for name in position if name not in self._axes]
        if unknown:
            self.log.error('Unknown scanner axes {}, available are {}'.format(unknown, list(self._axes)))
            return self.get_target()
        new_position = self._target_position.copy()
        for i, name in enumerate(self._axes):
            if name in position:
                clipped = self._axes[name].clip_value(float(position[name]))
                if clipped != float(position[name]):
                    self.log.warning('Position {:.3e} of axis {} is out of range, clipped to {:.3e}.'.format(
                        float(position[name]), name, clipped))
                new_position[i] = clipped
        try:
            self._ramp_to(new_position)
            self._target_position = self._current_position.copy()
        except Exception:
            self.log.exception('Could not move the scanner.')
        return self.get_target()

    def move_relative(self, distance, velocity=None, blocking=False):
        if self.module_state() != 'idle':
            self.log.error('Cannot move the scanner while a scan is running.')
            return self.get_target()
        target = self.get_target()
        position = {name: target[name] + float(dist) for name, dist in distance.items() if name in target}
        return self.move_absolute(position, velocity=velocity, blocking=blocking)

    def get_target(self):
        return {name: float(pos) for name, pos in zip(self._axes, self._target_position)}

    def get_position(self):
        """No position feedback: the position is the target."""
        return self.get_target()

    # ----------------------------------------------------------------------------------------------------------
    # axes, channels, ranges
    # ----------------------------------------------------------------------------------------------------------
    def _build_axes_and_channels(self) -> None:
        n_axes = len(self._scanner_ao_channels)
        if not 1 <= n_axes <= len(AXIS_NAMES):
            raise ValueError('scanner_ao_channels must contain 1 to {} channels.'.format(len(AXIS_NAMES)))
        self._axes = OrderedDict()
        for name, prange in zip(AXIS_NAMES[:n_axes], self._position_ranges):
            self._axes[name] = ScannerAxis(name=name,
                                           unit=AXIS_UNITS[name],
                                           value_range=(float(prange[0]), float(prange[1])),
                                           step_range=(0.0, np.inf),
                                           resolution_range=(1, int(self._max_resolution)),
                                           frequency_range=(0.0, float(self._max_scan_frequency)))
        n_counter = len(self._scanner_counter_channels)
        n_ai = len(self._scanner_ai_channels)
        names = list(self._scanner_channel_names) if self._scanner_channel_names else []
        if len(names) != n_counter + n_ai:
            names = (['fluorescence'] if n_counter == 1 else ['fluorescence{}'.format(i + 1) for i in range(n_counter)])
            names += ['analog_in{}'.format(i + 1) for i in range(n_ai)]
        self._channels = ([ScannerChannel(name=n, unit='c/s', dtype=np.float64) for n in names[:n_counter]] +
                          [ScannerChannel(name=n, unit='V', dtype=np.float64) for n in names[n_counter:]])
        self._constraints = ScanConstraints(axes=list(self._axes.values()),
                                            channels=list(self._channels),
                                            backscan_configurable=True,
                                            has_position_feedback=False,
                                            square_px_only=False)

    def set_temperature_regime(self, is_lt: bool) -> None:
        """Switch to the configured LT or RT ranges (scanner_*_ranges_lt / _rt). The axes of the GUI and the logic
        are read at their activation, they have to be reactivated to see the new ranges."""
        volt = self._scanner_voltage_ranges_lt if is_lt else self._scanner_voltage_ranges_rt
        pos = self._scanner_position_ranges_lt if is_lt else self._scanner_position_ranges_rt
        if volt is None or pos is None:
            self.log.warning('No voltage and position ranges are configured for the {} regime.'.format(
                'LT' if is_lt else 'RT'))
            return
        if self.module_state() != 'idle':
            self.log.error('Cannot change the ranges while a scan is running.')
            return
        self._voltage_ranges = [list(r) for r in volt]
        self._position_ranges = [list(r) for r in pos]
        self._build_axes_and_channels()
        self._current_position = np.array(
            [self._axes[name].clip_value(p) for name, p in zip(self._axes, self._current_position)])
        self._target_position = self._current_position.copy()
        self._start_analog_output()           # reloads the voltage limits
        self.sigLimitsChanged.emit()

    # ----------------------------------------------------------------------------------------------------------
    # analog output
    # ----------------------------------------------------------------------------------------------------------
    def _start_analog_output(self) -> int:
        """Starts or restarts the analog output. @return int: error code (0:OK, -1:error)"""
        try:
            if self._scanner_ao_task is not None:
                daq.DAQmxStopTask(self._scanner_ao_task)
                daq.DAQmxClearTask(self._scanner_ao_task)
                self._scanner_ao_task = None
            self._scanner_ao_task = daq.TaskHandle()
            daq.DAQmxCreateTask('ScannerAO', daq.byref(self._scanner_ao_task))
            for n, chan in enumerate(self._scanner_ao_channels):
                daq.DAQmxCreateAOVoltageChan(self._scanner_ao_task, chan, 'Scanner AO Channel {0}'.format(n),
                                             self._voltage_ranges[n][0], self._voltage_ranges[n][1],
                                             daq.DAQmx_Val_Volts, '')
        except Exception:
            self.log.exception('Error starting analog output task.')
            return -1
        return 0

    def _stop_analog_output(self) -> int:
        """Stops the (timed) analog output and sets it back to on demand. @return int: 0 ok, -1 error"""
        if self._scanner_ao_task is None:
            return -1
        retval = 0
        try:
            daq.DAQmxStopTask(self._scanner_ao_task)
        except Exception:
            self.log.exception('Error stopping analog output.')
            retval = -1
        try:
            daq.DAQmxSetSampTimingType(self._scanner_ao_task, daq.DAQmx_Val_OnDemand)
        except Exception:
            self.log.exception('Error changing analog output mode.')
            retval = -1
        return retval

    def _write_scanner_ao(self, voltages, length=1, start=False):
        """Writes a set of voltages (n_axes x length) to the analog outputs. start: write immediately (True) or wait
        for the start of the task (False)."""
        n_written = daq.int32()
        daq.DAQmxWriteAnalogF64(self._scanner_ao_task, length, start, self._RWTimeout, daq.DAQmx_Val_GroupByChannel,
                                voltages, daq.byref(n_written), None)
        return n_written.value

    def _positions_to_volts(self, positions):
        """Positions (n_axes x m) -> voltages (n_axes x m), including the corrections for a distorted scan. Voltages
        outside of the voltage range are clipped."""
        positions = np.atleast_2d(np.asarray(positions, dtype=float))
        volts = []
        for i, pos in enumerate(positions):
            (pmin, pmax), (vmin, vmax) = self._position_ranges[i], self._voltage_ranges[i]
            volts.append((vmax - vmin) / (pmax - pmin) * (pos - pmin) + vmin)
        volts = self._scale_and_rotation_correction(np.asarray(volts))
        for i, v in enumerate(volts):
            vmin, vmax = self._voltage_ranges[i]
            if v.min() < min(vmin, vmax) or v.max() > max(vmin, vmax):
                self.log.warning('Voltages ({:.3f}, {:.3f}) exceed the limit of axis {}, clipped.'.format(
                    v.min(), v.max(), i))
                volts[i] = np.clip(v, min(vmin, vmax), max(vmin, vmax))
        return np.ascontiguousarray(volts, dtype=np.float64)

    def _scale_and_rotation_correction(self, volts):
        """Rescaling / rotation when the scan is distorted (as in the legacy module, for any number of axes)."""
        n_axes, n_samples = volts.shape
        v = np.zeros((4, n_samples))
        v[:n_axes] = volts
        rot = lambda r: np.asarray([[np.cos(r), -np.sin(r), 0, 0], [np.sin(r), np.cos(r), 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]])
        scale = lambda a, b: np.asarray([[a, 0, 0, 0], [0, b, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]])
        c = self._corrections
        v = scale(c['x'], c['y']) @ v                                   # deformation in x/y
        v = rot(c['rotation']) @ v                                      # rotated image
        v = rot(-c['trapezoid']) @ scale(c['a'], c['b']) @ rot(c['trapezoid']) @ v   # trapezoid deformation
        return v[:n_axes].copy()

    def _set_position(self, position) -> None:
        """Write a position (array, one value per axis) to the analog outputs right now."""
        with self._ao_lock:
            self._write_scanner_ao(self._positions_to_volts(np.vstack(position)), length=1, start=True)
            self._current_position = np.array(position, dtype=float)

    def _ramp_to(self, new_position, stop_event=None) -> None:
        """Move to a position in a short linear ramp, so that galvos and piezos are not kicked."""
        new_position = np.asarray(new_position, dtype=float)
        start = self._current_position.copy()
        ranges = np.array([[ax.max_value - ax.min_value] for ax in self._axes.values()]).ravel()
        fraction = float(np.max(np.abs(new_position - start) / np.where(ranges == 0, 1.0, ranges)))
        duration = fraction * float(self._ramp_time_full_range)
        n_steps = max(2, int(duration / 0.002)) if fraction > 0 else 1
        for step in range(1, n_steps + 1):
            if stop_event is not None and stop_event.is_set():
                break
            self._set_position(start + (new_position - start) * step / n_steps)
            if n_steps > 1:
                time.sleep(duration / n_steps)

    # ----------------------------------------------------------------------------------------------------------
    # scanning
    # ----------------------------------------------------------------------------------------------------------
    def _empty_retrace_data(self):
        res = self._scan_data.scan_resolution
        back = max(int(self._backwards_line_resolution), 1)
        shape = (back,) if len(res) == 1 else (back, res[1])
        return {ch.name: np.full(shape, np.nan, dtype=ch.dtype) for ch in self._channels}

    def _line_path(self, axes, start_position, fast_values, slow_value=None):
        """Positions of a line: array (n_axes x m); the axes that are not scanned stay where they were."""
        path = np.tile(np.asarray(start_position, dtype=float)[:, None], (1, len(fast_values)))
        names = list(self._axes)
        path[names.index(axes[0]), :] = fast_values
        if slow_value is not None:
            path[names.index(axes[1]), :] = slow_value
        return path

    def _scan_worker(self, stop_event, settings, start_position, back_resolution) -> None:
        """Scans line by line (forward and backward). Finishes by unlocking the module state."""
        axes = settings['axes']
        try:
            self._set_up_scan_hardware(settings['frequency'])
            (r0_start, r0_stop) = settings['range'][0]
            res0 = settings['resolution'][0]
            back_res = max(int(back_resolution), 2)
            fast = np.linspace(r0_start, r0_stop, res0)
            fast_back = np.linspace(r0_stop, r0_start, back_res)
            slow_values = [None]
            if len(axes) == 2:
                (r1_start, r1_stop) = settings['range'][1]
                slow_values = list(np.linspace(r1_start, r1_stop, settings['resolution'][1]))

            for j, slow in enumerate(slow_values):
                if stop_event.is_set():
                    return
                path = self._line_path(axes, start_position, fast, slow)
                self._ramp_to(path[:, 0], stop_event)
                data = self._scan_line(path, pixel_clock=self._output_pixel_clock)
                print("data hardware")
                print(data)
                if stop_event.is_set():
                    return
                if data is None:
                    raise RuntimeError('Scanning a line failed.')
                path_back = self._line_path(axes, start_position, fast_back, slow)
                data_back = self._scan_line(path_back)
                if stop_event.is_set():
                    return
                if data_back is None:
                    raise RuntimeError('Scanning the backward line failed.')
                with self._data_lock:
                    for ci, ch in enumerate(self._channels):
                        if slow is None:
                            self._scan_data.data[ch.name][:] = data[:, ci]
                            self._scan_data.retrace_data[ch.name][:] = data_back[:, ci]
                        else:
                            self._scan_data.data[ch.name][:, j] = data[:, ci]
                            self._scan_data.retrace_data[ch.name][:, j] = data_back[:, ci]
        except Exception:
            if not stop_event.is_set():
                self.log.exception('Error during the scan.')
        finally:
            try:
                self._close_scan_hardware()
                self._ramp_to(start_position)      # back to where the scanner was before the scan
                self._target_position = np.array(start_position, dtype=float)
            except Exception:
                self.log.exception('Error while finishing the scan.')
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
            try:     # a line that is being scanned ends when its clock stops
                if self._scanner_clock_daq_task is not None:
                    daq.DAQmxStopTask(self._scanner_clock_daq_task)
            except Exception:
                pass
            thread.join(timeout=10.0)
        self._scan_thread = None
        self._scan_stop_event = None

    # --- hardware: clock, counters, analog inputs (the scanner part of the legacy module) ---
    def _set_up_scan_hardware(self, frequency: float) -> None:
        self._scanner_clock_frequency = float(frequency)
        self._set_up_scanner_clock()
        self._set_up_scanner_counters()

    def _set_up_scanner_clock(self) -> None:
        """Configures the hardware clock that gives the timing of the scan."""
        if self._scanner_clock_daq_task is not None:
            self.log.warning('A scanner clock is still running, closing it.')
            self._close_scanner_clock()
        task = daq.TaskHandle()
        daq.DAQmxCreateTask('ScannerClock', daq.byref(task))
        self._scanner_clock_daq_task = task
        daq.DAQmxCreateCOPulseChanFreq(
            task,
            self._scanner_clock_channel,
            'Clock Producer',
            daq.DAQmx_Val_Hz,
            daq.DAQmx_Val_Low,          # idle state
            0,                          # initial delay
            self._scanner_clock_frequency,
            0.5)                        # duty cycle: high and low are both one count interval
        daq.DAQmxCfgImplicitTiming(task, daq.DAQmx_Val_ContSamps, 1000)

    def _set_up_scanner_counters(self) -> None:
        """Connects the scanner clock with one counting task per photon source (gated counting) and, if
        configured, with an analog input task."""
        self._scanner_counter_daq_tasks = []
        for i, ch in enumerate(self._scanner_counter_channels):
            task = daq.TaskHandle()
            daq.DAQmxCreateTask('ScannerCounter{0}'.format(i), daq.byref(task))
            self._scanner_counter_daq_tasks.append(task)
            # width of each pulse (high and low) of the scanner clock, measured in photon ticks
            daq.DAQmxCreateCISemiPeriodChan(task, ch, 'Scanner Counter Channel {0}'.format(i), 0,
                                            self._max_counts / self._scanner_clock_frequency,
                                            daq.DAQmx_Val_Ticks, '')
            daq.DAQmxSetCISemiPeriodTerm(task, ch, self._scanner_clock_channel + 'InternalOutput')
            daq.DAQmxSetCICtrTimebaseSrc(task, ch, self._photon_sources[i])
        if self._scanner_ai_channels:
            atask = daq.TaskHandle()
            daq.DAQmxCreateTask('ScanAnalogIn', daq.byref(atask))
            self._scanner_analog_daq_task = atask
            daq.DAQmxCreateAIVoltageChan(atask, ', '.join(self._scanner_ai_channels), 'Scan Analog In',
                                         daq.DAQmx_Val_RSE, self._counter_voltage_range[0],
                                         self._counter_voltage_range[1], daq.DAQmx_Val_Volts, '')

    def _set_up_line(self, length: int) -> None:
        """Connects the timing of the analog output with the counting for a line of 'length' pixels."""
        self._line_length = int(length)
        daq.DAQmxCfgSampClkTiming(self._scanner_ao_task, self._scanner_clock_channel + 'InternalOutput',
                                  self._scanner_clock_frequency, daq.DAQmx_Val_Rising, daq.DAQmx_Val_FiniteSamps,
                                  self._line_length)
        daq.DAQmxCfgImplicitTiming(self._scanner_clock_daq_task, daq.DAQmx_Val_FiniteSamps, self._line_length + 1)
        for task in self._scanner_counter_daq_tasks:
            # count twice for each voltage (high and low of the clock) +1 for safety
            daq.DAQmxCfgImplicitTiming(task, daq.DAQmx_Val_FiniteSamps, 2 * self._line_length + 1)
            daq.DAQmxSetReadRelativeTo(task, daq.DAQmx_Val_CurrReadPos)
            daq.DAQmxSetReadOffset(task, 1)          # do not read the first sample
            daq.DAQmxSetReadOverWrite(task, daq.DAQmx_Val_DoNotOverwriteUnreadSamps)
        if self._scanner_ai_channels:
            daq.DAQmxCfgSampClkTiming(self._scanner_analog_daq_task, self._scanner_clock_channel + 'InternalOutput',
                                      self._scanner_clock_frequency, daq.DAQmx_Val_Rising, daq.DAQmx_Val_ContSamps,
                                      self._line_length + 1)

    def _scan_line(self, line_path, pixel_clock=False):
        """
        Scans a line: the analog outputs follow the path with the scanner clock while the counters (and analog
        inputs) record.

        @param float[n_axes][m] line_path: positions of the m pixels
        @return float[m][n_channels]: counts per second (counters) and volts (analog inputs); None on error
        """
        line_path = np.asarray(line_path, dtype=float)
        n_pixels = line_path.shape[1]
        try:
            with self._ao_lock:
                # the analog output is clocked by the scanner clock
                daq.DAQmxSetSampTimingType(self._scanner_ao_task, daq.DAQmx_Val_SampClk)
                self._set_up_line(n_pixels)
                written = self._write_scanner_ao(self._positions_to_volts(line_path), length=self._line_length,
                                                 start=False)
                if written != self._line_length:
                    raise RuntimeError('Only {} of {} voltages were written.'.format(written, self._line_length))
                daq.DAQmxStartTask(self._scanner_ao_task)

                for task in self._scanner_counter_daq_tasks:
                    daq.DAQmxStopTask(task)
                daq.DAQmxStopTask(self._scanner_clock_daq_task)

                if pixel_clock and self._pixel_clock_channel is not None:
                    daq.DAQmxConnectTerms(self._scanner_clock_channel + 'InternalOutput', self._pixel_clock_channel,
                                          daq.DAQmx_Val_DoNotInvertPolarity)

                # start the counters first, then the clock that triggers everything
                for task in self._scanner_counter_daq_tasks:
                    daq.DAQmxStartTask(task)
                if self._scanner_ai_channels:
                    daq.DAQmxStartTask(self._scanner_analog_daq_task)
                daq.DAQmxStartTask(self._scanner_clock_daq_task)

                timeout = self._RWTimeout * 2 * self._line_length
                for task in self._scanner_counter_daq_tasks:
                    daq.DAQmxWaitUntilTaskDone(task, timeout)
                daq.DAQmxWaitUntilTaskDone(self._scanner_clock_daq_task, timeout)

                n_counters = len(self._scanner_counter_channels)
                counts = np.empty((n_counters, 2 * self._line_length), dtype=np.uint32)
                n_read = daq.int32()
                for i, task in enumerate(self._scanner_counter_daq_tasks):
                    daq.DAQmxReadCounterU32(task, 2 * self._line_length, self._RWTimeout, counts[i],
                                            2 * self._line_length, daq.byref(n_read), None)
                    daq.DAQmxStopTask(task)

                analog = None
                if self._scanner_ai_channels:
                    analog = np.full((len(self._scanner_ai_channels), self._line_length + 1), np.nan,
                                     dtype=np.float64)
                    n_read_analog = daq.int32()
                    daq.DAQmxReadAnalogF64(self._scanner_analog_daq_task, self._line_length + 1, self._RWTimeout,
                                           daq.DAQmx_Val_GroupByChannel, analog,
                                           len(self._scanner_ai_channels) * (self._line_length + 1),
                                           daq.byref(n_read_analog), None)
                    daq.DAQmxStopTask(self._scanner_analog_daq_task)

                daq.DAQmxStopTask(self._scanner_clock_daq_task)
                self._stop_analog_output()
                if pixel_clock and self._pixel_clock_channel is not None:
                    daq.DAQmxDisconnectTerms(self._scanner_clock_channel + 'InternalOutput', self._pixel_clock_channel)

                # add up the two samples of a pixel (high and low time of the clock), counts -> counts/s
                all_data = np.full((n_counters + len(self._scanner_ai_channels), self._line_length), np.nan,
                                   dtype=np.float64)
                if n_counters:
                    summed = counts[:, ::2].astype(np.float64) + counts[:, 1::2]
                    all_data[:n_counters] = summed * self._scanner_clock_frequency
                if analog is not None:
                    all_data[n_counters:] = analog[:, :-1]
                self._current_position = np.array(line_path[:, -1])
        except Exception:
            self.log.exception('Error while scanning line.')
            try:
                self._stop_analog_output()
            except Exception:
                pass
            return None
        return all_data.T

    def _close_scanner_clock(self) -> int:
        task, self._scanner_clock_daq_task = self._scanner_clock_daq_task, None
        if task is None:
            return 0
        try:
            daq.DAQmxStopTask(task)
            daq.DAQmxClearTask(task)
        except Exception:
            self.log.exception('Could not close the scanner clock.')
            return -1
        return 0

    def _close_scan_hardware(self) -> int:
        """Closes the counters, the analog inputs and the scanner clock; the analog outputs stay on."""
        error = 0
        for task in self._scanner_counter_daq_tasks:
            try:
                daq.DAQmxStopTask(task)
                daq.DAQmxClearTask(task)
            except Exception:
                self.log.exception('Could not close scanner counter.')
                error = -1
        self._scanner_counter_daq_tasks = []
        if self._scanner_analog_daq_task is not None:
            try:
                daq.DAQmxStopTask(self._scanner_analog_daq_task)
                daq.DAQmxClearTask(self._scanner_analog_daq_task)
            except Exception:
                self.log.exception('Could not close the analog inputs.')
                error = -1
            self._scanner_analog_daq_task = None
        error = min(error, self._close_scanner_clock())
        self._stop_analog_output()
        return error

    def reset_hardware(self) -> int:
        """Resets the NI device(s) so that the connection is lost and other programs can access it."""
        self.log.info('Resetting the NI device.')
        retval = 0
        channels = [self._scanner_clock_channel] + list(self._scanner_ao_channels) + list(self._photon_sources) + \
            list(self._scanner_counter_channels)
        devices = []
        for channel in channels:
            if channel is None:
                continue
            match = re.match(r'^/(?P<dev>[0-9A-Za-z\- ]+[0-9A-Za-z\-_ ]*)/(?P<chan>[0-9A-Za-z]+)', channel)
            if match:
                devices.append(match.group('dev'))
            else:
                self.log.error('Did not find device name in {0}.'.format(channel))
        for device in set(devices):
            try:
                daq.DAQmxResetDevice(device)
            except Exception:
                self.log.exception('Could not reset NI device {0}'.format(device))
                retval = -1
        return retval
    # # =================== SlowCounterInterface Commands ========================
    # def get_constraints(self):
    #     """ Get hardware limits of NI device.

    #     @return SlowCounterConstraints: constraints class for slow counter

    #     FIXME: ask hardware for limits when module is loaded
    #     """
    #     constraints = SlowCounterConstraints()
    #     constraints.max_detectors = 4
    #     constraints.min_count_frequency = 1e-3
    #     constraints.max_count_frequency = 10e9
    #     constraints.counting_mode = [CountingMode.CONTINUOUS]
    #     return constraints

    # def set_up_clock(self, clock_frequency=None, clock_channel=None, scanner=False, idle=False):
    #     """ Configures the hardware clock of the NiDAQ card to give the timing.

    #     @param float clock_frequency: if defined, this sets the frequency of
    #                                     the clock in Hz
    #     @param string clock_channel: if defined, this is the physical channel
    #                                     of the clock within the NI card.
    #     @param bool scanner: if set to True method will set up a clock function
    #                             for the scanner, otherwise a clock function for a
    #                             counter will be set.
    #     @param bool idle: set whether idle situation of the counter (where
    #                         counter is doing nothing) is defined as
    #                             True  = 'Voltage High/Rising Edge'
    #                             False = 'Voltage Low/Falling Edge'

    #     @return int: error code (0:OK, -1:error)
    #     """

    #     if not scanner and self._clock_daq_task is not None:
    #         print('Trying to close _clock_daq_task...', self._clock_daq_task)
    #         self.log.warning('Another counter clock is already running, close this one first. "_clock_daq_task"')
    #         #TODO: change warning back to error
    #         self.close_clock()
    #         return -1

    #     if scanner and self._scanner_clock_daq_task is not None:
    #         print('Trying to close _scanner_clock_daq_task...', self._scanner_clock_daq_task)
    #         self.log.warning('Another scanner clock is already running, close this one first."_scanner_clock_daq_task"')
    #         #TODO: change warning back to error
    #         self.close_clock()
    #         #self.close_scanner_clock()
    #         # Probably error was when calling method "close_clock", it should be "close_scanner_clock"
    #         return -1

    #     # Create handle for task, this task will generate pulse signal for
    #     # photon counting
    #     my_clock_daq_task = daq.TaskHandle()

    #     # assign the clock frequency, if given
    #     if clock_frequency is not None:
    #         if not scanner:
    #             self._clock_frequency = float(clock_frequency)
    #         else:
    #             self._scanner_clock_frequency = float(clock_frequency)
    #     else:
    #         if not scanner:
    #             self._clock_frequency = self._default_clock_frequency
    #         else:
    #             self._scanner_clock_frequency = self._default_scanner_clock_frequency

    #     # use the correct clock in this method
    #     if scanner:
    #         my_clock_frequency = self._scanner_clock_frequency * 2
    #     else:
    #         my_clock_frequency = self._clock_frequency * 2

    #     # assign the clock channel, if given
    #     if clock_channel is not None:
    #         if not scanner:
    #             self._clock_channel = clock_channel
    #         else:
    #             self._scanner_clock_channel = clock_channel

    #     # use the correct clock channel in this method
    #     if scanner:
    #         my_clock_channel = self._scanner_clock_channel
    #     else:
    #         my_clock_channel = self._clock_channel

    #     # check whether only one clock pair is available, since some NI cards
    #     # only one clock channel pair.
    #     if self._scanner_clock_channel == self._clock_channel:
    #         if not ((self._clock_daq_task is None) and (self._scanner_clock_daq_task is None)):
    #             self.log.error(
    #                 'Only one clock channel is available!\n'
    #                 'Another clock is already running, close this one first '
    #                 'in order to use it for your purpose!')
    #             return -1

    #     # Adjust the idle state if necessary
    #     my_idle = daq.DAQmx_Val_High if idle else daq.DAQmx_Val_Low
    #     try:

    #         # create task for clock
    #         task_name = 'ScannerClock' if scanner else 'CounterClock'
    #         daq.DAQmxCreateTask(task_name, daq.byref(my_clock_daq_task))

    #         # create a digital clock channel with specific clock frequency:
    #         daq.DAQmxCreateCOPulseChanFreq(
    #             # The task to which to add the channels
    #             my_clock_daq_task,
    #             # which channel is used?
    #             my_clock_channel,
    #             # Name to assign to task (NIDAQ uses by # default the physical channel name as
    #             # the virtual channel name. If name is specified, then you must use the name
    #             # when you refer to that channel in other NIDAQ functions)
    #             'Clock Producer',
    #             # units, Hertz in our case
    #             daq.DAQmx_Val_Hz,
    #             # idle state
    #             my_idle,
    #             # initial delay
    #             0,
    #             # pulse frequency, divide by 2 such that length of semi period = count_interval
    #             my_clock_frequency / 2,
    #             # duty cycle of pulses, 0.5 such that high and low duration are both
    #             # equal to count_interval
    #             0.5)

    #         # Configure Implicit Timing.
    #         # Set timing to continuous, i.e. set only the number of samples to
    #         # acquire or generate without specifying timing:

    #         daq.DAQmxCfgImplicitTiming(
    #             # Define task
    #             my_clock_daq_task,
    #             # Sample Mode: set the task to generate a continuous amount of running samples
    #             daq.DAQmx_Val_ContSamps,
    #             # buffer length which stores temporarily the number of generated samples
    #             1000)

    #         if scanner:
    #             self._scanner_clock_daq_task = my_clock_daq_task
    #         else:
    #             # actually start the preconfigured clock task
    #             daq.DAQmxStartTask(my_clock_daq_task)
    #             self._clock_daq_task = my_clock_daq_task
    #     except:

    #         self.log.exception('Error while setting up clock.')
    #         return -1

    #     return 0

    # def set_up_counter(self,
    #                     counter_channels=None,
    #                     sources=None,
    #                     clock_channel=None,
    #                     counter_buffer=None):
    #     """ Configures the actual counter with a given clock.

    #     @param list(str) counter_channels: optional, physical channel of the counter
    #     @param list(str) sources: optional, physical channel where the photons
    #                                 are to count from
    #     @param str clock_channel: optional, specifies the clock channel for the
    #                                 counter
    #     @param int counter_buffer: optional, a buffer of specified integer
    #                                 length, where in each bin the count numbers
    #                                 are saved.

    #     @return int: error code (0:OK, -1:error)
    #     """

    #     if self._clock_daq_task is None and clock_channel is None:
    #         self.log.error('No clock running, call set_up_clock before starting the counter.')
    #         return -1

    #     if len(self._counter_daq_tasks) > 0:
    #         self.log.error('Another counter is already running, close this one first.')
    #         return -1

    #     my_counter_channels = counter_channels if counter_channels else self._counter_channels
    #     my_photon_sources = sources if sources else self._photon_sources
    #     my_clock_channel = clock_channel if clock_channel else self._clock_channel

    #     if len(my_photon_sources) < len(my_counter_channels):
    #         self.log.error('You have given {0} sources but {1} counting channels.'
    #                         'Please give an equal or greater number of sources.'
    #                         ''.format(len(my_photon_sources), len(my_counter_channels)))
    #         return -1

    #     try:

    #         for i, ch in enumerate(my_counter_channels):
    #             # This task will count photons with binning defined by the clock_channel
    #             task = daq.TaskHandle()  # Initialize a Task
    #             # Create task for the counter
    #             daq.DAQmxCreateTask('Counter{0}'.format(i), daq.byref(task))
    #             # Create a Counter Input which samples with Semi-Periodes the Channel.
    #             # set up semi period width measurement in photon ticks, i.e. the width
    #             # of each pulse (high and low) generated by pulse_out_task is measured
    #             # in photon ticks.
    #             #   (this task creates a channel to measure the time between state
    #             #    transitions of a digital signal and adds the channel to the task
    #             #    you choose)
    #             daq.DAQmxCreateCISemiPeriodChan(
    #                 # define to which task to connect this function
    #                 task,
    #                 # use this counter channel
    #                 ch,
    #                 # name to assign to it
    #                 'Counter Channel {0}'.format(i),
    #                 # expected minimum count value
    #                 0,
    #                 # Expected maximum count value
    #                 self._max_counts / 2 / self._clock_frequency,
    #                 # units of width measurement, here photon ticks
    #                 daq.DAQmx_Val_Ticks,
    #                 # empty extra argument
    #                 '')

    #             # Set the Counter Input to a Semi Period input Terminal.
    #             # Connect the pulses from the counter clock to the counter channel
    #             daq.DAQmxSetCISemiPeriodTerm(
    #                     # The task to which to add the counter channel.
    #                     task,
    #                     # use this counter channel
    #                     ch,
    #                     # assign a named Terminal
    #                     my_clock_channel + 'InternalOutput')

    #             # Set a Counter Input Control Timebase Source.
    #             # Specify the terminal of the timebase which is used for the counter:
    #             # Define the source of ticks for the counter as self._photon_source for
    #             # the Scanner Task.
    #             daq.DAQmxSetCICtrTimebaseSrc(
    #                 # define to which task to connect this function
    #                 task,
    #                 # counter channel
    #                 ch,
    #                 # counter channel to output the counting results
    #                 my_photon_sources[i])

    #             # Configure Implicit Timing.
    #             # Set timing to continuous, i.e. set only the number of samples to
    #             # acquire or generate without specifying timing:
    #             daq.DAQmxCfgImplicitTiming(
    #                 # define to which task to connect this function
    #                 task,
    #                 # Sample Mode: Acquire or generate samples until you stop the task.
    #                 daq.DAQmx_Val_ContSamps,
    #                 # buffer length which stores  temporarily the number of generated samples
    #                 1000)

    #             # Set the Read point Relative To an operation.
    #             # Specifies the point in the buffer at which to begin a read operation.
    #             # Here we read most recent recorded samples:
    #             daq.DAQmxSetReadRelativeTo(
    #                 # define to which task to connect this function
    #                 task,
    #                 # Start reading samples relative to the last sample returned by the previously.
    #                 daq.DAQmx_Val_CurrReadPos)

    #             # Set the Read Offset.
    #             # Specifies an offset in samples per channel at which to begin a read
    #             # operation. This offset is relative to the location you specify with
    #             # RelativeTo. Here we set the Offset to 0 for multiple samples:
    #             daq.DAQmxSetReadOffset(task, 0)

    #             # Set Read OverWrite Mode.
    #             # Specifies whether to overwrite samples in the buffer that you have
    #             # not yet read. Unread data in buffer will be overwritten:
    #             daq.DAQmxSetReadOverWrite(
    #                 task,
    #                 daq.DAQmx_Val_DoNotOverwriteUnreadSamps)
    #             # add task to counter task list
    #             self._counter_daq_tasks.append(task)

    #             # Counter analog input task
    #             if len(self._counter_ai_channels) > 0:
    #                 atask = daq.TaskHandle()

    #                 daq.DAQmxCreateTask('CounterAnalogIn', daq.byref(atask))

    #                 daq.DAQmxCreateAIVoltageChan(
    #                     atask,
    #                     ', '.join(self._counter_ai_channels),
    #                     'Counter Analog In',
    #                     daq.DAQmx_Val_RSE,
    #                     self._counter_voltage_range[0],
    #                     self._counter_voltage_range[1],
    #                     daq.DAQmx_Val_Volts,
    #                     ''
    #                 )
    #                 # Analog in channel timebase
    #                 daq.DAQmxCfgSampClkTiming(
    #                     atask,
    #                     my_clock_channel + 'InternalOutput',
    #                     self._clock_frequency,
    #                     daq.DAQmx_Val_Rising,
    #                     daq.DAQmx_Val_ContSamps,
    #                     int(self._clock_frequency * 5)
    #                 )
    #                 self._counter_analog_daq_task = atask
    #     except:

    #         self.log.exception('Error while setting up counting task.')
    #         return -1

    #     try:

    #         for i, task in enumerate(self._counter_daq_tasks):
    #             # Actually start the preconfigured counter task
    #             daq.DAQmxStartTask(task)
    #         if len(self._counter_ai_channels) > 0:
    #             daq.DAQmxStartTask(self._counter_analog_daq_task)
    #     except:

    #         self.log.exception('Error while starting Counter')
    #         try:
    #             self.close_counter()
    #         except:
    #             self.log.exception('Could not close counter after error')
    #         return -1
    #     return 0

    # def get_counter_channels(self):
    #     """ Returns the list of counter channel names.

    #     @return tuple(str): channel names

    #     Most methods calling this might just care about the number of channels, though.
    #     """
    #     ch = self._counter_channels[:]
    #     ch.extend(self._counter_ai_channels)
    #     return ch

    # def get_counter(self, samples=None):
    #     """ Returns the current counts per second of the counter.

    #     @param int samples: if defined, number of samples to read in one go.
    #                         How many samples are read per readout cycle. The
    #                         readout frequency was defined in the counter setup.
    #                         That sets also the length of the readout array.

    #     @return float [samples]: array with entries as photon counts per second
    #     """
    #     if len(self._counter_daq_tasks) < 1:
    #         self.log.error(
    #             'No counter running, call set_up_counter before reading it.')
    #         # in case of error return a lot of -1
    #         return np.ones((len(self.get_counter_channels()), samples), dtype=np.uint32) * -1

    #     if len(self._counter_ai_channels) > 0 and self._counter_analog_daq_task is None:
    #         self.log.error(
    #             'No counter analog input task running, call set_up_counter before reading it.')
    #         # in case of error return a lot of -1
    #         return np.ones((len(self.get_counter_channels()), samples), dtype=np.uint32) * -1

    #     if samples is None:
    #         samples = int(self._samples_number)
    #     else:
    #         samples = int(samples)
    #     try:
    #         # count data will be written here in the NumPy array of length samples
    #         count_data = np.empty((len(self._counter_daq_tasks), 2 * samples), dtype=np.uint32)

    #         # number of samples which were actually read, will be stored here
    #         n_read_samples = daq.int32()
    #         for i, task in enumerate(self._counter_daq_tasks):
    #             # read the counter value: This function is blocking and waits for the
    #             # counts to be all filled:
    #             daq.DAQmxReadCounterU32(
    #                 # read from this task
    #                 task,
    #                 # number of samples to read
    #                 2 * samples,
    #                 # maximal timeout for the read process
    #                 self._RWTimeout,
    #                 # write the readout into this array
    #                 count_data[i],
    #                 # length of array to write into
    #                 2 * samples,
    #                 # number of samples which were read
    #                 daq.byref(n_read_samples),
    #                 # Reserved for future use. Pass NULL (here None) to this parameter
    #                 None)

    #         # Analog channels
    #         if len(self._counter_ai_channels) > 0:
    #             analog_data = np.full(
    #                 (len(self._counter_ai_channels), samples), 111, dtype=np.float64)

    #             analog_read_samples = daq.int32()

    #             daq.DAQmxReadAnalogF64(
    #                 self._counter_analog_daq_task,
    #                 samples,
    #                 self._RWTimeout,
    #                 daq.DAQmx_Val_GroupByChannel,
    #                 analog_data,
    #                 len(self._counter_ai_channels) * samples,
    #                 daq.byref(analog_read_samples),
    #                 None
    #             )
    #     except:
    #         self.log.exception(
    #             'Getting samples from counter failed.')
    #         # in case of error return a lot of -1
    #         return np.ones((len(self.get_counter_channels()), samples), dtype=np.uint32) * -1

    #     real_data = np.empty((len(self._counter_channels), samples), dtype=np.uint32)

    #     # add up adjoint pixels to also get the counts from the low time of
    #     # the clock:
    #     real_data = count_data[:, ::2]
    #     real_data += count_data[:, 1::2]

    #     all_data = np.full((len(self.get_counter_channels()), samples), 222, dtype=np.float64)
    #     # normalize to counts per second for counter channels
    #     all_data[0:len(real_data)] = np.array(real_data * self._clock_frequency, np.float64)

    #     if len(self._counter_ai_channels) > 0:
    #         all_data[-len(self._counter_ai_channels):] = analog_data

    #     return all_data

    # def close_counter(self, scanner=False):
    #     """ Closes the counter or scanner and cleans up afterwards.

    #     @param bool scanner: specifies if the counter- or scanner- function
    #                             will be excecuted to close the device.
    #                             True = scanner
    #                             False = counter

    #     @return int: error code (0:OK, -1:error)
    #     """
    #     error = 0
    #     if scanner:
    #         for i, task in enumerate(self._scanner_counter_daq_tasks):
    #             try:
    #                 # stop the counter task
    #                 daq.DAQmxStopTask(task)
    #                 # after stopping delete all the configuration of the counter
    #                 daq.DAQmxClearTask(task)
    #             except:
    #                 self.log.exception('Could not close scanner counter.')
    #                 error = -1
    #         self._scanner_counter_daq_tasks = []
    #     else:
    #         for i, task in enumerate(self._counter_daq_tasks):
    #             try:
    #                 # stop the counter task
    #                 daq.DAQmxStopTask(task)
    #                 # after stopping delete all the configuration of the counter
    #                 daq.DAQmxClearTask(task)
    #                 # set the task handle to None as a safety
    #             except:
    #                 self.log.exception('Could not close counter.')
    #                 error = -1
    #         self._counter_daq_tasks = []

    #         if len(self._counter_ai_channels) > 0:
    #             try:
    #                 # stop the counter task
    #                 daq.DAQmxStopTask(self._counter_analog_daq_task)
    #                 # after stopping delete all the configuration of the counter
    #                 daq.DAQmxClearTask(self._counter_analog_daq_task)
    #                 # set the task handle to None as a safety
    #             except:
    #                 self.log.exception('Could not close counter analog channels.')
    #                 error = -1
    #             self._counter_analog_daq_task = None
    #     return error

    # def close_clock(self, scanner=False):
    #     """ Closes the clock and cleans up afterwards.

    #     @param bool scanner: specifies if the counter- or scanner- function
    #                             should be used to close the device.
    #                             True = scanner
    #                             False = counter

    #     @return int: error code (0:OK, -1:error)
    #     """
    #     if scanner:
    #         my_task = self._scanner_clock_daq_task
    #     else:
    #         my_task = self._clock_daq_task

    #     try:
    #         # Stop the clock task:

    #         # system = nidaqmx.system.System.local()  # load local system
    #         # task_names = system.tasks.task_names  # returns a list of task names
    #         # print(task_names)
    #         self.tusk.append(my_task)
    #         self.cter+=1
    #         self.index.append(self.cter)
    #         if not my_task==None: #sometimes mytask is none which generates an error
    #             self.ret_val.append(daq.DAQmxStopTask(my_task))
    #             daq.DAQmxClearTask(my_task)
                
    #         self.index=self.index[:-1]
            
            

    #         # Found in pydaq documentation:
    #         #DAQmxClearTask() is automatically called when a Task instance is garbage collected, obviating the need to clean up manually.
    #         # After stopping delete all the configuration of the clock:
            
            
    #         # Set the task handle to None as a safety
    #         if scanner:
    #             self._scanner_clock_daq_task = None
    #         else:
    #             self._clock_daq_task = None
    #     except:

    #         print("My task: ", my_task)
    #         self.log.exception('Could not close clock.')
    #         return -1
    #         # https://knowledge.ni.com/KnowledgeArticleDetails?id=kA00Z0000004AE6SAM
    #         # 1. If the DAQmx task is successfully initialised and started, but this error occurs
    #         # when trying to read or write samples, this indicates that an empty task handle has
    #         # been connected to the DAQmx Read or DAQmx Write VI. 
    #             # Check the logic of the program to ensure that the initialisation state is not being
    #             # skipped, or that the task is not being cleared prior to the read/write
            
    #     return 0


class NationalInstrumentsXSeries(CoordinateTransformMixin, _NationalInstrumentsXSeriesBase):
    """ NI X series scanner with support for the tilt correction (coordinate transformation). """
    pass
