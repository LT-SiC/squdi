# coding=utf-8
from __future__ import print_function, absolute_import, division
__metaclass__ = type

import datetime
from pathlib import Path
import time
import os
import threading
import time
import traceback
from qudi.core.module import LogicBase
from qudi.core.connector import Connector
from qudi.core.configoption import ConfigOption
import multiprocess

import collections
import copy
import types
import numpy as np
from path import Path

class ODMRRefocuser(LogicBase):
    """
    Periodic ODMR refocus of the mw frequencies in the transition tracker (a NuclearOPs ODMR like the
    user script ODMR_Refocus, started automatically instead of by hand).

    When: once every <interval> seconds after the last refocus, independent of the user scripts. NuclearOPs does not
    have to call anything. The refocus is not started at the beginning of a script, but at the time it is due:

    * No script is running (queue idle, or between two scripts): the refocus runs right away. A refocus that
      became due while a script was running is done before the next script of the queue starts.
    * A script is running and its NuclearOPs has ``allow_periodic_ODMR_refocus = True`` (the default): the
      measurement is paused at its next safe point (start of an iteration, see NuclearOPs.check_manual_pause), the
      ODMR runs, then the measurement continues. The settings of the shared gated counter are restored.
    * A script is running and sets ``nuclear.allow_periodic_ODMR_refocus = False``: the refocus is delayed until
      that script has finished.

    The ODMR: the transitions are measured like in ODMR_Refocus (pulsed, mw_freq sweep, Lorentzian fit). If a
    transition shows no line (no fit, too little contrast, line at the edge of the sweep), the range is widened
    and only the missing transitions are measured again: ranges = [(span, step), ...] in MHz. Frequencies that
    were found are written to the transition tracker right away.

    The measurement is plotted live in the same plot window as every NuclearOPs script (PlotData(gui=True), counts
    versus mw frequency, with the fit at the end of every stage). The window has to be created in the GUI thread, which
    _MainThreadCaller takes care of. The windows of the last refocus stay open; the ones of the refocus before are
    closed when a new refocus starts. With plot=False no window is made.
    """
    DATA_FOLDER = r"D:/Data/NuclearOps"          # as in sequence_creation_helpers.create_nuclear
    DEFAULT_RANGES = [(3.0, 0.2), (10.0, 0.3)]    # (span, step) in MHz
    DEFAULT_PARAMETERS = collections.OrderedDict([
        ('trans', ['L', 'R', 'C']),
        ('sweeps', 2),
        ('t_read', 2.048),
        ('readout', 'A2'),
        ('init_time', 50),
        ('init_amp', 0.15),
        ('factor', 1),
        ('omega', 0.3),
        ('A2_power', 4),
        ('n_simultaneous', 40),
        ('confocal_refocus', None),       # None: refocus the confocal position during the ODMR if an optimizer is connected
    ])
    # settings of the gated counter trace that every NuclearOPs overwrites and that the paused script needs back
    TRACE_SETTINGS = ('analyze_type', 'number_of_simultaneous_measurements', 'analyze_sequence', 'binning_factor',
                          'average_results', 'consecutive_valid_result_numbers')
    
    queue_logic       = Connector(interface = 'QueueLogic')

    # periodic ODMR refocus of the mw frequencies (see ODMRRefocuser)
    _odmr_refocus_interval      = ConfigOption(name='odmr_refocus_interval', default=3600.0, missing='nothing')   # s, 0: off
    _odmr_refocus_ranges        = ConfigOption(name='odmr_refocus_ranges', default=None, missing='nothing')       # [[span, step], ...] in MHz
    _odmr_refocus_parameters    = ConfigOption(name='odmr_refocus_parameters', default=None, missing='nothing')   # overrides, see ODMRRefocuser.DEFAULT_PARAMETERS
    _odmr_refocus_min_contrast  = ConfigOption(name='odmr_refocus_min_contrast', default=2.0, missing='nothing')  # percent
    _odmr_refocus_min_snr       = ConfigOption(name='odmr_refocus_min_snr', default=3.0, missing='nothing')
    _odmr_refocus_pause_timeout = ConfigOption(name='odmr_refocus_pause_timeout', default=900.0, missing='nothing')
    _odmr_refocus_on_activation = ConfigOption(name='odmr_refocus_on_activation', default=False, missing='nothing')
    _odmr_refocus_plot          = ConfigOption(name='odmr_refocus_plot', default=True, missing='nothing')         # live plot window

    def __init__(self, config, **kwargs):
        """
        :param queue: the QueueLogic
        :param interval: seconds between two refocus runs, measured from the end of the last one. 0 switches it off.
        :param ranges: [(span, step), ...] in MHz, tried one after the other until all transitions are found
        :param parameters: overrides of DEFAULT_PARAMETERS
        :param min_contrast: minimum contrast of a line in percent
        :param min_snr: minimum height of the line in units of the standard deviation of the fit residual
        :param pause_timeout: seconds to wait until a running measurement has reached its safe point
        :param retry_interval: seconds until the next try after a refocus that did not find all transitions
        :param run_on_activation: refocus as soon as possible after the start, not only after one interval
        """
        super(ODMRRefocuser, self).__init__(config=config, **kwargs)
        self.retry_interval=900.0
        self.poll_interval=1.0

        self.enabled = True                       # periodic refocus can be switched off at run time
        self.last_result = None                   # summary of the last refocus
        #self._next_due = time.time() + (0.0 if run_on_activation else self._interval)
        self._shutdown = threading.Event()
        self._odmr_lock = threading.Lock()        # only one ODMR at a time
        self._abort = None
        self._delay_logged = False
        self._thread = None
        if self._odmr_refocus_interval > 0:
            self._thread = threading.Thread(target=self._loop, name='odmr_refocuser', daemon=True)
            self._thread.start()

    def on_activate(self):
        print("I AM NOW IN 'ON ACTIVATE'")
        self._q = self.queue_logic()
        self._interval = float(self._odmr_refocus_interval)
        
        self._ranges = [(float(span), float(step)) for span, step in (self._odmr_refocus_ranges or self.DEFAULT_RANGES)]
        self._parameters = collections.OrderedDict(self.DEFAULT_PARAMETERS)
        self._parameters.update(self._odmr_refocus_parameters or {})
        self._min_contrast = float(self._odmr_refocus_min_contrast)
        self._min_snr = float(self._odmr_refocus_min_snr)
        self._pause_timeout = float(self._odmr_refocus_pause_timeout)
        self._retry_interval = float(self.retry_interval)

        self._next_due = self.get_last_refocus_time() + (0.0 if self._odmr_refocus_on_activation else self._interval)
                
    def on_deactivate(self):
        self.close()
        
    # ------------------------------------------------------------------------------------------------------
    # public
    # ------------------------------------------------------------------------------------------------------
    @property
    def next_due(self):
        """Time (time.time()) at which the next refocus is due."""
        return self._next_due

    def is_due(self):
        return self.enabled and self._interval > 0 and not self._shutdown.is_set() and time.time() >= self._next_due

    def get_last_refocus_time(self):
        # Find folders matching the expected naming structure
        f = r"C:/Users/Erik Hesselmeier/Desktop/NuclearOpsData/29Si5/ODMR_Refocus_auto" # TODO get the TransitionTrackerLog here
        #TODO save fit result to tt log

        folders = [
            p for p in Path(f).iterdir()
            #p for p in Path(self._q.user_script_folder).iterdir() #TODO why does this not work?
            if p.is_dir()
        ]

        # Extract timestamps and select the newest folder
        def folder_timestamp(folder):
            timestamp_str = folder.name[:17]  # e.g. 20261028-h10m34s28
            dt = datetime.datetime.strptime(timestamp_str, "%Y%m%d-h%Hm%Ms%S")
            return dt.timestamp()

        newest_folder = max(folders, key=folder_timestamp)
        newest_time = folder_timestamp(newest_folder)
        return newest_time

    def refocus_now(self):
        """Make the refocus due now. It still waits for the hardware like the periodic one (permission, pause)."""
        self._next_due = 0.0
        if self._thread is None and not self._shutdown.is_set():
            self._interval = max(self._interval, 1.0)
            self._thread = threading.Thread(target=self._loop, name='odmr_refocuser', daemon=True)
            self._thread.start()

    def run_if_due(self):
        """Called by the queue thread between two scripts: do a due refocus before the next script starts."""
        if not self.is_due():
            return
        if self._q._hw_lock.acquire(False):
            try:
                self._run_refocus(None)
            except Exception:
                traceback.print_exc()
                self._next_due = time.time() + self._retry_interval
            finally:
                self._q._hw_lock.release()

    def close(self):
        self._shutdown.set()
        if self._abort is not None:
            self._abort.set()
        if self._thread is not None and self._thread is not threading.current_thread():
            self._thread.join(timeout=2.0)

    # ------------------------------------------------------------------------------------------------------
    # scheduling
    # ------------------------------------------------------------------------------------------------------
    def _loop(self):
        while not self._shutdown.wait(self.poll_interval):
            try:
                if self.is_due():
                    self._try_refocus()
            except Exception:
                traceback.print_exc()
                self._next_due = time.time() + self._retry_interval

    def _try_refocus(self):
        q = self._q
        if q._hw_lock.acquire(False):             # no script has the hardware: the queue is idle
            try:
                self._run_refocus(None)
            finally:
                q._hw_lock.release()
            return
        module_name = q._current_module_name()
        nuclear = q._script_nuclear(module_name) if module_name else None
        if nuclear is None:
            return                                # helper script, or the next script is just starting
        if not getattr(nuclear, 'allow_periodic_ODMR_refocus', True):
            if not self._delay_logged:
                q.log.info('ODMR refocus is due, but {} does not allow it during its measurement. '
                           'Delayed until the script has finished.'.format(module_name[10:]))
                self._delay_logged = True
            return
        if getattr(nuclear, 'manual_pause', False) or not q._measurement_running(nuclear):
            return                                # paused by hand, or just finishing
        if not self._pause(nuclear):
            return
        try:
            self._run_refocus(nuclear)
        finally:
            nuclear.external_pause = False

    def _pause(self, nuclear):
        """Ask the running measurement to pause at its next safe point and wait until it did."""
        nuclear.external_pause = True
        t0 = time.time()
        while time.time() - t0 < self._pause_timeout and not self._shutdown.is_set():
            if getattr(nuclear, 'is_paused', False):
                return True
            if not self._q._measurement_running(nuclear):
                break                             # it finished: the refocus follows between the scripts
            time.sleep(0.2)
        nuclear.external_pause = False
        if self._q._measurement_running(nuclear):
            self._q.log.warning('The measurement did not pause within {} s, ODMR refocus postponed.'.format(
                self._pause_timeout))
            self._next_due = time.time() + 60.0
        return False

    # ------------------------------------------------------------------------------------------------------
    # the refocus
    # ------------------------------------------------------------------------------------------------------
    def _run_refocus(self, main_nuclear):
        if not self._odmr_lock.acquire(False):
            return
        abort = multiprocess.Event()
        self._abort = abort
        self._close_windows(self._windows_previous)       # plots of the refocus before
        self._windows_previous = []
        self._windows_current = []
        state = self._snapshot()
        t0 = time.time()
        success = False
        try:
            print('Starting ODMR refocus.')
            self._q.log.info('Starting ODMR refocus.')
            self._stop_awgs()
            success = self._staged_odmr(abort, main_nuclear)
        except Exception:
            traceback.print_exc()
        finally:
            self._restore(state)
            self._stop_awgs()
            self._abort = None
            self._windows_previous = self._windows_current   # these plots stay open until the next refocus
            self._windows_current = []
            self._delay_logged = False
            self.last_result = {'success': success, 'finished': time.time(), 'duration': time.time() - t0}
            self._next_due = time.time() + (self._interval if success else min(self._retry_interval, self._interval))
            self._odmr_lock.release()
        self._q.log.info('ODMR refocus {} after {:.0f} s.'.format('finished' if success else 'did not find all transitions',
                                                                  time.time() - t0))

    def _staged_odmr(self, abort, main_nuclear):
        """Measure the missing transitions with growing range until every transition has been found."""
        tt = self._q.tt
        remaining = list(self._parameters['trans'])
        for stage, (span, step) in enumerate(self._ranges, 1):
            if abort.is_set() or self._shutdown.is_set():
                return False
            self._q.log.info('ODMR refocus stage {}/{}: transitions {}, range {} MHz, step {} MHz.'.format(
                stage, len(self._ranges), remaining, span, step))
            nuclear = self._build_nuclear(remaining, span, step)
            nuclear.run(abort)
            self._wait_for_measurement(nuclear, abort, main_nuclear)
            if abort.is_set():
                return False
            found = self._evaluate(nuclear, remaining, span, step)
            for transition, offset in found.items():
                attribute = 'mw_mixing_frequency_' + transition
                setattr(tt, attribute, getattr(tt, attribute) + offset)
                self._q.log.info('ODMR refocus: transition {} shifted by {:+.3f} MHz.'.format(transition, offset))
            remaining = [t for t in remaining if t not in found]
            if not remaining:
                return True
            self._q.log.warning('ODMR refocus: no line found for {} within {} MHz.'.format(remaining, span))
        self._q.log.error('ODMR refocus: no line found for {} in any range.'.format(remaining))
        return False

    def _wait_for_measurement(self, nuclear, abort, main_nuclear):
        q = self._q
        while q._measurement_running(nuclear):
            if (self._shutdown.is_set() or q._queue_thread.stop_request.is_set() or
                    (main_nuclear is not None and not q._measurement_running(main_nuclear))):
                abort.set()           # shutdown, or the user stopped the queue / the paused script ended
            time.sleep(0.2)

    def _evaluate(self, nuclear, transitions, span, step):
        """Fit the averaged counts. Returns {transition: offset in MHz} for every transition with a clear line."""
        pld = nuclear.pld
        try:
            pld._custom_default_settings = types.MethodType(self._odmr_plot_defaults, pld)
            pld.fit_function = 'lorentz'
            pld.set_custom_default_settings()
            pld.update_data_fit_results(pld.data_selected)
            df = pld.data_fit_results.df
            if hasattr(pld, '_gui'):
                try:
                    pld.update_plot_fit()              # show the fit in the plot window
                except Exception:
                    traceback.print_exc()
        except Exception:
            traceback.print_exc()
            return {}
        if 'trans' in df.columns:
            labels = list(df['trans'])
        else:
            labels = sorted(transitions)      # the fits are made in alphabetical order of the transitions
        found = {}
        for label, result in zip(labels, df['fit_result']):
            ok, center = self._line_found(result, span, step)
            self._q.log.info('ODMR refocus: transition {}: center {:+.3f} MHz, {}.'.format(
                label, center if center is not None else float('nan'), 'line found' if ok else 'no clear line'))
            if ok:
                found[label] = center
        return found

    def _line_found(self, result, span, step):
        """Is there a line in the fit: not at the edge of the sweep, enough contrast, enough signal to noise."""
        try:
            params = result.params
            center = float(params['center'].value)
            if abs(center) > 0.5 * span - 2.0 * step:
                return False, center
            if all(name in params for name in ('a', 'g', 'c')):
                a, g, c = float(params['a'].value), abs(float(params['g'].value)), float(params['c'].value)
                if g <= 0 or c == 0:
                    return False, center
                if abs(100.0 * a / (np.pi * g * c)) < self._min_contrast:
                    return False, center
                residual = getattr(result, 'residual', None)
                noise = float(np.std(residual)) if residual is not None else 0.0
                if noise > 0 and abs(a / (np.pi * g)) < self._min_snr * noise:
                    return False, center
                if not 0.5 * step <= g <= 0.5 * span:
                    return False, center
            return True, center
        except Exception:
            traceback.print_exc()
            return False, None

    # ------------------------------------------------------------------------------------------------------
    # the measurement (the settings of the user script ODMR_Refocus)
    # ------------------------------------------------------------------------------------------------------
    def _build_nuclear(self, transitions, span, step):
        from qudi.logic.NuclearOPs import NuclearOPs
        from qudi.logic.qudip_enhanced import data_handling
        import qudi.notebooks.UserScripts.helpers.sequence_creation_helpers as sch
        import qudi.notebooks.UserScripts.helpers.snippets_awg as sna
        import qudi.logic.mcas.elements as E

        q = self._q
        p = self._parameters
        script_path = os.path.join(q.user_script_folder, 'ODMR_Refocus_auto.py')   # only used for the save location

        def ret_mcas(self, current_iterator_df, sequence_name=None):
            sequence_name = 'NuclearOps' if sequence_name is None else sequence_name
            mcas = self.queue._awg.mcas(name=sequence_name, ch_dict={'2g': [1, 2], 'ps': [1]})
            trans = {}
            for idx, _I_ in current_iterator_df.iterrows():
                for t in ['L', 'C', 'R']:
                    for i in [1, 2]:
                        trans[t + str(i)] = self.queue.tt.mfl(
                            td={self.queue._transition_tracker.si29_list[0]: [-0.5, 0.5]}, ms_trans=t)[i - 1]
                state = 'p12' if 'R' in _I_['trans'] else 'm12'
                sna.repump(mcas, 10)
                sna.electron_init(mcas, state, _I_['init_time'], [trans['L1'], trans['L2']], [trans['R1'], trans['R2']],
                                  segment_length=10, max_amp=_I_['init_amp'])
                mcas.start_new_segment(name='sequence', loop_count=1)
                mcas.asc(length_mus=E.round_length_mus_to_x_multiple_ps(1))

                amp, pi_dur, pi2_dur = sna.get_hardcoded_e_values_for_control(_I_['trans'] + '2')
                amp = amp / _I_['factor']
                pi_dur = pi_dur * _I_['factor']
                t = _I_['trans']
                freq1 = np.mean([trans[t + '1'], trans[t + '2']]) + _I_['mw_freq']

                mcas.asc(length_mus=E.round_length_mus_to_x_multiple_ps(0.256), gateMW=True, name='gateMW')
                mcas.asc(length_mus=10, gateMW=True, name='gateMW')
                sna.electron_rabi(mcas, new_segment=True, length_mus=E.round_length_mus_to_x_multiple_ps(pi_dur),
                                  gateMW=True, amplitudes=[amp], frequencies=[freq1], mixer_deg=[-90],
                                  pulseshape='sinehermite')
                if 'C' in _I_['trans']:
                    amp_project = self.queue.tt.RP('e_rabi_ou350deg-90-R2', omega=_I_['omega']).amp
                    pi_dur_project = E.round_length_mus_to_x_multiple_ps(
                        self.queue.tt.RP('e_rabi_ou350deg-90-L2', omega=_I_['omega']).pi)
                    mcas.asc(length_mus=E.round_length_mus_to_x_multiple_ps(0.256), gateMW=True, name='gateMW')
                    sna.electron_rabi(mcas, new_segment=True, length_mus=E.round_length_mus_to_x_multiple_ps(pi_dur_project),
                                      gateMW=True, amplitudes=[amp_project, amp_project],
                                      frequencies=[trans['L1'], trans['L2']], mixer_deg=[-90, -90],
                                      pulseshape='sinehermite')
                nuc = 'ple_A2' if _I_['readout'] == 'A2' else 'ple_A1'
                sna.ssr(mcas=mcas, queue=self.queue, frequencies=[3000], wait_dur=0.0, robust=False, nuc=nuc,
                        mixer_deg=-90, eom_ampl=0.0, step_idx=0,
                        laser_dur=E.round_length_mus_to_x_multiple_ps(_I_['t_read']))
                mcas.asc(length_mus=E.round_length_mus_to_x_multiple_ps(0.512), name='sequence wait 2')
            self.queue._gated_counter.set_n_values(mcas, self.number_of_simultaneous_measurements)
            return mcas

        def create_nuclear():
            nuc = NuclearOPs()
            nuc.make_save_location_params(script_path=script_path, folder=self.DATA_FOLDER, sub_folder_kw="UserScripts")
            title = "NuclearOPs{}_{}".format(
                nuc.file_name, datetime.datetime.strftime(nuc.date_of_creation, nuc.__TITLE_DATE_FORMAT__))
            nuc.pld = data_handling.PlotData(title=title, gui=self._plot)    # the plot window is made here
            return nuc

        # Qt widgets (the plot window) can only be created in the GUI thread
        nuclear = self._main_thread.call(create_nuclear) if self._plot else create_nuclear()
        self._windows_current.append(nuclear)
        nuclear.file_notes = ''
        nuclear.queue = q
        sch.settings(nuclear=nuclear, ret_mcas=ret_mcas, analyze_sequence=[['result', '>', 1, 1, 0, 1]], pdc={},
                     meas_code='# ODMR refocus of the queue (ODMRRefocuser in queue_logic.py)\n# {}\n'.format(dict(p)),
                     script_path=script_path)

        confocal_refocus = p['confocal_refocus']
        if confocal_refocus is None:
            confocal_refocus = getattr(q, '_optimizer_runner', None) is not None
        nuclear.x_axis_title = 'Freq [MHz]'
        nuclear.analyze_type = 'average'
        nuclear.save_smartly = False
        nuclear.do_ple_refocusA1 = False
        nuclear.do_ple_refocusA2 = False
        nuclear.refocus_cw_odmr = False
        nuclear.refocus_pulsed_odmr = False
        nuclear.do_confocal_repump_refocus = False
        nuclear.do_confocal_A1A2_refocus = bool(confocal_refocus)
        nuclear.do_confocal_A2MW_refocus = False
        nuclear.check_A2_power = False
        nuclear.do_repump = False
        nuclear.ple_refocus_interval = 200
        nuclear.confocal_refocus_interval = 200
        nuclear.odmr_refocus_interval = 1800
        nuclear.allow_periodic_ODMR_refocus = False       # never refocus during a refocus
        q._gated_counter.trace.consecutive_valid_result_numbers = [0]
        q._gated_counter.trace.average_results = False
        q._gated_counter.readout_duration = 15 * 1e6
        nuclear.pld.fit_function = 'lorentz'
        # applied by the plot at every new data point: counts versus mw frequency, averaged over the sweeps
        nuclear.pld._custom_default_settings = types.MethodType(self._odmr_plot_defaults, nuclear.pld)
        nuclear.hashed = False
        nuclear.debug_mode = False

        mw_freq = np.arange(-span / 2.0, span / 2.0, step)
        nuclear.parameters = collections.OrderedDict((
            ('sweeps', range(int(p['sweeps']))),
            ('A2_power', [p['A2_power']]),
            ('omega', [p['omega']]),
            ('t_read', [p['t_read']]),
            ('readout', [p['readout']]),
            ('init_time', [p['init_time']]),
            ('init_amp', [p['init_amp']]),
            ('factor', [p['factor']]),
            ('trans', list(transitions)),
            ('mw_freq', mw_freq),
        ))
        nuclear.number_of_simultaneous_measurements = int(min(int(p['n_simultaneous']), len(mw_freq)))
        return nuclear
    
    def _odmr_plot_defaults(pld):
        """Plot of the ODMR refocus: counts versus mw frequency, averaged over the sweeps."""
        pld.x_axis_parameter_list.update_selected_value('mw_freq')
        pld.average_parameter_list.update_selected_data(['sweeps'])
        pld.observation_list.update_selected_data(['average_counts'])

    # ------------------------------------------------------------------------------------------------------
    # shared hardware state
    # ------------------------------------------------------------------------------------------------------
    def _snapshot(self):
        """The ODMR overwrites settings of the shared gated counter; a paused script needs them back."""
        gated_counter = self._q._gated_counter
        trace = getattr(gated_counter, 'trace', None)
        state = {'readout_duration': copy.deepcopy(getattr(gated_counter, 'readout_duration', None)), 'trace': {}}
        for name in self.TRACE_SETTINGS:
            try:
                state['trace'][name] = copy.deepcopy(getattr(trace, name))
            except Exception:
                pass
        return state

    def _restore(self, state):
        gated_counter = self._q._gated_counter
        try:
            if state['readout_duration'] is not None:
                gated_counter.readout_duration = state['readout_duration']
            for name, value in state['trace'].items():
                setattr(gated_counter.trace, name, value)
        except Exception:
            traceback.print_exc()

    def _close_windows(self, nuclears):
        for nuclear in nuclears:
            try:
                if hasattr(nuclear.pld, '_gui'):
                    nuclear.pld.gui.close_gui()
            except Exception:
                pass

    def _stop_awgs(self):
        try:
            self._q._awg.mcas_dict.stop_awgs()
        except Exception:
            pass