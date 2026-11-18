# -*- coding: utf-8 -*-

"""
Interfuse that combines an NI analog output (piezo mirror / galvo voltages, with pixel clock output) and the Time Tagger
(photon counting) to a scanner for the ScanningProbeInterface (scanning_probe_logic, scanner GUI, optimizer).

Why: the newest Time Tagger software has no GP0 channel any more, which was connected to the NI card to count the
photons while the card scanned the voltages. Now the NI card only scans and gives out the pixel clock, and the Time
Tagger counts the photons between two pixel clock edges.

Wiring:   NI pixel_clock_channel (e.g. /Dev1/PFI6)  ->  Time Tagger input <begin_channel>
          detector(s)                               ->  Time Tagger inputs <click_channels>

How a line is scanned
---------------------
For every line the interfuse
  1. arms the Time Tagger: one CountBetweenMarkers per click channel, bins between two successive pixel clock edges
     (begin_channel only, no end channel), n_values = forward pixels + backward pixels,
  2. starts the NI waveform: the forward line followed by the backward line (retrace). The i-th voltage is output with the
     i-th pixel clock edge, so the counts of bin i belong to pixel i. The NI card outputs n + 1 clock pulses, which close
     the last bin,
  3. waits until the Time Tagger has filled all bins (if the pixel clock does not arrive, the scan stops with an error
     that names the channel), converts counts to counts/s (counts * pixel frequency) and fills the scan data line.
During the backward line the slow axis moves to the next line, so the scan runs without jumps. At the end the scanner
goes back to where it was before the scan. The module state is 'locked' during the scan and 'idle' afterwards.

The time tagger module itself is not changed: only count_between_markers(click_channel, begin_channel, end_channel,
n_values) of it is used. Set the trigger level of the begin channel in the channels_params of the Time Tagger config.

Example config:

scanner:
    module.Class: 'interfuse.time_tagger_voltage_scanner_interfuse.TimeTaggerScanningProbeInterfuse'
    connect:
        tt: 'timetagger'
        triggered_ao: 'nicard_6323'
    options:
        position_ranges:                  # axes of the analog output channels (x, y, z, a) that are scanned / moved
            x: [-104.86e-6, 104.86e-6]
            y: [-104.86e-6, 104.86e-6]
            z: [0, 15e-6]
        click_channels:                   # name of the data channel: Time Tagger channel of the detector
            APD1: 1
            APD2: 2
        begin_channel: 5                  # Time Tagger channel that sees the NI pixel clock
        sum_channels: [APD1, APD2]        # optional: adds the data channel 'sum'
        frequency_ranges:                 # optional, pixel frequency in Hz (default 0 ... max of the NI card)
            x: [1, 1000]
        resolution_ranges:                # optional (default 1 ... 10000)
            x: [1, 1000]
        units:                            # optional (default m for x, y, z and V for a)
            z: 'm'
        backwards_line_resolution: 50     # optional, points of the backward line
        ramp_time_full_range: 0.1         # optional, s for a move over the full range of an axis
        timeout_margin: 5                 # optional, s that a line may take longer than expected
"""

import threading
import time
from collections import OrderedDict
from typing import Dict
from PySide6 import QtCore

import numpy as np

from qudi.core.configoption import ConfigOption
from qudi.core.connector import Connector
from qudi.interface.scanning_probe_interface import (ScanningProbeInterface, ScanConstraints, ScannerAxis,
                                                     ScannerChannel, ScanData, CoordinateTransformMixin)

DEFAULT_UNITS = {'x': 'm', 'y': 'm', 'z': 'm', 'a': 'V'}


class _TimeTaggerScanningProbeInterfuseBase(ScanningProbeInterface):
    """ NI analog output with pixel clock + Time Tagger as scanner. See the module docstring. """

    # connectors: the time tagger module (class TT) and the analog output with pixel clock
    tt = Connector(name='tt', interface='TT')
    triggered_ao = Connector(name='triggered_ao', interface='NationalInstrumentsXSeries')
    #triggered_ao = Connector(name='triggered_ao', interface='TriggeredAnalogOutputInterface')

    _frequency_ranges = ConfigOption(name='frequency_ranges', default=None, missing='nothing')
    _resolution_ranges = ConfigOption(name='resolution_ranges', default=None, missing='nothing')
    _units = ConfigOption(name='units', default=None, missing='nothing')
    _click_channels = ConfigOption(name='click_channels', missing='error')
    _begin_channel = ConfigOption(name='begin_channel', missing='error')
    _sum_channels = ConfigOption(name='sum_channels', default=None, missing='nothing')
    _initial_backwards_line_resolution = ConfigOption(name='backwards_line_resolution', default=50, missing='nothing')
    _ramp_time_full_range = ConfigOption(name='ramp_time_full_range', default=0.1, missing='nothing')
    _timeout_margin = ConfigOption(name='timeout_margin', default=5.0, missing='nothing')
    
    sigChangeTemperatureRegime = QtCore.Signal(bool)
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._data_lock = threading.RLock()
        self._state_lock = threading.RLock()
        self._ao = None
        self._tagger = None
        self._axes: 'OrderedDict[str, ScannerAxis]' = OrderedDict()
        self._channels = []
        self._constraints = None
        #self._voltage_ranges: Dict[str, tuple] = {}
        # self._target = {}
        self._target = []
        self._scan_data = None
        self._scan_settings = None
        self._scan_thread = None
        self._scan_stop_event = None

    # ----------------------------------------------------------------------------------------------------------
    # qudi module
    # ----------------------------------------------------------------------------------------------------------
    def on_activate(self):
        self._ao = self.triggered_ao()
        self._tagger = self.tt()
        self._backwards_line_resolution = int(self._initial_backwards_line_resolution)
        self._constraints = self._ao.get_constraints()
        # self._voltage_ranges = dict(constraints.voltage_ranges)
        # self._position_ranges = dict(constraints.position_ranges)

        # unknown = [ax for ax in self._position_ranges if ax not in constraints.channel_names]
        # if unknown:
        #     raise ValueError('position_ranges has the axes {}, but the analog output only has the channels {}.'.format(
        #         unknown, constraints.channel_names))
        sum_channels = list(self._sum_channels or [])
        missing = [name for name in sum_channels if name not in self._click_channels]
        if missing:
            raise ValueError('sum_channels {} are not in click_channels {}.'.format(missing, list(self._click_channels)))

        #self._axes = constraints.axes
        # self._axes = OrderedDict()
        # for name in constraints.channel_names:
        # #    if name not in self._position_ranges:
        # #        continue
        #     print(constraints.axes[name].value_range)
        #     print(constraints.axes[name].min_value)
        #     print("___________________")
        #     prange = self._ao._position_ranges[name]
        #     fr = (self._frequency_ranges or {}).get(name, [0.0, constraints.max_sample_rate])
        #     rr = (self._resolution_ranges or {}).get(name, [1, 10000])
        #     unit = (self._units or {}).get(name, DEFAULT_UNITS.get(name, 'm'))
        #     self._axes[name] = ScannerAxis(name=name, unit=unit,
        #                                    value_range=constraints.axes[name].value_range,
        #                                    step_range=constraints.axes[name].step_range,
        #                                    resolution_range=(int(rr[0]), int(rr[1])),
        #                                    frequency_range=(float(fr[0]), float(min(fr[1], constraints.max_sample_rate))))
        names = list(self._click_channels) + (['sum'] if sum_channels else [])
        self._channels = [ScannerChannel(name=name, unit='c/s', dtype=np.float64) for name in names]
        # self._constraints = ScanConstraints(axes=list(self._axes.values()), channels=list(self._channels),
        #                                     backscan_configurable=True, has_position_feedback=False,
        #                                     square_px_only=False)
        self._target = self._ao._current_position
        #self._target = self._position_from_voltages()

        self.sigChangeTemperatureRegime.connect(self._ao.set_temperature_regime) # FIXME

    def on_deactivate(self):
        try:
            self.sigChangeTemperatureRegime.disconnect(self._ao.set_temperature_regime)
        except Exception:
            pass
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
        return None

    def reset(self):
        """Stop the scan and reset the NI card. The analog outputs are at 0 V afterwards."""
        self.stop_scan()
        self._ao.reset()
        self._target = self._ao._current_position
        #self._target = self._position_from_voltages()

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
            self._scan_data = ScanData(channels=list(self._channels), scan_axes=axes, scan_range=ranges,
                                       scan_resolution=resolution, scan_frequency=frequency,
                                       target_at_start=self.get_target(), position_feedback_axes=None)
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
        back_resolution = self._back_resolution()
        with self._data_lock:
            self._scan_data.new_scan()
            self._scan_data.retrace_data = self._empty_retrace_data(back_resolution)
        self._scan_stop_event = threading.Event()
        self._scan_thread = threading.Thread(
            target=self._scan_worker,
            args=(self._scan_stop_event, dict(self._scan_settings), dict(self._target), back_resolution),
            name='tt_voltage_scanner_scan', daemon=True)
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
        print("MOVE ABSOLUTE")
        print(self._axes)
        print(ax.name for ax in self._axes)
        unknown = [name for name in position if name not in self._axes]
        print(unknown)
        if unknown:
            self.log.error('Unknown scanner axes {}, available are {}'.format(unknown, list(self._axes)))
            return self.get_target()
        new_target = dict(self._target)
        for name, value in position.items():
            clipped = self._axes[name].clip_value(float(value))
            if clipped != float(value):
                self.log.warning('Position {:.3e} of axis {} is out of range, clipped to {:.3e}.'.format(
                    float(value), name, clipped))
            new_target[name] = clipped
        fraction = max((abs(new_target[n] - self._target[n]) / self._axis_span(n) for n in position), default=0.0)
        try:
            self._ao.set_voltages({n: self._to_voltage(n, new_target[n]) for n in position},
                                  ramp_time=fraction * float(self._ramp_time_full_range))
            self._target = new_target
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
        target_dict = dict(zip(['x','y','z','a'], self._target))
        print(target_dict)
        return target_dict
        # return dict(self._target)

    def get_position(self):
        """No position feedback: the position is the target."""
        return dict(self._target)

    # ----------------------------------------------------------------------------------------------------------
    # positions <-> voltages
    # ----------------------------------------------------------------------------------------------------------
    def _axis_span(self, name):
        ax = self._axes[name]
        return (ax.max_value - ax.min_value) or 1.0

    def _to_voltage(self, name, position):
        """Position(s) -> voltage(s): the position range is mapped linearly onto the voltage range of the channel."""
        ax = self._axes[name]
        vmin, vmax = self._voltage_ranges[name]
        return vmin + (np.asarray(position, dtype=float) - ax.min_value) / (ax.max_value - ax.min_value) * (vmax - vmin)

    def _position_from_voltages(self):
        voltages = self._ao.get_voltages()
        position = {}
        for name, ax in self._axes.items():
            vmin, vmax = self._voltage_ranges[name]
            position[name] = ax.clip_value(ax.min_value + (voltages[name] - vmin) / (vmax - vmin) *
                                           (ax.max_value - ax.min_value))
        return position

    # ----------------------------------------------------------------------------------------------------------
    # scanning
    # ----------------------------------------------------------------------------------------------------------
    def _back_resolution(self):
        return max(int(self._backwards_line_resolution), 2)

    def _empty_retrace_data(self, back_resolution):
        res = self._scan_data.scan_resolution
        shape = (back_resolution,) if len(res) == 1 else (back_resolution, res[1])
        return {ch.name: np.full(shape, np.nan, dtype=ch.dtype) for ch in self._channels}

    def _arm_counters(self, n_values):
        """One CountBetweenMarkers per detector. They count between successive pixel clock edges."""
        return {name: self._tagger.count_between_markers(click_channel=channel, begin_channel=self._begin_channel,
                                                         end_channel=None, n_values=n_values)
                for name, channel in self._click_channels.items()}

    @staticmethod
    def _dispose(counters):
        for counter in (counters or {}).values():
            try:
                counter.stop()
            except Exception:
                pass

    def _wait_for_line(self, counters, line_time, stop_event):
        """Wait until all counters have all their bins. @return bool: True if they have, False if stopped"""
        deadline = time.time() + line_time + float(self._timeout_margin)
        while not all(counter.ready() for counter in counters.values()):
            if stop_event.is_set():
                return False
            if time.time() > deadline:
                raise RuntimeError(
                    'The Time Tagger did not receive the pixel clock within {:.1f} s: check the cable from the NI '
                    'pixel_clock_channel to Time Tagger channel {} and its trigger level.'.format(
                        line_time + float(self._timeout_margin), self._begin_channel))
            time.sleep(0.002)
        return True

    def _scan_worker(self, stop_event, settings, start_target, back_resolution):
        axes = settings['axes']
        frequency = settings['frequency']
        counters = None
        try:
            (r0_start, r0_stop) = settings['range'][0]
            n_fast = settings['resolution'][0]
            fast_forward = np.linspace(r0_start, r0_stop, n_fast)
            fast_backward = np.linspace(r0_stop, r0_start, back_resolution)
            if len(axes) == 2:
                (r1_start, r1_stop) = settings['range'][1]
                slow = np.linspace(r1_start, r1_stop, settings['resolution'][1])
            else:
                slow = [None]
            n_bins = n_fast + back_resolution

            # go to the start of the first line
            first = dict(start_target)
            first[axes[0]] = r0_start
            if len(axes) == 2:
                first[axes[1]] = slow[0]
            self._ramp_to(start_target, first, stop_event)

            for j, slow_value in enumerate(slow):
                if stop_event.is_set():
                    return
                waveforms = {axes[0]: self._to_voltage(axes[0], np.concatenate([fast_forward, fast_backward]))}
                if slow_value is not None:
                    # the slow axis stays during the forward line and moves to the next line during the backward line
                    next_value = slow[j + 1] if j + 1 < len(slow) else slow_value
                    waveforms[axes[1]] = self._to_voltage(axes[1], np.concatenate([
                        np.full(n_fast, slow_value), np.linspace(slow_value, next_value, back_resolution)]))

                # the Time Tagger has to be armed before the pixel clock starts
                counters = self._arm_counters(n_bins)
                self._ao.start_waveform(waveforms, frequency)
                complete = self._wait_for_line(counters, (n_bins + 1) / frequency, stop_event)
                self._ao.wait_until_waveform_done(self._timeout_margin)
                if not complete:
                    return
                counts = {name: np.asarray(counter.getData(), dtype=float) * frequency   # counts per bin -> counts/s
                          for name, counter in counters.items()}
                self._dispose(counters)
                counters = None
                if 'sum' in [ch.name for ch in self._channels]:
                    counts['sum'] = sum(counts[name] for name in self._sum_channels)
                with self._data_lock:
                    for name, values in counts.items():
                        if slow_value is None:
                            self._scan_data.data[name][:] = values[:n_fast]
                            self._scan_data.retrace_data[name][:] = values[n_fast:]
                        else:
                            self._scan_data.data[name][:, j] = values[:n_fast]
                            self._scan_data.retrace_data[name][:, j] = values[n_fast:]
        except Exception:
            if not stop_event.is_set():
                self.log.exception('Error during the scan.')
        finally:
            self._dispose(counters)
            try:
                self._ao.stop_waveform()
                self._ramp_to(self._ao._current_position, start_target, None)   # back to where the scanner was
                # self._ramp_to(self._position_from_voltages(), start_target, None)   # back to where the scanner was
            except Exception:
                self.log.exception('Error while finishing the scan.')
            if not stop_event.is_set():
                # scan finished on its own: back to idle, the scan logic polls for this
                with self._state_lock:
                    if self.module_state() == 'locked':
                        self.module_state.unlock()

    def _ramp_to(self, current, new, stop_event):
        """Software timed move of all axes of 'new' from the position 'current' (voltages are set by the analog output)."""
        fraction = max((abs(new[n] - current[n]) / self._axis_span(n) for n in new if n in current), default=0.0)
        if stop_event is not None and stop_event.is_set():
            return
        self._ao.set_voltages({n: self._to_voltage(n, v) for n, v in new.items()},
                              ramp_time=fraction * float(self._ramp_time_full_range))

    def _stop_scan_thread(self):
        thread = self._scan_thread
        if self._scan_stop_event is not None:
            self._scan_stop_event.set()
        if thread is not None and thread is not threading.current_thread():
            try:                    # ends a line that is being scanned
                self._ao.stop_waveform()
            except Exception:
                pass
            thread.join(timeout=10.0)
        self._scan_thread = None
        self._scan_stop_event = None


class TimeTaggerScanningProbeInterfuse(CoordinateTransformMixin, _TimeTaggerScanningProbeInterfuseBase):
    """ NI analog output with pixel clock + Time Tagger as scanner, with support for the tilt correction. """
    pass
