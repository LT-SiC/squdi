# -*- coding: utf-8 -*-
"""
Settings of the multi channel AWG sequence (MCAS) layer.

The legacy ``settings.py`` was a module with globals. Here the same values live in a
``McasSettings`` object whose defaults are the legacy values. Any of them can be
overridden from the qudi config via the ``settings:`` option of the
``mcas_dict_holder`` logic module (see config/mcas_example.cfg).

Hardware-specific values that used to live here moved to the hardware modules'
config options:
    awg_instrument_adress   -> hardware/keysight/m8190a.py      ``address``
    PulseStreamer ip        -> hardware/swabian/pulse_streamer_mcas.py ``ip``
    settings_folder         -> hardware/keysight/m8190a.py      ``settings_folder``
"""
from __future__ import print_function, absolute_import, division

import copy

from .elements import __BLM__


def _default_marker_alias():
    # marker name: [awg, channel, marker type on that awg, ps output channel (ps only, else None)]
    return {
        'gateAWG': ['2g', 1, 'smpl', None],
        'gate': ['2g', 1, 'smpl', None],
        'gateMW': ['2g', 2, 'smpl', None],
        'memory': ['2g', 2, 'sync', None],
        'closeRF': ['ps', 1, 'closeRF', '0'],
        'A2': ['ps', 1, 'A2', '1'],
        'repump': ['ps', 1, 'repump', '2'],
        'laser': ['ps', 1, 'laser', '3'],  # opens second AOM
        # PS CHANNEL 4 IS CLOCK
        'A1': ['ps', 1, 'A1', '5'],
        'shutter': ['ps', 1, 'shutter', '6'],  # optical shutter
        'gateRF': ['ps', 1, 'gateRF', '7'],
    }


class McasSettings:
    """Attribute container. Names are identical to the legacy ``settings`` module."""

    def __init__(self, **overrides):
        self.ch_dict_full = {'2g': [1, 2], 'ps': [1]}
        self.ch_dict_awgs = None  # derived from ch_dict_full (everything but 'ps') unless given
        self.master_awg = '2g'
        self.master_trigger_channel = 1
        self.restore_awg_settings = True
        self.marker_alias = _default_marker_alias()
        self.max_sine_avg_power = {'2g': {1: None, 2: None}}
        self.amplifier_power = {'2g': {1: 5., 2: 5.}}

        # internal timing settings [mus]
        # the awg has a fixed trigger delay (sample clock dependent) of < 1 mus (right now 864 ns)
        self.trigger_delay_length_mus = 27 * __BLM__
        # duration of the trigger sent to the slave awgs. Must not be longer than trigger_delay_length_mus
        self.trigger_length_mus = 27 * __BLM__
        # after master awg finishes its sequence it waits this time until it starts over and sends a new trigger (1024 ns)
        self.slave_trigger_safety_length_mus = 32 * __BLM__
        # delay [ns] for the PulseStreamer slave to be synchronized with the master. If not given it is
        # trigger_length_mus * 1000 - 69 (right now 795 ns)
        self.slave_start_delay = None

        unknown = [k for k in overrides if not hasattr(self, k)]
        if unknown:
            raise ValueError('Unknown mcas settings {}. Valid settings: {}'.format(sorted(unknown), sorted(vars(self))))
        for key, value in overrides.items():
            setattr(self, key, copy.deepcopy(value))

        if self.ch_dict_awgs is None:
            self.ch_dict_awgs = {k: list(v) for k, v in self.ch_dict_full.items() if 'ps' not in k}
        if self.slave_start_delay is None:
            self.slave_start_delay = self.trigger_length_mus * 1000 - 69

    def ps_channel_map(self):
        """{marker name: pulse streamer digital output} for every marker routed to a pulse streamer."""
        ch_map = {}
        for alias, value in self.marker_alias.items():
            if 'ps' in value:
                out = int(value[3])
                ch_map[alias] = out
                ch_map[value[2]] = out  # the name that ends up in the ps sequences
        return ch_map

    def __repr__(self):
        return 'McasSettings({})'.format(', '.join('{}={!r}'.format(k, v) for k, v in sorted(vars(self).items())))
