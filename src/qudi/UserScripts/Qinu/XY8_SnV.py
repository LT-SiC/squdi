"""Sweep complete XY blocks at fixed total free-evolution time.

Based on Hahn_echo_SnV_new.py. Edit the scan controls in settings().
num_pulses counts refocusing pi pulses, excluding the two pi/2 pulses.
For N pulses the free gaps are tau, 2*tau, ..., 2*tau, tau, with
tau = total_free_evolution_ns / (2*N). Microwave pulse durations are
additional, so the full sequence duration grows slightly with N.
"""

import importlib
import os
from collections import OrderedDict

import qudi.hardware.OPX.program_container as pc
import qudi.UserScripts.helpers.sequence_creation_helpers as sch
import qudi.UserScripts.helpers.shared as ush
import qudi.UserScripts.helpers.snippets_awg_OPX as sna
from qm import qua
from qm.qua import for_each_, infinite_loop_
from qudi.hardware.OPX import OPX_utils
from qudi.logic.nuclear_ops_opx_utils import NuclearOpsOPXUtils
from qudi.logic.NuclearOPs import NuclearOPs

importlib.reload(sch)
importlib.reload(ush)
importlib.reload(sna)
importlib.reload(pc)
importlib.reload(OPX_utils)

seq_name = os.path.splitext(os.path.basename(__file__))[0]
nuclear: NuclearOPs = sch.create_nuclear(__file__)
with open(__file__, "r", encoding="utf-8") as f:
    meas_code = f.read()


XY8_AXES = ("x", "y", "x", "y", "y", "x", "y", "x")
# Same XY16 phase convention as XY_n.py: XY8 followed by phase-inverted XY8.
XY_PHASE_BLOCKS = {
    "XY4": ("x", "y", "x", "y"),
    "XY8": XY8_AXES,
    "XY16": XY8_AXES + tuple("-" + axis for axis in XY8_AXES),
}


def ret_ret_mcas(pdc):
    def ret_mcas(self, current_iterator_df, sequence_name=None):
        sequence_name = "XY pulse-count sweep" if sequence_name is None else sequence_name
        ou: NuclearOpsOPXUtils = self.queue.nuclear_ops_opx_utils
        mcas = pc.MultiChSeq(name=sequence_name, awg=self.queue.awg, ou=ou)

        # Each acquisition uses one pulse count and one total evolution time.
        sequence = current_iterator_df["sequence"].unique()[0]
        num_pulses = int(current_iterator_df["num_pulses"].unique()[0])
        total_time_ns = current_iterator_df["total_free_evolution_ns"].unique()[0]
        last_pulse = current_iterator_df["last_pulse"].unique()[0]
        init_state = current_iterator_df["init_state"].unique()[0]
        SSR_state = current_iterator_df["SSR_state"].unique()[0]

        # N refocusing pulses: tau at each end, 2*tau between pi pulses.
        # Total free-evolution time = 2*N*tau (excluding microwave pulses).
        tau_ns = total_time_ns / (2 * num_pulses)
        phase_block = XY_PHASE_BLOCKS[sequence]
        qua_array_1 = ou.get_fast_sweep_qua_array(0)
        qua_array_2 = ou.get_fast_sweep_qua_array(1)

        with qua.program() as myprog:
            ou.init_program()
            sna.setup_laser_powers(mcas)
            sna.set_IQ_freq(mcas)
            ou.pause(10_000)
            with infinite_loop_(), for_each_(ou.i_1, qua_array_1):
                with for_each_(ou.i_2, qua_array_2):
                    # Prepare the charge/spin state and record the initial SSR.
                    sna.crc(mcas, set_laser_power=False)
                    sna.electron_init(mcas, init_state, set_laser_power=False)
                    sna.ssr(mcas, state="e2" if init_state == "e1" else "e1", set_laser_power=False)
                    ou.pause(1000)

                    # pi/2 -- tau -- pi -- 2*tau -- ... -- pi -- tau -- pi/2
                    # Keep all coherent gates and gaps on MW without realigning.
                    qua.align()
                    with qua.strict_timing_():
                        sna.electron_gate(mcas, "pi/2", align_elements=False)
                        ou.pause(tau_ns, align_before=False, elements="MW")

                        for pulse_index in range(num_pulses):
                            if pulse_index > 0:
                                ou.pause(2 * tau_ns, align_before=False, elements="MW")
                            # Repeat the chosen phase block, e.g. X Y X Y Y X Y X.
                            axis = phase_block[pulse_index % len(phase_block)]
                            sna.electron_gate(mcas, "pi", axis=axis, align_elements=False)

                        ou.pause(tau_ns, align_before=False, elements="MW")
                        sna.electron_gate(mcas, "pi/2", axis=last_pulse, align_elements=False)

                    # Read out the final spin state, then check the charge state.
                    ou.pause(1000)
                    sna.ssr(mcas, state=SSR_state, set_laser_power=False)
                    sna.csr(mcas, set_laser_power=False)
                    ou.pause("cooldown_time")
                    qua.align()

        mcas.program = myprog
        return mcas

    return ret_mcas


def settings(pdc=None):
    if pdc is None:
        pdc = {}

    # Edit these scan controls. Use pulse counts that are multiples of 4/8/16.
    sequence = "XY8"  # "XY4", "XY8", or "XY16"
    num_pulses_array = [8, 16, 32, 64, 128]  # For XY16 start at 16.
    total_free_evolution_ns_array = [102_400]  # 102.4 us, held fixed as N changes.
    # Multiple total times also allow a coherence-time scan for each pulse count.
    # Every T/(2*N) must be >=16 ns and an exact multiple of the 4 ns OPX clock.
    nr_repeating_integration = 1000

    ana_seq = [
        ["init", "<", nuclear.setup_parameters.ssr.init_threshold, 1, 0, 1],
        ["result", ">", nuclear.setup_parameters.ssr.threshold, 1, 0, 1],
        ["init", ">", nuclear.setup_parameters.csr.csr_threshold, 1, 0, 1],
    ]
    sch.settings(
        nuclear=nuclear, ret_mcas=ret_ret_mcas(pdc), analyze_sequence=ana_seq,
        pdc=pdc, meas_code=meas_code,
    )

    nuclear.x_axis_title = "Number of refocusing pi pulses"
    nuclear.analyze_type = "average"
    nuclear.save_smartly = False
    nuclear.no_trace = False
    nuclear.save_trace_efficient = True
    nuclear.do_ple_refocus_A1 = True
    nuclear.lock_laser_to_wavemeter = True
    nuclear.ple_refocus_interval = 2 * 60
    nuclear.do_confocal_refocus_red = False
    nuclear.do_confocal_refocus_green = False
    nuclear.confocal_refocus_interval = 10 * 60
    nuclear.queue.gated_counter.trace.consecutive_valid_result_numbers = [0]
    nuclear.queue.gated_counter.trace.average_results = False

    # Slow sweep: build one pulse sequence for each N and total evolution time.
    # The two preparation states and +/-X final pulses follow the Hahn script.
    nuclear.parameters = OrderedDict((
        ("sweeps", range(10)),
        ("click_channel", [2]),
        ("init_state", (["e1", "e2"], "slow")),
        ("SSR_state", (["e1"], "slow")),
        ("last_pulse", (["x", "-x"], "slow")),
        ("sequence", ([sequence], "slow")),
        ("total_free_evolution_ns", (total_free_evolution_ns_array, "slow")),
        ("num_pulses", (num_pulses_array, "slow")),
        ("cooldown_time", [500]),
    ))
    nuclear.number_of_simultaneous_measurements = 1
    nuclear.queue.gated_counter.set_n_values(
        mcas=None, sm=1,
        n_values=nr_repeating_integration * len(ana_seq),
    )


def run_fun(abort, **kwargs):
    nuclear.queue = kwargs["queue"]
    nuclear.capture_setup_parameters()
    nuclear.queue.gated_counter.readout_duration = 1 * 1e6
    nuclear.hashed = False
    nuclear.debug_mode = False
    settings()
    nuclear.run(abort)
