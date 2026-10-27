# -*- coding: utf-8 -*-
"""
qudi hardware module for the Keysight M8190A AWG.

All SCPI communication lives in ``m8190a_driver.AWG``. This module owns one driver instance, creates it in
``on_activate`` (config options instead of the legacy global settings) and closes it in ``on_deactivate``.

To keep every legacy call working (``md.awgs['2g'].ch[1].output = 1``, ``md.awgs['2g'].run = False``,
``md.awgs['2g'].sample_frequency`` ...) attribute reads and writes that are not defined on this module are
forwarded to the driver.

Example config:

    m8190a:
        module.Class: 'keysight.m8190a.KeysightM8190A'
        address: 'TCPIP0::localhost::inst0::INSTR'
        name: '2g'
        channels: [1, 2]
        settings_folder: 'C:/src/squdi/src/qudi/hardware/keysight/hardware_settings'
"""
import os

#from qudi.core.module import Base
from qudi.core.configoption import ConfigOption
from qudi.interface.mcas_keysight_interface import AwgM8190Interface

from .m8190a_driver import AWG, DEFAULT_SETTINGS_FOLDER

# the legacy code hardcoded this path; keep it as default on Windows
_LEGACY_VISA_LIBRARY = r"C:\Windows\System32\visa64.dll" if os.name == 'nt' else None


#class KeysightM8190A(Base, AwgM8190Interface):
class KeysightM8190A(AwgM8190Interface):
    """Keysight M8190A AWG (SCPI over VISA)."""

    _address = ConfigOption('address', missing='error')
    _awg_name = ConfigOption('name', default='2g', missing='nothing')
    _channels = ConfigOption('channels', default=[1, 2], missing='nothing')
    _visa_library = ConfigOption('visa_library', default=_LEGACY_VISA_LIBRARY, missing='nothing')
    _settings_folder = ConfigOption('settings_folder', default=DEFAULT_SETTINGS_FOLDER, missing='nothing')
    _timeout = ConfigOption('timeout', default=10000, missing='nothing')  # ms

    def on_activate(self):
        self._awg = AWG(address=self._address,
                        name=self._awg_name,
                        channel_numbers=list(self._channels),
                        visa_library=self._visa_library,
                        settings_folder=self._settings_folder,
                        timeout=self._timeout)

    def on_deactivate(self):
        awg = self.__dict__.get('_awg')
        if awg is None:
            return
        try:
            awg.run = False  # do not leave the instrument playing
        except Exception as err:
            self.log.warning('Could not stop {} on deactivation: {}'.format(self._awg_name, err))
        try:
            awg.awg_visa_device.close()
        except Exception as err:
            self.log.warning('Could not close VISA session of {}: {}'.format(self._awg_name, err))
        self._awg = None

    @property
    def awg(self):
        """The low-level driver instance."""
        return self._awg

    # --- interface -------------------------------------------------------------------------------------------------
    def clear_memories(self):
        self._awg.clear_memories()

    def restore_settings_from_file(self, filepath=None):
        self._awg.restore_settings_from_file(filepath)

    def dump_current_settings_to_file(self):
        self._awg.dump_current_settings_to_file()

    def send_begin(self):
        self._awg.send_begin()

    # --- forward everything else to the driver ---------------------------------------------------------------------
    def __getattr__(self, name):
        # only called when normal lookup fails
        if name.startswith('__') or name == '_awg':
            raise AttributeError(name)
        awg = self.__dict__.get('_awg')
        if awg is None:
            raise AttributeError("'{}' has no attribute '{}' (driver not active)".format(type(self).__name__, name))
        return getattr(awg, name)

    def __setattr__(self, name, value):
        # forward writes of driver properties (run, sample_frequency, ...) that this class does not define itself
        awg = self.__dict__.get('_awg')
        if awg is not None and not name.startswith('_') and not hasattr(type(self), name) \
                and isinstance(getattr(type(awg), name, None), property):
            setattr(awg, name, value)
        else:
            super().__setattr__(name, value)
