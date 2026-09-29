"""Grouped editor for persistent transition-tracker setup settings."""
from PySide2 import QtCore, QtWidgets
from qudi.logic.transition_tracker_settings import SCHEMA


class SetupParametersDock(QtWidgets.QDockWidget):
    def __init__(self, tracker, parent=None):
        super().__init__("OPX setup parameters", parent)
        self.setObjectName("opx_setup_parameters")
        self.tracker = tracker
        self.editors, self.dirty = {}, set()
        body = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(body)
        info = QtWidgets.QLabel(
            "Apply saves defaults for the next queued experiment. Running experiments keep their snapshot. "
            "General A1/B2 powers override group powers when checked. "
            "Qinu sets powers once at program startup; pulse helpers leave them unchanged by default.")
        info.setWordWrap(True)
        layout.addWidget(info)
        self.tabs = QtWidgets.QTabWidget()
        layout.addWidget(self.tabs)
        for group, fields in SCHEMA.items():
            page = QtWidgets.QWidget()
            form = QtWidgets.QFormLayout(page)
            for name, spec in fields.items():
                key = (group, name)
                if spec.choices:
                    editor = QtWidgets.QComboBox()
                    editor.addItems(spec.choices)
                    signal = editor.currentTextChanged
                elif isinstance(spec.default, bool):
                    editor = QtWidgets.QCheckBox()
                    signal = editor.toggled
                else:
                    editor = QtWidgets.QLineEdit()
                    signal = editor.textEdited
                editor.setToolTip(spec.description or f"{group}.{name}")
                signal.connect(lambda *args, key=key: self.mark_dirty(key))
                self.editors[key] = editor
                label = name.replace("_", " ")
                if key == ("general", "override_operation_powers"):
                    label = "Use general A1/B2 powers for all groups"
                elif key == ("csr", "use_crc_threshold"):
                    label = "Use CRC threshold"
                elif key == ("crc", "repump_laser"):
                    label = "CRC repump laser"
                elif key == ("crc", "laser_power_repump"):
                    label = "520 nm repump power"
                elif key == ("crc", "laser_power_repump_450"):
                    label = "450 nm repump power"
                elif key == ("ssr", "threshold"):
                    label = "SSR threshold"
                elif key == ("ssr", "init_threshold"):
                    label = "Init SSR threshold"
                if spec.unit:
                    label += f" ({spec.unit})"
                form.addRow(label, editor)
            scroll = QtWidgets.QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setWidget(page)
            self.tabs.addTab(scroll, group.replace("_", " ").upper())
        buttons = QtWidgets.QHBoxLayout()
        self.apply_button = QtWidgets.QPushButton("Apply and save")
        self.reload_button = QtWidgets.QPushButton("Discard edits")
        self.rabi_button = QtWidgets.QPushButton("Use measured Rabi period")
        self.rabi_button.setToolTip("Interpolate at the saved gate amplitude; round the period to 16 ns.")
        for button in (self.apply_button, self.reload_button, self.rabi_button):
            buttons.addWidget(button)
        layout.addLayout(buttons)
        self.status = QtWidgets.QLabel()
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.setWidget(body)
        self.apply_button.clicked.connect(self.apply)
        self.reload_button.clicked.connect(self.discard)
        self.rabi_button.clicked.connect(self.use_rabi_period)
        tracker.setup_parameters_changed.connect(self.refresh, QtCore.Qt.QueuedConnection)
        self.refresh()

    def mark_dirty(self, key):
        self.dirty.add(key)
        if key == ("general", "override_operation_powers"):
            self.update_power_override_controls()
        if key == ("csr", "use_crc_threshold"):
            self.update_threshold_controls()
        self.status.setText("Unsaved edits. Apply to use them in the next experiment.")

    def refresh(self):
        values = self.tracker.setup_parameters.to_dict()
        for (group, name), editor in self.editors.items():
            if (group, name) in self.dirty:
                continue
            value = values[group][name]
            blocker = QtCore.QSignalBlocker(editor)
            if isinstance(editor, QtWidgets.QComboBox):
                editor.setCurrentText(value)
            elif isinstance(editor, QtWidgets.QCheckBox):
                editor.setChecked(value)
            else:
                editor.setText(str(value))
            del blocker
        self.update_power_override_controls()
        self.update_threshold_controls()

    def update_threshold_controls(self):
        linked = self.editors["csr", "use_crc_threshold"].isChecked()
        editor = self.editors["csr", "csr_threshold"]
        editor.setEnabled(not linked)
        editor.setToolTip("Stored independent CSR value; CRC threshold is used while checked."
                          if linked else SCHEMA["csr"]["csr_threshold"].description)

    def update_power_override_controls(self):
        override = self.editors["general", "override_operation_powers"].isChecked()
        for (group, name), editor in self.editors.items():
            if group != "general" and name in ("laser_power_A1", "laser_power_B2"):
                editor.setEnabled(not override)
                editor.setToolTip(
                    "Stored group value; general A1/B2 power is used while override is checked."
                    if override else "Group value used when explicitly setting this operation's power.")

    def discard(self):
        self.dirty.clear()
        self.refresh()
        self.status.setText("Showing saved settings.")

    def apply(self):
        try:
            changes = {}
            for group, name in self.dirty:
                editor = self.editors[group, name]
                if isinstance(editor, QtWidgets.QComboBox):
                    value = editor.currentText()
                elif isinstance(editor, QtWidgets.QCheckBox):
                    value = editor.isChecked()
                else:
                    value = float(editor.text())
                changes.setdefault(group, {})[name] = value
            if changes:
                self.tracker.update_setup_parameters(changes)
            self.dirty.clear()
            self.refresh()
            self.status.setText("Saved for the next experiment. After changing gate amplitude, use the measured Rabi period or set it manually.")
        except (ValueError, OSError) as exc:
            self.status.setText(f"Settings were not saved: {exc}")

    def use_rabi_period(self):
        if self.dirty:
            self.status.setText("Apply or discard pending edits before using the measured Rabi period.")
            return
        try:
            period = self.tracker.apply_rabi_period()
            self.status.setText(f"Saved gate period: {period} ns (rounded to 16 ns).")
        except (ValueError, OSError) as exc:
            self.status.setText(str(exc))

    def disconnect_tracker(self):
        self.tracker.setup_parameters_changed.disconnect(self.refresh)
