# -*- coding: utf-8 -*-
"""
Logic module that owns the AWG memory (``mcas_dict``) and creates sequences (``mcas``).

This is the successor of ``mcas_dict_holder`` from the legacy ``pym8190a.py`` and is what ``queue_logic`` connects to:

    mcas_holder = Connector(interface='McasDictHolderInterface')
    self._awg = self.mcas_holder()
    self._awg.mcas_dict      # MultiChSeqDict, .awgs['2g'] / .awgs['ps'] are the hardware modules
    self._awg.mcas(name=..., ch_dict={...})   # new sequence
    self._awg.settings       # McasSettings (marker_alias, master_awg, ...)

Hardware is no longer created here: the AWG and the pulse streamer are separate qudi hardware modules that
are connected through the ``awg`` and ``pulsestreamer`` connectors.

Example config: see config/mcas_example.cfg
"""
import collections

from qudi.core.connector import Connector
from qudi.core.configoption import ConfigOption
from qudi.core.module import LogicBase
from qudi.interface.mcas_dict_holder_interface import McasDictHolderInterface   # adjust if the interface file lives elsewhere

from qudi.logic.mcas.settings import McasSettings
from qudi.logic.mcas.sequence import MultiChSeqDict, make_mcas_class, set_default_settings, clear_default_settings


class mcas_dict_holder(LogicBase, McasDictHolderInterface):   # LogicBase first, then the interface (both derive from Base)
    """Holds the multi channel sequence dict and the connected awg / pulse streamer."""

    # connectors
    awg = Connector(interface='AwgM8190Interface')
    pulsestreamer = Connector(interface='McasPulseStreamerInterface')

    # config options
    _awg_name = ConfigOption('awg_name', default='2g', missing='nothing')    # key in mcas_dict.awgs / ch_dict
    _ps_name = ConfigOption('ps_name', default='ps', missing='nothing')      # key in mcas_dict.awgs / ch_dict
    _settings_cfg = ConfigOption('settings', default=None, missing='nothing')  # overrides of McasSettings
    _debug_mode = ConfigOption('debug_mode', default=False, missing='nothing')  # no communication with the awgs

    def on_activate(self):
        self.settings = McasSettings(**dict(self._settings_cfg or {}))

        awgs = collections.OrderedDict([(self._awg_name, self.awg()),
                                        (self._ps_name, self.pulsestreamer())])
        unknown = [name for name in self.settings.ch_dict_full if name not in awgs]
        if unknown:
            raise ValueError('ch_dict_full of the mcas settings contains {}, but only {} are connected '
                             '(see awg_name / ps_name options).'.format(unknown, list(awgs)))

        # one source of truth for the marker -> ps output assignment
        awgs[self._ps_name].set_channel_map(self.settings.ps_channel_map())

        self.mcas = make_mcas_class(self.settings)
        self.mcas_dict = MultiChSeqDict(awgs, self.settings, mcas_class=self.mcas, debug_mode=self._debug_mode)
        # legacy scripts create sequences with the bare MultiChSeq class; they get these settings
        set_default_settings(self.settings)

    def on_deactivate(self):
        clear_default_settings(self.settings)
        try:
            self.mcas_dict.stop_awgs()
        except Exception as err:
            self.log.warning('Could not stop the awgs on deactivation: {}'.format(err))
        del self.mcas_dict