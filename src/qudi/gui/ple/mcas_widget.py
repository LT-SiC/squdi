# -*- coding: utf-8 -*-

"""GUI controls for PLE state settings that do not directly actuate hardware."""

import os
from typing import cast

from PySide6 import QtCore, QtWidgets

import qudi.util.uic as uic
from qudi.util.widgets.scientific_spinbox import ScienDSpinBox


class MCASWidget(QtWidgets.QWidget):
    """Controls A1/A2/repump/init-charge flags and microwave settings."""

    sigControlsChanged = QtCore.Signal(dict)
    microwaveTable: QtWidgets.QTableWidget
    a1CheckBox: QtWidgets.QCheckBox
    a2CheckBox: QtWidgets.QCheckBox
    repumpCheckBox: QtWidgets.QCheckBox
    initChargeCheckBox: QtWidgets.QCheckBox
    addMicrowaveButton: QtWidgets.QPushButton
    removeMicrowaveButton: QtWidgets.QPushButton

    _FREQUENCY_RANGE = (0.0, 1e12)
    _AMPLITUDE_RANGE = (-200.0, 100.0)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        ui_file = os.path.join(os.path.dirname(__file__), 'mcas_widget.ui')
        uic.loadUi(ui_file, self)
        self._updating = False

        self.microwaveTable.setHorizontalHeaderLabels(
            ('Frequency [Hz]', 'Amplitude [dBm]')
        )
        self.microwaveTable.verticalHeader().setVisible(False)
        self.microwaveTable.setSelectionBehavior(
            QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.microwaveTable.horizontalHeader().setSectionResizeMode(
            QtWidgets.QHeaderView.ResizeMode.Stretch
        )

        for checkbox in (
            self.a1CheckBox,
            self.a2CheckBox,
            self.repumpCheckBox,
            self.initChargeCheckBox,
        ):
            checkbox.toggled.connect(self._emit_controls_changed)

        self.addMicrowaveButton.clicked.connect(self._add_microwave_row)
        self.removeMicrowaveButton.clicked.connect(self._remove_microwave_rows)

    @property
    def controls(self):
        return {
            'a1': self.a1CheckBox.isChecked(),
            'a2': self.a2CheckBox.isChecked(),
            'repump': self.repumpCheckBox.isChecked(),
            'init_charge': self.initChargeCheckBox.isChecked(),
            'microwaves': [
                {
                    'frequency': cast(
                        ScienDSpinBox, self.microwaveTable.cellWidget(row, 0)
                    ).value(),
                    'amplitude': cast(
                        ScienDSpinBox, self.microwaveTable.cellWidget(row, 1)
                    ).value(),
                }
                for row in range(self.microwaveTable.rowCount())
            ],
        }

    def get_controls(self):
        return self.controls

    def set_controls(self, controls):
        self._updating = True
        try:
            self.a1CheckBox.setChecked(bool(controls.get('a1', False)))
            self.a2CheckBox.setChecked(bool(controls.get('a2', False)))
            self.repumpCheckBox.setChecked(bool(controls.get('repump', False)))
            self.initChargeCheckBox.setChecked(
                bool(controls.get('init_charge', False))
            )
            self.microwaveTable.setRowCount(0)
            for microwave in controls.get('microwaves', []):
                self._add_microwave_row(
                    microwave['frequency'],
                    microwave['amplitude'],
                    emit=False,
                )
        finally:
            self._updating = False

    @QtCore.Slot()
    def _emit_controls_changed(self, *args):
        if not self._updating:
            self.sigControlsChanged.emit(self.controls)

    def _add_microwave_row(self, frequency=0.0, amplitude=0.0, emit=True):
        row = self.microwaveTable.rowCount()
        self.microwaveTable.insertRow(row)

        frequency_spinbox = self._make_spinbox(
            self._FREQUENCY_RANGE,
            'Hz',
            frequency,
        )
        amplitude_spinbox = self._make_spinbox(
            self._AMPLITUDE_RANGE,
            'dBm',
            amplitude,
        )
        self.microwaveTable.setCellWidget(row, 0, frequency_spinbox)
        self.microwaveTable.setCellWidget(row, 1, amplitude_spinbox)
        frequency_spinbox.editingFinished.connect(self._emit_controls_changed)
        amplitude_spinbox.editingFinished.connect(self._emit_controls_changed)
        if emit:
            self._emit_controls_changed()

    def _remove_microwave_rows(self):
        rows = sorted(
            {index.row() for index in self.microwaveTable.selectedIndexes()},
            reverse=True,
        )
        if not rows and self.microwaveTable.rowCount():
            rows = [self.microwaveTable.rowCount() - 1]
        for row in rows:
            self.microwaveTable.removeRow(row)
        self._emit_controls_changed()

    @staticmethod
    def _make_spinbox(value_range, suffix, value):
        spinbox = ScienDSpinBox()
        spinbox.setRange(*value_range)
        spinbox.setDecimals(6)
        spinbox.setSuffix(suffix)
        spinbox.setButtonSymbols(QtWidgets.QAbstractSpinBox.ButtonSymbols.NoButtons)
        width = max(90, spinbox.sizeHint().width())
        spinbox.setMinimumSize(width, spinbox.sizeHint().height())
        spinbox.lineEdit().setMinimumWidth(width)
        spinbox.setValue(value)
        return spinbox
