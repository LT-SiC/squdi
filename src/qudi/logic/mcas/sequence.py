# -*- coding: utf-8 -*-
"""
Multi channel AWG sequences (MCAS): sequence container + the dict that owns the AWG memory.

Port of the sequence part of the legacy ``pym8190a.py``. The logic is unchanged; what is different:

* No hardware is created here. ``MultiChSeqDict`` receives the already connected qudi hardware
  modules (``awgs = {'2g': <KeysightM8190A>, 'ps': <PulseStreamerMcas>}``).
* No global ``settings`` module. A ``McasSettings`` instance is passed in. ``MultiChSeq`` gets it as a
  class attribute through ``make_mcas_class(settings)``, so ``md.mcas(name=..., ch_dict=...)`` keeps
  working exactly like before.
* ``x is 'ps'`` / ``x is not 'ps'`` -> ``==``. Identity comparison of strings only worked for interned
  literals; names that come from the (YAML) qudi config are not interned.
* PS sequence unwrapping (``unwrap_ps_sequence``) lives here instead of on the PulseStreamer driver,
  because it needs the AWG sample granularity from ``elements``.
* ``run``/``stop`` are no longer assigned on the pulse streamer. In the legacy code ``ps.run = True``
  silently replaced the ``run()`` method by a bool and did nothing else.
"""
from __future__ import print_function, absolute_import, division

__metaclass__ = type

import collections
import collections.abc
import itertools
import logging
import sys
import time
import traceback

import numpy as np

from . import util
from .elements import Sequence, SequenceStep, SequenceStepReuseSegment, WaveStep, __BLM__
from . import elements as el

logger = logging.getLogger(__name__)

# Settings used by a bare ``MultiChSeq(...)``, i.e. by legacy user scripts that call
# ``MCAS.MultiChSeq(name=..., ch_dict=...)`` directly. The mcas holder logic registers its settings here when it
# is activated. ``globals().get`` keeps the value if a script calls importlib.reload() on this module.
_default_settings = globals().get('_default_settings')


def set_default_settings(settings):
    """Register the McasSettings that a bare MultiChSeq(...) falls back to."""
    global _default_settings
    _default_settings = settings


def get_default_settings():
    return _default_settings


def clear_default_settings(settings=None):
    """Forget the default settings (if ``settings`` is given, only when they are the registered ones)."""
    global _default_settings
    if settings is None or _default_settings is settings:
        _default_settings = None


def is_ps(awg_str):
    """The pulse streamer is recognised by 'ps' in its name (legacy convention)."""
    return 'ps' in awg_str


########################################################################################################################
# the dict that owns the awg memory
########################################################################################################################
class MultiChSeqDict(collections.OrderedDict):

    def __init__(self, awgs, settings, mcas_class=None, debug_mode=False, restore_awg_settings=None):
        """
        :param awgs: {name: connected hardware module}, e.g. {'2g': KeysightM8190A, 'ps': PulseStreamerMcas}
        :param settings: McasSettings
        :param mcas_class: MultiChSeq class bound to ``settings`` (created if not given)
        :param debug_mode: completely stops interaction with the awgs
        :param restore_awg_settings: restore the last stored awg settings; default settings.restore_awg_settings
        """
        super(MultiChSeqDict, self).__init__()
        self.settings = settings
        self.mcas_class = make_mcas_class(settings) if mcas_class is None else mcas_class
        self.awgs = collections.OrderedDict(awgs)
        self.debug_mode = debug_mode
        if restore_awg_settings is None:
            restore_awg_settings = settings.restore_awg_settings

        self.initialize_awgs(restore_awg_settings=restore_awg_settings)
        self.set_wait()

    @property
    def debug_mode(self):
        return self._debug_mode

    @debug_mode.setter
    def debug_mode(self, val):
        if not hasattr(self, '_debug_mode') or self._debug_mode != util.check_type(val, 'debug_mode', bool):
            self._debug_mode = val
            if val is True:
                logger.info("mcas_dict set to debug_mode {}".format(self.debug_mode))
            written_list = [val.written for val in self.values()]
            if val is True and not all(written_list):
                self.rewrite_keys_awg_memory(keys=[k for k in list(self.keys())[written_list.index(False):]])

    def initialize_awgs(self, restore_awg_settings, notify=True):
        """Bring the connected awgs into a defined state (replaces the legacy connect_to_awgs)."""
        if self.debug_mode:
            if notify:
                logger.info("Debug mode! Did not initialize awgs {}".format(list(self.awgs)))
            return
        t0 = time.time()
        for name, awg in self.awgs.items():
            if is_ps(name):
                continue
            awg.run = False
            if restore_awg_settings:
                awg.restore_settings_from_file()
            awg.clear_memories()
        if notify:
            logger.info("Initialized awgs {} in {:.2f}s".format(list(self.awgs), time.time() - t0))

    def stop_awgs(self):
        if not self.debug_mode:
            stop_awgs(self.awgs, self.settings)

    def set_wait(self):
        mcas = self.mcas_class(name='wait', ch_dict=self.settings.ch_dict_awgs)
        mcas.start_new_segment('wait')
        mcas.asc(length_smpl=320)
        mcas.status = 1

        self['wait'] = mcas

    def __setitem__(self, key, value, dict_setitem=dict.__setitem__):
        if not isinstance(key, str):
            raise TypeError("key must be type str but is {} ({})".format(key, type(key)))
        if key != value.name:
            raise TypeError("Not allowed: {}, {}, probably you need to have the same name for the mcas and the name you try to attribute to the mcas_dict".format(key, type(value)))
        if key in self:
            del self[key]
        if value.written:
            raise Exception('Error: Sequence has already been written and can not be added.')

        value.mcas_dict = self
        if value.status == 0 and not self.debug_mode:
            value.finalize()
        if not self.debug_mode:
            value.write_to_awg_memory(notify=True)  # longest part
        collections.OrderedDict.__setitem__(self, key, value)

    def __delitem__(self, key, dict_delitem=dict.__delitem__):
        didx = list(self.keys()).index(key)
        delete_keys = [k for k in list(self.keys())[didx:]]
        self.delete_keys_from_awg_memory(delete_keys)
        del self[key].mcas_dict
        collections.OrderedDict.__delitem__(self, key)
        self.write_keys_to_awg_memory(delete_keys[1:])

    def rewrite_keys_awg_memory(self, keys):
        self.delete_keys_from_awg_memory(keys)
        self.write_keys_to_awg_memory(keys)

    def delete_keys_from_awg_memory(self, keys):
        for key in keys[::-1]:
            if self[key].written:
                self[key].delete_from_awg_memory()

    def write_keys_to_awg_memory(self, keys):
        if not self.debug_mode:
            for key in keys:
                self[key].write_to_awg_memory(notify=True)

    def dl(self, key, *args, **kwargs):
        return self[key].dl(*args, **kwargs)

    @property
    def info(self):
        return "\n".join(["{}, {}".format(key, val.ch_dict) for key, val in self.items()])

    def __repr__(self):
        return self.info

    def __str__(self):
        return self.info

    def print_info(self):
        print(self.info)


########################################################################################################################
# a single multi channel sequence
########################################################################################################################
class MultiChSeq:
    #: McasSettings. Set on the subclass returned by make_mcas_class(settings).
    settings = None

    def __init__(self, ch_dict=None, **kwargs):
        if self.settings is None:
            # bare class, as used by legacy scripts: fall back to the settings registered by the mcas holder
            if _default_settings is None:
                raise RuntimeError('MultiChSeq has no settings. Activate the mcas holder module (it registers the '
                                   'default settings) or create sequences with mcas_holder.mcas(...) '
                                   '(or make_mcas_class(settings)).')
            self.settings = _default_settings
        self.name = kwargs.get('name', kwargs.get('seq_name'))

        self.ch_dict = valid_ch_dict(self.settings.ch_dict_full if ch_dict is None else ch_dict, self.settings)
        self.init_sequences()
        self.status = 0
        logger.debug("MCAS {} initialized".format(self.name))

    name = util.ret_property_typecheck('name', str)

    def init_sequences(self):
        # TODO: create a PS sequence also, which could be assembled later in asc, start_new_segment.
        self.sequences = {}

        for awg_str, chl in self.ch_dict.items():
            self.sequences[awg_str] = dict([[ch, Sequence(name=self.name)] for ch in chl])
            if is_ps(awg_str):
                self.sequences[awg_str] = {1: [([], self.settings.slave_start_delay)]}

    def dl(self, awg, ch, sequence_step_num=None, wave_step_num=None):
        out = self.sequences[awg][ch]
        if sequence_step_num is not None:
            out = out.dl(sequence_step_num, wave_step_num)
        return out

    @property
    def written(self):
        return getattr(self, '_written', False)

    @written.setter
    def written(self, val):
        self._written = val

    @property
    def length_mus(self):
        # legacy: first awg of the dict; on py3 this always ended up at sequences['2g'][1]
        for awg_str in self.sequences:
            if not is_ps(awg_str):
                return next(iter(self.sequences[awg_str].values())).length_mus
        raise RuntimeError('MCAS {} contains no awg channel, length is undefined.'.format(self.name))

    def asc(self, **kwargs):
        self.add_step_complete(**kwargs)

    def add_step_complete(self, **kwargs):
        pd = {}
        if (kwargs.get("A2", False) or kwargs.get("A1", False)) and kwargs.get("laser", True):
            kwargs.update({"laser": True})  # UNFUG ?

        for awg_str, chl in self.ch_dict.items():
            pd[awg_str] = {}
            for ch in chl:
                pd[awg_str][ch] = kwargs.pop('pd' + awg_str + str(ch), {})
        for key in [k for k in kwargs if k in self.settings.marker_alias]:
            awg_str, ch, marker_name, _ = self.settings.marker_alias[key]
            pd[awg_str][ch][marker_name + '_marker'] = kwargs.pop(key)
        self.add_step(pd=pd, **kwargs)

    def step_length_mus(self, pd, length_mus):
        lml = []
        if length_mus is not None:
            lml.append(length_mus)
        for awg_str in pd.keys():
            for ch in pd[awg_str].keys():
                if pd[awg_str][ch].get('type', 'wait') in ['robust']:
                    lml.append(WaveStep(**pd[awg_str][ch]).length_mus)
                elif 'length_mus' in pd[awg_str][ch]:
                    lml.append(pd[awg_str][ch]['length_mus'])
        if len(lml) == 0:
            return 0.0
        else:
            for i in lml:
                if abs(i - lml[0]) > 0.1 * (1e-9 * 1e6):
                    raise Exception('The steps for different channels must have same length')
            else:
                return lml[0]

    def add_step(self, pd=None, name='', length_mus=None, ssi=None, wsi=None, **kwargs):
        if self.status != 0:
            raise Exception('Error: MCAS {} is in state {} and can not be changed anymore.'.format(self.name, self.status))
        if pd is None:
            pd = {}
        length_mus = self.step_length_mus(pd, length_mus=length_mus)
        ## Strange conversion but seems it is only related to optimal pulses.
        for awg_str, chl in self.ch_dict.items():
            if awg_str not in pd:
                pd[awg_str] = {}
            for ch in chl:
                if ch not in pd[awg_str]:
                    pd[awg_str][ch] = {}
                if not pd[awg_str].get('type', 'wait') in ['robust']:
                    pd[awg_str][ch].update(length_mus=length_mus)
                if 'name' not in pd[awg_str][ch]:
                    pd[awg_str][ch].update(name=name)
                pd[awg_str][ch].update(**kwargs)
                if not is_ps(awg_str):
                    if len(self.sequences[awg_str][ch].data_list) == 0:
                        raise Exception('There is no segment to append to. Start a new one first.')
                    elif ssi is None:
                        ssi = len(self.sequences[awg_str][ch].data_list) - 1
                    elif ssi > len(self.sequences[awg_str][ch].data_list) - 1:
                        raise Exception('Error: selected SequenceStep too big ({}, {}). '.format(ssi, len(self.sequences[awg_str][ch].data_list)))
                    wsi = len(self.sequences[awg_str][ch].data_list[ssi].data_list) if wsi is None else wsi
                    if wsi > (len(self.sequences[awg_str][ch].data_list[ssi].data_list)):
                        raise Exception('THIS PROBABLY IS NOT GOOD, PLEASE CHECK!')
                    self.sequences[awg_str][ch].data_list[ssi].data_list.insert(wsi, WaveStep(**pd[awg_str][ch]))
                else:  # if awg is ps
                    self.sequences[awg_str][ch].append(([marker[0:-7] for marker in pd[awg_str][ch].keys() if 'marker' in marker and
                                                         pd[awg_str][ch][marker] == True
                                                         ], 1000 * length_mus))

    def start_new_segment(self, name='', reuse_segment=False, **kwargs):
        for awg_str, chl in self.ch_dict.items():
            for ch in chl:
                if is_ps(awg_str):
                    if 'loop_count' in kwargs.keys():
                        self.sequences[awg_str][ch].append((kwargs['loop_count'],))
                    else:
                        self.sequences[awg_str][ch].append((1,))
                else:
                    if reuse_segment:
                        for idx, step in enumerate(self.sequences[awg_str][ch].data_list):
                            if step.name == name:
                                self.sequences[awg_str][ch].data_list.append(SequenceStepReuseSegment(name=name, reused_sequence_step=step, **kwargs))
                                break
                        else:
                            self.sequences[awg_str][ch].data_list.append(SequenceStep(name=name, **kwargs))
                            print('Warning: reuse_segment was set for {} but no previously defined segment was found. reuse_segment was set to False'.format(name))
                    else:
                        self.sequences[awg_str][ch].data_list.append(SequenceStep(name=name, **kwargs))

    def set_master_trigger_settings(self):
        s = self.settings
        for awg_str, chl in self.ch_dict.items():
            if awg_str == s.master_awg:
                for ch in chl:
                    trigger_sync_marker = True if ch == s.master_trigger_channel else False
                    trigger_step = SequenceStep(name='triggerwait')
                    trigger_step.data_list.append(WaveStep(name='trigger', length_mus=s.trigger_length_mus, sync_marker=trigger_sync_marker))
                    trigger_step.data_list.append(WaveStep(name='waittrigger', length_mus=s.trigger_delay_length_mus - s.trigger_length_mus))
                    w_trig_safety_step = SequenceStep(name='w_trig_safety', data_list=[WaveStep(name='w_trig_safety', length_mus=s.slave_trigger_safety_length_mus)])
                    self.sequences[awg_str][ch].data_list = [trigger_step] + self.sequences[awg_str][ch].data_list + [w_trig_safety_step]

    def set_slave_trigger_settings(self):
        for awg_str, chl in self.ch_dict.items():
            if awg_str != self.settings.master_awg and is_ps(awg_str):
                self.mcas_dict.awgs[awg_str].proxy.setTrigger('HARDWARE_RISING')

    def finalize(self, ignore_max_avg_power=False, notify=True):
        if self.status != 0:
            raise Exception('Error: MCAS {} has already been finalized'.format(self.name))
        self.fix_avg_rf_power(ignore_max_avg_power=ignore_max_avg_power)
        if self.settings.master_awg is not None and self.settings.master_awg in self.ch_dict and len(self.ch_dict) > 1:
            self.set_master_trigger_settings()
            self.set_slave_trigger_settings()

        self.status = 1

    def fix_avg_rf_power(self, ignore_max_avg_power=False):
        s = self.settings
        awtd = {}
        for awg_str, l in s.max_sine_avg_power.items():
            awtd[awg_str] = {}
            for ch, max_avg_power in l.items():
                if max_avg_power is not None and ch in self.ch_dict.get(awg_str, []):
                    awtd[awg_str][ch] = self.additional_wait_time(awg_str, ch, max_avg_power, ignore_max_avg_power=ignore_max_avg_power)

            if all([i == 0 for i in flatten_dict_dict(awtd)]):
                return
            self.start_new_segment(name='rf_power_safety', loop_count=int(np.ceil(max(flatten_dict_dict(awtd)) / __BLM__)))
            self.asc(length_mus=__BLM__)
            for awg_str, l in s.max_sine_avg_power.items():
                for ch, max_avg_power in l.items():
                    if max_avg_power is not None and ch in self.ch_dict.get(awg_str, []):
                        if s.amplifier_power[awg_str][ch] * self.sequences[awg_str][ch].normalized_avg_sine_power / max_avg_power > 1.1 and not ignore_max_avg_power:
                            raise Exception(' Additional wait time added, but power still too high on awg {} ch {}! Sequence {} is {} mus long '
                                            'and has an average rf-power of {} W (maximally allowed: {} W) after adding an additional '
                                            'waiting time of {} mus'.format(awg_str, ch, self.name,
                                                                            self.sequences[awg_str][ch].length_mus,
                                                                            s.amplifier_power[awg_str][ch] * self.sequences[awg_str][ch].normalized_avg_sine_power,
                                                                            max_avg_power,
                                                                            awtd[awg_str][ch]))

    def additional_wait_time(self, awg_str, ch, max_avg_power, ignore_max_avg_power=False):
        if ignore_max_avg_power:
            return 0
        else:
            return check_avg_rf_power(self.sequences[awg_str][ch], awg_str=awg_str, ch=ch, settings=self.settings,
                                      max_avg_power=max_avg_power)

    def precompile_samples_waveform(self, notify=True):
        if self.status != 1:
            raise Exception('Error: MCAS {} has already been precompiled'.format(self.name))
        t0 = time.time()
        for awg_str, chl in self.ch_dict.items():
            for ch in chl:
                self.sequences[awg_str][ch].precompile_samples_waveform(0, notify=False)
        self.status = 2
        if notify:
            logger.info("MCAS '{}' precompiled ({} s).".format(self.name, time.time() - t0))

    def write_seq(self, notify=True):
        self.finalize(notify=notify)
        self.precompile_samples_waveform(notify=notify)

    def write_to_awg_memory(self, ignore_max_avg_power=False, abort=None, notify=True):
        if not ignore_max_avg_power:
            for awg_str, l in self.settings.max_sine_avg_power.items():
                for ch, max_avg_power in l.items():
                    if max_avg_power is not None and ch in self.ch_dict.get(awg_str, []):
                        if check_avg_rf_power(self.dl(awg_str, ch), awg_str, ch, self.settings, max_avg_power, notify=True) != 0:
                            raise Exception('Average rf power too high')
        time_dict = {}
        for awg_str in self.ch_dict.keys():
            if not is_ps(awg_str):
                for ch, sequence in self.sequences[awg_str].items():
                    if abort is not None and abort.is_set():
                        break
                    try:
                        t0 = time.time()
                        self.mcas_dict.awgs[awg_str].ch[ch].write_sequence(sequence=sequence, sample_offset=0)
                        time_dict[awg_str + str(ch)] = float("{:.4f}".format(time.time() - t0))
                    except Exception:
                        exc_type, exc_value, exc_tb = sys.exc_info()
                        traceback.print_exception(exc_type, exc_value, exc_tb)
                        raise Exception('awg {} ch {} could not write sequence {} to memory.'.format(awg_str, ch, self.name))
        self.written = True

    def delete_from_awg_memory(self):
        for awg_str in self.ch_dict.keys():
            if not is_ps(awg_str):
                for ch, sequence in self.sequences[awg_str].items():
                    self.mcas_dict.awgs[awg_str].ch[ch].delete_sequence(sequence=sequence)
        self.written = False

    def initialize(self):
        for awg_str, chl in self.settings.ch_dict_full.items():
            for ch in chl:
                if is_ps(awg_str):
                    if awg_str in self.ch_dict:  # In green md there is no awg_str == ps.
                        sequence = self.sequences[awg_str][ch]
                        sequence = unwrap_ps_sequence(sequence)
                        self.mcas_dict.awgs[awg_str].setSequence(sequence, triggered=True,
                                                                 run=False, loops=1)
                else:
                    if ch in self.ch_dict.get(awg_str, []):
                        sequence = self.sequences[awg_str][ch]
                    else:
                        sequence = self.mcas_dict['wait'].sequences[awg_str][ch]
                    self.mcas_dict.awgs[awg_str].ch[ch].initialize_sequence(sequence)

    def start_awgs(self, trigger=True):
        start_awgs(awgs=self.mcas_dict.awgs, settings=self.settings, ch_dict=self.ch_dict, trigger=trigger)

    def run(self, trigger=True):
        self.initialize()
        self.start_awgs(trigger=trigger)


def make_mcas_class(settings):
    """MultiChSeq subclass bound to ``settings``. Behaves like the legacy ``MultiChSeq`` class."""
    return type('MultiChSeq', (MultiChSeq,), {'settings': settings, '__module__': __name__})


########################################################################################################################
# helpers (formerly module level functions that read the global settings)
########################################################################################################################
def valid_ch_dict(ch_dict, settings):
    if len(ch_dict) > 1:
        if settings.master_awg is None or settings.master_trigger_channel is None:
            raise Exception('No settings.master_awg and settings.master_trigger_channel must be given when multiple awgs are used. If you own the synchronization module, changes to the code need to be made.')
        if settings.master_awg not in ch_dict or settings.master_trigger_channel not in ch_dict[settings.master_awg]:
            raise Exception('No settings.master_awg and settings.master_trigger_channel must be in ch_dict when multiple awgs are used.')
    return ch_dict


def check_avg_rf_power(sequence, awg_str, ch, settings, max_avg_power=None, notify=True):
    avg_power = settings.amplifier_power[awg_str][ch] * sequence.normalized_avg_sine_power
    additional_wait_time = max(0, sequence.length_mus * (avg_power / max_avg_power - 1))
    if notify:
        logger.info("avg_power {:.2f} W,max_avg_power: {} W, additional_wait_time: {} mus".format(avg_power, max_avg_power, additional_wait_time))
    return additional_wait_time


def send_trigger(awgs, settings, ch_dict=None):
    ch_dict = settings.ch_dict_full if ch_dict is None else ch_dict
    awg_str = list(ch_dict.keys())[0] if len(ch_dict) == 1 else settings.master_awg
    awgs[awg_str].send_begin()


def set_outputs(awgs, settings, ch_dict=None):
    ch_dict = settings.ch_dict_full if ch_dict is None else ch_dict
    for awg_str, chl in settings.ch_dict_full.items():
        for ch in chl:
            if not is_ps(awg_str):
                awgs[awg_str].ch[ch].output = 1 if ch in ch_dict.get(awg_str, []) else 0


def start_awgs(awgs, settings=None, ch_dict=None, trigger=True):
    settings = _default_settings if settings is None else settings # FIXME is it fine to use defualt settings?
    ch_dict = settings.ch_dict_full if ch_dict is None else ch_dict
    for awg_str in ch_dict:
        if not is_ps(awg_str):
            awgs[awg_str].run = True
    set_outputs(awgs, settings, ch_dict=ch_dict)
    if trigger:
        send_trigger(awgs, settings, ch_dict=ch_dict)


def stop_awgs(awgs, settings, ch_dict=None):
    ch_dict = settings.ch_dict_full if ch_dict is None else ch_dict
    for awg_str in ch_dict:
        if not is_ps(awg_str):
            awgs[awg_str].run = False
    # stops the ps if it was running. Safety, because the setupcontrol and laserscanner might be running stuff directly on the ps
    for awg_str, awg in awgs.items():
        if is_ps(awg_str):
            awg.Night()


def missing_smpl(ls):
    return float(max(5 * 64 - ls, (-ls) % 64))


def unwrap_ps_sequence(sequence):
    """
    Flatten a ps sequence ``[([markers], length_ns), (loop_count,), ...]`` (loops expanded) and pad every
    segment to the awg segment granularity so that the ps stays in sync with the awg.
    Moved here from PulseStreamerPGProxy.unwrap_sequence, unchanged.
    """
    seq = []
    segment = []
    length = 0
    for idx, item in enumerate(sequence[::-1]):
        if len(item) == 2:
            segment.append(item)
            length += item[1]
        elif len(item) == 1:
            segment.insert(0, ([],
                               np.round(
                                   el.length_smpl2length_mus(
                                       missing_smpl(
                                           el.length_mus2length_smpl(length * 1e-3))) * 1e3, 3),
                               )
                           )

            length = 0
            for i in range(item[0]):  # item[0] is loop count
                for step in segment:
                    seq.append(step)
            segment = []
    if len(segment) > 0:
        for step in segment:
            seq.append(step)
    return seq[::-1]  # should be flipped.


def update(d, u):
    for k, v in u.items():
        if isinstance(v, collections.abc.Mapping):
            r = update(d.get(k, {}), v)
            d[k] = r
        else:
            d[k] = u[k]
    return d


def flatten_dict_dict(dd):
    return list(itertools.chain(*[i.values() for i in dd.values()]))