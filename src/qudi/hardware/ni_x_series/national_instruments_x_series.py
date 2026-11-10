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
        max_scan_frequency: 1000                    # optional, Hz; default: default_scanner_clock_frequency
        scan_debug: False                           # True: print the raw counter data of every line
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
    # maximum scan frequency in Hz. The scan logic starts with the maximum frequency of an axis, so if it is not given
    # default_scanner_clock_frequency is used (as the legacy module did), to start with a slow, safe scan.
    _max_scan_frequency = ConfigOption('max_scan_frequency', None, missing='nothing')
    _scan_debug = ConfigOption('scan_debug', False, missing='nothing')      # print the raw counter data of every line
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
        self._scanner_ai_channels = self._scanner_ai_channels or list()
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
                                           frequency_range=(0.0, self._scan_frequency_limit()))
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

    def _scan_frequency_limit(self) -> float:
        value = self._max_scan_frequency if self._max_scan_frequency is not None else self._default_scanner_clock_frequency
        return float(value)

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
            if self._scan_debug:
                print('NI scanner: starting scan with {}'.format(settings))
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
                    if self._scan_debug:
                        print('NI scanner line: {} pixels at {:g} Hz, {} samples read per counter; raw counts per clock '
                              'half period: min {} max {} sum {}; counts/s per pixel: mean {:.4g} max {:.4g}'.format(
                                  self._line_length, self._scanner_clock_frequency, n_read.value, counts.min(),
                                  counts.max(), int(counts.sum()), all_data[:n_counters].mean(),
                                  all_data[:n_counters].max()))
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


class NationalInstrumentsXSeries(CoordinateTransformMixin, _NationalInstrumentsXSeriesBase):
    """ NI X series scanner with support for the tilt correction (coordinate transformation). """
    pass