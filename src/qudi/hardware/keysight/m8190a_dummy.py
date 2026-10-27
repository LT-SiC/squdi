# -*- coding: utf-8 -*-
"""
Dummy for the Keysight M8190A: same qudi module API as ``m8190a.KeysightM8190A``, no instrument, no VISA needed.

What it does
  * Exposes the same attributes as the real driver: ``awg.run``, ``awg.sample_frequency``, ``awg.ch[1].output``,
    ``awg.ch[1].output_amplitude``, ... Settings are simply stored (placeholder defaults, NOT the real instrument defaults).
  * ``Channel.write_sequence`` / ``delete_sequence`` / ``initialize_sequence`` follow the real driver, so mistakes in a
    sequence show up here as well:
      - an empty sequence is rejected,
      - the waveform samples of every step are generated (``generate_samples: True``, the default; this is the
        expensive part of a real write, switch it off with ``generate_samples: False`` for quick tests),
      - segment ids are assigned, ``sequence_table_data_block`` is built (sets the sequence ids of the steps),
      - ``initialize_sequence`` fails for a sequence that was never written,
      - ``delete_sequence`` fails while the channel is running or if the segments are not in the memory.
  * ``awg.history`` keeps the last 1000 actions (run, trigger, write, delete, ...) for inspection.

What it does not do: model the instrument memory limits, timing, or the SCPI error queue.

Example config:

    m8190a:
        module.Class: 'keysight.m8190a_dummy.KeysightM8190ADummy'
        options:
            name: '2g'
            channels: [1, 2]
            # generate_samples: True
"""
import collections
import copy
import logging
import sys
import time
import traceback

import numpy as np

from qudi.core.configoption import ConfigOption

from qudi.hardware.keysight.m8190a import KeysightM8190A

logger = logging.getLogger(__name__)

# placeholder values returned until something is set (the real driver would query the instrument)
CHANNEL_DEFAULTS = dict(
    run=False,
    fine_delay_limits=(0.0, 30e-12), fine_delay=0.0,
    coarse_delay_limits=(0.0, 10e-9), coarse_delay=0.0,
    arm_mode='SELF', continuous_mode=False, gate_mode=False, trigger_mode='continuous', gate_open=False,
    output=False, complement_output=False, differential_offset=0.0,
    sample_clock_source='internal', sample_frequency=12e9,
    output_amplitude=0.35, output_offset=0.0,
    sample_marker_amplitude=1.0, sample_marker_offset=0.0, sample_marker_low=0.0, sample_marker_high=1.0,
    sync_marker_amplitude=1.0, sync_marker_offset=0.0, sync_marker_low=0.0, sync_marker_high=1.0,
    sequencer_mode='STS', selected_sequence=0, dynamic_mode=False,
    scenario_mode_sequence_start_index=0, scenario_advance_mode='AUTO', scenario_loop_count=1,
)
CHANNEL_READ_ONLY = ('fine_delay_limits', 'coarse_delay_limits')

AWG_DEFAULTS = dict(
    trigger_input_threshold_level_limits=(-5.0, 5.0), trigger_input_threshold_level=0.0,
    trigger_input_impedance='HIGH', trigger_input_slope='POS', trigger_source='EXT',
    internal_trigger_frequency_limits=(1e-3, 1e7), internal_trigger_frequency=1e6,
    event_input_threshold_level_limits=(-5.0, 5.0), event_input_threshold_level=0.0,
    event_input_impedance='HIGH', event_input_slope='POS',
    enable_event_source='TRIG', advancement_event_source='EVEN',
    external_sample_frequency_limits=(125e6, 12e9), external_sample_frequency=12e9,
    internal_sample_frequency_limits=(125e6, 12e9), internal_sample_frequency=12e9,
    sample_frequency=12e9, sample_clock_output_source='INT', reference_clock_source='INT',
    gate_open=False, current_settings='', byte_order='NORM', channels_coupled=True,
    errors=[], is_ready=True, status_byte=0,
)
AWG_READ_ONLY = ('trigger_input_threshold_level_limits', 'internal_trigger_frequency_limits',
                 'event_input_threshold_level_limits', 'external_sample_frequency_limits',
                 'internal_sample_frequency_limits', 'errors', 'is_ready', 'status_byte')


def _install_properties(cls, defaults, read_only=()):
    """Add one real ``property`` per setting (the qudi module forwards writes only for real properties)."""
    for name in defaults:
        if name in cls.__dict__:
            continue

        def getter(self, name=name):
            return copy.copy(self._values.get(name, defaults[name]))

        if name in read_only:
            prop = property(getter)
        else:
            def setter(self, value, name=name):
                self._values[name] = value
                self._log('set {} = {!r}'.format(name, value))
            prop = property(getter, setter)
        setattr(cls, name, prop)


class _DummyVisaDevice:
    """Stand-in for the VISA session (``awg_visa_device``)."""

    def __init__(self, owner):
        self._owner = owner
        self.closed = False

    def write(self, cmd, *args, **kwargs):
        self._owner._log('visa write {!r}'.format(cmd))

    def write_raw(self, cmd, *args, **kwargs):
        self._owner._log('visa write_raw ({} bytes)'.format(len(cmd)))

    def query(self, cmd, *args, **kwargs):
        self._owner._log('visa query {!r}'.format(cmd))
        return '+0,"No error"' if cmd.strip().upper() == 'SYST:ERR?' else '0'

    def close(self):
        self.closed = True


class DummyChannel:
    def __init__(self, awg, channel_number):
        self.awg = awg
        self.channel_number = channel_number
        self._values = {}
        self.segments = collections.OrderedDict()  # segment id -> dict(name, length_smpl, comment)
        self.sequencer_table_data = None
        self._next_segment_id = 1

    def _log(self, msg):
        self.awg._log('ch{}: {}'.format(self.channel_number, msg))

    def _clear(self):
        self.segments.clear()
        self.sequencer_table_data = None
        self._next_segment_id = 1
        self._log('memory cleared')

    def send_enable_event(self):
        self._log('enable event')

    def send_advancement_event(self):
        self._log('advancement event')

    def send_begin(self):
        self._log('begin')

    def write_sequence(self, sequence, sample_offset, sequence_id_offset=0):
        if sequence.number_of_steps == 0:
            raise ValueError('An empty sequence can not be written.')
        segment_ids = []
        length_smpl_dict = {}
        try:
            for i, step in enumerate(sequence.data_list):
                if hasattr(step, 'reused_sequence_step'):
                    segment_ids.append(step.segment_id)
                else:
                    sid = self._next_segment_id
                    self._next_segment_id += 1
                    if self.awg.generate_samples:
                        data = np.asarray(step.segment_block_data(coherent_offset=sample_offset))
                        if data.nbytes != 2 * step.length_smpl:
                            logger.warning('Dummy AWG ch{}: step {} of {} has {} bytes of samples but length_smpl*2 = {}'.format(
                                self.channel_number, step.name, sequence.name, data.nbytes, 2 * step.length_smpl))
                    self.segments[sid] = dict(name=step.name, length_smpl=int(step.length_smpl),
                                              comment=getattr(step, 'comment', None))
                    segment_ids.append(sid)
                    step._segment_id = sid
                    length_smpl_dict[sid] = int(step.length_smpl)
                sample_offset += int(step.loop_count) * length_smpl_dict[step.segment_id]
        except Exception:
            exc_type, exc_value, exc_tb = sys.exc_info()
            traceback.print_exception(exc_type, exc_value, exc_tb)
            raise Exception('An error occured while writing sequence {}, sequencestep ({},{})'.format(
                sequence.name, step.name, i))
        self.sequencer_table_data = sequence.sequence_table_data_block(segment_ids, sequence_id_offset=0)
        self._log("wrote sequence '{}' ({} steps)".format(sequence.name, sequence.number_of_steps))

    def delete_sequence(self, sequence):
        for i, step in enumerate(sequence.data_list):
            if not hasattr(step, 'reused_sequence_step'):
                if not hasattr(step, 'segment_id'):
                    raise Exception('Error: step {} of sequence {} does not have a segment_id. Either the sequence has not been '
                                    'written to the channel {}, or this is unexpected behaviour.'.format(i, sequence.name, self.channel_number))
                if step.segment_id not in self.segments:
                    raise Exception('Error: associated segment_id {} of step {} sequence {} can not be found on awg channel {}'.format(
                        step.segment_id, i, sequence.name, self.channel_number))
        if self.run:
            raise Exception('Error: Device is running!')
        self.sequencer_table_data = None
        for step in sequence.data_list:
            if not hasattr(step, 'reused_sequence_step'):
                del self.segments[step.segment_id]
        self._log("deleted sequence '{}'".format(sequence.name))

    def initialize_sequence(self, sequence):
        self.trigger_mode = 'triggered'
        self.sequencer_mode = 'STS'
        self.selected_sequence = sequence.data_list[0]._sequence_id  # AttributeError if never written, like the real one
        self._log("initialized sequence '{}'".format(sequence.name))


_install_properties(DummyChannel, CHANNEL_DEFAULTS, CHANNEL_READ_ONLY)


class DummyAWG:
    """Drop-in for ``m8190a_driver.AWG`` that never touches an instrument."""

    def __init__(self, address, name, channel_numbers, generate_samples=True):
        self._address = address
        self._name = name
        self.channel_numbers = list(channel_numbers)
        self.generate_samples = generate_samples
        self._values = {}
        self._run = False
        self.trigger_count = 0
        self.history = collections.deque(maxlen=1000)  # (time, message)
        self.awg_visa_device = _DummyVisaDevice(self)
        self.previous_comand = None
        self.previous_res = None
        self._ch = collections.OrderedDict((n, DummyChannel(self, n)) for n in self.channel_numbers)

    def _log(self, msg):
        self.history.append((time.time(), msg))
        logger.debug('Dummy AWG %s: %s', self._name, msg)

    @property
    def address(self):
        return self._address

    @property
    def name(self):
        return self._name

    @property
    def ch(self):
        return self._ch

    @property
    def run(self):
        return self._run

    @run.setter
    def run(self, value):
        self._run = bool(value)
        for channel in self._ch.values():
            channel._values['run'] = self._run
        self._log('run = {}'.format(self._run))

    def clear_memories(self):
        for channel in self._ch.values():
            channel._clear()

    def write(self, cmd, *args, **kwargs):
        self.awg_visa_device.write(cmd)

    def write_raw(self, cmd, *args, **kwargs):
        self.awg_visa_device.write_raw(cmd)

    def query(self, cmd, *args, **kwargs):
        return self.awg_visa_device.query(cmd)

    def send_enable_event(self):
        self._log('enable event')

    def send_advancement_event(self):
        self._log('advancement event')

    def send_begin(self):
        self.trigger_count += 1
        self._log('begin trigger #{} (running: {})'.format(self.trigger_count, self._run))

    def dump_settings_to_file(self, filepath=None):
        self._log('dump_settings_to_file (dummy: nothing written)')

    def dump_current_settings_to_file(self):
        self._log('dump_current_settings_to_file (dummy: nothing written)')

    def load_settings_from_file(self, filepath=None):
        self._log('load_settings_from_file (dummy: nothing loaded)')

    def restore_settings_from_file(self, filepath=None):
        self._log('restore_settings_from_file (dummy: nothing loaded)')

    def rst(self):
        self._log('*RST')
        self.run = False


_install_properties(DummyAWG, AWG_DEFAULTS, AWG_READ_ONLY)


class KeysightM8190ADummy(KeysightM8190A):
    """M8190A module without instrument. Use instead of ``keysight.m8190a.KeysightM8190A`` for debugging."""

    # not required for the dummy
    _address = ConfigOption('address', default='dummy', missing='nothing')
    _generate_samples = ConfigOption('generate_samples', default=True, missing='nothing')

    def on_activate(self):
        self._awg = DummyAWG(address=self._address, name=self._awg_name, channel_numbers=list(self._channels),
                             generate_samples=self._generate_samples)
        self.log.warning("Dummy M8190A '{}' active: no instrument is accessed.".format(self._awg_name))
