"""Offscreen GUI, tracker and QUA construction tests; never connects hardware."""
import os
import builtins
os.environ["QT_QPA_PLATFORM"] = "offscreen"
if os.path.isdir("C:/Windows/Fonts"):
    os.environ.setdefault("QT_QPA_FONTDIR", "C:/Windows/Fonts")

from pathlib import Path
import sys
import tempfile
import threading
import datetime
import logging
from collections import OrderedDict
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

import numpy as np
import pandas as pd
from PySide2 import QtCore, QtWidgets

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))
# Qudi's UI loader invokes pyside2-uic; direct interpreter runs need the
# environment's Scripts directory just as an activated conda shell provides.
os.environ["PATH"] = str(Path(sys.executable).parent / "Scripts") + os.pathsep + os.environ.get("PATH", "")

from qudi.logic.transition_tracker_settings import SetupParameterStore
from qudi.logic.transition_tracker import Transition, TransitionTracker
import qudi.logic.transition_tracker as tracker_module
from qudi.logic.qudip_enhanced.nv_hamilton import NVHam
from qudi.logic.qudip_enhanced.data_generation import DataGeneration
from qudi.logic.snv_calibration_nops import SnVCalibration
from qudi.logic.NuclearOPs import NuclearOPs
from qudi.logic.nuclear_ops_opx_utils import NuclearOpsOPXUtils
from qudi.logic.snv_calibration_nops import sna
from qudi.logic.snv_calibration import fit_time_sine
from qudi.gui.queue.snv_calibration import SnVCalibrationDock
from qudi.gui.queue.Queue import queue_gui
from qudi.gui.transition_tracker.setup_parameters import SetupParametersDock
from qudi.gui.transition_tracker.transition_tracker_gui import TransitionTrackerGui
from qudi.core.connector import Connector
from qudi.logic.gated_counter_logic import GatedCounter
from qudi.logic.queue.queue_logic import queue_logic, ScriptQueueList, ScriptQueueStep
from qudi.gui.queue.acquisition_progress import AcquisitionProgressBar
from queue import Queue


class Signals(QtCore.QObject):
    snv_calibration_updated = QtCore.Signal(object)
    update_selected_user_script_combo_box_signal = QtCore.Signal(OrderedDict)
    update_queue_list = QtCore.Signal(OrderedDict)
    acquisition_progress = QtCore.Signal(object)


class IntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def setUp(self):
        self.settings_folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.settings_folder.cleanup)
        self.store = SetupParameterStore(Path(self.settings_folder.name, "setup.json"))
        self.settings = self.store.snapshot()

    def test_save_unicode_script_and_notes_with_windows_default_encoding(self):
        source = (ROOT / "UserScripts/Qinu/SnV_Rabi_calibration.py").read_text(encoding="utf-8")
        notes = "Rabi calibration: \u03a9(A), pulse duration in \u03bcs"

        def windows_open(file, mode="r", **kwargs):
            kwargs.setdefault("encoding", "cp1252")
            return builtins.open(file, mode, **kwargs)

        with tempfile.TemporaryDirectory() as folder:
            measurement = SimpleNamespace(
                save_dir=folder, init_from_file=None, iterator_df_done=pd.DataFrame(),
                file_notes=notes, _meas_code=source, meas_code=source,
                save_measurement_data=Mock(), pld=SimpleNamespace(save_plot=Mock()),
            )
            with patch("qudi.logic.qudip_enhanced.data_generation.open", windows_open, create=True):
                DataGeneration.save(measurement)
            self.assertEqual(Path(folder, "meas_code.py").read_text(encoding="utf-8"), source)
            self.assertEqual(Path(folder, "notes.dat").read_text(encoding="utf-8"), notes)
            measurement.save_measurement_data.assert_called_once_with(notify=False)
            measurement.pld.save_plot.assert_called_once()

    def test_half_spin_hamiltonian_and_labels(self):
        hamiltonian = NVHam(magnet_field={"z": 0.1}, electron_spin=0.5)
        self.assertEqual(hamiltonian.h_nv.shape, (2, 2))
        self.assertEqual(hamiltonian.dims, [2])
        for label, ms in (("e1", 0.5), ("e2", -0.5)):
            transition = Transition("13c5 " + label)
            self.assertEqual(transition.electron_state, label)
            self.assertEqual(transition.ms_state, ms)

    def test_tracker_startup_and_measured_log_round_trip(self):
        with tempfile.TemporaryDirectory() as folder:
            Path(folder, "current_n_spins.csv").write_text("13c5\n", encoding="utf-8")
            tracker = TransitionTracker(name="test_tracker", qudi_main_weakref=lambda: None,
                config=dict(electron_spin=0.5, log_folder=folder))
            SetupParameterStore(Path(folder, "setup_parameters.json")).update({"smiq": {"frequency_ghz": 4.125}})
            awg = SimpleNamespace(mcas_dict=SimpleNamespace(debug_mode=False))
            with patch.object(tracker, "mcas_holder", lambda: awg), \
                 patch.object(tracker_module, "get_last_value_from_file", side_effect=lambda name: np.array([1.0]) if "fit_params" in name or "history" in name else 1.0), \
                 patch.object(tracker_module, "get_last_values_from_file", return_value=[1.0]), \
                 patch.object(tracker_module, "save_value_to_file"):
                tracker.on_activate()
            self.assertEqual(tracker.current_local_oscillator_freq, 4125.0)
            self.assertEqual(tracker.transition_name_list[0], ["e1", "e2"])
            self.assertEqual({t.name for t in tracker.transitions}, {"13c5 e1", "13c5 e2"})
            self.assertNotIn("snv_e1_e2", tracker.rabi_parameters)
            self.assertIn("snv_e1_e2_dummy", tracker.rabi_parameters)
            rp = tracker.save_snv_rabi_calibration([0, 0.5, 1], [0, 2.5, 5])
            np.testing.assert_allclose(rp.omega(amplitude=[0.2, 0.8]), [1, 4])
            tracker.save_snv_rabi_calibration([0, 0.5, 1], [0, 3, 6])
            self.assertEqual(len(list(Path(folder, "rabi_parameters_archive").rglob("*.dat"))), 1)
            with patch.object(tracker_module, "save_values_to_file") as save:
                tracker.update_snv_frequency(220.123)
                self.assertEqual(tracker.snv_frequency_mhz, 220.123)
                self.assertEqual(save.call_args.args[0], [220.123])

    def test_panels_can_plot_and_remain_alive(self):
        queue = Signals()
        queue.tt = SimpleNamespace(snv_frequency_mhz=221.1)
        queue.set_stop_request = lambda: None
        window = QtWidgets.QMainWindow()
        for kind in ("odmr", "rabi"):
            dock = SnVCalibrationDock(kind, queue, window)
            window.addDockWidget(QtCore.Qt.RightDockWidgetArea, dock)
            frame = pd.DataFrame(dict(MW_amp=[0., 50., 100.], MW_pulse_len=400,
                                      MW_f=[220e6, 221e6, 222e6], result_0=[0.1, 0.5, 0.2]))
            queue.snv_calibration_updated.emit(dict(kind=kind, status="Test data", data=frame))
            self.app.processEvents()
            self.assertEqual(dock.status.text(), "Test data")
        window.close()

    def test_queue_gui_activation_creates_calibration_docks(self):
        queue = Signals()
        queue.tt = SimpleNamespace(electron_spin=0.5, snv_frequency_mhz=221.1)
        for method in ("remove_last_script", "set_stop_request", "add_rco", "evaluate",
                       "write_standard_awg_sequences"):
            setattr(queue, method, lambda: None)
        gui = queue_gui(config={}, name="test_queue_gui", qudi_main_weakref=lambda: None)
        with patch.object(gui, "queue_logic", lambda: queue):
            try:
                gui.on_activate()
                self.app.processEvents()
                self.assertEqual([dock.kind for dock in gui._snv_docks], ["odmr", "rabi"])
                self.assertEqual(gui._mw.dockWidgetArea(gui._snv_docks[0]), QtCore.Qt.RightDockWidgetArea)
                queue.acquisition_progress.emit(dict(phase="acquiring", completed=25, total=100, estimated=True))
                self.app.processEvents()
                self.assertEqual(gui._acquisition_progress.value(), 250)
                self.assertIn("~75 / 100", gui._acquisition_progress.format())
            finally:
                gui.on_deactivate()

    def test_rabi_panel_queues_time_grid_at_fixed_amplitudes(self):
        queue = Signals()
        queue.tt = SimpleNamespace(snv_frequency_mhz=221.1)
        queue.set_stop_request = lambda: None
        window = QtWidgets.QMainWindow()
        dock = SnVCalibrationDock("rabi", queue, window)
        submitted = []
        queue.add_snv_calibration = lambda kind, options: submitted.append((kind, options))
        dock.enqueue()
        self.assertEqual(submitted[0][0], "rabi")
        self.assertEqual(submitted[0][1]["amplitudes_percent"], [20, 40, 60, 80, 100])
        self.assertEqual(submitted[0][1]["durations_ns"], list(range(20, 2001, 20)))
        duration = np.arange(20, 2001, 20)
        fit = fit_time_sine(duration, 0.5+0.4*np.cos(2*np.pi*2.5*duration/1000))
        dock.update_result(dict(kind="rabi", status="Test fit", fits={50: fit}))
        data_curve, fit_curve = dock.plot.listDataItems()
        np.testing.assert_allclose(data_curve.xData, duration)
        np.testing.assert_allclose(fit_curve.xData, fit.fit_x*1000)
        dock.controls["time_step_ns"].setValue(22)
        dock.enqueue()
        self.assertEqual(len(submitted), 1)
        self.assertIn("multiples of 4", dock.status.text())
        window.close()

    def make_test_queue(self):
        queue = queue_logic(config={}, name="test_calibration_queue", qudi_main_weakref=lambda: None)
        queue.q = Queue()
        queue._script_queue = ScriptQueueList(ScriptQueueStep, queue)
        queue.thread = SimpleNamespace(stop_request=threading.Event())
        queue.tt = SimpleNamespace(snv_frequency_mhz=221.1)
        self.addCleanup(queue.timer.stop)
        self.addCleanup(queue._clear_pending_queue)
        return queue

    def test_rabi_button_enqueues_and_scheduler_calls_real_script(self):
        queue = self.make_test_queue()
        connector = Connector(interface="queue_logic")
        connector.connect(queue)
        window = QtWidgets.QMainWindow()
        dock = SnVCalibrationDock("rabi", connector(), window)
        self.addCleanup(window.close)
        self.addCleanup(connector.disconnect)
        # Reproduce a click after a previous Stop but before the scheduler tick.
        queue.thread.stop_request.set()
        dock.start.click()
        self.app.processEvents()
        self.assertEqual(queue.q.qsize(), 1)
        self.assertFalse(queue.thread.stop_request.is_set())
        self.assertIn("Queued", dock.status.text())
        self.assertEqual(queue.script_queue[0].pd["durations_ns"], list(range(20, 2001, 20)))
        module_name = queue.q.queue[0]["module_name"]
        self.addCleanup(sys.modules.pop, module_name, None)
        with patch.object(SnVCalibration, "start_calibration") as start:
            queue.mainloop_handler()
            start.assert_called_once()
            self.assertEqual(start.call_args.kwargs["amplitudes_percent"], [20, 40, 60, 80, 100])
        self.app.processEvents()
        self.assertIn("Starting", dock.status.text())
        queue.finish_measurement()

    def test_rabi_queue_import_failure_is_visible_and_does_not_queue(self):
        queue = self.make_test_queue()
        window = QtWidgets.QMainWindow()
        dock = SnVCalibrationDock("rabi", queue, window)
        self.addCleanup(window.close)
        with patch.object(queue, "init_task", side_effect=ImportError("missing calibration dependency")):
            dock.start.click()
        self.assertTrue(queue.q.empty())
        self.assertIn("missing calibration dependency", dock.status.text())
        self.assertIn("Could not queue", dock.status.text())

    def test_calibration_waits_while_stop_is_pending_and_reports_removal(self):
        queue = self.make_test_queue()
        queue.thread.stop_request.set()
        queue.current_script = {"module_name": "fake", "script_name": "other"}
        with self.assertRaisesRegex(RuntimeError, "stopping"):
            queue.add_snv_calibration("rabi", {})
        del queue.current_script
        queue.thread.stop_request.clear()
        messages = []
        queue.snv_calibration_updated.connect(messages.append)
        queue.q.put(dict(script_name="SnV_Rabi_calibration"))
        queue._clear_pending_queue()
        self.assertIn("Removed", messages[-1]["status"])

    def test_counter_progress_counts_down_to_processing_and_resets(self):
        counter = GatedCounter(config={}, name="progress_counter", qudi_main_weakref=lambda: None)
        bar = AcquisitionProgressBar()
        self.addCleanup(bar.close)
        counter.sigAcquisitionProgress.connect(bar.update_progress)
        counter.gated_counter_data = np.array([1, 0, 2, 0, 0])
        with patch.object(counter, "_all_counters_ready", return_value=False):
            counter.set_progress()
            self.assertEqual(bar.value(), 600)
            self.assertIn("~2 / 5 readouts remaining", bar.format())
            counter.gated_counter_data = np.zeros(5)
            counter.set_progress()
            self.assertEqual(bar.value(), 0)
        with patch.object(counter, "_all_counters_ready", return_value=True):
            counter.set_progress()
            self.assertEqual(bar.value(), 1000)
            self.assertIn("processing", bar.format())
        bar.update_progress(dict(phase="data_arrived"))
        self.assertEqual(bar.format(), "New data arrived")
        bar.update_progress(dict(phase="preparing"))
        self.assertEqual(bar.value(), 0)
        bar.update_progress(dict(phase="failed", message="counter disconnected"))
        bar.update_progress(dict(phase="stopped"))
        self.assertIn("counter disconnected", bar.format())

    def test_counter_loop_publishes_progress_without_live_plot_analysis(self):
        counter = GatedCounter(config={}, name="progress_counter_loop", qudi_main_weakref=lambda: None)
        counter.trace.analyze_sequence = [["result", ">", 0, 1, 0, 1]]
        counter.analyze_trace_during_experiment = False
        counter.n_values = 5
        counter._fast_counter_device = SimpleNamespace(gated_counter_countbetweenmarkers=SimpleNamespace(
            getData=lambda: np.array([1, 2, 0, 0, 0])))
        messages = []
        counter.sigAcquisitionProgress.connect(messages.append)
        def read():
            counter.gated_counter_data = np.array([1, 2, 0, 0, 0])
        with patch.object(counter, "set_counter"), patch.object(counter, "_read_gated_counter_data", side_effect=read), \
             patch.object(counter, "_all_counters_ready", side_effect=[False, False, True, True]), \
             patch.object(counter, "update_plot"), patch.object(counter, "stop_timetaggers"), \
             patch("qudi.logic.gated_counter_logic.time.sleep"):
            counter.count(threading.Event(), mcas=Mock())
        self.assertEqual(messages[0]["phase"], "preparing")
        self.assertTrue(any(m.get("completed") == 2 for m in messages))
        self.assertEqual(messages[-1]["phase"], "processing")
        self.assertEqual(messages[-1]["completed"], 5)

    def test_configuration_and_slow_fast_blocking(self):
        queue = SimpleNamespace(
            transition_tracker=SimpleNamespace(electron_spin=0.5, log_folder=str(ROOT/"log/transition_tracker_log"), setup_parameters=self.settings),
            tt=SimpleNamespace(snv_frequency_mhz=221.1),
            gated_counter=SimpleNamespace(trace=SimpleNamespace(), set_n_values=lambda **kwargs: None))
        for kind in ("odmr", "rabi"):
            nuclear = SnVCalibration(kind, str(ROOT/"UserScripts/Qinu/SnV_Rabi_calibration.py"))
            nuclear.configure(queue)
            self.assertTrue(nuclear.do_ple_refocus_A1)
            self.assertTrue(nuclear.lock_laser_to_wavemeter)
            self.assertEqual(nuclear.ple_refocus_interval, 60 if kind == "odmr" else 180)
            # Reusing a queued calibration must not skip its initial refocus
            # just because the previous run refocused recently, then unlocked.
            queue.log = Mock()
            with patch.object(nuclear, "_run_refocus_ple_A1_sequence", return_value=True) as refocus:
                nuclear.refocus_ple_A1(threading.Event())
                nuclear.refocus_ple_A1(threading.Event())
                self.assertEqual(refocus.call_count, 1)
                nuclear.configure(queue)
                nuclear.refocus_ple_A1(threading.Event())
                self.assertEqual(refocus.call_count, 2)
            expected = "MW_pulse_len" if kind == "rabi" else "MW_f"
            self.assertEqual(nuclear.fast_changing_parameters, [expected])
            nuclear.set_iterator_df()
            size = nuclear.number_of_simultaneous_measurements
            for start in range(0, len(nuclear.iterator_df), size):
                block = nuclear.iterator_df.iloc[start:start+size]
                self.assertEqual(block[expected].nunique(), size)
                for name in nuclear.slow_changing_parameters:
                    if name in block:
                        self.assertEqual(block[name].nunique(), 1)

    def make_settings_tracker(self):
        tracker = TransitionTracker(name="settings_tracker", qudi_main_weakref=lambda: None,
            config=dict(electron_spin=0.5, log_folder=self.settings_folder.name))
        tracker._setup_store = self.store
        tracker.rabi_parameters = {}
        return tracker

    def test_calibration_start_binds_snapshot_through_real_connector(self):
        tracker = self.make_settings_tracker()
        ou = NuclearOpsOPXUtils(name="connector_opx", config={}, qudi_main_weakref=lambda: None)
        connector = Connector(interface="NuclearOpsOPXUtils")
        connector.connect(ou)
        self.addCleanup(connector.disconnect)
        with patch.object(ou, "power_calibration_logic", return_value=Mock()), \
             patch.object(ou, "ple_scanner_logic", return_value=Mock()), \
             patch.object(ou, "transition_tracker_logic", return_value=tracker), \
             patch.object(ou, "opx", return_value=Mock()):
            ou.on_activate()
        proxy = connector()
        queue = SimpleNamespace(transition_tracker=tracker, tt=tracker,
            nuclear_ops_opx_utils=proxy, awg=SimpleNamespace(mcas_dict={}),
            gated_counter=SimpleNamespace(trace=SimpleNamespace(), set_n_values=Mock()),
            snv_calibration_updated=Mock())
        for kind in ("odmr", "rabi"):
            with self.subTest(kind=kind):
                nuclear = SnVCalibration(kind, str(ROOT / "UserScripts/Qinu/SnV_Rabi_calibration.py"))
                with patch("qudi.logic.NuclearOPs.threading.Thread") as thread:
                    nuclear.start_calibration(threading.Event(), queue)
                    thread.return_value.start.assert_called_once()
                self.assertIs(proxy.setup_parameters, nuclear.setup_parameters)
                before = proxy.setup_parameters.crc.threshold
                tracker.update_setup_parameters({"crc": {"threshold": before + 1}})
                self.assertEqual(proxy.setup_parameters.crc.threshold, before)
        ou.on_deactivate()
        self.assertIsNone(ou._setup_parameters)

    def test_setup_editor_apply_validation_and_calibration_refresh(self):
        tracker = self.make_settings_tracker()
        dock = SetupParametersDock(tracker)
        self.addCleanup(dock.disconnect_tracker)
        self.addCleanup(dock.close)
        key = ("crc", "threshold")
        editor = dock.editors[key]
        editor.setText("12")
        dock.mark_dirty(key)
        with patch.object(tracker_module, "save_values_to_file"):
            tracker.update_snv_frequency(225.5)
        self.app.processEvents()
        self.assertEqual(editor.text(), "12")
        self.assertEqual(dock.editors["electron", "IQ_freq"].text(), "225500000")
        dock.apply()
        self.assertEqual(tracker.setup_parameters.crc.threshold, 12)
        self.assertEqual(tracker.snv_frequency_mhz, 225.5)
        editor.setText("-1")
        dock.mark_dirty(key)
        dock.apply()
        self.assertIn("not saved", dock.status.text())
        self.assertEqual(tracker.setup_parameters.crc.threshold, 12)
        dock.discard()
        self.assertEqual(editor.text(), "12")

    def test_tracker_gui_activation_exposes_setup_dock(self):
        tracker = self.make_settings_tracker()
        tracker._snv_frequency_mhz = 221.1
        tracker._current_local_oscillator_freq = 4000.
        tracker._ple_A1 = tracker._ple_A2 = 1.
        tracker.transitions = []
        gui = TransitionTrackerGui(config={}, name="test_tracker_gui", qudi_main_weakref=lambda: None)
        with patch.object(gui, "transition_tracker_logic", lambda: tracker):
            gui.on_activate()
            try:
                self.assertEqual(len(gui._setup_dock.editors), sum(len(fields) for fields in self.store.snapshot().to_dict().values()))
            finally:
                gui.on_deactivate()

    def test_rabi_updates_gate_period_at_selected_amplitude_without_extrapolation(self):
        tracker = self.make_settings_tracker()
        tracker.update_setup_parameters({"electron": {"electron_rabi_opx_amp": 50}})
        tracker.save_snv_rabi_calibration([0.2, 0.5, 0.8], [1., 2.5, 4.])
        self.assertEqual(tracker.setup_parameters.electron.electron_rabi_period, 400)
        tracker.update_setup_parameters({"electron": {"electron_rabi_opx_amp": 100}})
        with self.assertRaisesRegex(ValueError, "outside"):
            tracker.apply_rabi_period()
        self.assertEqual(tracker.setup_parameters.electron.electron_rabi_period, 400)

    def test_nuclearops_save_records_captured_settings(self):
        import json
        tracker = self.make_settings_tracker()
        nuclear = NuclearOPs()
        nuclear.queue = SimpleNamespace(transition_tracker=tracker, save_pi3diamond=Mock(), log=Mock())
        nuclear.pld = SimpleNamespace(data=SimpleNamespace(df=pd.DataFrame({"result": [1]})))
        nuclear.file_path, nuclear.file_name = self.settings_folder.name, "measurement"
        nuclear.start_time = datetime.datetime.now()
        nuclear.save_trace_efficient = True
        nuclear.capture_setup_parameters()
        tracker.update_setup_parameters({"crc": {"threshold": 14}})
        with patch.object(DataGeneration, "save"), patch.object(nuclear, "save_sequence_file"), \
             patch("qudi.logic.NuclearOPs.save_qutip_enhanced"):
            nuclear.save()
        saved = json.loads(Path(nuclear.save_dir, "setup_parameters.json").read_text())
        self.assertEqual(saved["parameters"]["crc"]["threshold"], 7)
        self.assertEqual(tracker.setup_parameters.crc.threshold, 14)

    def test_real_qua_helpers_use_snapshot_and_local_overrides(self):
        from qm import qua
        tracker = self.make_settings_tracker()
        tracker.update_setup_parameters({"general": {"override_operation_powers": False}, "electron": {"IQ_freq": 224000000,
            "electron_rabi_period": 320, "electron_rabi_opx_amp": 60},
            "crc": {"laser_power_A1": 31}, "ssr": {"laser_power_A1": 41},
            "optical_pi_pulse": {"laser_power": 55, "pulse_duration": 80}})
        nuclear = NuclearOPs()
        nuclear.queue = SimpleNamespace(transition_tracker=tracker)
        snapshot = nuclear.capture_setup_parameters()
        tracker.update_setup_parameters({"electron": {"IQ_freq": 230000000}, "crc": {"laser_power_A1": 99}})
        ou = NuclearOpsOPXUtils(name="settings_opx", config={}, qudi_main_weakref=lambda: None)
        ou._setup_parameters = snapshot
        mcas = SimpleNamespace(ou=ou)
        with patch.object(ou, "set_laser_power") as power, \
             patch.object(ou, "MW_pulse", wraps=ou.MW_pulse) as pulse, \
             patch.object(sna, "update_frequency", wraps=sna.update_frequency) as frequency:
            with qua.program():
                ou.init_program()
                sna.set_IQ_freq(mcas)
                sna.crc(mcas, set_laser_power=True)
                sna.electron_init(mcas, set_laser_power=True)
                sna.ssr(mcas, set_laser_power=True)
                sna.csr(mcas, set_laser_power=True)
                sna.optical_pi_pulse(mcas, laser_power="Laser_620_pi_power", set_laser_power=True)
                sna.electron_gate(mcas, "pi/2")
            frequency.assert_called_once_with("MW", 224000000)
            pulse.assert_called_once_with(duration_ns=80., pulse="x", amplitude=0.6)
            power.assert_any_call("Laser_620_det", 31, 1000)
            power.assert_any_call(laser_name="Laser_620_det", power_nw=41, pause_after=1000)
            power.assert_any_call(laser_name="Laser_620_pi", power_nw="Laser_620_pi_power", pause_after=1000)
        self.assertEqual(nuclear.setup_parameters.electron.IQ_freq, 224000000)
        self.assertEqual(tracker.setup_parameters.electron.IQ_freq, 230000000)
        self.assertEqual(snapshot.optical_pi_pulse.laser_power, 55)

    def test_default_qua_helpers_do_not_repeat_startup_power_writes(self):
        from qm import qua
        ou = NuclearOpsOPXUtils(name="startup_power_opx", config={}, qudi_main_weakref=lambda: None)
        ou.set_setup_parameters(self.store.update({"general": {"laser_power_A1": 32, "laser_power_B2": 43}}))
        mcas = SimpleNamespace(ou=ou)
        with patch.object(ou, "set_laser_power") as power:
            with qua.program():
                ou.init_program()
                sna.setup_laser_powers(mcas)
                with qua.infinite_loop_():
                    sna.crc(mcas)
                    sna.electron_init(mcas)
                    sna.ssr(mcas)
                    sna.csr(mcas)
                    sna.optical_pi_pulse(mcas)
            self.assertEqual(power.call_count, 3)
            power.assert_any_call("Laser_620_det", 32)
            power.assert_any_call("Laser_620", 43)
            power.assert_any_call("Laser_520", 100000)

    def test_crc_selected_repump_and_startup_power(self):
        from qm import qua
        ou = NuclearOpsOPXUtils(name="repump_test", config={}, qudi_main_weakref=lambda: None)
        mcas = SimpleNamespace(ou=ou)
        for laser, selected_power in (("Laser_520", 50000), ("Laser_450", 1234)):
            ou.set_setup_parameters(self.store.update({"crc": {
                "repump_laser": laser, "laser_power_repump": 50000,
                "laser_power_repump_450": 1234}}))
            with self.subTest(laser=laser), patch.object(ou, "set_laser_power") as power, \
                    patch.object(ou, "laser_pulse", wraps=ou.laser_pulse) as pulse:
                with qua.program():
                    ou.init_program()
                    sna.setup_laser_powers(mcas)
                    startup_calls = power.call_count
                    with qua.infinite_loop_():
                        sna.crc(mcas)
                pulse.assert_called_once_with(laser, 100000)
                power.assert_any_call(laser, selected_power)
                self.assertEqual(power.call_count, startup_calls)
                self.assertEqual(startup_calls, 4 if laser == "Laser_450" else 3)
            with patch.object(ou, "set_laser_power") as power:
                with qua.program():
                    ou.init_program()
                    sna.crc(mcas, set_laser_power=True, laser_power_repump_450=2468)
                power.assert_any_call(laser, 2468 if laser == "Laser_450" else 50000, 1000)

    def test_crc_repump_gui_controls(self):
        tracker = self.make_settings_tracker()
        dock = SetupParametersDock(tracker)
        self.addCleanup(dock.disconnect_tracker)
        self.addCleanup(dock.close)
        selector = dock.editors["crc", "repump_laser"]
        self.assertEqual(selector.currentText(), "Laser_520")
        selector.setCurrentText("Laser_450")
        editor = dock.editors["crc", "laser_power_repump_450"]
        editor.setText("1234")
        editor.textEdited.emit("1234")
        dock.apply()
        self.assertEqual(tracker.setup_parameters.crc.repump_laser, "Laser_450")
        self.assertEqual(tracker.setup_parameters.crc.laser_power_repump_450, 1234)

    def test_hahn_and_xy_strict_regions_contain_only_mw_pulses_and_waits(self):
        import ast
        from qm import qua
        from qudi.hardware.OPX import program_container as pc

        def strict_regions(value):
            if isinstance(value, dict):
                for key, child in value.items():
                    if key == "strictTiming":
                        yield child["body"]["statements"]
                    else:
                        yield from strict_regions(child)
            elif isinstance(value, list):
                for child in value:
                    yield from strict_regions(child)

        cases = [
            ("Hahn_echo_SnV_new.py", "tau", None, ["x", "y", "-x"]),
            ("XY_n.py", "tau_half", None, ["x", "x", "y", "x", "y", "-x"]),
        ]
        xy8 = ["x", "y", "x", "y", "y", "x", "y", "x"]
        for family, block in (("XY4", ["x", "y", "x", "y"]), ("XY8", xy8),
                              ("XY16", xy8 + ["-" + axis for axis in xy8])):
            for count in (len(block), 32, 64, 128):
                cases.append(("XY8_SnV.py", "total_free_evolution_ns", family,
                              ["x"] + block * (count // len(block)) + ["-x"]))

        for filename, time_key, family, pulses in cases:
            with self.subTest(script=filename, family=family, pulses=len(pulses) - 2):
                path = ROOT / "UserScripts/Qinu" / filename
                tree = ast.parse(path.read_text(encoding="utf-8"))
                # Execute the actual sequence functions without the script's
                # import-time GUI creation or hardware/module reloads.
                functions = [node for node in tree.body if isinstance(node, ast.FunctionDef)
                             and node.name in ("ret_ret_mcas", "inverted_axis", "xy_phase_sequence")]
                constants = [node for node in tree.body if isinstance(node, ast.Assign)
                             and any(isinstance(target, ast.Name) and target.id.startswith("XY") for target in node.targets)]
                selected = sorted(functions + constants, key=lambda node: node.lineno)
                namespace = dict(qua=qua, pc=pc, sna=sna, NuclearOpsOPXUtils=NuclearOpsOPXUtils,
                                 for_each_=qua.for_each_, infinite_loop_=qua.infinite_loop_)
                exec(compile(ast.Module(body=selected, type_ignores=[]), str(path), "exec"), namespace)
                ou = NuclearOpsOPXUtils(name="strict_opx", config={}, qudi_main_weakref=lambda: None)
                ou.set_setup_parameters(self.settings)
                times = [102400] if filename == "XY8_SnV.py" else [100, 200]
                frame = pd.DataFrame({time_key: times, "init_state": "e1", "SSR_state": "e1",
                                      "last_pulse": "-x", "cooldown_time": 500, "order": 4})
                if filename == "XY8_SnV.py":
                    frame["sequence"] = family
                    frame["num_pulses"] = len(pulses) - 2
                ou.create_fast_sweep_qua_arrays(frame)
                owner = SimpleNamespace(queue=SimpleNamespace(nuclear_ops_opx_utils=ou,
                    awg=SimpleNamespace(qm=None, qmm=None, _configuration=None)))
                with patch.object(ou, "set_laser_power"):
                    sequence = namespace["ret_ret_mcas"]({})(owner, frame)
                regions = list(strict_regions(sequence.program._program.to_dict()))
                self.assertEqual(len(regions), 1)
                emitted_pulses = []
                for statement in regions[0]:
                    self.assertIn(next(iter(statement)), ("play", "wait"))
                    if "play" in statement:
                        play = statement["play"]
                        self.assertEqual(play["qe"]["name"], "MW")
                        emitted_pulses.append(play["namedPulse"]["name"])
                    else:
                        self.assertEqual([element["name"] for element in statement["wait"]["qe"]], ["MW"])
                self.assertEqual(emitted_pulses, pulses)
                if filename == "XY8_SnV.py":
                    waits = [int(s["wait"]["time"]["literal"]["value"])
                             for s in regions[0] if "wait" in s]
                    count = len(pulses) - 2
                    tau_cycles = 102400 // (2 * count * 4)
                    self.assertEqual(waits, [tau_cycles] + [2 * tau_cycles] * (count - 1)
                                     + [tau_cycles])
                    self.assertEqual(sum(waits) * 4, 102400)
                if filename.startswith("Hahn"):
                    self.assertEqual(len(regions[0]), 5)
                    self.assertEqual([s["play"]["duration"]["literal"]["value"]
                                      for s in regions[0] if "play" in s], ["13", "26", "13"])

    def test_electron_gate_keeps_default_boundary_alignment(self):
        from qm import qua
        ou = NuclearOpsOPXUtils(name="aligned_gate_opx", config={}, qudi_main_weakref=lambda: None)
        ou.set_setup_parameters(self.settings)
        with qua.program() as program:
            sna.electron_gate(SimpleNamespace(ou=ou), "pi/2")
        statements = program._program.to_dict()["script"]["body"]["statements"]
        self.assertEqual([next(iter(statement)) for statement in statements], ["align", "play", "align"])

    def test_threshold_editor_and_crc_link(self):
        tracker = self.make_settings_tracker()
        tracker.update_setup_parameters({"csr": {"csr_threshold": 9}, "crc": {"threshold": 14}})
        dock = SetupParametersDock(tracker)
        self.addCleanup(dock.disconnect_tracker)
        self.addCleanup(dock.close)
        for key, value in ((("ssr", "threshold"), "3"), (("ssr", "init_threshold"), "2")):
            dock.editors[key].setText(value)
            dock.editors[key].textEdited.emit(value)
        checkbox = dock.editors["csr", "use_crc_threshold"]
        field = dock.editors["csr", "csr_threshold"]
        checkbox.setChecked(True)
        self.assertFalse(field.isEnabled())
        dock.apply()
        self.assertEqual(tracker.setup_parameters.ssr.threshold, 3)
        self.assertEqual(tracker.setup_parameters.ssr.init_threshold, 2)
        self.assertEqual(tracker.setup_parameters.csr.csr_threshold, 14)
        self.assertEqual(float(field.text()), 9)
        checkbox.setChecked(False)
        self.assertTrue(field.isEnabled())
        dock.apply()
        self.assertEqual(tracker.setup_parameters.csr.csr_threshold, 9)

    def test_power_override_checkbox_retains_and_disables_individual_values(self):
        tracker = self.make_settings_tracker()
        tracker.update_setup_parameters({"crc": {"laser_power_A1": 12}})
        dock = SetupParametersDock(tracker)
        self.addCleanup(dock.disconnect_tracker)
        self.addCleanup(dock.close)
        checkbox = dock.editors["general", "override_operation_powers"]
        field = dock.editors["crc", "laser_power_A1"]
        self.assertTrue(checkbox.isChecked())
        self.assertFalse(field.isEnabled())
        self.assertEqual(float(field.text()), 12)
        checkbox.setChecked(False)
        self.assertTrue(field.isEnabled())
        dock.apply()
        self.assertEqual(tracker.setup_parameters.crc.laser_power_A1, 12)
        checkbox.setChecked(True)
        dock.apply()
        self.assertEqual(tracker.setup_parameters.crc.laser_power_A1, 25)
        self.assertEqual(tracker.setup_parameters.to_dict()["crc"]["laser_power_A1"], 12)

    def test_fixed_smiq_defaults_and_tracker_metadata_stay_aligned(self):
        params = SimpleNamespace(frequency_ghz=4.125, power_dbm=-13.5,
                                 frequency_tolerance_hz=1., power_tolerance_dbm=0.01)
        for initially_on, frequency in ((False, 3.9e9), (True, 3.9e9), (True, 4.125e9)):
            with self.subTest(initially_on=initially_on, frequency=frequency):
                state = ["running" if initially_on else "idle"]
                microwave = SimpleNamespace(is_scanning=False, cw_frequency=frequency,
                    cw_power=params.power_dbm, module_state=lambda: state[0],
                    read_cw_parameters=Mock(), set_cw=Mock(), set_cw_parameters_live=Mock(),
                    cw_on=Mock(side_effect=lambda: state.__setitem__(0, "running")))
                tracker = SimpleNamespace(electron_spin=0.5, current_local_oscillator_freq=999.,
                    setup_parameters=self.store.update({"smiq": vars(params)}))
                nuclear = NuclearOPs()
                nuclear.queue = SimpleNamespace(mw_source_smiq=microwave,
                    transition_tracker=tracker, log=logging.getLogger("test_smiq"))
                nuclear.ensure_smiq_cw()
                self.assertEqual(tracker.current_local_oscillator_freq, 4125.)
                if frequency != 4.125e9:
                    setter = microwave.set_cw_parameters_live if initially_on else microwave.set_cw
                    setter.assert_called_once_with(frequency=4.125e9, power=-13.5)
                else:
                    microwave.set_cw.assert_not_called()
                    microwave.set_cw_parameters_live.assert_not_called()
                self.assertEqual(microwave.cw_on.call_count, int(not initially_on))
                microwave.is_scanning = True
                tracker.current_local_oscillator_freq = 999.
                with self.assertRaises(RuntimeError):
                    nuclear.ensure_smiq_cw()
                self.assertEqual(tracker.current_local_oscillator_freq, 999.)

    def test_explicit_smiq_scan_updates_tracker_in_mhz(self):
        tracker = SimpleNamespace(electron_spin=0.5, current_local_oscillator_freq=4000.)
        microwave = SimpleNamespace(cw_power=-14., module_state=lambda: "running",
                                    set_cw_parameters_live=Mock())
        nuclear = NuclearOPs()
        nuclear.queue = SimpleNamespace(mw_source_smiq=microwave,
            transition_tracker=tracker, log=logging.getLogger("test_smiq"))
        nuclear.parameters = OrderedDict(smiq_freq=[3.95e9])
        nuclear.current_iterator_df = pd.DataFrame(dict(smiq_freq=[3.95e9]))
        nuclear.ensure_smiq_cw()
        self.assertEqual(tracker.current_local_oscillator_freq, 4000.)
        nuclear.set_smiq_frequency()
        microwave.set_cw_parameters_live.assert_called_once_with(frequency=3.95e9, power=-14.)
        self.assertEqual(tracker.current_local_oscillator_freq, 3950.)

    def test_qua_build_uses_normalized_amplitude_and_ns_duration(self):
        queue = SimpleNamespace(
            transition_tracker=SimpleNamespace(electron_spin=0.5, log_folder=str(ROOT/"log/transition_tracker_log"), setup_parameters=self.settings),
            tt=SimpleNamespace(snv_frequency_mhz=221.1),
            awg=SimpleNamespace(qm=None, qmm=None, _configuration=None),
            gated_counter=SimpleNamespace(trace=SimpleNamespace(), set_n_values=lambda **kwargs: None))
        ou = NuclearOpsOPXUtils(name="test_opx_utils", config={}, qudi_main_weakref=lambda: None)
        queue.nuclear_ops_opx_utils = ou
        ou._setup_parameters = self.settings
        for kind in ("odmr", "rabi"):
            nuclear = SnVCalibration(kind, str(ROOT/"UserScripts/Qinu/SnV_Rabi_calibration.py"))
            options = dict(amplitudes_percent=np.linspace(0.5, 99.5, 51)) if kind == "rabi" else {}
            nuclear.configure(queue, **options)
            nuclear.set_iterator_df()
            frame = nuclear.iterator_df.iloc[:nuclear.number_of_simultaneous_measurements]
            ou.slow_changing_parameters = nuclear.slow_changing_parameters
            ou.fast_changing_parameters = nuclear.fast_changing_parameters
            ou.create_fast_sweep_qua_arrays(frame, scales=nuclear.opx_fast_sweep_scales)
            if kind == "rabi":
                np.testing.assert_allclose(ou.get_fast_sweep_qua_array(0), frame.MW_pulse_len)
            with patch.object(ou, "set_laser_power"), patch.object(ou, "pause"), \
                 patch.object(sna, "crc"), patch.object(sna, "electron_init"), \
                 patch.object(sna, "ssr"), patch.object(sna, "csr"), \
                 patch.object(ou, "MW_pulse", wraps=ou.MW_pulse) as pulse:
                sequence = nuclear.sequence(nuclear, frame)
                self.assertIsNotNone(sequence.program)
                self.assertEqual(pulse.call_args.kwargs["duration_ns"], "MW_pulse_len")
                self.assertAlmostEqual(pulse.call_args.kwargs["amplitude"], float(frame.MW_amp.iloc[0])/100)
                if kind == "rabi":
                    self.assertIs(ou._get_value_from_key("MW_pulse_len")[1], ou.i_1)

    def test_aborted_run_does_not_publish_calibration(self):
        queue = Signals()
        queue.awg = SimpleNamespace(stop_awgs=lambda: None)
        queue.log = logging.getLogger("test_snv")
        queue.tt = SimpleNamespace()
        messages = []
        queue.snv_calibration_updated.connect(messages.append)
        nuclear = SnVCalibration("rabi", __file__)
        nuclear.queue = queue
        abort = threading.Event()
        abort.set()
        with patch.object(NuclearOPs, "run_measurement"):
            nuclear.run_measurement(abort)
        self.assertEqual(nuclear.state, "idle")
        self.assertIn("unchanged", messages[-1]["status"])

    def test_complete_run_publishes_fit_and_summary(self):
        with tempfile.TemporaryDirectory() as folder:
            queue = Signals()
            tracker = TransitionTracker(name="test_tracker", qudi_main_weakref=lambda: None,
                config=dict(electron_spin=0.5, log_folder=folder))
            tracker._setup_store = SetupParameterStore(Path(folder, "setup_parameters.json"))
            tracker.rabi_parameters = {}
            queue.tt = tracker
            queue.awg = SimpleNamespace(stop_awgs=lambda: None)
            queue.log = logging.getLogger("test_snv")
            messages = []
            queue.snv_calibration_updated.connect(messages.append)
            nuclear = SnVCalibration("rabi", __file__)
            nuclear.queue = queue
            duration = np.arange(20, 2001, 20)
            frame = pd.concat([pd.DataFrame(dict(MW_amp=a, MW_pulse_len=duration, events=100,
                result_0=0.5+0.4*np.cos(2*np.pi*5*(a/100)*(duration/1000)))) for a in (20, 50, 80)])
            nuclear.pld._data = SimpleNamespace(df=frame)
            nuclear.expected_rows = len(frame)
            nuclear.file_path, nuclear.file_name = folder, "test"
            nuclear.start_time = datetime.datetime.now()
            Path(nuclear.save_dir).mkdir()
            with patch.object(NuclearOPs, "run_measurement"):
                nuclear.run_measurement(threading.Event())
            self.assertEqual(nuclear.state, "idle")
            self.assertIn("Saved", messages[-1]["status"])
            self.assertTrue(Path(nuclear.save_dir, "calibration_fit.json").exists())
            np.testing.assert_allclose(tracker.rp("snv_e1_e2").omega(amplitude=[0.5]), [2.5], atol=1e-5)


if __name__ == "__main__":
    unittest.main()
