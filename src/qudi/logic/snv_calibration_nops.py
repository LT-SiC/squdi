"""Queue-owned OPX measurements for the permanent NuclearOps calibration panels."""

import json
import os
from collections import OrderedDict

import numpy as np
from qm import qua
from qudi.hardware.OPX import program_container as pc
from qudi.logic.NuclearOPs import NuclearOPs
from qudi.logic.qudip_enhanced.data_handling import PlotData
from qudi.logic.snv_calibration import fit_odmr, rabi_calibration
from qudi.UserScripts.helpers import snippets_awg_OPX as sna


class SnVCalibration(NuclearOPs):
    def __init__(self, kind, script_path):
        super().__init__()
        if kind not in ("odmr", "rabi"):
            raise ValueError("Unknown SnV calibration.")
        self.kind, self.script_path = kind, script_path
        self.opx_fast_sweep_scales = {}
        self.pld = PlotData(title="SnV " + kind, gui=False)

    def emit(self, **payload):
        self.queue.snv_calibration_updated.emit(dict(kind=self.kind, **payload))

    def start_calibration(self, abort, queue, **options):
        self.queue = queue
        try:
            self.configure(queue, **options)
            self.run(abort)
        except Exception as exc:
            self.emit(status=f"Could not start: {exc}")
            self.report_data_progress("failed", message=str(exc))
            raise

    def configure(self, queue, **options):
        self.queue = queue
        self.capture_setup_parameters()
        if queue.transition_tracker.electron_spin != 0.5:
            raise ValueError("Select electron_spin: 0.5 in the transition tracker configuration.")
        self.reset_settings()
        self.debug_mode = False
        self.hashed = False
        if hasattr(self, "_dtypes"):
            del self._dtypes
        self.make_save_location_params(self.script_path, folder=os.path.join(
            queue.transition_tracker.log_folder, "snv_calibration_runs", self.kind))
        with open(self.script_path, encoding="utf-8") as stream:
            self.meas_code = stream.read()
        self.file_notes = json.dumps(options, indent=2, default=lambda value: value.tolist())
        self.save_trace_efficient = True
        self.do_ple_refocus_A1 = True
        self.lock_laser_to_wavemeter = True
        # Match the regular ODMR/Rabi scripts, and always refocus at the start
        # of a new queued run (the previous run stopped the laser lock).
        self.ple_refocus_interval = 60 if self.kind == "odmr" else 3 * 60
        self.last_ple_refocus = float("-inf")
        self.do_confocal_refocus_red = self.do_confocal_refocus_green = False
        self.start_pause_time = self.end_pause_time = 0
        self.analyze_type = "average"
        self.ana_trace.analyze_sequence = [["init", "<", self.setup_parameters.ssr.init_threshold, 1, 0, 1],
                                           ["result", ">", self.setup_parameters.ssr.threshold, 1, 0, 1],
                                           ["init", ">", self.setup_parameters.csr.csr_threshold, 1, 0, 1]]
        self.ana_trace.consecutive_valid_result_numbers = [0]
        self.ana_trace.average_results = False
        sweeps = int(options.get("sweeps", 5))
        repetitions = int(options.get("repetitions", 200))
        if sweeps < 1 or repetitions < 1:
            raise ValueError("Sweeps and repetitions must be positive.")
        frequency = float(options.get("frequency_mhz", queue.tt.snv_frequency_mhz))
        if not np.isfinite(frequency) or frequency <= 0:
            raise ValueError("Frequency must be positive MHz.")
        state = options.get("init_state", "e1")
        if state not in ("e1", "e2"):
            raise ValueError("Initial state must be e1 or e2.")
        params = OrderedDict([
            ("sweeps", (range(sweeps), "slow")),
            ("click_channel", ([2], "slow")),
            ("init_state", ([state], "slow")),
            ("SSR_state", (["e2" if state == "e1" else "e1"], "slow")),
            ("cooldown_time", ([500_000], "slow")),
        ])
        if self.kind == "rabi":
            amplitudes = np.asarray(options.get("amplitudes_percent", [20, 40, 60, 80, 100]), dtype=float)
            durations = np.asarray(options.get("durations_ns", np.arange(20, 2001, 20)), dtype=float)
            self._validate_axis(amplitudes, 2)
            self._validate_axis(durations, 12)
            if np.any((amplitudes <= 0) | (amplitudes > 100)):
                raise ValueError("Rabi amplitudes must be in (0, 100]%; zero has no oscillation to fit.")
            params.update(MW_f=([round(frequency*1e6)], "slow"),
                          MW_amp=(amplitudes, "slow"),
                          MW_pulse_len=(durations.astype(int), "fast"))
            points = len(durations)
        else:
            span = float(options.get("span_mhz", 10))
            points = int(options.get("points", 81))
            if not np.isfinite(span) or span <= 0 or points < 8 or frequency-span/2 <= 0:
                raise ValueError("Choose a positive frequency window and at least 8 points.")
            frequencies = np.rint(np.linspace(frequency-span/2, frequency+span/2, points)*1e6).astype(int)
            self._validate_axis(frequencies, 8)
            durations = np.array([float(options.get("duration_ns", 512))])
            amplitude = float(options.get("amplitude_percent", 50))
            if not np.isfinite(amplitude) or not 0 < amplitude <= 100:
                raise ValueError("ODMR amplitude must be in (0, 100]%.")
            params.update(MW_pulse_len=(durations.astype(int), "slow"),
                          MW_amp=([amplitude], "slow"), MW_f=(frequencies, "fast"))
        if not np.isfinite(durations).all() or np.any(durations < 20) or np.any(durations % 4 != 0):
            raise ValueError("Pulse durations must be multiples of 4 ns, at least 20 ns.")
        self.parameters = params
        self.number_of_simultaneous_measurements = points
        self.expected_rows = int(np.prod([len(v) for v in self.parameters.values()]))
        self.ret_mcas = self.sequence
        queue.gated_counter.readout_duration = 1e6
        queue.gated_counter.set_n_values(mcas=None, sm=1,
            n_values=points*repetitions*len(self.ana_trace.analyze_sequence))

    @staticmethod
    def _validate_axis(values, minimum):
        if (values.ndim != 1 or values.size < minimum or not np.isfinite(values).all()
                or np.any(np.diff(values) <= 0)):
            raise ValueError(f"Need at least {minimum} finite, increasing scan values.")

    def sequence(self, owner, current_iterator_df, sequence_name=None):
        ou = self.queue.nuclear_ops_opx_utils
        mcas = pc.MultiChSeq(name=sequence_name or "SnV calibration", awg=self.queue.awg, ou=ou)
        row = current_iterator_df.iloc[0]
        with qua.program() as program:
            ou.init_program()
            sna.setup_laser_powers(mcas)
            sweep = ou.get_fast_sweep_qua_array(0)

            ou.pause(10_000)
            with qua.infinite_loop_(), qua.for_each_(ou.i_1, sweep):
                frequency, frequency_qua = ou._get_value_from_key("MW_f")
                qua.update_frequency("MW", frequency if frequency_qua is None else frequency_qua)
                sna.crc(mcas, set_laser_power=False)
                sna.electron_init(mcas, row.init_state, set_laser_power=False)
                sna.ssr(mcas, state="e2" if row.init_state == "e1" else "e1", set_laser_power=False)
                ou.pause(500)
                qua.align()
                # MW_pulse expects ns; it performs the clock conversion itself.
                ou.MW_pulse(duration_ns="MW_pulse_len", amplitude=float(row.MW_amp)/100)
                qua.align()
                ou.pause(500)
                sna.ssr(mcas, state=row.SSR_state, set_laser_power=False)
                sna.csr(mcas, set_laser_power=False)
                ou.pause("cooldown_time")
        mcas.program = program
        return mcas

    def analyze(self, *args, **kwargs):
        repeat = super().analyze(*args, **kwargs)
        if not repeat:
            columns = ["MW_amp", "MW_pulse_len", "MW_f", "result_0"]
            self.emit(status="Acquiring", data=self.data.df[columns].copy(deep=True))
        return repeat

    def run_measurement(self, abort, **kwargs):
        self.emit(status="Acquiring", clear=True)
        try:
            super().run_measurement(abort, **kwargs)
            self.queue.awg.stop_awgs()
            if abort.is_set():
                self.emit(status="Stopped; calibration unchanged")
                return
            self.state = "run"
            frame = self.data.df
            if len(frame) != self.expected_rows or not np.isfinite(frame.result_0).all():
                raise ValueError("Incomplete scan; calibration unchanged.")
            if "events" in frame and (frame.events <= 0).any():
                raise ValueError("Scan contains points with no valid events.")
            if self.kind == "odmr":
                averaged = frame.groupby("MW_f").result_0.mean().sort_index()
                fit = fit_odmr(averaged.index.to_numpy()/1e6, averaged.to_numpy())
                if abort.is_set():
                    self.emit(status="Stopped; calibration unchanged")
                    return
                self.queue.tt.update_snv_frequency(fit.frequency)
                self.emit(status=f"Saved e1 ↔ e2: {fit.frequency:.6f} ± {fit.error:.6f} MHz",
                          fits={"e1 ↔ e2": fit})
                summary = dict(frequency_mhz=fit.frequency, error_mhz=fit.error, r_squared=fit.r_squared)
            else:
                amplitude, omega, fits = rabi_calibration(frame)
                if abort.is_set():
                    self.emit(status="Stopped; calibration unchanged")
                    return
                rp = self.queue.tt.save_snv_rabi_calibration(amplitude, omega)
                sample = np.linspace(amplitude.min(), amplitude.max(), 300)
                self.emit(status="Saved e1 ↔ e2 Rabi calibration from time sweeps", fits=fits,
                          amplitude=amplitude, omega=omega, interpolation_x=sample,
                          interpolation_y=rp.omega(amplitude=sample))
                summary = {str(a): dict(amplitude_percent=a, frequency_mhz=f.frequency,
                                        error_mhz=f.error, r_squared=f.r_squared)
                           for a, f in fits.items()}
            with open(os.path.join(self.save_dir, "calibration_fit.json"), "w", encoding="utf-8") as stream:
                json.dump(summary, stream, indent=2)
        except Exception as exc:
            self.queue.log.exception("SnV calibration failed")
            self.report_data_progress("failed", message=str(exc))
            self.emit(status=f"Failed: {exc}")
            abort.set()
        finally:
            try:
                self.queue.awg.stop_awgs()
            finally:
                self.state = "idle"
