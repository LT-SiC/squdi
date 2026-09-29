"""Sweep pulse duration at fixed OPX amplitudes and calibrate e1/e2 Ω(A)."""
from qudi.logic.snv_calibration_nops import SnVCalibration
from qudi.UserScripts.helpers import snippets_awg_OPX as sna

nuclear = SnVCalibration("rabi", __file__)


def run_fun(abort, **kwargs):
    queue = kwargs.pop("queue")
    nuclear.start_calibration(abort, queue, **kwargs)
