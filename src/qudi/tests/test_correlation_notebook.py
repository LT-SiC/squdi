"""Exercise the notebook's actual analysis cells with known event totals."""
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
import pandas as pd

NOTEBOOK = Path(__file__).resolve().parents[1] / "jupyternotebooks/Qinu_stuff/correlation_analysis.ipynb"


class CorrelationNotebookTests(unittest.TestCase):
    def analyze(self, traces, both=False):
        cells = json.loads(NOTEBOOK.read_text(encoding="utf-8"))["cells"]
        ns = dict(np=np, pd=pd, plt=plt, display=lambda *args: None, DATA_DIR=Path("."),
                  INITIAL_CSR_MAX=1, FINAL_CSR_MIN=2, SSR_BRIGHT_THRESHOLD=2,
                  PHOTON_THRESHOLD=0, REQUIRE_EXACTLY_ONE_CLICK=True,
                  REQUIRE_BOTH_PHOTON_BINS=both)
        ns["results"] = pd.DataFrame([
            dict(sweeps=i // 2, SSR_state=state, trace=str(i))
            for i, (state, shots) in enumerate(traces)])
        arrays = {str(i): np.asarray(shots, dtype=int).reshape(-1)
                  for i, (state, shots) in enumerate(traces)}
        with patch.object(np, "load", side_effect=lambda path, **kwargs: arrays[path.name]), \
                contextlib.redirect_stdout(io.StringIO()):
            for index in (4, 6, 7):
                exec("".join(cells[index]["source"]), ns)
        self.addCleanup(plt.close, "all")
        return ns

    def test_failed_acquisitions_excluded_and_event_totals_summed(self):
        ns = self.analyze([
            ("e1", [[0, 1, 0, 3, 5], [0, 0, 1, 3, 5]]),
            ("e2", [[0, 0, 0, 3, 5]] * 4),
            ("e1", [[0, 1, 0, 3, 5], [0, 1, 0, 0, 5]]),
            ("e2", [[0, 0, 1, 3, 5], [1, 1, 0, 3, 5]]),
        ])
        self.assertEqual(ns["diagnostics"]["included"].tolist(), [True, False, True, True])
        np.testing.assert_array_equal(ns["counts"].to_numpy(), [[2, 1], [0, 1]])
        self.assertEqual(ns["total_events"], 4)
        self.assertEqual([t.get_text().split("N=")[1] for t in ns["ax"].texts], ["2", "1", "0", "1"])
        self.assertEqual(sum(len(v) for v in ns["csr_counts_all"]), 6)

    def test_raw_detections_prevent_exclusion_even_if_postselection_rejects_them(self):
        ns = self.analyze([("e1", [[1, 1, 0, 3, 5]])])
        self.assertTrue(ns["diagnostics"].iloc[0]["included"])
        self.assertEqual(ns["total_events"], 0)

    def test_all_failed_and_optional_single_bin_filter(self):
        for shots, both in (([[0, 0, 0, 3, 5]], False), ([[0, 1, 0, 3, 5]], True)):
            with self.subTest(both=both):
                ns = self.analyze([("e1", shots)], both=both)
                self.assertEqual(ns["total_events"], 0)
                self.assertFalse(ns["diagnostics"]["included"].any())


if __name__ == "__main__":
    unittest.main()
