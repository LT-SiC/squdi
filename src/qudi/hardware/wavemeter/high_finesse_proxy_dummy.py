# -*- coding: utf-8 -*-

"""
Dummy of the HighFinesse wavemeter proxy (qudi.hardware.wavemeter.high_finesse_proxy.HighFinesseProxy).

It needs neither the wavemeter application nor wlmData.dll. Instead of the DLL callback, a background thread
produces simulated wavelengths and hands them to the connected wavemeter modules with
``module.process_new_wavelength(channel, wavelength_in_m, timestamp_in_s)``, exactly like the real proxy does.

The class is called ``HighFinesseProxy`` on purpose: qudi connectors match the *name* of the interface class, so every
module that asks for ``interface='HighFinesseProxy'`` (the wavemeter module, your logic modules) accepts this dummy
without changes. (A connector that is given the class object itself, like in ``high_finesse_pid.py``, would need
the string ``'HighFinesseProxy'`` instead.)

Simulated signal of a channel: base wavelength + slow random drift + piezo voltage * tuning + white noise.
If locking is switched on (toggle_locking), the drift of the lock channel is pulled to the reference wavelength.

Example config. All options of the real proxy can stay in the config, they are accepted (and mostly ignored):

wavemeter_proxy:
    module.Class: 'dummy.high_finesse_proxy_dummy.HighFinesseProxy'
    options:
        watchdog_interval: 1.0              # accepted, not used
        simulated_wavelengths_nm:           # optional: base wavelength per switch channel
            1: 620.0
            2: 637.2
        noise_nm: 1.0e-4                    # white noise per sample
        drift_nm: 2.0e-4                    # random walk step per sample
        lock_channel: 1                     # channel that reacts to lock and piezo voltage
        has_switch: True                    # False: behave like a wavemeter without multi-channel switch (only channel 1)
"""

import threading
import time
from typing import Dict, List, Set, Optional, Tuple

import numpy as np

from qudi.core.configoption import ConfigOption
from qudi.core.module import Base
from qudi.util.mutex import Mutex

SWITCHING_TIME_MS = 12   # same estimate as in the real proxy
DEFAULT_EXPOSURE_MS = 10.0


class HighFinesseProxy(Base):
    """Hardware-free stand-in for the HighFinesse proxy. See the module docstring."""

    # options of the real proxy: accepted so that the config block can be switched without editing it
    _watchdog_interval: float = ConfigOption(name='watchdog_interval', default=1.0)
    _wavemeter_executable_path: Optional[str] = ConfigOption(name='wavemeter_executable_path', default=None,
                                                             missing='nothing')
    _allow_direct_process_start: bool = ConfigOption(name='allow_direct_process_start', default=False,
                                                     missing='nothing')
    _allow_force_process_kill: bool = ConfigOption(name='allow_force_process_kill', default=False, missing='nothing')
    _restart_settle_time: float = ConfigOption(name='restart_settle_time', default=0.5, missing='nothing')

    # options of the dummy
    _simulated_wavelengths_nm: Dict[int, float] = ConfigOption(name='simulated_wavelengths_nm', default={1: 620.0},
                                                               missing='nothing')
    _default_wavelength_nm: float = ConfigOption(name='default_wavelength_nm', default=620.0, missing='nothing')
    _noise_nm: float = ConfigOption(name='noise_nm', default=1e-4, missing='nothing')
    _drift_nm: float = ConfigOption(name='drift_nm', default=2e-4, missing='nothing')
    _piezo_nm_per_volt: float = ConfigOption(name='piezo_nm_per_volt', default=1e-3, missing='nothing')
    _lock_channel: int = ConfigOption(name='lock_channel', default=1, missing='nothing')
    _has_switch: bool = ConfigOption(name='has_switch', default=True, missing='nothing')
    _seed: Optional[int] = ConfigOption(name='seed', default=None, missing='nothing')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._lock = Mutex()
        self._sim_lock = threading.RLock()

        self.error_in_callback: bool = False
        self._connected_instream_modules: Dict[object, List[int]] = {}   # module -> channels in the module's order
        self._active_channels: Set[int] = {1}
        self._exposure_ms: Dict[int, float] = {}
        self._measuring = False

        self._thread: Optional[threading.Thread] = None
        self._stop_event: Optional[threading.Event] = None

        # simulated laser / lock state
        self._rng = np.random.default_rng()
        self._offset_nm: Dict[int, float] = {}
        self._piezo_voltage = 0.0
        self._locked = False
        self._reference_nm = 0.0

        # simulated PID outputs (used by the HighFinesse PID module)
        self._pid_settings: Dict[Tuple[int, int], Tuple[float, int]] = {}
        self._pid_enabled = False
        self._setpoints: Dict[int, float] = {}
        self._manual_values: Dict[int, float] = {}

    # ----------------------------------------------------------------------------------------------------------
    # qudi module
    # ----------------------------------------------------------------------------------------------------------
    def on_activate(self) -> None:
        self._rng = np.random.default_rng(self._seed)
        self.log.warning('Using the DUMMY HighFinesse proxy: all wavelengths are simulated.')
        
    def on_deactivate(self) -> None:
        thread = self._thread
        self._stop_callback_if_running()
        if thread is not None:
            thread.join(timeout=1.0)
        self._connected_instream_modules = {}

    # ----------------------------------------------------------------------------------------------------------
    # API used by the wavemeter module (same names and signatures as the real proxy)
    # ----------------------------------------------------------------------------------------------------------
    def connect_instreamer(self, module, channels: List[int]):
        """Connect an instreamer module to the proxy. The proxy starts to push new samples into it."""
        if module in self._connected_instream_modules:
            self.log.warning('Instream module is already connected.')
            return
        with self._lock:
            not_connected_yet = set(channels) - self.get_connected_channels()
            for ch in not_connected_yet:
                self._activate_channel(ch)
            self._connected_instream_modules[module] = list(channels)
        if self._thread is None:
            self._activate_only_connected_channels()
            self._start_measurement()
            self._start_callback()

    def disconnect_instreamer(self, module):
        """Disconnect an instreamer module from the proxy."""
        if module not in self._connected_instream_modules:
            self.log.warning('Instream module is not connected and can therefore not be disconnected.')
            return
        with self._lock:
            channels_disconnecting_instreamer = set(self._connected_instream_modules.pop(module))
            if not self._connected_instream_modules:
                self._stop_callback()
            else:
                for ch in channels_disconnecting_instreamer - self.get_connected_channels():
                    self._deactivate_channel(ch)

    def restart_wlm_application(self, timeout: float = 30.0, start_silent: bool = True) -> None:
        """Simulated restart of the wavemeter application: streams are stopped, then reconnected."""
        remembered_streamers = list(self._connected_instream_modules.items())
        self.log.warning('Restarting the (simulated) HighFinesse WLM application.')
        for streamer, _ in remembered_streamers:
            streamer.stop_stream_watchdog()
        with self._lock:
            self._connected_instream_modules = {}
            self._stop_callback_if_running()
            self._measuring = False
        time.sleep(self._restart_settle_time)
        for streamer, _ in remembered_streamers:
            streamer.reapply_wavemeter_settings()
            streamer.start_stream()
        self.log.info('Simulated HighFinesse WLM application restart complete.')

    def sample_rate(self) -> float:
        """Estimated sample rate in Hz from the exposure times of the active channels and the switching time."""
        channels = self.get_active_channels() or [1]
        total_exposure = sum(self._exposure_ms.get(ch, DEFAULT_EXPOSURE_MS) for ch in channels)
        turnaround_time_ms = total_exposure + len(channels) * SWITCHING_TIME_MS
        return 1e3 / turnaround_time_ms

    def get_wavelength_m(self, ch: int) -> float:
        """Current wavelength of a switch channel in meters."""
        return 1e-9 * self._read_wavelength_nm(ch, advance=False)

    def set_exposure_time(self, ch: int, exp_time: float) -> None:
        self._exposure_ms[ch] = float(exp_time)

    def get_active_channels(self) -> List[int]:
        if not self._has_switch:
            return [1]
        return sorted(self._active_channels)

    def get_connected_channels(self) -> Set[int]:
        channels = set()
        for chs in self._connected_instream_modules.values():
            channels |= set(chs)
        return channels

    def stop_everything(self) -> None:
        self.log.warning('Stopping all streams.')
        streamers = list(self._connected_instream_modules)
        self._stop_callback_if_running()
        self._connected_instream_modules = {}
        for streamer in streamers:
            streamer.stop_stream_watchdog()

    # --- laser piezo and locking ---
    def get_laser_piezo_voltage(self, ch: int) -> float:
        return self._piezo_voltage

    def set_laser_piezo_voltage(self, voltage: float) -> None:
        self._piezo_voltage = float(voltage)

    def toggle_locking(self, state: bool) -> None:
        self._locked = bool(state)

    def set_reference_wavelength(self, wavelength: float) -> None:
        """Reference of the lock in nm."""
        self._reference_nm = float(wavelength)

    def get_reference_wavelength(self, offset=0) -> float:
        return self._reference_nm

    # ----------------------------------------------------------------------------------------------------------
    # API used by the HighFinesse PID module
    # ----------------------------------------------------------------------------------------------------------
    def set_pid_setting(self, port: int, setting: int, d_val: float = 0.0, i_val: int = 0) -> None:
        self._pid_settings[(port, setting)] = (d_val, i_val)

    def get_pid_setting(self, port: int, setting: int) -> Tuple[float, int]:
        return self._pid_settings.get((port, setting), (0.0, 0))

    def activate_channel(self, ch: int) -> None:
        self._activate_channel(ch)

    def start_measurement(self) -> None:
        self._start_measurement()

    def get_wavelength(self, ch: int) -> float:
        """Current wavelength in meters."""
        return self.get_wavelength_m(ch)

    def get_setpoint(self, port: int) -> float:
        return self._setpoints.get(port, 0.0)

    def set_setpoint(self, port: int, setpoint: float) -> None:
        self._setpoints[port] = float(setpoint)

    def set_manual_value(self, port: int, value: float) -> None:
        self._manual_values[port] = float(value)

    def get_pid_enabled(self) -> bool:
        return self._pid_enabled

    def set_pid_enabled(self, enabled: bool) -> None:
        self._pid_enabled = bool(enabled)

    def get_control_value(self, port: int) -> float:
        if self._pid_enabled:
            return self._piezo_voltage
        return self._manual_values.get(port, 0.0)

    # ----------------------------------------------------------------------------------------------------------
    # simulation
    # ----------------------------------------------------------------------------------------------------------
    def _base_wavelength_nm(self, ch: int) -> float:
        return float(self._simulated_wavelengths_nm.get(ch, self._default_wavelength_nm + 10.0 * (ch - 1)))

    def _read_wavelength_nm(self, ch: int, advance: bool) -> float:
        with self._sim_lock:
            base = self._base_wavelength_nm(ch)
            piezo_nm = self._piezo_nm_per_volt * self._piezo_voltage if ch == self._lock_channel else 0.0
            offset = self._offset_nm.get(ch, 0.0)
            if advance:
                offset += self._drift_nm * self._rng.normal()
                if self._locked and ch == self._lock_channel and self._reference_nm > 0:
                    # the lock pulls the wavelength to the reference
                    offset += 0.2 * ((self._reference_nm - base - piezo_nm) - offset)
                self._offset_nm[ch] = offset
            return base + offset + piezo_nm + self._noise_nm * self._rng.normal()

    def _generation_loop(self, stop_event: threading.Event) -> None:
        """Stands in for the callback of the DLL: cycles through the connected switch channels."""
        t0 = time.monotonic()
        while not stop_event.is_set():
            channels = sorted(self.get_connected_channels())
            if not channels:
                stop_event.wait(0.01)
                continue
            for ch in channels:
                if stop_event.is_set():
                    return
                wavelength_m = 1e-9 * self._read_wavelength_nm(ch, advance=True)
                timestamp = round(time.monotonic() - t0, 3)   # the wavemeter records timestamps in ms
                for module, module_channels in list(self._connected_instream_modules.items()):
                    if ch in module_channels:
                        try:
                            module.process_new_wavelength(ch, wavelength_m, timestamp)
                        except Exception:
                            self.log.exception('Error while processing simulated wavemeter callback.')
                            self.error_in_callback = True
                stop_event.wait(1e-3 * (self._exposure_ms.get(ch, DEFAULT_EXPOSURE_MS) + SWITCHING_TIME_MS))

    # ----------------------------------------------------------------------------------------------------------
    # protected
    # ----------------------------------------------------------------------------------------------------------
    def _activate_channel(self, ch: int) -> None:
        if not self._has_switch:
            if ch == 1:
                return
            raise RuntimeError(f'Cannot activate channel {ch}: wavemeter does not have a multi-channel switch.')
        self._active_channels.add(ch)

    def _deactivate_channel(self, ch: int) -> None:
        if not self._has_switch:
            if ch == 1:
                return
            raise RuntimeError(f'Cannot deactivate channel {ch}: wavemeter does not have a multi-channel switch.')
        self._active_channels.discard(ch)

    def _activate_only_connected_channels(self) -> None:
        connected_channels = self.get_connected_channels()
        if not connected_channels:
            raise RuntimeError('Cannot deactivate all channels.')
        for ch in connected_channels:
            self._activate_channel(ch)
        for ch in self.get_active_channels():
            if ch not in connected_channels:
                self._deactivate_channel(ch)

    def _start_measurement(self) -> None:
        self._measuring = True

    def _start_callback(self) -> None:
        self._stop_event = threading.Event()
        self._thread = threading.Thread(target=self._generation_loop, args=(self._stop_event,),
                                        name='wavemeter_dummy_callback', daemon=True)
        self._thread.start()
        if self.module_state() == 'idle':
            self.module_state.lock()
        self.log.debug('Started simulated callback procedure.')

    def _stop_callback(self) -> None:
        # No join here: the caller may hold the lock of an instreamer that the loop is waiting for.
        if self._stop_event is not None:
            self._stop_event.set()
        self._stop_event = None
        self._thread = None
        if self.module_state() == 'locked':
            self.module_state.unlock()
        self.log.debug('Stopped simulated callback procedure.')

    def _stop_callback_if_running(self) -> None:
        if self._thread is not None:
            self._stop_callback()