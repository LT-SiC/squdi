"""Scheduled NuclearOps pauses with a simulated clock and no hardware."""
import datetime
import threading
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from test_snv_calibration_integration import NuclearOPs, AcquisitionProgressBar, QtWidgets
import pandas as pd


class ScheduledPauseTests(unittest.TestCase):
    def check_window(self, start, end, times, stop=False):
        measurement = SimpleNamespace(start_pause_time=start, end_pause_time=end,
                                      queue=SimpleNamespace(log=Mock()),
                                      report_data_progress=Mock())
        abort = threading.Event()
        real_datetime = datetime.datetime
        clock = [datetime.datetime(2026, 9, 24) + datetime.timedelta(hours=t) for t in times]
        with patch("qudi.logic.NuclearOPs.datetime.datetime") as dt, \
                patch.object(abort, "wait", side_effect=lambda timeout: abort.set() if stop else None) as wait:
            dt.now.side_effect = clock
            dt.combine.side_effect = real_datetime.combine
            waited = NuclearOPs.checktime(measurement, abort)
        return measurement, waited, wait.call_count

    def test_boundaries_and_disabled_window(self):
        for start, end, times, waits in (
                (1.75, 6.25, [1.749], 0),
                (1.75, 6.25, [1.75, 6.25], 1),
                (1.75, 6.25, [6.25], 0),
                (23, 6, [23, 25, 30], 2),
                (23, 6, [12], 0),
                (0, 0, [], 0),
                (24, 0, [], 0)):
            with self.subTest(start=start, end=end, times=times):
                measurement, waited, count = self.check_window(start, end, times)
                self.assertEqual(count, waits)
                self.assertEqual(waited, bool(waits))
                if waits:
                    phases = [call.args[0] for call in measurement.report_data_progress.call_args_list]
                    self.assertEqual(phases, ["paused", "preparing"])

    def test_stop_interrupts_pause_without_resuming(self):
        measurement, waited, count = self.check_window(1, 6, [2], stop=True)
        self.assertTrue(waited)
        self.assertEqual(count, 1)
        self.assertEqual(measurement.report_data_progress.call_count, 1)
        self.assertEqual(measurement.report_data_progress.call_args.args[0], "paused")

    def test_invalid_hours_fail_clearly(self):
        for value in (-1, 25, float("nan"), float("inf")):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, "decimal hours"):
                self.check_window(value, 6, [])

    def test_runner_checks_before_preparation_and_before_acquisition(self):
        for stop_on_check in (1, 2, 3):
            with self.subTest(stop_on_check=stop_on_check):
                abort = threading.Event()
                checks = []

                def checktime(event):
                    checks.append(True)
                    if len(checks) == stop_on_check:
                        event.set()
                    # Simulate an overnight wait after compilation. The runner
                    # must restart preparation rather than acquire immediately.
                    return len(checks) == 2

                frame = pd.DataFrame()
                measurement = SimpleNamespace(
                    queue=SimpleNamespace(log=Mock(), gated_counter=Mock(),
                                          confocal=SimpleNamespace(scanner_position=dict(x=0, y=0, z=0))),
                    init_run=Mock(), ensure_smiq_cw=Mock(), iterator=lambda: iter([None]),
                    check_manual_pause=Mock(), checktime=checktime, report_data_progress=Mock(),
                    lock_laser_to_wavemeter=False, do_ple_refocus_A1=False,
                    do_confocal_refocus_green=False, do_confocal_refocus_red=False,
                    current_iterator_df=frame, setup_rf=Mock(), hashed=False,
                    get_trace=Mock(), mark_completed_rows_done=Mock(),
                    data=SimpleNamespace(df=frame), iterator_df_done=frame, pld=Mock(),
                    update_current_str=Mock(), session_meas_count=1,
                    save_dir="unused", stop_laser_lock=Mock())
                with patch("qudi.logic.NuclearOPs.data_handling.df_take_duplicate_rows", return_value=frame), \
                        patch("qudi.logic.NuclearOPs.os.path.exists", return_value=False):
                    NuclearOPs.run_measurement(measurement, abort)
                self.assertEqual(len(checks), stop_on_check)
                self.assertEqual(measurement.setup_rf.call_count, 0 if stop_on_check == 1 else 1)
                measurement.get_trace.assert_not_called()
                measurement.stop_laser_lock.assert_called_once()

    def test_pause_status_is_visible_in_queue(self):
        app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
        bar = AcquisitionProgressBar()
        bar.update_progress(dict(phase="paused", message="Scheduled pause until 06:15"))
        self.assertEqual(bar.format(), "Scheduled pause until 06:15")
        bar.update_progress(dict(phase="preparing"))
        self.assertIn("Preparing", bar.format())
        bar.close()


if __name__ == "__main__":
    unittest.main()
