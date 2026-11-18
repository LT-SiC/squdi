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


class McasDictHolderInterface(Base):
    """Logic module that owns the AWG memory and creates sequences (``mcas_dict_holder``).

    This is the interface that ``queue_logic``, ``transition_tracker`` and ``gated_counter_logic`` connect to
    (``Connector(interface='McasDictHolderInterface')``). Implementing modules provide, after activation:

        mcas_dict   MultiChSeqDict; ``.awgs['2g']`` / ``.awgs['ps']`` are the hardware modules
        mcas        class that creates a new sequence: ``mcas(name=..., ch_dict={...})``
        settings    McasSettings (marker_alias, master_awg, ...)

    These are plain attributes, so there is nothing abstract to declare here; the class only has to be in the
    base classes of the implementing module for qudi to accept the connection.
    """
    _modtype = 'McasDictHolderInterface'
    _modclass = 'interface'


class AwgM8190Interface(Base):
    """Keysight M8190A arbitrary waveform generator.

    Besides the methods below, the module forwards every attribute of the low-level driver
    (``awg.ch[1].output``, ``awg.sample_frequency``, ...) so existing scripts keep working.
    """
    _modtype = 'AwgM8190Interface'
    _modclass = 'interface'

    @abstractmethod
    def clear_memories(self):
        """Delete all segments and reset the sequencer table of all channels."""
        pass

    @abstractmethod
    def restore_settings_from_file(self, filepath=None):
        """Restore the instrument settings from the newest stored settings file (or ``filepath``)."""
        pass

    @abstractmethod
    def dump_current_settings_to_file(self):
        """Store the current instrument settings in the settings folder."""
        pass

    @abstractmethod
    def send_begin(self):
        """Software trigger: start the (coupled) channels."""
        pass


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