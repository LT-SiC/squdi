# coding=utf-8
from __future__ import print_function, absolute_import, division
__metaclass__ = type

# ----------------------------
# Original imports (kept)
# ----------------------------
import sys, os
import imp

import zipfile

from PySide6.QtCore import Signal, QObject, Qt

import qudi.logic.misc as misc
import datetime
import os
import pickle
import sys
import threading
import time
import traceback
from qudi.core.module import LogicBase
from qudi.core.connector import Connector
import multiprocess
from queue import Queue   
import shutil

import collections
import collections.abc
# import qudi.logic.odmr_nops_logic as odmr; importlib.reload(odmr) # FIXME connect via connector (really?)
from qudi.util.mutex import Mutex

# ----------------------------
# Additions for GUI adapter
# ----------------------------
import uuid

# Lightweight Status enum for GUI
try:
    # Python 3 Enum exists
    from enum import Enum
except Exception:
    Enum = object

#QUDI_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

class Status(Enum):
    QUEUED = "Queued"
    RUNNING = "Running"
    PAUSED = "Paused"
    COMPLETED = "Completed"
    ERROR = "Error"
    ABORTED = "Aborted"

# @dataclass
# class ScriptTask:
#     id: str
#     original_path: Path
#     queued_path: Path
#     status: Status = Status.QUEUED
#     process: Optional[QtCore.QProcess] = None
#     thread: Optional[threading.Thread] = None
#     worker: Optional[object] = None
#     pid: Optional[int] = None
#     stdout: str = ""
#     stderr: str = ""
#     start_time: Optional[datetime] = None
#     end_time: Optional[datetime] = None
#     accumulated_time: float = 0.0
#     pause_start: Optional[datetime] = None
#     is_embedded: bool = False

# Task representation used for GUI signals
class ScriptTask:
    def __init__(self, id, module_name, pd, queued_time=None,original_path="",queued_path=""):
        self.id = id
        self.module_name = module_name
        self.pd = pd or {}
        self.status = Status.QUEUED
        self.start_time = None
        self.end_time = None
        self.accumulated_time = 0.0
        self.queued_time = queued_time or datetime.datetime.now()
        self.is_embedded = True
        self.original_path=original_path
        self.queued_path=queued_path
        self.saved_dir = None  # data folder of this run, known once the measurement has started

    def __repr__(self):
        return "<ScriptTask id={} module={} status={}>".format(self.id, self.module_name, getattr(self.status, "value", self.status))

# QObject wrapper for signals to avoid metaclass issues
class QueueSignals(QObject):
    task_added = Signal(object)    # emits ScriptTask
    task_updated = Signal(object)  # emits ScriptTask
    log_output = Signal(str)       # emits log text

class OptimizerRunner(QObject):
    """
    Runs the scanning optimizer (e.g. xy-scan, fit, z-scan, fit) on behalf of a worker thread and waits for its end
    without polling and without blocking any Qt event loop.

    * The optimization is started through a queued signal, so ScanningOptimizeLogic.start_optimize runs in the
      thread of the optimizer module, exactly as if the optimize button of the scanner GUI had been pressed.
      The scanner GUI therefore blocks itself (sigOptimizeStateChanged) and is released again afterwards.
    * The end is reported by sigOptimizeStateChanged(False, ...), which sets a threading.Event.

    run() blocks, so call it only from a plain worker thread (e.g. the NuclearOPs measurement thread), never from
    the GUI thread or from the thread of a logic module.
    """
    _sigStart = Signal()
    _sigStop = Signal()

    def __init__(self, optimize_logic):
        super().__init__()
        self._logic = optimize_logic
        self._finished = threading.Event()
        self._sigStart.connect(optimize_logic.start_optimize, Qt.ConnectionType.QueuedConnection)
        self._sigStop.connect(optimize_logic.stop_optimize, Qt.ConnectionType.QueuedConnection)
        # direct: the handler only sets an Event, so it is safe to run in the thread of the optimizer
        optimize_logic.sigOptimizeStateChanged.connect(self._on_state_changed, Qt.ConnectionType.DirectConnection)

    def close(self):
        for disconnect in (lambda: self._logic.sigOptimizeStateChanged.disconnect(self._on_state_changed),
                           lambda: self._sigStart.disconnect(),
                           lambda: self._sigStop.disconnect()):
            try:
                disconnect()
            except Exception:
                pass

    def _on_state_changed(self, is_running, position=None, fit_data=None):
        if not is_running:
            self._finished.set()

    def _stop(self):
        self._sigStop.emit()
        self._finished.wait(10.0)

    def run(self, abort=None, timeout=300.0, start_timeout=10.0):
        """
        Run one complete optimization and wait for it.

        :param abort: optional Event; if it is set the optimization is stopped
        :param timeout: seconds after which the optimization is stopped
        :param start_timeout: seconds to wait for the optimizer to actually start (e.g. it does not if a scan is running)
        :return: True if the optimization ended on its own (also if a fit failed, see optimal_position of the
                 optimize logic), False if it was stopped, timed out or did not start.
        """
        t0 = time.time()
        # an optimization that is already running (e.g. started with the GUI button) has to end first
        self._finished.clear()
        while self._logic.optimizer_running:
            if (abort is not None and abort.is_set()) or time.time() - t0 > timeout:
                return False
            self._finished.wait(0.2)

        self._finished.clear()
        self._sigStart.emit()
        t_start = time.time()
        seen_running = False
        while not self._finished.wait(0.1):
            seen_running = seen_running or self._logic.optimizer_running
            if not seen_running and time.time() - t_start > start_timeout:
                self._logic.log.warning('The optimizer did not start (is a scan running?).')
                return False
            if abort is not None and abort.is_set():
                self._stop()
                return False
            if time.time() - t0 > timeout:
                self._logic.log.warning('The optimizer did not finish within {} s, stopping it.'.format(timeout))
                self._stop()
                return False
        return True

# ----------------------------
# Original ScriptQueueStep & ScriptQueueList (kept as-is)
# ----------------------------
class ScriptQueueStep:
    def __init__(self, name, pd):
        self.name = name
        self.pd = pd


class ScriptQueueList(collections.abc.MutableSequence):
    def __init__(self, oktypes, list_owner, *args):
        self.oktypes = oktypes
        self.list_owner = list_owner
        self._list = list()
        self.extend(list(args))

    @property
    def list(self):
        return self._list

    @list.setter
    def list(self, val):
        """
        inefficient, calls script_queue_changed multiple times. In practice not relevant.
        """
        self._list = []
        if len(val) == 0:
            self.list_owner.script_queue_changed()
        else:
            try:
                for i in val:
                    self.append(i)
            except Exception:
                self._list = []
                self.list_owner.script_queue_changed()
                exc_type, exc_value, exc_tb = sys.exc_info()
                traceback.print_exception(exc_type, exc_value, exc_tb)

    def check(self, val):
        if not isinstance(val, self.oktypes):
            raise TypeError("list item {} is not allowed, as it can not be found in {}".format(val, self.oktypes))

    # def check_duplicate(self, v):
    #     duplicates = [item.name for item in self.list if item.name == v.name]
    #     if len(duplicates) > 0:
    #         raise Exception('Error: {}, {}, {}'.format(duplicates, self.list, v))

    def set_parent(self, v):
        v.parent = self.list_owner

    def __len__(self):
        return len(self.list)

    def __getitem__(self, i):
        return self.list[i]

    def __delitem__(self, i):
        del self.list[i]
        self.list_owner.script_queue_changed()

    def __setitem__(self, i, v):
        raise NotImplementedError
        # self.check(v)
        # self.check_duplicate(v)
        # self.list[i] = v
        # self.list_owner.script_queue_changed(i, v)

    def insert(self, i, v):
        if i != len(self.list):
            raise Exception('Only appending and popping items allowed')
        self.check(v)
        # self.check_duplicate(v)
        self.list.insert(i, v)
        self.list_owner.script_queue_changed()

    def __str__(self):
        return str(self.list)

    def __repr__(self):
        return str(self.list)


# ----------------------------
# Main queue_logic (original preserved, with adapter additions)
# ----------------------------
class QueueLogic(LogicBase):
    # declare connections
    mcas_dict_holder    = Connector(interface='McasDictHolderInterface')
    transition_tracker  = Connector(interface = 'TransitionTracker')
    gated_counter       = Connector('GatedCounter')

    # make some modules optional. This will make them "None"
    # This will raise 'NoneType' object has no attribute ...
    # errors if the modules are called from other scripts. e.g.
    # when NuclearOps calls queue.optimize_logic
    optimize_logic              = Connector(interface = 'ScanningOptimizeLogic', optional = True)
    PLE_logic                   = Connector("LaserScannerLogic", optional = True)
    currentmeasurementlogic     = Connector("CurrentMeasurementLogic", optional = True)
    biaslogic                   = Connector("BiasLogic", optional = True)
    poimanagerlogic             = Connector('PoiManagerLogic', optional = True)
    powerstabilization_logic    = Connector("PowerStabilizationLogic", optional = True)
    counterlogic1               = Connector("CounterLogic", optional = True)


    update_selected_user_script_combo_box_signal = Signal(collections.OrderedDict)
    update_queue_list = Signal(collections.OrderedDict)
    user_script_list = misc.ret_property_array_like_typ('user_script_list', str)
    guis = []  #stores names of all open guis (later on used to dump them periodically)
    _StopTimeout = 60.

    __TIME_FORMAT_STR__ = '%Y%m%d-h%Hm%Ms%S'

    # smiq_visa_device = 'GPIB0::28::INSTR'
    # app_dir = r'D:/Python/pi3diamond'
    # log_dir = '{}/log/'.format(app_dir)
    # log_archive_dir = '{}/log/archive/'.format(app_dir)
    # log_single_val_dir = '{}/log/single_values/'.format(app_dir)
    # log_tmp = '{}/log/temp/'.format(app_dir)

    def _optional_module(self, name):
        """Return the connected module, or None (with a warning) if it is not in the config."""
        try:
            module = getattr(self, name)()
        except Exception:
            module = None
        if module is None:
            self.log.warning("Optional module '{}' is not connected in the config; "
                            "scripts that need it will not work.".format(name))
        return module

    def __init__(self, config , **kwargs):
        super(QueueLogic, self).__init__(config=config, **kwargs)
        self._threadlock=Mutex()
        self.script_history = []

        # ----------------------------
        # Adapter state for new GUI
        # ----------------------------
        self.signals = QueueSignals()   # exposes task_added, task_updated, log_output
        self.tasks = []                 # list[ScriptTask] visible to GUI
        self._task_by_id = {}           # id -> ScriptTask
        self._task_by_module = {}       # module_name -> ScriptTask (module names are unique in this design)
        self._monitor_thread = None
        self._monitor_stop_event = threading.Event()
        self._last_script_history_len = 0
        # set by abort_task() when only the running script should stop and the queue should go on
        self._abort_current_only = False
        # guards current_script / stop_request / script_queue between the queue thread and GUI calls
        self._control_lock = threading.RLock()

    def on_activate(self):

        # crucial modules
        self._awg                       = self.mcas_dict_holder()
        self._transition_tracker        = self.transition_tracker()
        self._gated_counter             = self.gated_counter()

        # optional modules
        self._optimizer                 = self._optional_module('optimize_logic')
        self._optimizer_runner          = OptimizerRunner(self._optimizer) if self._optimizer is not None else None
        self._PLE_logic                 = self._optional_module('PLE_logic')
        self._currentmeasurementlogic   = self._optional_module('currentmeasurementlogic')
        self._biaslogic                 = self._optional_module('biaslogic')
        self._powerstabilization_logic  = self._optional_module('powerstabilization_logic')
        self._poimanagerlogic           = self._optional_module('poimanagerlogic')
        self._counter                   = self._optional_module('counterlogic1')
        
        self.tt = self._transition_tracker # FIXME give the already correct name in lines 253. Maybe both names are used in other files
        #self.create_odmr()  #only logic (no gui)
        # odmr should be run via NucOps refocus script
        # data should be tracked and visualized via TT logic and gui
        # create_odmr could then be used to keep a global tracking time 
        # of odmr refocus. Such that it does not refocus before each measurement
        # or after a fixed measurement time but globally once an hour.
        self.init_run()
        self.write_standard_awg_sequences()

    def on_deactivate(self):
        if getattr(self, '_optimizer_runner', None) is not None:
            self._optimizer_runner.close()
        # stop task monitor thread gracefully if active
        try:
            self._monitor_stop_event.set()
            if self._monitor_thread and self._monitor_thread.is_alive():
                self._monitor_thread.join(timeout=1.0)
        except Exception:
            pass
        # pass
        #FIXME destroy me gently

    def run_optimizer(self, abort=None, timeout=300.0):
        """
        Refocus with the scanning optimizer (as configured in the scanner GUI) and wait until it is finished.
        Call from a worker thread only (see OptimizerRunner.run). Returns False if it did not finish properly.
        """
        if self._optimizer_runner is None:
            raise RuntimeError("run_optimizer: 'optimize_logic' is not connected in the config.")
        return self._optimizer_runner.run(abort=abort, timeout=timeout)

    @property
    def md(self):
        return self._mcas_dict#

    @property
    def gui(self):
        return self._gui

    # def restart_timetagger(self):
    #     import TimeTaggerHandler
    #     reload(TimeTaggerHandler)
    #     self._timetagger = TimeTaggerHandler.init_timetagger()

    def init_run(self):
        self.user_script_folder = r"C:/src/squdi/src/qudi/notebooks/UserScripts"
        #self.user_script_folder = QUDI_DIR+"/notebooks/UserScripts/29Si5"
        self._script_queue = ScriptQueueList(oktypes=(ScriptQueueStep), list_owner=self)
        self.q = Queue() # use connector
        self.run_thread()

        # start the monitor thread that observes current_script/script_history
        # This allows emitting task_updated events without changing run()
        try:
            self._monitor_stop_event.clear()
            self._monitor_thread = threading.Thread(target=self._monitor_tasks_loop, name="QueueLogicMonitor", daemon=True)
            self._monitor_thread.start()
        except Exception:
            # non-fatal; continue
            pass

        # self.track_memory_usage_thread()

    @property
    def script_queue(self):
        return self._script_queue
    @property
    def nowstr(self):
        return datetime.datetime.now().strftime('%Y%m%d-h%Hm%Ms%S')

    @property
    def nowstr_colon(self):
        return datetime.datetime.now().strftime('%Y/%m/%d-%H:%M:%S')

    @property
    def nowstr_pd(self):
        return datetime.datetime.now().strftime('%Y-%m-%d-%H:%M:%S')

    @property
    def awgs(self):
        return self._mcas_dict.awgs

    ####################################################################################################################
    # dump and restore
    ####################################################################################################################

    def persistent_file_name(self, model):
        if hasattr(model, 'pi3d_dump_filename'):
            return self.log_dir + model.pi3d_dump_filename
        return self.log_dir + str(model.__class__).replace('>', '').replace('<',

                                                                            '') + '.pyd'  # windows does not allow '>' and '<' in filenames
    #
    def restore(self, model, fp=None):
        filename = self.persistent_file_name(model) if fp is None else fp

        if os.access(filename, os.F_OK):

            self.log.info('Restoring state of ' + model.__str__() + '\nfrom ' + filename + '..')

            try:
                a = pickle.load(open(filename, 'rb'))
                a = a if type(a) is dict else a.__getstate__()
                model.set_items(a)
                self.log.info('[DONE1]')

            except Exception as inst:
                self.log.exception(str(inst))
                self.log.warning('[FAILED]')
                raise inst

    def dump(self, model):
        filename = self.persistent_file_name(model)
        self.log.info('attempting to save state of ' + model.__str__() + '\nto ' + filename + '..', )
        try:
            fil = open(filename, 'wb')
            pickle.dump(model.__getstate__(), fil)
            fil.close()
            self.log.info('[DONE]')
        except Exception:
            self.log.exception(str(Exception))
            self.log.warning('[FAILED]')

    # @property
    # def current_nuclear(self):
    #     l = [i for i in self.__dict__ if 'Nuclear' in i]
    #     df = pd.DataFrame({'attr_name': l, 'date': [datetime.datetime.strptime(i[-17:], '%Y%m%dh%Hm%Ms%S') for i in l]})
    #     return getattr(self, df[df['date'] == df['date'].max()].iloc[0, 0])

    @property
    def script_module_names(self):
        return [i for i in sys.modules if '__script__' in i]

    @property
    def last_running_script_name(self):
        sm = self.script_module_names
        if hasattr(self, 'current_script'):
            if not self.current_script['module_name'] in sm:
                raise Exception('Error: {}, {}'.format(sm, self.current_script))
            else:
                return self.current_script['module_name']
        else:
            return sm[-1]
    @property
    def cun_modules(self):
        lrs = self.last_running_script_name
        if hasattr(sys.modules[lrs], 'nuclear'):
            return sys.modules[lrs]
        else:
            for smi in self.script_module_names[::-1]:
                if hasattr(sys.modules[smi], 'nuclear'):
                    return sys.modules[smi]

    @property
    def cun(self):
        return self.cun_modules.nuclear

    def track_memory_usage(self):
        while True:
            self.save_value_to_file(self.current_memory_usage(), 'memory_mb')
            # CAREFUL WITH THREADING AND WRITING TO SAME HDF FILE self.save_values_hdf(classifier='memory_mb', vd=dict(none=self.current_memory_usage()))
            # possible solution: https://stackoverflow.com/questions/22522551/pandas-hdf5-as-a-database
            time.sleep(5)

    # def current_memory_usage(self):
    #     print(os.getpid())
    #     p = psutil.Process(os.getpid())
    #     return p.memory_info()[0] / 1024.
    #
    # def track_memory_usage_thread(self):
    #     self.tmu_thread = threading.Thread(target=self.track_memory_usage)
    #     self.tmu_thread.stop_request = multiprocess.Event()
    #     self.tmu_thread.start()

    def script_queue_changed(self):
        self.update_script_queue_table_data()

    @property
    def script_queue_table_data(self):
        return self._script_queue_table_data

    def update_script_queue_table_data(self):
        out = collections.OrderedDict([('name', []), ('pd', [])])
        for ridx, i in enumerate(self.script_queue):
            for cidx, attr_name in enumerate(['name', 'pd']):
                out[attr_name].append(getattr(i, attr_name))
        self._script_queue_table_data = out
        if hasattr(self, '_gui'): # this is the problem.
            self.gui.update_script_queue_table_data(self.script_queue_table_data)
        self.update_queue_list.emit(self.script_queue_table_data)

    ####################################################################################################################
    # script queue
    ####################################################################################################################
    def run(self):


        ## Why this is needed??????

        #from tools_2 import emod
        #emod.JobManager().start() ## maybe this is something which makes multiple sequences actuakly working.

        # start the CronDaemon
        #from tools_2 import cron
        #cron.CronDaemon().start()
        #self.dummy_test_variable = 123

        while True:
            if self._queue_thread.stop_request.is_set():
                self.q.queue.clear()
                self.script_queue.list = []
                self._queue_thread.stop_request.clear()
            task = None
            try: ### runs the measurement!
                item = self.q.get()
                with self._control_lock:
                    self.current_script = item
                    self._queue_thread.stop_request.clear() # this is necessary although it shouldn't be.
                    self._abort_current_only = False
                module_name = self.current_script['module_name']
                task = self._task_by_module.get(module_name)

                # A waiting script that was paused in the GUI holds the queue here
                # until it is resumed ("Run") or aborted.
                if task is not None and task.status == Status.PAUSED:
                    self.log.info("Userscript {} is paused, queue waits until it is resumed or aborted.".format(module_name[10:]))
                    while task.status == Status.PAUSED and not self._queue_thread.stop_request.is_set():
                        time.sleep(0.5)
                if self._queue_thread.stop_request.is_set() or (task is not None and task.status == Status.ABORTED):
                    self._set_task_status(task, Status.ABORTED)
                    with self._control_lock:
                        self.script_queue.pop(0)
                        del self.current_script
                    self.q.task_done()
                    continue

                self._set_task_status(task, Status.RUNNING, start=True)
                self.log.info("Starting Userscript {}...".format(module_name[10:]))

                # Remember the start time the script's NuclearOPs had before this run, so that
                # saved_dir is only taken from the new run (a re-queued script reuses its object).
                nuclear = self._script_nuclear(module_name)
                previous_start_time = getattr(nuclear, 'start_time', None)

                sys.modules[module_name].run_fun(
                    self._queue_thread.stop_request, queue = self, **self.current_script['pd']) ## Creates a nuclear and runs it.!!!

                # run_fun only starts the measurement thread and returns immediately.
                # Block here until that thread has really finished, so the next script
                # in the queue cannot start while this one is still measuring.
                self._wait_for_script(module_name, task, previous_start_time)

                with self._control_lock:
                    aborted = self._queue_thread.stop_request.is_set()
                    if aborted and self._abort_current_only:
                        # only this script was aborted from the GUI: keep the rest of the queue
                        self._queue_thread.stop_request.clear()
                        self._abort_current_only = False
                    self.script_history.append(self.current_script)
                    self.script_queue.pop(0)
                    del self.current_script
                self._set_task_status(task, Status.ABORTED if aborted else Status.COMPLETED, end=True)
                self.log.info("Userscript {} has finished{}.".format(module_name[10:], " (aborted)" if aborted else ""))
                self.q.task_done()
            except Exception: #Not running the measurement.
                exc_type, exc_value, exc_tb = sys.exc_info()
                traceback.print_exception(exc_type, exc_value, exc_tb)
                # If the script failed after its measurement thread was started, let that
                # thread end first; otherwise a script added later could run in parallel.
                try:
                    current = self._current_module_name()
                    if current is not None:
                        self._wait_for_script(current)
                except Exception:
                    pass
                self._set_task_status(task, Status.ERROR, end=True)
                self.q.queue.clear()
                self.script_queue.list = []
                if hasattr(self, 'current_script'):
                    del self.current_script

    # ----------------------------
    # Helpers for waiting on a queued script
    # ----------------------------
    @staticmethod
    def _script_nuclear(module_name):
        """Return the NuclearOPs object a queued user script created at module level, or None."""
        module = sys.modules.get(module_name)
        return getattr(module, 'nuclear', None)

    @staticmethod
    def _measurement_running(nuclear):
        """True while the measurement started by nuclear.run() is still going."""
        thread = getattr(nuclear, 'thread', None)
        if isinstance(thread, threading.Thread):
            return thread.is_alive()
        # scripts that run synchronously have no thread; fall back to the state flag
        return getattr(nuclear, '_state', 'idle') == 'run'

    def _wait_for_script(self, module_name, task=None, previous_start_time=None, poll_s=0.5):
        """Block the queue thread until the measurement of module_name has finished."""
        nuclear = self._script_nuclear(module_name)
        if nuclear is None:
            return  # helper scripts without a NuclearOPs finish inside run_fun
        while True:
            self._remember_saved_dir(task, nuclear, previous_start_time)
            if not self._measurement_running(nuclear):
                break
            time.sleep(poll_s)
        self._remember_saved_dir(task, nuclear, previous_start_time)

    @staticmethod
    def _remember_saved_dir(task, nuclear, previous_start_time):
        if task is None or task.saved_dir is not None:
            return
        start_time = getattr(nuclear, 'start_time', None)
        if start_time is None or start_time is previous_start_time:
            return  # this run has not initialised yet
        try:
            task.saved_dir = nuclear.save_dir
        except Exception:
            pass

    def _set_task_status(self, task, status, start=False, end=False):
        if task is None:
            return
        now = datetime.datetime.now()
        if start:
            task.start_time = now
            task.end_time = None
            task.accumulated_time = 0.0
        if end:
            task.end_time = now
            if task.start_time:
                task.accumulated_time = (now - task.start_time).total_seconds()
        task.status = status
        try:
            self.signals.task_updated.emit(task)
        except Exception:
            pass

    def _current_module_name(self):
        current = getattr(self, 'current_script', None)
        return current.get('module_name') if isinstance(current, dict) else None

    def run_thread(self):
        self._queue_thread = threading.Thread(target=self.run)
        self._queue_thread.stop_request = multiprocess.Event()
        self._queue_thread.start()

    def add_to_queue(self, name=None, pd=None, folder=None):
        #self.confocal.counter_state = 'idle'
        #self.md.stop_awgs()
        folder = self.user_script_folder if folder is None else folder
        name = self.selected_user_script if name is None else name
        pd = self.user_script_params if pd is None else pd
        if name == '':
            return
        try:
            module_name = self.init_task(name, folder)

            # Order matters: script_queue entry, then ScriptTask, then q.put().
            # An idle queue thread picks the item up immediately and must find its task and
            # script_queue entry already registered; the monitor thread must never see a
            # QUEUED task that is missing from script_queue.
            self.script_queue.append(ScriptQueueStep(module_name[10:], pd))

            # ----------------------------
            # GUI adapter: create ScriptTask & emit task_added
            # ----------------------------
            try:
                tid = uuid.uuid4().hex
                task = ScriptTask(id=tid, module_name=module_name, pd=pd, queued_time=datetime.datetime.now(),original_path=folder,queued_path=name)
                # start_time is set when the script actually starts running
                self.tasks.append(task)
                self._task_by_id[tid] = task
                self._task_by_module[module_name] = task
                # emit signal for GUI
                try:
                    self.signals.task_added.emit(task)
                except Exception:
                    # if emitting fails, fallback to log_output
                    try:
                        self.signals.log_output.emit("[QueueLogic] task_added emit failed for {}\n".format(module_name))
                    except Exception:
                        pass
            except Exception:
                pass

            self.q.put({'module_name': module_name, 'pd': pd})

        except Exception:
            print("Queuelogic: Could not add script to queue.")
            exc_type, exc_value, exc_tb = sys.exc_info()
            traceback.print_exception(exc_type, exc_value, exc_tb)

    def set_user_script_list(self):
        file_list = []
        unwanted_files = ['__init__.py', 'refocus_confocal_odmr.py']
        for files in os.listdir(self.user_script_folder):
            if files.endswith(".py") and not files in unwanted_files:
                file_list.append(str(files.split('.')[0]))
        self._user_script_list = file_list
        if len(self.user_script_list) > 0:
            self._selected_user_script = self.user_script_list[0]
            #if hasattr(self, '_gui'):
            val = collections.OrderedDict([('user_script_list', self.user_script_list), ('selected_user_script', self.selected_user_script)])
            #self.update_selected_user_script_combo_box(val)
            #Instead emit a signal which will updates it.
            self.update_selected_user_script_combo_box_signal.emit(val)

    # Convenience wrapper for GUI: accept a Path and add it to queue
    def add_task(self, path):
        """
        GUI-friendly add: path is a pathlib.Path or string path to a .py file
        It extracts folder and module name and calls add_to_queue.
        """
        try:
            p = path if isinstance(path, str) else str(path)
            folder, base = os.path.split(p)
            name = os.path.splitext(base)[0]
            # Temporarily set user_script_folder so set_user_script_list doesn't override
            old_folder = getattr(self, '_user_script_folder', None)
            self.user_script_folder = folder
            # set selected user script if possible
            try:
                if name in self.user_script_list:
                    self.selected_user_script = name
            except Exception:
                # ignore
                pass
            # add to queue using existing routine
            self.add_to_queue(name=name, pd=self.user_script_params, folder=folder)
            # restore folder (keep it changed because GUI may expect the new folder)
            # self.user_script_folder = old_folder
        except Exception:
            exc_type, exc_value, exc_tb = sys.exc_info()
            traceback.print_exception(exc_type, exc_value, exc_tb)

    @property
    def selected_user_script(self):
        return self._selected_user_script

    @selected_user_script.setter
    def selected_user_script(self, val):
        if val != '':
            if val not in self.user_script_list:
                raise Exception('Script {} not in {}'.format(val, self.user_script_list))
            self._selected_user_script = val
            #if hasattr(self, '_gui'):
            val = collections.OrderedDict([('selected_user_script', self.selected_user_script)])
            self.update_selected_user_script_combo_box_signal.emit(val)
            #self.gui.update_selected_user_script_combo_box(val)

    @property
    def user_script_params(self):
        return getattr(self, '_user_script_params', {})

    @user_script_params.setter
    def user_script_params(self, val):
        self.user_script_params = misc.check_type(val, 'user_script_params', dict)

    @property
    def user_script_folder(self):
        return self._user_script_folder

    @user_script_folder.setter
    def user_script_folder(self, val):
        if os.path.isdir(val):
            self._user_script_folder = val
            self.set_user_script_list()
            #This now is done in gui automatically.
            #if hasattr(self, '_gui'):
                #self.gui.update_user_script_folder_text_field(val)

    

    # Convenience wrapper for GUI: accept a Path and add it to queue
    def add_task(self, path):
        """
        GUI-friendly add: path is a pathlib.Path or string path to a .py file
        It extracts folder and module name and calls add_to_queue.
        """
        try:
            p = path if isinstance(path, str) else str(path)
            folder, base = os.path.split(p)
            name = os.path.splitext(base)[0]
            # Temporarily set user_script_folder so set_user_script_list doesn't override
            old_folder = getattr(self, '_user_script_folder', None)
            self.user_script_folder = folder
            # set selected user script if possible
            try:
                if name in self.user_script_list:
                    self.selected_user_script = name
            except Exception:
                # ignore
                pass
            # add to queue using existing routine
            self.add_to_queue(name=name, pd=self.user_script_params, folder=folder)
            # restore folder (keep it changed because GUI may expect the new folder)
            # self.user_script_folder = old_folder
        except Exception:
            exc_type, exc_value, exc_tb = sys.exc_info()
            traceback.print_exception(exc_type, exc_value, exc_tb)

    def add_rco(self):
        folder = r"C:/src/squdi/src/qudi/notebooks/UserScripts"
        name = 'refocus_confocal_odmr'
        pd = self.user_script_params
        self.add_to_queue(name, pd, folder)

    def in_script_queue(self, name):
        for step in self.script_queue:
            if step.name == name:
                return True
        else:
            return False

    def evaluate(self):
        raise NotImplementedError
        # name = self.selected_user_script
        # pd = self.user_script_params
        # if self.in_script_queue(name):
        #     raise Exception("Running the 'evaluate' function of a script is only possible when its 'run_fun' is not running.")
        # else:
        #     self.get_user_script(name).evaluate(**pd)

    def remove_last_script(self):
        # q.get() would remove the *first* waiting script while the display drops the last one;
        # take the last waiting item instead.
        with self._control_lock:
            with self.q.mutex:
                if len(self.q.queue) == 0:
                    return
                item = self.q.queue.pop()
            del self.script_queue[-1]
        task = self._task_by_module.get(item.get('module_name'))
        self._set_task_status(task, Status.ABORTED)

    def create_odmr(self):
        # seperate class which tracks the ODMR over time?
        # --> This should be handeled by TransitionTracker
        # Could be handy if scan ranges need to be changed.
        self.odmr = odmr.ODMR(self)


    def init_task(self, name, folder=None):
        folder = self.user_script_folder if folder is None else folder
        funa = "{}/{}.py".format(folder, name)
        task_name = "__script__{}_{}".format(self.nowstr, name)
        # The timestamp has 1 s resolution: adding the same script twice within a second
        # would reuse the module (and its NuclearOPs object) of the first entry.
        base_name, n = task_name, 2
        while task_name in sys.modules:
            task_name = "{}_{}".format(base_name, n)
            n += 1
        _ = imp.load_source(task_name, funa)
        return task_name

    def set_stop_request(self):
        self._queue_thread.stop_request.set()

    def write_standard_awg_sequences(self):
        self.add_to_queue('standard_awg_sequences', folder='C:/src/squdi/src/qudi/notebooks/UserScripts/helpers')
        #self.add_to_queue('standard_awg_sequences', folder=QUDI_DIR+'/notebooks/UserScripts/helpers')

    def dl(self, key, *args, **kwargs):
        return self._mcas_dict[key].dl(*args, **kwargs)

    def save_pi3diamond(self, destination_dir):
        src = os.getcwd()
        f = '{}/qudi.zip'.format(destination_dir)
        if not os.path.isfile(f):
            zf = zipfile.ZipFile(f, 'a')
            for root, dirs, files in os.walk(src):
                if (not any([i in root for i in ['__pycache__',
                                                 'awg_settings',
                                                 'currently_unused',
                                                 ".idea",
                                                 ".hg",
                                                 'UserScripts',
                                                 'log',
                                                 'notebooks' #FIXME - include logic, explode heavy stuff.
                                                 ]
                             ]
                            )
                ) or root.endswith('transition_tracker_log') or root.endswith('helpers'):
                    for file in files:
                        if any([file.endswith(i) for i in ['.py', '.dat', '.ui', '.hdf']]):
                            zf.write(os.path.join(root, file), os.path.join(root.replace(os.path.commonprefix([root, src]), ""), file))
            zf.close()


    # ----------------------------
    # NEW: monitor loop that observes current_script and script_history
    # This lets us emit task_updated events without touching run()
    # ----------------------------
    def _monitor_tasks_loop(self):
        """
        Background thread: periodically checks self.current_script and self.script_history
        and updates task status accordingly. Runs as daemon.
        """
        try:
            poll_interval = 0.5
            while not self._monitor_stop_event.is_set():
                try:
                    # Running / completed / aborted / error states are set by run() itself
                    # (see _set_task_status); the monitor only catches entries that vanished
                    # because the whole queue was cleared (stop request or script error).

                    # If queue cleared unexpectedly: mark queued tasks as ABORTED when queue empty but tasks remain
                    try:
                        qsize = self.q.qsize() if hasattr(self, 'q') else 0
                        if qsize == 0:
                            current = self._current_module_name()
                            # check for tasks still marked QUEUED / PAUSED that are not running
                            for task in list(self.tasks):
                                if task.status in (Status.QUEUED, Status.PAUSED) and task.module_name != current:
                                    # if script_queue has no matching ScriptQueueStep, consider it removed
                                    has_in_script_queue = False
                                    try:
                                        for step in self.script_queue:
                                            # step.name holds module name without prefix in original impl:
                                            # original added ScriptQueueStep(module_name[10:], ...)
                                            # so compare using suffix of module_name
                                            if task.module_name.endswith(step.name):
                                                has_in_script_queue = True
                                                break
                                    except Exception:
                                        pass
                                    if not has_in_script_queue:
                                        task.status = Status.ABORTED
                                        try:
                                            self.signals.task_updated.emit(task)
                                        except Exception:
                                            pass
                    except Exception:
                        pass

                except Exception:
                    # guard against unexpected monitor exceptions
                    try:
                        self.signals.log_output.emit("[QueueLogic monitor] exception in monitor loop\n")
                    except Exception:
                        pass
                # sleep
                self._monitor_stop_event.wait(poll_interval)
        except Exception:
            # final guard
            try:
                self.signals.log_output.emit("[QueueLogic monitor] terminated due to exception\n")
            except Exception:
                pass


    def Delete_measurement(self,tid):
        tsk=self._find_task_by_id(tid)
        if tsk is None or not tsk.saved_dir:
            print("could not remove folder: this task has no data folder (yet)")
            return
        if tsk.module_name == self._current_module_name():
            print("could not remove folder: the measurement is still running, abort it first")
            return
        try:
            shutil.rmtree(tsk.saved_dir)
        except Exception as e:
            print("could not remove folder:", e)

    # ----------------------------
    # GUI control methods
    # ----------------------------
    def _find_task_by_id(self, tid):
        return self._task_by_id.get(tid)

    def _find_task_by_module(self, module_name):
        return self._task_by_module.get(module_name)

    def _is_measuring(self, task):
        """True if task is the current script and its measurement has started."""
        return task.module_name == self._current_module_name() and task.start_time is not None

    def _remove_pending(self, task):
        """Remove a waiting (not yet started) task from q and script_queue. Caller holds _control_lock."""
        with self.q.mutex:
            for it in list(self.q.queue):
                if it.get('module_name') == task.module_name:
                    self.q.queue.remove(it)
        shortname = task.module_name[10:]
        start = 1 if self._current_module_name() is not None else 0
        for i in range(start, len(self.script_queue.list)):
            if self.script_queue.list[i].name == shortname:
                del self.script_queue[i]
                break

    def pause_task(self, task_id):
        """
        GUI "Pause".
        Running script: sets manual_pause on its NuclearOPs; the measurement holds before its next point.
        Waiting script: marked PAUSED; when the queue reaches it, the queue holds until "Run" or "Abort".
        """
        try:
            task = self._find_task_by_id(task_id)
            if not task:
                return
            with self._control_lock:
                if task.status == Status.RUNNING:
                    nuclear = self._script_nuclear(task.module_name)
                    if nuclear is None or not hasattr(nuclear, 'manual_pause'):
                        print("Queue: this script has no NuclearOPs that can be paused.")
                        return
                    nuclear.manual_pause = True
                    self._set_task_status(task, Status.PAUSED)
                elif task.status == Status.QUEUED:
                    self._set_task_status(task, Status.PAUSED)
        except Exception:
            exc_type, exc_value, exc_tb = sys.exc_info()
            traceback.print_exception(exc_type, exc_value, exc_tb)

    def start_task(self, task_or_obj):
        """
        GUI "Run".
        Paused running script: resume it. Paused waiting script: release it (it keeps its place).
        Waiting script: move it to the front of the waiting scripts (runs after the current one).
        """
        try:
            if isinstance(task_or_obj, str):
                task = self._find_task_by_id(task_or_obj)
            else:
                task = task_or_obj
            if not task:
                return
            with self._control_lock:
                if task.status == Status.PAUSED:
                    if self._is_measuring(task):
                        nuclear = self._script_nuclear(task.module_name)
                        if nuclear is not None:
                            nuclear.manual_pause = False
                        self._set_task_status(task, Status.RUNNING)
                    else:
                        self._set_task_status(task, Status.QUEUED)
                elif task.status == Status.QUEUED and task.module_name != self._current_module_name():
                    # move to front: reorder the waiting items in q and in script_queue the same way
                    with self.q.mutex:
                        items = [it for it in self.q.queue if it.get('module_name') == task.module_name]
                        for it in items:
                            self.q.queue.remove(it)
                        self.q.queue.extendleft(reversed(items))
                    shortname = task.module_name[10:]
                    lst = self.script_queue.list
                    start = 1 if self._current_module_name() is not None else 0
                    for i in range(start, len(lst)):
                        if lst[i].name == shortname:
                            lst.insert(start, lst.pop(i))
                            break
                    self.script_queue_changed()
                    self._set_task_status(task, Status.QUEUED)
        except Exception:
            exc_type, exc_value, exc_tb = sys.exc_info()
            traceback.print_exception(exc_type, exc_value, exc_tb)

    def abort_task(self, task_id):
        """
        GUI "Abort" for one script.
        Running script: stops that measurement; the queue then continues with the next script.
        Waiting script: removed from the queue; the running measurement is not touched.
        (set_stop_request() still stops the running script and clears the whole queue.)
        """
        try:
            task = self._find_task_by_id(task_id)
            if not task:
                return
            with self._control_lock:
                if task.module_name == self._current_module_name():
                    if self._is_measuring(task):
                        self._abort_current_only = True
                        self._queue_thread.stop_request.set()
                    # a held (paused, not started) current script is skipped by run()
                    self._set_task_status(task, Status.ABORTED)
                elif task.status in (Status.QUEUED, Status.PAUSED):
                    self._remove_pending(task)
                    self._set_task_status(task, Status.ABORTED)
        except Exception:
            exc_type, exc_value, exc_tb = sys.exc_info()
            traceback.print_exception(exc_type, exc_value, exc_tb)

    # End of class queue_logic