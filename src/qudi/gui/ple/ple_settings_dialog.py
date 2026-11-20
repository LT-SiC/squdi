# -*- coding: utf-8 -*-

"""Settings dialog for PLE scanner controls."""

__all__ = ('PleSettingDialog', 'ScannerSettingsWidget')

from PySide6 import QtCore, QtGui, QtWidgets
from qudi.util.widgets.scientific_spinbox import ScienDSpinBox


class PleSettingDialog(QtWidgets.QDialog):
    """Dialog for infrequently changed PLE scanner settings."""

    def __init__(self, scanner_axes, scanner_constraints):
        super().__init__()
        self.setObjectName('scanner_settings_dialog')
        self.setWindowTitle('Scanner Settings')

        self.settings_widget = ScannerSettingsWidget(
            scanner_axes=scanner_axes,
            scanner_constraints=scanner_constraints,
        )
        self.button_box = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.StandardButton.Ok
            | QtWidgets.QDialogButtonBox.StandardButton.Cancel
            | QtWidgets.QDialogButtonBox.StandardButton.Apply,
            QtCore.Qt.Horizontal,
            self,
        )
        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)

        layout = QtWidgets.QVBoxLayout(self)
        layout.addWidget(self.settings_widget)
        layout.addWidget(self.button_box)
        layout.setSizeConstraint(QtWidgets.QLayout.SetFixedSize)


class ScannerSettingsWidget(QtWidgets.QWidget):
    """Widget containing PLE scanner frequency, range, shift, and control settings."""

    sigFrequencyChanged = QtCore.Signal(str, float, float)
    sigShiftChanged = QtCore.Signal(str, float)

    def __init__(self, *args, scanner_axes, scanner_constraints, **kwargs):
        super().__init__(*args, **kwargs)
        self.axes_widgets = {}
        self._backscan_configurable = scanner_constraints._backscan_configurable
        self._controls = {}
        self._microwave_frequency_range = (0.0, 1e12)
        self._microwave_amplitude_range = (-200.0, 100.0)

        font = QtGui.QFont()
        font.setBold(True)

        # frequency_layout = QtWidgets.QGridLayout()
        # for column, heading in enumerate(('Axis', 'Forward', 'Backward')):
        #     label = QtWidgets.QLabel(heading)
        #     label.setFont(font)
        #     label.setAlignment(QtCore.Qt.AlignCenter)
        #     frequency_layout.addWidget(label, 0, column)

        shift_layout = QtWidgets.QGridLayout()
        range_layout = QtWidgets.QGridLayout()
        for column, heading in enumerate(('Axis', 'Shift')):
            label = QtWidgets.QLabel(heading)
            label.setFont(font)
            label.setAlignment(QtCore.Qt.AlignCenter)
            shift_layout.addWidget(label, 0, column)
        for column, heading in enumerate(('Axis', 'Start', 'Stop')):
            label = QtWidgets.QLabel(heading)
            label.setFont(font)
            label.setAlignment(QtCore.Qt.AlignCenter)
            range_layout.addWidget(label, 0, column)

        for row, axis in enumerate(scanner_axes, 1):
            name = axis.name
        #     label = QtWidgets.QLabel(f'{name.title()}-Axis:')
        #     label.setAlignment(QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)
            # frequency_layout.addWidget(label, row, 0)

            # forward = self._make_spinbox(axis.frequency_range, 'Hz')
            # forward.setObjectName(f'{name}_forward_scienDSpinBox')
            # forward.setValue(max(axis.min_frequency, axis.max_frequency / 100))
            # backward = self._make_spinbox(axis.frequency_range, 'Hz')
            # backward.setObjectName(f'{name}_backward_scienDSpinBox')
            # backward.setValue(max(axis.min_frequency, axis.max_frequency / 100))
            # if not self._backscan_configurable:
            #     backward.setRange(0, 1)
            #     backward.setValue(0)
            #     backward.setSuffix('/na')
            #     backward.setDisabled(True)
            # frequency_layout.addWidget(forward, row, 1)
            # frequency_layout.addWidget(backward, row, 2)

            shift_label = QtWidgets.QLabel(name.title())
            shift_label.setAlignment(QtCore.Qt.AlignCenter)
            shift_layout.addWidget(shift_label, row, 0)
            shift = self._make_spinbox(axis.value_range, 'm')
            shift.setObjectName(f'{name}_shift_scienDSpinBox')
            shift.setValue(0)
            shift_layout.addWidget(shift, row, 1)

            range_label = QtWidgets.QLabel(name.title())
            range_label.setAlignment(QtCore.Qt.AlignCenter)
            range_layout.addWidget(range_label, row, 0)
            start = self._make_spinbox(axis.value_range, 'm')
            stop = self._make_spinbox(axis.value_range, 'm')
            start.setObjectName(f'{name}_range_start_scienDSpinBox')
            stop.setObjectName(f'{name}_range_stop_scienDSpinBox')
            start.setValue(axis.value_range[0])
            stop.setValue(axis.value_range[1])
            range_layout.addWidget(start, row, 1)
            range_layout.addWidget(stop, row, 2)

            self.axes_widgets[name] = {
                'shift_spinbox': shift,
                'start_scan_spinbox': start,
                'stop_scan_spinbox': stop,
            }
        #     forward.editingFinished.connect(
        #         self.__get_axis_forward_callback(name, forward)
        #     )
        #     backward.editingFinished.connect(
        #         self.__get_axis_backward_callback(name, backward)
        #     )
        #     shift.editingFinished.connect(self.__get_axis_shift_callback(name, shift))

        # frequency_groupbox = QtWidgets.QGroupBox('Pixel Frequency')
        # frequency_groupbox.setFont(font)
        # frequency_groupbox.setLayout(frequency_layout)

        self.shift_groupbox = QtWidgets.QGroupBox('Shift')
        self.shift_groupbox.setFont(font)
        self.shift_groupbox.setLayout(shift_layout)
        self.scan_range_groupbox = QtWidgets.QGroupBox('Scan Range')
        self.scan_range_groupbox.setFont(font)
        self.scan_range_groupbox.setLayout(range_layout)
        self.controls_groupbox = self._create_controls_groupbox(font)

        settings_layout = QtWidgets.QHBoxLayout()
        settings_layout.addWidget(self.shift_groupbox)
        settings_layout.addWidget(self.scan_range_groupbox)
        settings_layout.addWidget(self.controls_groupbox)

        main_layout = QtWidgets.QVBoxLayout(self)
        #main_layout.addWidget(frequency_groupbox)
        main_layout.addLayout(settings_layout)

    @staticmethod
    def _make_spinbox(value_range, suffix):
        spinbox = ScienDSpinBox()
        spinbox.setRange(*value_range)
        spinbox.setSuffix(suffix)
        spinbox.setButtonSymbols(QtWidgets.QAbstractSpinBox.NoButtons)
        width = max(90, spinbox.sizeHint().width())
        spinbox.setMinimumSize(width, spinbox.sizeHint().height())
        # The global QSS can otherwise collapse a no-button editor to one pixel.
        spinbox.lineEdit().setMinimumWidth(width)
        spinbox.setSizePolicy(
            QtWidgets.QSizePolicy.Preferred,
            QtWidgets.QSizePolicy.Preferred,
        )
        return spinbox

    def _create_controls_groupbox(self, font):
        groupbox = QtWidgets.QGroupBox('Controls')
        groupbox.setFont(font)
        layout = QtWidgets.QVBoxLayout(groupbox)

        checkbox_layout = QtWidgets.QGridLayout()
        for index, (key, label) in enumerate((
            ('a1', 'A1'),
            ('a2', 'A2'),
            ('repump', 'Repump'),
            ('init_charge', 'Init. Charge'),
        )):
            checkbox = QtWidgets.QCheckBox(label)
            checkbox.setObjectName(f'ple_{key}_checkBox')
            checkbox_layout.addWidget(checkbox, index // 2, index % 2)
            self._controls[key] = checkbox
        layout.addLayout(checkbox_layout)

        self.microwave_table = QtWidgets.QTableWidget(0, 2)
        self.microwave_table.setHorizontalHeaderLabels(
            ('Frequency [Hz]', 'Amplitude [dBm]')
        )
        self.microwave_table.verticalHeader().setVisible(False)
        self.microwave_table.setSelectionBehavior(
            QtWidgets.QAbstractItemView.SelectRows
        )
        self.microwave_table.horizontalHeader().setSectionResizeMode(
            QtWidgets.QHeaderView.Stretch
        )
        layout.addWidget(self.microwave_table)

        buttons_layout = QtWidgets.QHBoxLayout()
        self.add_microwave_button = QtWidgets.QPushButton('Add')
        self.remove_microwave_button = QtWidgets.QPushButton('Remove')
        buttons_layout.addWidget(self.add_microwave_button)
        buttons_layout.addWidget(self.remove_microwave_button)
        layout.addLayout(buttons_layout)
        self.add_microwave_button.clicked.connect(
            lambda: self.add_microwave_row()
        )
        self.remove_microwave_button.clicked.connect(self.remove_microwave_rows)
        return groupbox

    @property
    def axes(self):
        return tuple(self.axes_widgets)

    @property
    def frequency(self):
        return {
            axis: (
                widgets['forward_freq_spinbox'].value(),
                widgets['backward_freq_spinbox'].value()
                if self._backscan_configurable else None,
            )
            for axis, widgets in self.axes_widgets.items()
        }

    @property
    def shift(self):
        return {
            axis: widgets['shift_spinbox'].value()
            for axis, widgets in self.axes_widgets.items()
        }

    @property
    def scan_range(self):
        return {
            axis: (
                widgets['start_scan_spinbox'].value(),
                widgets['stop_scan_spinbox'].value(),
            )
            for axis, widgets in self.axes_widgets.items()
        }

    @property
    def controls(self):
        controls = {key: checkbox.isChecked() for key, checkbox in self._controls.items()}
        controls['microwaves'] = [
            {
                'frequency': self.microwave_table.cellWidget(row, 0).value(),
                'amplitude': self.microwave_table.cellWidget(row, 1).value(),
            }
            for row in range(self.microwave_table.rowCount())
        ]
        return controls

    def set_shift(self, value, axis=None):
        values = value if axis is None or isinstance(value, dict) else {axis: value}
        for name, shift in values.items():
            spinbox = self.axes_widgets[name]['shift_spinbox']
            spinbox.blockSignals(True)
            spinbox.setValue(shift)
            spinbox.blockSignals(False)

    def set_frequency(self, value, axis=None):
        values = value if axis is None or isinstance(value, dict) else {axis: value}
        for name, (forward, backward) in values.items():
            widgets = self.axes_widgets[name]
            widgets['forward_freq_spinbox'].blockSignals(True)
            widgets['forward_freq_spinbox'].setValue(forward)
            widgets['forward_freq_spinbox'].blockSignals(False)
            widgets['backward_freq_spinbox'].blockSignals(True)
            if self._backscan_configurable and backward is not None:
                widgets['backward_freq_spinbox'].setValue(backward)
            widgets['backward_freq_spinbox'].blockSignals(False)

    def set_scan_range(self, value):
        for name, (start, stop) in value.items():
            for key, setting in (
                ('start_scan_spinbox', start),
                ('stop_scan_spinbox', stop),
            ):
                spinbox = self.axes_widgets[name][key]
                spinbox.blockSignals(True)
                spinbox.setValue(setting)
                spinbox.blockSignals(False)

    def set_controls(self, controls):
        for name, checkbox in self._controls.items():
            checkbox.blockSignals(True)
            checkbox.setChecked(bool(controls.get(name, False)))
            checkbox.blockSignals(False)

        microwaves = controls.get('microwaves', [])
        self.microwave_table.setRowCount(0)
        for microwave in microwaves:
            self.add_microwave_row(
                microwave['frequency'],
                microwave['amplitude'],
            )

    def add_microwave_row(self, frequency=0.0, amplitude=0.0):
        row = self.microwave_table.rowCount()
        self.microwave_table.insertRow(row)
        frequency_spinbox = self._make_spinbox(
            self._microwave_frequency_range,
            'Hz',
        )
        frequency_spinbox.setDecimals(6)
        frequency_spinbox.setValue(frequency)
        amplitude_spinbox = self._make_spinbox(
            self._microwave_amplitude_range,
            'dBm',
        )
        amplitude_spinbox.setDecimals(6)
        amplitude_spinbox.setValue(amplitude)
        self.microwave_table.setCellWidget(row, 0, frequency_spinbox)
        self.microwave_table.setCellWidget(row, 1, amplitude_spinbox)

    def remove_microwave_rows(self):
        rows = sorted(
            {index.row() for index in self.microwave_table.selectedIndexes()},
            reverse=True,
        )
        if not rows and self.microwave_table.rowCount():
            rows = [self.microwave_table.rowCount() - 1]
        for row in rows:
            self.microwave_table.removeRow(row)

    def __get_axis_backward_callback(self, axis, spinbox):
        def callback():
            forward = self.axes_widgets[axis]['forward_freq_spinbox']
            self.sigFrequencyChanged.emit(axis, forward.value(), spinbox.value())
        return callback

    def __get_axis_forward_callback(self, axis, spinbox):
        def callback():
            backward = self.axes_widgets[axis]['backward_freq_spinbox']
            self.sigFrequencyChanged.emit(axis, spinbox.value(), backward.value())
        return callback

    def __get_axis_shift_callback(self, axis, spinbox):
        def callback():
            self.sigShiftChanged.emit(axis, spinbox.value())
        return callback
