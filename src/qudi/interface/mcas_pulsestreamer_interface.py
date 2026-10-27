# -*- coding: utf-8 -*-
"""
Interfaces of the MCAS logic (``McasDictHolderInterface``, implemented by ``mcas_dict_holder``) and of the
two hardware modules it connects to.

The style (``InterfaceMetaclass`` / ``abstractmethod``) follows the standard qudi interface files.
If the header of your existing ``interface/mcas_interface.py`` looks different (other import paths), copy
its import lines and ``_modtype``/``_modclass`` convention over to this file.
"""

from abc import abstractmethod
from qudi.core.module import Base

class McasPulseStreamerInterface(Base):
    """Swabian PulseStreamer used as slave of the AWG (digital markers for lasers, switches, ...)."""
    _modtype = 'McasPulseStreamerInterface'
    _modclass = 'interface'

    @abstractmethod
    def set_channel_map(self, channel_map):
        """Set {marker name: digital output number}."""
        pass

    @abstractmethod
    def setSequence(self, sequence, loops=-1, triggered=False, padding=[], run=True):
        """Upload a sequence [([marker names], duration_ns), ...]."""
        pass

    @abstractmethod
    def constant(self, pulse=(0, [], 0, 0)):
        """Output a constant pulse (time, [marker names], analog0, analog1)."""
        pass

    @abstractmethod
    def Night(self):
        """All outputs off."""
        pass