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