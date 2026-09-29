"""Standalone e1/e2 ODMR refocus; also used by the NuclearOps calibration dock."""
from qudi.logic.snv_calibration_nops import SnVCalibration
from qudi.UserScripts.helpers import snippets_awg_OPX as sna

nuclear = SnVCalibration("odmr", __file__)


def run_fun(abort, **kwargs):
    queue = kwargs.pop("queue")
    nuclear.start_calibration(abort, queue, **kwargs)
