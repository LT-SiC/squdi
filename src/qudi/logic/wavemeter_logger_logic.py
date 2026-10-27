# -*- coding: utf-8 -*-

"""
This file contains the logic responsible for coordinating laser scanning.

Copyright (c) 2021, the qudi developers. See the AUTHORS.md file at the top-level directory of this
distribution and on <https://github.com/Ulm-IQO/qudi-iqo-modules/>

This file is part of qudi.

Qudi is free software: you can redistribute it and/or modify it under the terms of
the GNU Lesser General Public License as published by the Free Software Foundation,
either version 3 of the License, or (at your option) any later version.

Qudi is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY;
without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.
See the GNU Lesser General Public License for more details.

You should have received a copy of the GNU Lesser General Public License along with qudi.
If not, see <https://www.gnu.org/licenses/>.
"""
#! TODO WHEN we get an array with wavelengths from the wavemeter -- iterpolate the missing one (since we get batchezz -- we can interpolate already on the server side)
from PySide6 import QtCore
import numpy as np
import time

from qudi.core.connector import Connector
from qudi.core.configoption import ConfigOption
from qudi.core.module import LogicBase
from qudi.util.mutex import RecursiveMutex

from qudi.core.statusvariable import StatusVar

COUNT_DTYPE =  np.dtype([('wavelength', np.float64), ('counts', np.float64)])
WAVELENGTH_DTYPE = np.dtype([('wavelength', np.float64), ('time', np.float64)])
class WavemeterLoggerLogic(LogicBase):
    """This logic module gathers data from wavemeter and the counter logic.
    """


    sigUpdateSettings = QtCore.Signal(dict)
    sigFitUpdated = QtCore.Signal(object, str)
    # declare connectors
    wavemeter = Connector(interface='WavemeterInterface')
    timetagger = Connector(interface='TimeTaggerInterface', optional=True)
    _fit_config = StatusVar(name='fit_config', default=None)
    _fit_region = StatusVar(name='fit_region', default=[0, 1])

    _default_fit_configs = (
        {'name'             : 'Lorentzian',
         'model'            : 'Lorentzian',
         'estimator'        : 'Peak',
         'custom_parameters': None},

        {'name'             : 'Gaussian',
         'model'            : 'Gaussian',
         'estimator'        : 'Peak',
         'custom_parameters': None}
         
    )
    wavelength_buffer = 5000
    wavelengths_log = None
    average_times = 4
    default_settings = {
        'bin_width':20e6, #20 MHz
        'start_value':350e12, # 350 THz
        'stop_value':351e12 # 351 THz
    }
    _settings = StatusVar(name = 'wavelogger_settings', default=default_settings)
    current_wavelength = -1
    count_data = np.array([], dtype = COUNT_DTYPE)
    wavelengths = np.array([], dtype = WAVELENGTH_DTYPE)

    plot_x = []
    plot_y = []
    accumulated_data = []

    # config opts
    _logic_update_timing = ConfigOption('logic_query_timing', 600, missing='warn') # has to be larger than the count time
    # time tagger counter: fixed bins that are mapped onto the wavemeter samples by their timestamps
    _counter_bin_width = ConfigOption('counter_bin_width', 1e-3, missing='nothing')    # s
    _counter_window = ConfigOption('counter_window', 5.0, missing='nothing')           # s, longer than the update interval
    _counter_time_offset = ConfigOption('counter_time_offset', 0.0, missing='nothing') # s, newest wavemeter sample is this much older than the end of the counter window
    #sig_query_wavemeter = QtCore.Signal()
    sig_update_current_wavelength = QtCore.Signal(float)
    sig_update_data = QtCore.Signal(object,object)
    sig_toggle_log = QtCore.Signal(bool)
    
    def __init__(self, config, **kwargs):
        """ Create WavemeterLoggerLogic object with connectors.
        """
        super().__init__(config=config, **kwargs)
        self.start_toggled = False
        self.counter = 0
        self._counter_bin_s = 1e-3         # actual bin width of the counter in s
        self._prev_sample_time = None      # timestamp of the last wavemeter sample of the previous update
        # locking for thread safety
        self._thread_lock = RecursiveMutex()
        # internal min and max wavelength determined by the measured wavelength
    
    def _get_new_wavelength_data(self):
            data = np.asarray(self._wavemeter.get_wavelength_buffer())
            result = np.recarray(data.shape[0], dtype=WAVELENGTH_DTYPE)
            result.wavelength = data[:, 0]
            result.time = data[:, 1]
            return result
    
    def on_activate(self):
        """ Initialisation performed during activation of the module.
        """

        self._timetagger = self.timetagger()
        self._wavemeter = self.wavemeter()
        self._wavemeter.start_acquisition()
        self.count_time = self._wavemeter._measurement_timing

        #self._get_new_wavelength_data = lambda :  np.rec.array(np.array(self._wavemeter.get_wavelength_buffer()), dtype = WAVELENGTH_DTYPE)
        
        self.wavelengths = self._get_new_wavelength_data()
        
        if self._timetagger:
            self.determine_count_time()
            self.recalculate_histogram()
            self.configure_counter()

        

        #self.sig_query_wavemeter.connect(self.query_wavemeter, QtCore.Qt.QueuedConnection)
        # connect the signals in and out of the threaded object

        self.sigUpdateSettings.connect(self._udpate_settings)
        
        self._queryTimer = QtCore.QTimer()
        self._queryTimer.setInterval(self._logic_update_timing)
        # self._queryTimer.setSingleShot(False)
        self._queryTimer.timeout.connect(self.update_data, QtCore.Qt.QueuedConnection)     
        
        self._wavemeter.start_acquisition()
        self._acquisition_start_time = time.time()

        self._queryTimer.start()
        #self.sig_query_wavemeter.emit()

        

    def on_deactivate(self):
        """ Deinitialisation performed during deactivation of the module.
        """
        self._queryTimer = None
        # if self.module_state() != 'idle' and self.module_state() != 'deactivated':
        # self.stop_scanning()

    @QtCore.Slot()
    def update_data(self):
        self.wavelengths = self._get_new_wavelength_data() # calling for wavelengths with callback
        
        wavelengths = self.wavelengths[self.wavelengths.wavelength > 0]
        if len(wavelengths) > 0:   
            self.current_wavelength = wavelengths.wavelength.mean() *1e12 
        
        self._time_elapsed = time.time() - self._acquisition_start_time
        
        
        wavelengths = wavelengths[-self.wavelength_buffer:]
       
        count_data = None
        if self.start_toggled:
            count_data = self.update_histogram()
        self.sig_update_data.emit(wavelengths, count_data)

    @QtCore.Slot()
    def start_scan(self):
        self.accumulated_data = 0 # data
        #emit scan next line

    def empty_buffer(self):
        self.wavelengths = None
        self._prev_sample_time = None
        self._wavemeter.empty_buffer()
        self._acquisition_start_time = time.time()
        

    def determine_count_time(self):
        #OBSOLETE
        #get average time for the wavemeter server to send signal to the client
        for i in range(self.average_times):
            self.wavelengths = self._get_new_wavelength_data()
            count_time = self.wavelengths.time # calling for wavelengths with callback
            self.count_time = (self.count_time + count_time[-1]) / 2 # determine the average counting time
            # print("count time",count_time[-1])
            #!TODO delay from utils istead of sleep
            time.sleep(0.2 + self._logic_update_timing/1000) #! TODO safely determine the count time (update time should be for this function larger than the count time)
        if self.count_time > self._logic_update_timing / 1000 + 0.1:
            self._logic_update_timing = int((self.count_time + 0.1)*1000)
            
        return self.count_time
    
    def configure_counter(self):
        """
        The counter has a fixed number of fixed-width bins covering the last <counter_window> seconds. It does not
        depend on how many wavemeter samples arrive per update: update_histogram maps the counts onto the samples
        by their timestamps.
        """
        if not self._timetagger:
            return
        bin_width_ps = int(round(self._counter_bin_width * 1e12))
        n_values = int(np.ceil(self._counter_window / self._counter_bin_width))
        # the key of the bin width is 'bins_width' in the config of the time tagger module, pass both spellings
        self.counter = self._timetagger.counter(channels=self._timetagger._counter['channels'],
                                                bin_width=bin_width_ps, bins_width=bin_width_ps,
                                                n_values=n_values)
        # use the bin width the counter really has
        index = np.asarray(self.counter.getIndex(), dtype=float)
        if index.size > 1 and index[1] > index[0]:
            self._counter_bin_s = 1e-12 * (index[1] - index[0])
        else:
            self._counter_bin_s = 1e-12 * bin_width_ps
        self._prev_sample_time = None

    def _current_count_data(self):
        count_data = np.zeros(self.plot_x.shape[0], dtype=COUNT_DTYPE)
        count_data['wavelength'] = self.plot_x
        count_data['counts'] = self.plot_y
        return count_data

    def update_histogram(self):
        """
        Add the new wavemeter samples and the counts that were measured between them to the histogram.

        The counter delivers its last n bins (oldest -> newest, the newest bin ends 'now'), the wavemeter delivers
        an arbitrary number of samples with timestamps. The counts belonging to a sample are the counts between the
        previous sample and this one, taken from the cumulative counts of the counter bins.
        """
        cts = np.asarray(self.counter.getData()).sum(axis=0)       # counts per bin, oldest -> newest
        n_bins = len(cts)
        bin_s = self._counter_bin_s

        wl = np.asarray(self.wavelengths.wavelength, dtype=float) * 1e12   # Hz
        t = np.asarray(self.wavelengths.time, dtype=float)                  # s
        if len(t) == 0:
            return self._current_count_data()

        # also use the last sample of the previous update, so that no interval between two updates is lost
        has_prev = self._prev_sample_time is not None and self._prev_sample_time < t[0]
        t_all = np.concatenate(([self._prev_sample_time], t)) if has_prev else t
        self._prev_sample_time = t[-1]
        if len(t_all) < 2:
            return self._current_count_data()
        wl = wl if has_prev else wl[1:]                                     # one wavelength per interval

        # position of every sample time on the counter axis in units of bins: the newest sample is at the end
        pos = n_bins - (t_all[-1] + self._counter_time_offset - t_all) / bin_s
        cumulative = np.concatenate(([0.0], np.cumsum(cts)))
        counts_between = np.diff(np.interp(pos, np.arange(n_bins + 1), cumulative))
        inside_window = (pos[:-1] >= 0) & (pos[1:] <= n_bins)

        # histogram bin of every wavelength; samples outside the range or without a valid wavelength are skipped
        valid = inside_window & np.isfinite(wl) & (wl > 0)
        bin_idx = np.full(len(wl), -1, dtype=int)
        finite = np.isfinite(wl)
        bin_idx[finite] = np.rint((wl[finite] - self._settings['start_value']) / self._settings['bin_width']).astype(int)
        valid &= (bin_idx >= 0) & (bin_idx < len(self.cts_ys))

        # np.add.at, because several samples can fall into the same histogram bin
        np.add.at(self.cts_ys, bin_idx[valid], counts_between[valid])
        np.add.at(self.samples_num, bin_idx[valid], 1)

        self.plot_y = np.divide(self.cts_ys, self.samples_num, out=np.zeros_like(self.cts_ys),
                                where=self.samples_num != 0)
        return self._current_count_data()

    @QtCore.Slot(dict)
    def _udpate_settings(self, settings):
        if self.module_state() != 'locked':
            self._settings.update(settings)
            self.recalculate_histogram()
            # settings['mode'] # frequency or vac or air
        return 

    @QtCore.Slot(bool)
    def toggle_log(self, start):
        self.start_toggled = start
        with self._thread_lock:
            if start:
                self.module_state.lock()
                self.configure_counter()
                self.recalculate_histogram()
                self._queryTimer.start(int(self._logic_update_timing))
                self._acquisition_start_time = time.time()
                # self.sig_query_wavemeter.emit()
            else:
                self._queryTimer.stop()
                self.module_state.unlock()
                
                # self.sig_query_wavemeter.emit()
    
    def recalculate_histogram(self):
        if self.module_state() != 'locked':
                self.wlth_xs = np.arange(
                    self._settings['start_value'], 
                    self._settings['stop_value'], 
                    self._settings['bin_width']
                )
                self.cts_ys = np.zeros(len(self.wlth_xs))
                self.samples_num = np.zeros(len(self.wlth_xs))
                self.plot_x = self.wlth_xs
                self.plot_y = self.cts_ys

    def wavelength_to_freq(self, wavelength):
        if isinstance(wavelength, float):
            return 299792458.0 * 1e9 / wavelength
        wavelength = np.array(wavelength)
        aa = 299792458.0 * 1e9 * np.ones(wavelength.shape[0])
        freqs = np.divide(aa, wavelength, out=np.zeros_like(aa), where=wavelength!=0)
        return freqs
    def freq_to_wavelength(self, freq):
        if isinstance(freq, float):
            return 299792458.0 / freq
        freq = np.array(freq)
        aa = 299792458.0 * np.ones(freq.shape[0])
        freqs = np.divide(aa, freq, out=np.zeros_like(aa), where=freq!=0)
        return freqs