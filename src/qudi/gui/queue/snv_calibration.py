"""Persistent SnV calibration docks; all hardware work is queued."""

import numpy as np
import pyqtgraph as pg
from PySide2 import QtCore, QtWidgets


class SnVCalibrationDock(QtWidgets.QDockWidget):
    def __init__(self, kind, queue, parent):
        super().__init__("SnV ODMR refocus" if kind == "odmr" else "SnV Rabi calibration", parent)
        self.kind, self.queue = kind, queue
        self.setObjectName("snv_" + kind + "_dock")
        self.setFeatures(self.DockWidgetMovable | self.DockWidgetFloatable)
        body = QtWidgets.QWidget(self)
        layout = QtWidgets.QVBoxLayout(body)
        form = QtWidgets.QFormLayout()
        layout.addLayout(form)
        self.controls = {}

        def number(key, label, value, minimum, maximum, decimals=3):
            widget = QtWidgets.QDoubleSpinBox()
            widget.setDecimals(decimals)
            widget.setRange(minimum, maximum)
            widget.setValue(value)
            form.addRow(label, widget)
            self.controls[key] = widget

        number("frequency_mhz", "e1 ↔ e2 OPX IF (MHz)", queue.tt.snv_frequency_mhz, 0.001, 500)
        self.follow_tracker = QtWidgets.QCheckBox("Use latest tracked frequency when run starts")
        self.follow_tracker.setChecked(True)
        self.controls["frequency_mhz"].setEnabled(False)
        self.follow_tracker.toggled.connect(lambda checked: self.controls["frequency_mhz"].setEnabled(not checked))
        form.addRow(self.follow_tracker)
        self.initial_state = QtWidgets.QComboBox()
        self.initial_state.addItems(["e1", "e2"])
        form.addRow("Initial state", self.initial_state)
        if kind == "odmr":
            number("span_mhz", "Frequency span (MHz)", 10, 0.001, 200)
            number("points", "Frequency points", 81, 8, 5001, 0)
            number("duration_ns", "Pulse duration (ns, multiple of 4)", 512, 20, 1000000, 0)
            number("amplitude_percent", "OPX amplitude (%)", 50, 0.01, 100)
        else:
            self.amplitudes = QtWidgets.QLineEdit("20, 40, 60, 80, 100")
            form.addRow("Fixed OPX amplitudes (%)", self.amplitudes)
            number("time_start_ns", "Duration start (ns)", 20, 20, 1000000, 0)
            number("time_stop_ns", "Duration end (ns, inclusive)", 2000, 20, 1000000, 0)
            number("time_step_ns", "Duration step (ns)", 20, 4, 1000000, 0)
        number("sweeps", "Sweeps", 5, 1, 10000, 0)
        number("repetitions", "Repetitions per point", 200, 1, 100000, 0)
        buttons = QtWidgets.QHBoxLayout()
        self.start = QtWidgets.QPushButton("Queue calibration")
        stop = QtWidgets.QPushButton("Stop queue")
        self.start.clicked.connect(self.enqueue)
        stop.clicked.connect(queue.set_stop_request)
        buttons.addWidget(self.start)
        buttons.addWidget(stop)
        layout.addLayout(buttons)
        self.status = QtWidgets.QLabel("Ready — e1 ↔ e2")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.plot = pg.PlotWidget()
        self.plot.setMinimumHeight(200)
        self.plot.addLegend()
        self.plot.setLabel("bottom", "OPX IF (MHz)" if kind == "odmr" else "Pulse duration (ns)")
        self.plot.setLabel("left", "Readout result")
        layout.addWidget(self.plot)
        if kind == "rabi":
            explanation = QtWidgets.QLabel("One time-trace fit per amplitude. Frequencies are Ω/2π in MHz.")
            explanation.setWordWrap(True)
            layout.addWidget(explanation)
            self.omega_plot = pg.PlotWidget()
            self.omega_plot.setMinimumHeight(180)
            self.omega_plot.addLegend()
            self.omega_plot.setLabel("bottom", "OPX amplitude (%)")
            self.omega_plot.setLabel("left", "Ω/2π (MHz)")
            layout.addWidget(self.omega_plot)
            dummy = QtWidgets.QPushButton("Preview synthetic calibration")
            dummy.clicked.connect(self.preview_dummy)
            layout.addWidget(dummy)
        self.setWidget(body)
        queue.snv_calibration_updated.connect(self.update_result, QtCore.Qt.QueuedConnection)

    @QtCore.Slot()
    def enqueue(self):
        try:
            options = {key: widget.value() for key, widget in self.controls.items()}
            if self.follow_tracker.isChecked():
                options.pop("frequency_mhz")
            options["init_state"] = self.initial_state.currentText()
            if self.kind == "rabi":
                amplitudes = [float(value.strip()) for value in self.amplitudes.text().split(",")]
                if (len(amplitudes) < 2 or not np.isfinite(amplitudes).all()
                        or any(a <= 0 or a > 100 for a in amplitudes) or np.any(np.diff(amplitudes) <= 0)):
                    raise ValueError("Use at least two increasing amplitudes in (0, 100]%.")
                options["amplitudes_percent"] = amplitudes
                start, stop, step = (int(options.pop(key)) for key in
                                     ("time_start_ns", "time_stop_ns", "time_step_ns"))
                if start >= stop or any(t % 4 for t in (start, stop, step)) or (stop-start) % step:
                    raise ValueError("Use a rising time grid in multiples of 4 ns; the step must land on the end.")
                points = (stop-start)//step + 1
                if not 12 <= points <= 5001:
                    raise ValueError("Choose 12 to 5001 duration points.")
                options["durations_ns"] = np.arange(start, stop+1, step).tolist()
            elif options["duration_ns"] % 4:
                raise ValueError("Pulse duration must be a multiple of 4 ns.")
            status = self.queue.add_snv_calibration(self.kind, options)
            self.status.setText(status or "Queued; waiting to start")
            self.status.setStyleSheet("")
        except Exception as exc:
            self.status.setText(f"Could not queue calibration: {exc}")
            self.status.setStyleSheet("color: #c0392b; font-weight: bold;")
            self.status.setToolTip(str(exc))

    @QtCore.Slot(object)
    def update_result(self, payload):
        if payload["kind"] != self.kind:
            return
        self.status.setText(payload.get("status", ""))
        self.status.setStyleSheet("")
        if payload.get("clear"):
            self.plot.clear()
            if self.kind == "rabi":
                self.omega_plot.clear()
        if "data" in payload:
            frame = payload["data"].dropna(subset=["result_0"])
            self.plot.clear()
            groups = frame.groupby("MW_amp") if self.kind == "rabi" else [("e1 ↔ e2", frame)]
            for index, (amplitude, rows) in enumerate(groups):
                key = "MW_pulse_len" if self.kind == "rabi" else "MW_f"
                values = rows.groupby(key).result_0.mean().sort_index()
                x = values.index.to_numpy() / (1 if self.kind == "rabi" else 1e6)
                label = f"{amplitude:g}%" if self.kind == "rabi" else str(amplitude)
                self.plot.plot(x, values.to_numpy(), pen=pg.intColor(index), symbol="o", symbolSize=4, name=label)
        if "fits" in payload:
            self.plot.clear()
            for index, (amplitude, fit) in enumerate(payload["fits"].items()):
                scale = 1000 if self.kind == "rabi" else 1
                label = f"{amplitude:g}%" if self.kind == "rabi" else str(amplitude)
                color = pg.intColor(index)
                self.plot.plot(fit.x*scale, fit.y, pen=None, symbol="o", symbolSize=5, symbolBrush=color, name=label)
                self.plot.plot(fit.fit_x*scale, fit.fit_y, pen=color, name=f"Fit {label}, R²={fit.r_squared:.3f}")
        if "omega" in payload:
            self.omega_plot.clear()
            self.omega_plot.plot(payload["amplitude"]*100, payload["omega"], pen=None, symbol="o", name="Time-fit Ω(A)")
            self.omega_plot.plot(payload["interpolation_x"]*100, payload["interpolation_y"], pen="y", name="RabiParameters interpolation")

    @QtCore.Slot()
    def preview_dummy(self):
        rp = self.queue.tt.rabi_parameters.get("snv_e1_e2_dummy")
        if rp is None:
            self.status.setText("Synthetic calibration file not found.")
            return
        amplitude, omega = rp.amp_rabi_freq
        sample = np.linspace(amplitude.min(), amplitude.max(), 300)
        self.update_result(dict(kind="rabi", status="SYNTHETIC preview — not a measured calibration",
            amplitude=amplitude, omega=omega, interpolation_x=sample, interpolation_y=rp.omega(amplitude=sample)))
