# -*- coding: utf-8 -*-

"""
NI X series card as analog output with pixel clock output (TriggeredAnalogOutputInterface).

Adapted from national_instruments_x_series.py (scanner for the ScanningProbeInterface): everything that counted
photons on the card is gone. The card only moves the piezo / galvo (analog outputs) and gives out the pixel clock on a
PFI terminal, which is wired to a channel of the Time Tagger. The Time Tagger counts the photons between two edges.

!!!!!! NI USB 63XX, NI PCIe 63XX and NI PXIe 63XX DEVICES ONLY !!!!!!

How a waveform runs: a counter of the card generates the pixel clock (square wave, 50 % duty, n_samples + 1 pulses).
The analog output is clocked by it, so sample i is output with rising edge i. The same clock is routed to the
pixel_clock_channel terminal, where the Time Tagger sees it. Wiring: pixel_clock_channel -> Time Tagger input.

Example config (the options of the scanner module that are not needed here are accepted and ignored, so its config
block can be reused):

nicard_6323:
    module.Class: 'national_instruments_x_series.NiTriggeredAnalogOutput'
    options:
        scanner_clock_channel: '/Dev1/Ctr2'         # counter that generates the pixel clock
        pixel_clock_channel: '/Dev1/PFI6'           # terminal where the pixel clock is output -> Time Tagger input
        scanner_ao_channels:                        # 1 to 4 channels, named x, y, z, a
            - '/Dev1/AO0'
            - '/Dev1/AO1'
            - '/Dev1/AO2'
            - '/Dev1/AO3'
        scanner_voltage_ranges:
            - [-10, 10]
            - [-10, 10]
            - [0, 10]
            - [-10, 10]
        max_sample_rate: 1000                       # Hz, maximum pixel clock frequency
        trapezoid_rotation_correction: "np.pi/4"    # optional corrections of a distorted scan, as before
        rotation_correction: "np.pi/4"
        scaling_correction_a: "1"
        scaling_correction_b: "1/np.sqrt(2)"
        scaling_correction_x: "1"
        scaling_correction_y: "1"
        read_write_timeout: 10
"""

import re
import threading
import time
from typing import Dict, List

import numpy as np
import PyDAQmx as daq

from PySide6 import QtCore

from qudi.core.configoption import ConfigOption
from qudi.interface.triggered_analog_output_interface import (TriggeredAnalogOutputInterface,
                                                              TriggeredAnalogOutputConstraints)

AXIS_NAMES = ['x', 'y', 'z', 'a']

def _number(value):
    """Numbers of the correction options may be given as numbers or as expressions like 'np.pi/4'."""
    if isinstance(value, str):
        return float(eval(value, {'np': np, 'pi': np.pi}))
    return float(value)


class NiTriggeredAnalogOutput(TriggeredAnalogOutputInterface):
    """ NI X series analog output with pixel clock. See the module docstring. """

    _scanner_clock_channel = ConfigOption('scanner_clock_channel', missing='error')
    _pixel_clock_channel = ConfigOption('pixel_clock_channel', missing='error')
    _scanner_ao_channels = ConfigOption('scanner_ao_channels', missing='error')
    _scanner_voltage_ranges_lt = ConfigOption('scanner_voltage_ranges_lt', missing='error')
    _scanner_voltage_ranges_rt = ConfigOption('scanner_voltage_ranges_rt', missing='error')
    _max_sample_rate = ConfigOption('max_sample_rate', 1000.0, missing='nothing')
    _initial_voltages = ConfigOption('initial_voltages', None, missing='nothing')      # {'x': 0.0, ...} or None
    _RWTimeout = ConfigOption('read_write_timeout', default=10)

    # corrections of a distorted scan (as in the scanner module); they act on the voltages x, y, z, a
    _trapezoid_rotation_correction = ConfigOption('trapezoid_rotation_correction', 0)
    _rotation_correction = ConfigOption('rotation_correction', 0)
    _scaling_correction_a = ConfigOption('scaling_correction_a', 1)
    _scaling_correction_b = ConfigOption('scaling_correction_b', 1)
    _scaling_correction_x = ConfigOption('scaling_correction_x', 1)
    _scaling_correction_y = ConfigOption('scaling_correction_y', 1)

    # options of the scanner module (photon counting on the card) that are accepted and ignored
    for _ignored_name in ('photon_sources', 'scanner_counter_channels', 'scanner_ai_channels', 'counter_voltage_range',
                          'default_scanner_clock_frequency', 'max_scan_frequency', 'max_resolution',
                          'ramp_time_full_range', 'output_pixel_clock', 'initial_position', 'scan_debug', 'max_counts',
                          'scanner_channel_names', 'clock_channel', 'default_clock_frequency', 'counter_channels',
                          'counter_ai_channels', 'odmr_trigger_channel', 'odmr_trigger_line', 'odmr_switch_line',
                          'gate_in_channel', 'default_samples_number', 'counting_edge_rising',
                          'scanner_position_ranges'):
        locals()['_ignored_' + _ignored_name] = ConfigOption(_ignored_name, None, missing='nothing')
    del _ignored_name

    sigLimitsChanged = QtCore.Signal()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._ao_lock = threading.RLock()          # analog output task and the stored voltages
        self._wf_lock = threading.RLock()          # start and end of a waveform
        self._channels: List[str] = []
        self._voltage_ranges: Dict[str, tuple] = {}
        self._voltages = np.zeros(0)               # requested voltages (before the corrections)
        self._ao_task = None
        self._clock_task = None
        self._waveform_running = False
        self._pending_voltages = None              # voltages that the channels have after the running waveform

    # ----------------------------------------------------------------------------------------------------------
    # qudi module
    # ----------------------------------------------------------------------------------------------------------

    def on_activate(self):
        self._scanner_ao_channels = list(self._scanner_ao_channels)
        n = len(self._scanner_ao_channels)
        if not 1 <= n <= len(AXIS_NAMES):
            raise ValueError('scanner_ao_channels must contain 1 to {} channels.'.format(len(AXIS_NAMES)))
        if len(self._scanner_voltage_ranges_lt) < n:
            raise ValueError('Specify a LT voltage range for every scanner_ao_channel.')
        if len(self._scanner_voltage_ranges_rt) < n:
            raise ValueError('Specify a RT voltage range for every scanner_ao_channel.')
        self._channels = AXIS_NAMES[:n]
        
        self._voltage_ranges = {ch: (float(r[0]), float(r[1]))
                                for ch, r in zip(self._channels, self._scanner_voltage_ranges_rt)}
        
        self._corrections = {
            'trapezoid': _number(self._trapezoid_rotation_correction),
            'rotation': _number(self._rotation_correction),
            'a': _number(self._scaling_correction_a),
            'b': _number(self._scaling_correction_b),
            'x': _number(self._scaling_correction_x),
            'y': _number(self._scaling_correction_y),
        }
        initial = self._initial_voltages or {}
        # like the scanner module: nothing is written at activation, the first set_voltages sets the outputs
        self._voltages = np.array([self._clip(ch, float(initial.get(ch, 0.0))) for ch in self._channels])
        if self._start_analog_output() < 0:
            raise Exception('Failed to start the NI card module due to analog output failure.')

    def on_deactivate(self):
        self._reset_device()      # no tasks left, other programs can use the card

    def set_temperature_regime(self, is_lt: bool) -> None:
        # is_lt is sent from Gui where it is a toggle-button. Is this a statusVar?
        """Switch to the configured LT or RT ranges (scanner_*_ranges_lt / _rt). The axes of the GUI and the logic
        are read at their activation, they have to be reactivated to see the new ranges."""
        _voltage_ranges = self._scanner_voltage_ranges_lt if is_lt else self._scanner_voltage_ranges_rt
        self._voltage_ranges = {ch: (float(r[0]), float(r[1]))
                                        for ch, r in zip(self._channels, _voltage_ranges)}
        # volt = self._scanner_voltage_ranges_lt if is_lt else self._scanner_voltage_ranges_rt
        # pos = self._scanner_position_ranges_lt if is_lt else self._scanner_position_ranges_rt
        # if volt is None:
        #     self.log.warning('No voltage and position ranges are configured for the {} regime.'.format(
        #         'LT' if is_lt else 'RT'))
        #     return
        # if self.module_state() != 'idle':
        #     self.log.error('Cannot change the ranges while a scan is running.')
        #     return
        # self._voltage_ranges = [list(r) for r in volt]
        # self._position_ranges = [list(r) for r in pos]
        # self._build_axes_and_channels()
        # self._current_position = np.array(
        #     [self._axes[name].clip_value(p) for name, p in zip(self._axes, self._current_position)])
        # self._target_position = self._current_position.copy()
        self._start_analog_output()           # reloads the voltage limits
        self.sigLimitsChanged.emit()

    # ----------------------------------------------------------------------------------------------------------
    # TriggeredAnalogOutputInterface
    # ----------------------------------------------------------------------------------------------------------
    def get_constraints(self):
        return TriggeredAnalogOutputConstraints(self._channels, self._voltage_ranges, self._max_sample_rate)

    def get_voltages(self):
        return {ch: float(v) for ch, v in zip(self._channels, self._voltages)}

    def set_voltages(self, voltages, ramp_time=0.0):
        with self._wf_lock:
            if self._waveform_running:
                raise RuntimeError('Cannot set voltages while a waveform is running.')
        unknown = [ch for ch in voltages if ch not in self._channels]
        if unknown:
            raise ValueError('Unknown analog output channels {}, available are {}'.format(unknown, self._channels))
        with self._ao_lock:
            start = self._voltages.copy()
            target = start.copy()
            for i, ch in enumerate(self._channels):
                if ch in voltages:
                    target[i] = self._clip(ch, float(voltages[ch]))
            n_steps = max(2, int(ramp_time / 0.002)) if ramp_time > 0 and np.any(target != start) else 1
            for step in range(1, n_steps + 1):
                self._write_now(start + (target - start) * step / n_steps)
                if n_steps > 1:
                    time.sleep(ramp_time / n_steps)
            self._voltages = target

    def start_waveform(self, waveforms, sample_rate):
        unknown = [ch for ch in waveforms if ch not in self._channels]
        if unknown:
            raise ValueError('Unknown analog output channels {}, available are {}'.format(unknown, self._channels))
        lengths = {len(w) for w in waveforms.values()}
        if len(lengths) != 1 or not lengths.pop():
            raise ValueError('The waveforms must have the same non-zero length.')
        n_samples = len(next(iter(waveforms.values())))
        sample_rate = float(min(sample_rate, self._max_sample_rate))
        with self._wf_lock:
            if self._waveform_running:
                raise RuntimeError('A waveform is already running.')
            with self._ao_lock:
                matrix = np.tile(self._voltages[:, None], (1, n_samples))
                for i, ch in enumerate(self._channels):
                    if ch in waveforms:
                        matrix[i, :] = [self._clip(ch, float(v)) for v in waveforms[ch]]
                self._pending_voltages = matrix[:, -1].copy()
                volts = self._to_hardware_volts(matrix)

                # the pixel clock: n_samples + 1 pulses, the first rising edge outputs sample 0
                clock = daq.TaskHandle()
                daq.DAQmxCreateTask('ScannerClock', daq.byref(clock))
                self._clock_task = clock
                daq.DAQmxCreateCOPulseChanFreq(clock, self._scanner_clock_channel, 'Clock Producer', daq.DAQmx_Val_Hz,
                                               daq.DAQmx_Val_Low, 0, sample_rate, 0.5)
                daq.DAQmxCfgImplicitTiming(clock, daq.DAQmx_Val_FiniteSamps, n_samples + 1)

                # the analog output is clocked by the pixel clock
                daq.DAQmxSetSampTimingType(self._ao_task, daq.DAQmx_Val_SampClk)
                daq.DAQmxCfgSampClkTiming(self._ao_task, self._scanner_clock_channel + 'InternalOutput', sample_rate,
                                          daq.DAQmx_Val_Rising, daq.DAQmx_Val_FiniteSamps, n_samples)
                written = self._write_buffer(volts, n_samples)
                if written != n_samples:
                    self._cleanup()
                    raise RuntimeError('Only {} of {} voltages were written.'.format(written, n_samples))
                daq.DAQmxStartTask(self._ao_task)

                # route the pixel clock to the terminal that is wired to the Time Tagger
                daq.DAQmxConnectTerms(self._scanner_clock_channel + 'InternalOutput', self._pixel_clock_channel,
                                      daq.DAQmx_Val_DoNotInvertPolarity)
                self._waveform_running = True
                daq.DAQmxStartTask(clock)         # starts the clock and with it the output; returns at once

    def is_waveform_running(self):
        return self._waveform_running

    def wait_until_waveform_done(self, timeout):
        clock = self._clock_task
        if not self._waveform_running or clock is None:
            return True
        finished = True
        try:
            daq.DAQmxWaitUntilTaskDone(clock, float(timeout))
        except Exception as err:
            finished = False
            if self._waveform_running and self._clock_task is clock:
                self.log.warning('The pixel clock did not finish within {} s: {}'.format(timeout, err))
        if finished or not self._waveform_running:
            self._finish_waveform()
            return True
        return False

    def stop_waveform(self):
        with self._wf_lock:
            clock = self._clock_task
            if clock is not None:
                try:
                    daq.DAQmxStopTask(clock)      # also ends a wait in another thread
                except Exception:
                    pass
        self._finish_waveform()

    def reset(self):
        """Reset the device and restart the analog output task. The analog outputs are 0 V afterwards."""
        self._reset_device()
        self._start_analog_output()

    def _reset_device(self):
        """Stop a waveform, clear the analog output task and reset the device (it can not be reset while a task
        holds it)."""
        self.stop_waveform()
        try:
            if self._ao_task is not None:
                daq.DAQmxStopTask(self._ao_task)
                daq.DAQmxClearTask(self._ao_task)
        except Exception:
            self.log.exception('Could not clear the AO task.')
        self._ao_task = None
        devices = []
        for channel in [self._scanner_clock_channel, self._pixel_clock_channel] + list(self._scanner_ao_channels):
            match = re.match(r'^/(?P<dev>[0-9A-Za-z\- ]+[0-9A-Za-z\-_ ]*)/(?P<chan>[0-9A-Za-z]+)', str(channel))
            if match:
                devices.append(match.group('dev'))
        for device in set(devices):
            try:
                daq.DAQmxResetDevice(device)
            except Exception:
                self.log.exception('Could not reset NI device {0}'.format(device))

    # ----------------------------------------------------------------------------------------------------------
    # internals
    # ----------------------------------------------------------------------------------------------------------
    def _clip(self, channel, voltage):
        vmin, vmax = self._voltage_ranges[channel]
        return float(np.clip(voltage, min(vmin, vmax), max(vmin, vmax)))

    def _start_analog_output(self) -> int:
        """ Starts (or restarts) the analog output task. @return int: 0 OK, -1 error """
        try:
            if self._ao_task is not None:
                daq.DAQmxStopTask(self._ao_task)
                daq.DAQmxClearTask(self._ao_task)
                self._ao_task = None
            self._ao_task = daq.TaskHandle()
            daq.DAQmxCreateTask('ScannerAO', daq.byref(self._ao_task))
            print("in start analog output")
            print("channels", self._channels)
            print("scanner_ao_channels", self._scanner_ao_channels)
            print("voltage range", self._voltage_ranges)
            for n, (ch, chan) in enumerate(zip(self._channels, self._scanner_ao_channels)):
                vmin, vmax = self._voltage_ranges[ch]
                daq.DAQmxCreateAOVoltageChan(self._ao_task, chan, 'Scanner AO Channel {0}'.format(n), vmin, vmax,
                                             daq.DAQmx_Val_Volts, '')
            print("Done")
        except Exception:
            self.log.exception('Error starting the analog output task.')
            return -1
        return 0

    def _write_buffer(self, volts, length):
        n_written = daq.int32()
        daq.DAQmxWriteAnalogF64(self._ao_task, length, False, self._RWTimeout, daq.DAQmx_Val_GroupByChannel, volts,
                                daq.byref(n_written), None)
        return n_written.value

    def _write_now(self, voltages):
        """Write one set of voltages (requested values, corrections are applied) right now."""
        volts = self._to_hardware_volts(np.asarray(voltages, dtype=float).reshape(-1, 1))
        n_written = daq.int32()
        daq.DAQmxWriteAnalogF64(self._ao_task, 1, True, self._RWTimeout, daq.DAQmx_Val_GroupByChannel, volts,
                                daq.byref(n_written), None)

    def _to_hardware_volts(self, matrix):
        """Requested voltages (n_channels x m) -> voltages at the card: corrections, then limited to the range."""
        volts = self._corrected(np.asarray(matrix, dtype=float))
        for i, ch in enumerate(self._channels):
            vmin, vmax = self._voltage_ranges[ch]
            volts[i] = np.clip(volts[i], min(vmin, vmax), max(vmin, vmax))
        return np.ascontiguousarray(volts, dtype=np.float64)

    def _corrected(self, volts):
        """Rescaling / rotation of a distorted scan (as in the scanner module, for 1 to 4 channels)."""
        n_channels, n_samples = volts.shape
        v = np.zeros((4, n_samples))
        v[:n_channels] = volts
        rot = lambda r: np.asarray([[np.cos(r), -np.sin(r), 0, 0], [np.sin(r), np.cos(r), 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]])
        scale = lambda a, b: np.asarray([[a, 0, 0, 0], [0, b, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]])
        c = self._corrections
        v = scale(c['x'], c['y']) @ v
        v = rot(c['rotation']) @ v
        v = rot(-c['trapezoid']) @ scale(c['a'], c['b']) @ rot(c['trapezoid']) @ v
        return v[:n_channels].copy()

    def _finish_waveform(self):
        """Clean up after a waveform (finished or aborted). Safe to call twice."""
        with self._wf_lock:
            if not self._waveform_running and self._clock_task is None:
                return
            self._cleanup()
            if self._pending_voltages is not None:
                with self._ao_lock:
                    self._voltages = self._pending_voltages
                self._pending_voltages = None
            self._waveform_running = False

    def _cleanup(self):
        with self._ao_lock:
            try:
                daq.DAQmxStopTask(self._ao_task)
                daq.DAQmxSetSampTimingType(self._ao_task, daq.DAQmx_Val_OnDemand)
            except Exception:
                self.log.exception('Error stopping the analog output.')
            clock, self._clock_task = self._clock_task, None
            if clock is not None:
                try:
                    daq.DAQmxStopTask(clock)
                    daq.DAQmxDisconnectTerms(self._scanner_clock_channel + 'InternalOutput', self._pixel_clock_channel)
                except Exception:
                    pass
                try:
                    daq.DAQmxClearTask(clock)
                except Exception:
                    self.log.exception('Could not clear the clock task.')
