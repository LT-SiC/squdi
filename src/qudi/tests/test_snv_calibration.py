"""Hardware-free checks: run with the Qudi Python environment."""
import ast
from pathlib import Path
import sys
import tempfile
import unittest

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))
from qudi.logic.snv_calibration import fit_time_sine, fit_odmr, rabi_calibration


class FitTests(unittest.TestCase):
    def test_time_sweeps_recover_nonlinear_rabi_response(self):
        rng = np.random.default_rng(1234)
        duration = np.arange(20, 2001, 20)
        frames = []
        for amp in (20, 40, 60, 80, 100):
            for sweep in range(3):
                frequency = 3*(amp/100) + 2*(amp/100)**2
                y = 0.5 + 0.4*np.cos(2*np.pi*frequency*(duration/1000)+0.27)
                frames.append(pd.DataFrame(dict(MW_amp=amp, MW_pulse_len=duration,
                    result_0=y+rng.normal(0, 0.01, len(duration)), sweeps=sweep)))
        amplitude, omega, fits = rabi_calibration(pd.concat(frames))
        np.testing.assert_allclose(omega, 3*amplitude+2*amplitude**2, atol=0.01)
        self.assertEqual(list(fits), [20, 40, 60, 80, 100])
        np.testing.assert_allclose(fits[20].x, duration/1000)

    def test_flat_and_missing_data_rejected(self):
        x = np.arange(20, 2001, 20)
        with self.assertRaises(ValueError):
            fit_time_sine(x, np.ones_like(x))
        y = np.sin(2*np.pi*3*x/1000)
        y[4] = np.nan
        with self.assertRaises(ValueError):
            fit_time_sine(x, y)

    def test_nonmonotonic_frequencies_rejected(self):
        duration = np.arange(20, 2001, 20)
        frame = pd.concat([pd.DataFrame(dict(MW_amp=a, MW_pulse_len=duration,
            result_0=0.5+0.4*np.cos(2*np.pi*f*duration/1000)))
            for a, f in ((20, 5), (80, 3))])
        with self.assertRaisesRegex(ValueError, "increase"):
            rabi_calibration(frame)

    def test_zero_amplitude_and_single_amplitude_rejected(self):
        duration = np.arange(20, 2001, 20)
        frame = pd.DataFrame(dict(MW_amp=0., MW_pulse_len=duration,
            result_0=0.5+0.4*np.cos(2*np.pi*3*duration/1000)))
        with self.assertRaisesRegex(ValueError, "zero"):
            rabi_calibration(frame)
        frame.MW_amp = 50.
        with self.assertRaisesRegex(ValueError, "at least two"):
            rabi_calibration(frame)

    def test_odmr_peak_and_dip(self):
        x = np.linspace(216, 226, 101)
        for contrast in (-0.3, 0.3):
            fit = fit_odmr(x, 0.5 + contrast/(1+((x-221.23)/0.45)**2))
            self.assertAlmostEqual(fit.frequency, 221.23, places=5)

    def test_existing_rabi_parameters_round_trip_and_archive(self):
        # Execute the actual standalone RP class, avoiding the tracker's Qt/
        # hardware imports; exercise its real file format and interpolator.
        import collections
        import datetime
        import os
        import shutil
        import scipy
        tree = ast.parse((ROOT / "logic/transition_tracker.py").read_text(encoding="utf-8"))
        nodes = [node for node in tree.body if isinstance(node, (ast.ClassDef, ast.FunctionDef))
                 and node.name in ("RabiParametersStatic", "nowstr")]
        namespace = dict(np=np, pd=pd, scipy=scipy, collections=collections,
                         datetime=datetime, os=os, shutil=shutil)
        exec(compile(ast.Module(body=nodes, type_ignores=[]), "transition_tracker.py", "exec"), namespace)
        cls = namespace["RabiParametersStatic"]
        rp = cls(str(ROOT / "log/transition_tracker_log/snv_e1_e2_dummy_rabi.dat"))
        np.testing.assert_allclose(rp.omega(amplitude=[0.2, 0.5, 0.9]), [1, 2.5, 4.5])
        np.testing.assert_allclose(rp.amplitude(omega=[1, 2.5, 4.5]), [0.2, 0.5, 0.9])
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/"calibration.dat"
            shutil.copyfile(rp.filepath, path)
            copy = cls(str(path))
            frame = copy.data_dataframe()
            frame["omega"] = frame.omega.astype(float)*2
            copy.update_file(frame)
            self.assertEqual(len(list((Path(folder)/"rabi_parameters_archive").rglob("*.dat"))), 1)
            np.testing.assert_allclose(copy.omega(amplitude=[0.5]), [5])

    def test_changed_python_files_parse(self):
        files = ["logic/snv_calibration.py", "logic/snv_calibration_nops.py",
                 "logic/transition_tracker.py", "logic/qudip_enhanced/nv_hamilton.py",
                 "logic/queue/queue_logic.py", "logic/NuclearOPs.py", "gui/queue/Queue.py",
                 "gui/queue/snv_calibration.py", "gui/transition_tracker/transition_tracker_gui.py",
                 "UserScripts/Qinu/SnV_ODMR_refocus.py", "UserScripts/Qinu/SnV_Rabi_calibration.py"]
        for name in files:
            with self.subTest(name=name):
                ast.parse((ROOT/name).read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
