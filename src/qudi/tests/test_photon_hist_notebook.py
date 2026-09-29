"""Check both photon-histogram fits and background-subtracted area ratios."""
import contextlib
import io
import json
from pathlib import Path
import unittest
from unittest.mock import patch

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from scipy.integrate import quad

NOTEBOOK = Path(__file__).resolve().parents[1] / "jupyternotebooks/Qinu_stuff/photon_hist.ipynb"


class PhotonHistogramTests(unittest.TestCase):
    def test_gaussian_decay_and_count_ratio(self):
        cells = json.loads(NOTEBOOK.read_text(encoding="utf-8"))["cells"]
        times = np.arange(240) * 0.25
        counts = np.where(times < 9.5,
                          300 * np.exp(-0.5 * ((times - 7.7) / 0.45)**2) + 2,
                          30 * np.exp(-(times - 10) / 5) + 2)
        ns = {}
        with patch.object(np, "loadtxt", return_value=counts), \
                patch.object(Path, "read_text", return_value="# bin width=2.5e-10\n"), \
                patch.object(plt, "show"), contextlib.redirect_stdout(io.StringIO()):
            exec("".join(cells[0]["source"]), ns)
            self.assertAlmostEqual(ns["gaussian_center_ns"], 7.7, places=4)
            self.assertAlmostEqual(ns["gaussian_sigma_ns"], 0.45, places=4)
            self.assertAlmostEqual(ns["t1_ns"], 5, places=4)
            laser = quad(lambda t: 300 * np.exp(-0.5 * ((t - 7.7) / 0.45)**2), 6, 9)[0] / 0.25
            emission = quad(lambda t: 30 * np.exp(-(t - 10) / 5), 10, 25)[0] / 0.25
            self.assertAlmostEqual(ns["laser_counts"], laser, places=2)
            self.assertAlmostEqual(ns["emission_counts"], emission, places=2)
            self.assertAlmostEqual(ns["suppression_db"], 10 * np.log10(emission / laser), places=4)
            self.assertIn("Emission / laser", ns["ax"].texts[0].get_text())
            exec("".join(cells[1]["source"]), ns)
            self.assertEqual(ns["ax"].get_yscale(), "linear")
            self.assertEqual(ns["ax"].get_xlim(), (10, 25))
        plt.close("all")


if __name__ == "__main__":
    unittest.main()
