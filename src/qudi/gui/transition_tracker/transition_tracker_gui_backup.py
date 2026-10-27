# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file 'D:\Python\pi3diamond/qtgui/transition_tracker.ui'
#
# Created by: PyQt5 UI code generator 5.6
#
# WARNING! All changes made in this file will be lost!
import datetime
import numpy as np
import os
import pyqtgraph as pg
import pyqtgraph.exporters

from core.connector import Connector
from core.util import units
from gui.guibase import GUIBase
from gui.colordefs import QudiPalettePale as palette
from gui.fitsettings import FitSettingsDialog, FitSettingsComboBox
from qtpy import QtWidgets
from PyQt5.QtWidgets import QTableWidgetItem
from qtpy import QtCore
from qtpy import uic
from PyQt5 import QtCore, QtGui, QtWidgets
from functools import partial

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QTableWidget, QTableWidgetItem, QFileDialog, QApplication, QHeaderView, QSpinBox,QComboBox
)

import sys
import pandas as pd

import math

try:
    NA = pd.NA
except AttributeError:
    # pandas < 1.0
    NA = np.nan

from PyQt5 import QtWidgets, QtCore, QtGui
from PyQt5.QtGui import QPalette, QColor
from PyQt5.QtCore import Qt
from pyqtgraph import ScatterPlotItem, TextItem

import warnings

def nowstr():
    return datetime.datetime.now().strftime('%Y%m%d-h%Hm%Ms%S')

class CouplingTabWidget(QtWidgets.QTabWidget):
    def __init__(self, tt):
        super().__init__()
        self.couplings = tt.couplings

        # Tab for -3/2
        self.tab_m3_2 = CouplingTableWidget(
            tt,"m32"
        )
        self.addTab(self.tab_m3_2, "-3/2")

        # Tab for +3/2
        self.tab_p3_2 = CouplingTableWidget(
            tt,"p32"
        )
        self.addTab(self.tab_p3_2, "+3/2")

class CouplingTableWidget(QtWidgets.QWidget):
    """
    A live-editable square table widget showing couplings between spins.
    Supports missing entries, adding new spins, and auto-saving to HDF on edit.
    """
    def __init__(self, tt,subspace="m32"):
        super().__init__()
        self.subspace=subspace
        if subspace=="m32":
            self.df = tt.couplings.df_m3_2
        elif subspace=="p32":
            self.df = tt.couplings.df_p3_2

        self.spins=tt.couplings.spins

        # Build UI
        self.init_ui()
        self.populate_table()


    def init_ui(self):
        layout = QtWidgets.QVBoxLayout(self)
        # Control layout: only Add Spin
        ctrl_layout = QtWidgets.QHBoxLayout()
        self.btn_add = QtWidgets.QPushButton('Add Spin')
        self.btn_add.clicked.connect(self.add_spin)
        ctrl_layout.addWidget(self.btn_add)
        ctrl_layout.addStretch()
        layout.addLayout(ctrl_layout)

        # Table widget
        self.table = QtWidgets.QTableWidget()
        self.table.setEditTriggers(
            QtWidgets.QAbstractItemView.DoubleClicked |
            QtWidgets.QAbstractItemView.SelectedClicked
        )
        self.table.itemChanged.connect(self.on_item_changed)
        layout.addWidget(self.table)

        self.setLayout(layout)
        self.setWindowTitle('Spin Couplings')
        self.resize(600, 600)

    def populate_table(self):
        n = len(self.spins)
        self.table.blockSignals(True)
        self.table.clear()
        self.table.setRowCount(n)
        self.table.setColumnCount(n)
        self.table.setHorizontalHeaderLabels(self.spins)
        self.table.setVerticalHeaderLabels(self.spins)

        for row, i in enumerate(self.spins):
            for col, j in enumerate(self.spins):
                val = self.df.at[i, j]
                txt = '' if pd.isna(val) else str(val)
                item = QtWidgets.QTableWidgetItem(txt)
                item.setTextAlignment(Qt.AlignCenter)
                self.table.setItem(row, col, item)

        self.table.blockSignals(False)

    def on_item_changed(self, item: QtWidgets.QTableWidgetItem):
        i = self.spins[item.row()]
        j = self.spins[item.column()]
        txt = item.text().strip()
        # Update DataFrame
        if txt == '':
            self.df.at[i, j] = np.nan
        else:
            try:
                self.df.at[i, j] = float(txt)
            except ValueError:
                QtWidgets.QMessageBox.warning(self, 'Invalid', f"Invalid value: {txt}")
                item.setText('')
                self.df.at[i, j] = np.nan
                return
        # Auto-save after edit
        self.save_to_hdf()

    def add_spin(self):
        text, ok = QtWidgets.QInputDialog.getText(self, 'New Spin', 'Enter new spin name:')
        if not ok or not text.strip():
            return
        new_spin = text.strip()
        if new_spin in self.spins:
            QtWidgets.QMessageBox.warning(self, 'Exists', f"Spin '{new_spin}' already exists.")
            return
        # Extend DataFrame with new row/column of nan
        self.spins.append(new_spin)
        self.df[new_spin] = np.nan
        self.df.loc[new_spin] = np.nan
        # Refresh UI and save
        self.populate_table()
        self.save_to_hdf()

    def save_to_hdf(self):
        print("Save hdf in gui")
        # Convert to long format, suppress pandas FutureWarning
        with warnings.catch_warnings():
            warnings.simplefilter('ignore', FutureWarning)
            stacked = self.df.stack(dropna=False)
        df_long = stacked.reset_index()
        df_long.columns = ['spin_i', 'spin_j', 'coupling']
        df_long['coupling'] = df_long['coupling'].astype('float64')
        # Save
        df_long.to_hdf(r"C:\src\qudi\log\transition_tracker_log\couplings_df"+f"_{self.subspace}"+"_live.hdf", key='data', mode='w', format='table')

    def save_backup_hdf(self):
        # Convert to long format, suppress pandas FutureWarning
        with warnings.catch_warnings():
            warnings.simplefilter('ignore', FutureWarning)
            stacked = self.df.stack(dropna=False)
        df_long = stacked.reset_index()
        df_long.columns = ['spin_i', 'spin_j', 'coupling']
        df_long['coupling'] = df_long['coupling'].astype('float64')
        # Save
        df_long.to_hdf(r"C:\src\qudi\log\transition_tracker_log\couplings_df"+f"_{self.subspace}"+"_backup.hdf", key='data', mode='w', format='table')
        df_long.to_hdf(r"C:\src\qudi\log\transition_tracker_log\couplings_log\couplings_df"+f"_{self.subspace}"+f"_log{nowstr()}.hdf", key='data', mode='w', format='table')
        
class DataFrameTableWidget(QtWidgets.QWidget):
    """
    PyQt5 widget that shows and edits Register.df as a modified QTableWidget.
    It keeps GUI <-> Register separation: the widget receives a Register instance
    through 'tt.register' in your original code pattern. For direct use, pass
    an object with attribute .register pointing to a Register() instance.
    """

    def __init__(self, tt):
        """
        tt is expected to have attribute 'register' pointing to a Register instance.
        """
        super().__init__()
        # External model
        self.tt = tt
        self.register = getattr(tt, 'register')
        self.pg_labels={}
        if self.register is None:
            raise ValueError("tt.register must be a Register instance")

        # Work on the same DataFrame object (so external callers see changes).
        # If you prefer widget-local copy, call .copy() here.
        self.df = self.register.df

        # Ensure key columns exist and are strings (preserve NaN)
        for c in ['spin_name', 'subspace', 'dd_method']:
            if c not in self.df.columns:
                self.df[c] = None
            self.df[c] = self.df[c].astype(object).where(self.df[c].isnull(), self.df[c].astype(str))

        # Extra columns (keep order)
        self.extra_columns = [c for c in self.df.columns if c not in ['spin_name', 'subspace', 'dd_method']]

        # UI-maintained choices
        self.unique_spins = sorted(self.df['spin_name'].dropna().unique().tolist())
        self.subspace_choices = ['_none_'] + sorted(self.df['subspace'].dropna().unique().tolist())
        self.dd_method_choices = ['_none_'] + sorted(self.df['dd_method'].dropna().unique().tolist())
        # default filters for each spin: tuple (subspace_choice, dd_method_choice)
        self.spin_filters = {s: (self.subspace_choices[0], self.dd_method_choices[0]) for s in self.unique_spins}

        # Row metadata (parallel to table rows)
        self.row_infos = []  # list of dicts with 'type' key: 'control'|'data'|'new'

        # Guard while programmatically updating items
        self.updating = False

        # Build UI
        self._init_ui()
        # Fill table
        self.rebuild_table()

    # ----------------------------
    # UI building
    # ----------------------------
    def _init_ui(self):
        vlay = QtWidgets.QVBoxLayout(self)

        # Global controls row
        ctrl_layout = QtWidgets.QHBoxLayout()
        btn_add_spin = QtWidgets.QPushButton('Add spin')
        btn_add_spin.clicked.connect(self.add_spin)
        ctrl_layout.addWidget(btn_add_spin)

        ctrl_layout.addWidget(QtWidgets.QLabel('Global Subspace:'))
        self.global_sub = QtWidgets.QComboBox()
        self.global_sub.addItems(self.subspace_choices)
        ctrl_layout.addWidget(self.global_sub)

        ctrl_layout.addWidget(QtWidgets.QLabel('Global dd_method:'))
        self.global_dd = QtWidgets.QComboBox()
        self.global_dd.addItems(self.dd_method_choices)
        ctrl_layout.addWidget(self.global_dd)

        btn_apply_global = QtWidgets.QPushButton('Apply Global')
        btn_apply_global.clicked.connect(self.apply_global_settings)
        ctrl_layout.addWidget(btn_apply_global)

        vlay.addLayout(ctrl_layout)

        # Table
        self.table = QtWidgets.QTableWidget()
        # Number of columns = two key columns + extra_columns + copy/add button column
        ncols = 2 + len(self.extra_columns) + 1
        self.table.setColumnCount(ncols)
        headers = ['Subspace', 'dd_method'] + self.extra_columns + ['Copy/Add']
        self.table.setHorizontalHeaderLabels(headers)
        self.table.itemChanged.connect(self.on_item_changed)
        self.table.setSortingEnabled(False)  # safer: avoid weird reordering while editing
        #vlay.addWidget(self.table)

        # --- Spectrum tabs using pyqtgraph ---
        self.spectrum_tabs = QtWidgets.QTabWidget()
        #vlay.addWidget(self.spectrum_tabs)

        self.subspaces_for_plot = ["3/2", "1/2", "-1/2", "-3/2"]
        self.pg_plots = {}

        pg.setConfigOptions(antialias=True)

        for sp in self.subspaces_for_plot:
            pw = pg.PlotWidget()
            pw.showGrid(x=True, y=True)
            pw.setLabel('bottom', 'detuning', 'MHz')
            pw.setLabel('left', 'amplitude', 'a.u.')

            self.pg_plots[sp] = pw
            self.spectrum_tabs.addTab(pw, sp)

        self.setWindowTitle('Register')
        self.spectrum_tabs.setMaximumHeight(250)
        #splitter = QtWidgets.QSplitter(QtCore.Qt.Vertical)
        #splitter.addWidget(self.table)
        #splitter.addWidget(self.spectrum_tabs)
        #splitter.setSizes([500, 100])       # initial ratio
        #splitter.setStretchFactor(0, 4)
        #splitter.setStretchFactor(1, 1)

        vlay.addWidget(self.table)
        vlay.addWidget(self.spectrum_tabs)
        

        self.setLayout(vlay)

        self.spectrum_tabs.setSizePolicy(
            QtWidgets.QSizePolicy.Expanding,
            QtWidgets.QSizePolicy.Fixed
        )

    def update_spectra(self):
        """
        Draw Gaussians (one per transition) grouped by subspace using pyqtgraph.
        center = detuning
        sigma from FWHM = 1/pi2_dur
        """
        for sp in self.subspaces_for_plot:
            pw = self.pg_plots[sp]
            pw.clear()

            df_sp = self.df[self.df["subspace"] == sp]
            if df_sp.empty:
                continue

            centers = df_sp["detuning"].dropna().astype(float).values
            if len(centers) == 0:
                continue

            xmin = min(centers)*1.1
            xmax = max(centers)*1.1

            x = np.linspace(xmin, xmax, 12000)

            label = pg.TextItem("", anchor=(0,1))
            pw.addItem(label)
            self.pg_labels[sp] = label

            for _, row in df_sp.iterrows():
                try:
                    det  = float(row.get("detuning", np.nan))
                    pi2  = float(row.get("pi2_dur", np.nan))
                    if np.isnan(det) or np.isnan(pi2) or pi2 == 0:
                        continue

                    # FWHM → sigma
                    fwhm = 1.0 / pi2
                    sigma = fwhm / (2*np.sqrt(2*np.log(2)))
                    y = np.exp(-0.5*((x-det)/sigma)**2)

                    # choose color by element
                    element = str(row.get("spin_name", ""))
                    if "C" in element.upper():
                        pen = pg.mkPen(pg.mkColor('#ff5555'))  # nice red
                    elif "SI" in element.upper():
                        pen = pg.mkPen(pg.mkColor('#5588ff'))  # nice blue
                    else:
                        pen = pg.mkPen('k', width=2)

                    pw.plot(x, y, pen=pen)

                    spin_name = str(row.get("spin_name", ""))
                    # find peak x,y (Gaussian peaks at detuning)
                    x_peak = det
                    y_peak = np.exp(-0.5*((0)/sigma)**2)  # = 1 actually, but keep general

                    anchor = ScatterPlotItem(
                        x=[x_peak], y=[y_peak],
                        pen=None, brush=None, size=10,
                        hoverSymbol='+',  # optional visible hover symbol
                    )

                    # attach name to object
                    anchor.spin_name = spin_name

                    # connect signals
                    def hover_event(points, plot_pw=pw, sp=sp, point_item=anchor):
                        if points:  # cursor on this point
                            self.pg_labels[sp].setText(point_item.spin_name)
                            self.pg_labels[sp].setPos(x_peak, y_peak)
                            self.pg_labels[sp].show()
                        else:
                            self.pg_labels[sp].hide()

                    anchor.hoverEvent = hover_event

                    pw.addItem(anchor)


                except Exception:
                    continue


    # ----------------------------
    # Table rebuild and helpers
    # ----------------------------
    def rebuild_table(self):
        """Recreate visible rows from self.df and spin_filters."""
        self.updating = True
        try:
            self.table.blockSignals(True)
            self.table.setRowCount(0)
            self.row_infos = []

            # Refresh unique spins and choices to reflect possible external changes
            self.unique_spins = sorted(self.df['spin_name'].dropna().unique().tolist())
            # ensure every spin has a filter entry
            for s in self.unique_spins:
                self.spin_filters.setdefault(s, (self.subspace_choices[0], self.dd_method_choices[0]))

            for spin in self.unique_spins:
                # Control row: per-spin filter comboboxes
                subf, ddf = self.spin_filters.get(spin, (self.subspace_choices[0], self.dd_method_choices[0]))
                r = self.table.rowCount()
                self.table.insertRow(r)
                self.table.setVerticalHeaderItem(r, QtWidgets.QTableWidgetItem(spin))

                cb_sub = QtWidgets.QComboBox()
                cb_sub.addItems(self.subspace_choices)
                cb_sub.setCurrentText(subf)
                cb_sub.currentIndexChanged.connect(partial(self._on_control_changed, spin, 'subspace', cb_sub))
                self.table.setCellWidget(r, 0, cb_sub)

                cb_dd = QtWidgets.QComboBox()
                cb_dd.addItems(self.dd_method_choices)
                cb_dd.setCurrentText(ddf)
                cb_dd.currentIndexChanged.connect(partial(self._on_control_changed, spin, 'dd_method', cb_dd))
                self.table.setCellWidget(r, 1, cb_dd)

                # fill non-editable placeholders for extra columns
                for ci in range(len(self.extra_columns)):
                    itm = QtWidgets.QTableWidgetItem('')
                    itm.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
                    self.table.setItem(r, 2 + ci, itm)

                btn_copy = QtWidgets.QPushButton('Copy')
                btn_copy.clicked.connect(partial(self.copy_row, r))
                self.table.setCellWidget(r, 2 + len(self.extra_columns), btn_copy)
                self.row_infos.append({'type': 'control', 'spin': spin})

                # Data rows for this spin filtered by subf/ddf
                df_spin = self.df[self.df['spin_name'] == spin]
                mask = pd.Series(True, index=df_spin.index)
                if subf != '_none_':
                    mask &= df_spin['subspace'] == subf
                if ddf != '_none_':
                    mask &= df_spin['dd_method'] == ddf
                df_match = df_spin[mask]

                for idx, rec in df_match.iterrows():
                    r2 = self.table.rowCount()
                    self.table.insertRow(r2)
                    self.table.setVerticalHeaderItem(r2, QtWidgets.QTableWidgetItem(''))

                    # subspace & dd_method readonly
                    for ci, key in enumerate(['subspace', 'dd_method']):
                        val = rec.get(key)
                        txt = '' if pd.isna(val) else str(val)
                        it = QtWidgets.QTableWidgetItem(txt)
                        it.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
                        self.table.setItem(r2, ci, it)

                    # extra columns editable
                    for ci, col in enumerate(self.extra_columns):
                        v = rec.get(col)
                        txt = '' if pd.isna(v) else str(v)
                        it = QtWidgets.QTableWidgetItem(txt)
                        it.setFlags(it.flags() | Qt.ItemIsEditable)
                        self.table.setItem(r2, 2 + ci, it)

                    b2 = QtWidgets.QPushButton('Copy')
                    b2.clicked.connect(partial(self.copy_row, r2))
                    self.table.setCellWidget(r2, 2 + len(self.extra_columns), b2)
                    self.row_infos.append({'type': 'data', 'df_idx': idx})

                # New-entry row for this spin
                rn = self.table.rowCount()
                self.table.insertRow(rn)
                self.table.setVerticalHeaderItem(rn, QtWidgets.QTableWidgetItem(''))

                in_sub = QtWidgets.QLineEdit()
                in_sub.setPlaceholderText('subspace')
                self.table.setCellWidget(rn, 0, in_sub)

                in_dd = QtWidgets.QLineEdit()
                in_dd.setPlaceholderText('dd_method')
                self.table.setCellWidget(rn, 1, in_dd)

                for ci in range(len(self.extra_columns)):
                    it = QtWidgets.QTableWidgetItem('')
                    it.setFlags(it.flags() | Qt.ItemIsEditable)
                    self.table.setItem(rn, 2 + ci, it)

                b3 = QtWidgets.QPushButton('Add')
                b3.clicked.connect(partial(self.add_new, rn, spin))
                self.table.setCellWidget(rn, 2 + len(self.extra_columns), b3)
                self.row_infos.append({'type': 'new', 'spin': spin})

        finally:
            self.table.blockSignals(False)
            self.updating = False
            self.update_spectra()

    def _on_control_changed(self, spin, which, combobox):
        """Update spin_filters and rebuild table."""
        cur_sub, cur_dd = self.spin_filters.get(spin, (self.subspace_choices[0], self.dd_method_choices[0]))
        if which == 'subspace':
            cur_sub = combobox.currentText()
        else:
            cur_dd = combobox.currentText()
        self.spin_filters[spin] = (cur_sub, cur_dd)
        self.rebuild_table()

    # ----------------------------
    # Event handlers
    # ----------------------------
    def on_item_changed(self, item):
        """
        Triggered when any editable item changes. We guard with self.updating.
        Only handle 'data' rows and columns corresponding to extra_columns.
        """
        if self.updating:
            return

        row = item.row()
        col = item.column()
        if row < 0 or row >= len(self.row_infos):
            return
        info = self.row_infos[row]
        if info.get('type') != 'data':
            return
        # Only extra columns are editable (columns 2 .. 2+len(extra_columns)-1)
        if not (2 <= col < 2 + len(self.extra_columns)):
            return

        field = self.extra_columns[col - 2]
        idx = info['df_idx']
        txt = item.text().strip()
        # Decide value to write: empty -> NA, else try float, else string
        if txt == '':
            val = NA
        else:
            # Try numeric first
            try:
                # Accept ints/floats but write floats so dtype consistent
                val = float(txt)
            except Exception:
                val = txt

        # Write back to underlying DataFrame safely (preserve index)
        try:
            self.df.at[idx, field] = val
            # Update register's df reference (if the widget uses direct reference it's already same object)
            self.register.df = self.df
            # Persist
            self.register.save_to_hdf()
        except Exception as exc:
            QtWidgets.QMessageBox.warning(self, "Write error", "Couldn't write value to DataFrame:\n{}".format(exc))

        self.update_spectra()

    # ----------------------------
    # Copy / Add helpers
    # ----------------------------
    def copy_row(self, row):
        """
        Build a simple textual representation of row contents and copy to clipboard.
        Works for both control/data/new rows (reads widgets/items depending on cell).
        """
        def get_text(col):
            w = self.table.cellWidget(row, col)
            if isinstance(w, QtWidgets.QLineEdit):
                return w.text().strip()
            if isinstance(w, QtWidgets.QComboBox):
                return w.currentText()
            it = self.table.item(row, col)
            return it.text().strip() if it else ''

        sub = get_text(0)
        dd = get_text(1)
        lines = ['subspace:{}'.format(sub), 'dd_method:{}'.format(dd)]
        for i, col in enumerate(self.extra_columns):
            txt = ''
            it = self.table.item(row, 2 + i)
            if it:
                txt = it.text().strip()
            lines.append('{}:{}'.format(col, txt))
        txt = '\n'.join(lines)
        cb = QtWidgets.QApplication.clipboard()
        cb.setText(txt)
        QtWidgets.QMessageBox.information(self, 'Copied', txt)

    def add_spin(self):
        """
        Prompt for new spin name and add default 4-subspace entries (same behaviour as original).
        This function modifies the Register.df and persists it.
        """
        text, ok = QtWidgets.QInputDialog.getText(self, 'New Spin', 'Enter new spin name:')
        if not ok:
            return
        new_spin = text.strip()
        if not new_spin:
            return
        if new_spin in self.unique_spins:
            QtWidgets.QMessageBox.warning(self, 'Exists', "Spin '{}' already exists.".format(new_spin))
            return

        # Create default rows for given spin (same pattern as original)
        data = {
            "subspace": ["3/2", "1/2", "-1/2", "-3/2"],
            "spin_name": [new_spin] * 4,
            "dd_method": ["knillpi"] * 4
        }
        add_df = pd.DataFrame(data)

        # Ensure new columns exist in self.df (preserve schema)
        for c in add_df.columns:
            if c not in self.df.columns:
                self.df[c] = NA

        # Append and reset indices (preserve columns order)
        self.df = pd.concat([self.df, add_df], ignore_index=True, sort=False)
        # update external register reference and persist
        self.register.df = self.df
        self.register.save_to_hdf()

        # refresh choices and UI
        self.unique_spins.append(new_spin)
        self.spin_filters[new_spin] = (self.subspace_choices[0], self.dd_method_choices[0])
        # update available choices from new data
        self._refresh_choices_from_df()
        self.rebuild_table()

    def add_new(self, row, spin):
        """
        Add a new data row for 'spin' using values entered in the New-entry row
        at 'row'. Validates required fields and appends to DataFrame.
        """
        # Read subspace and dd from the line edits
        w_sub = self.table.cellWidget(row, 0)
        w_dd = self.table.cellWidget(row, 1)
        sub = w_sub.text().strip() if isinstance(w_sub, QtWidgets.QLineEdit) else ''
        dd = w_dd.text().strip() if isinstance(w_dd, QtWidgets.QLineEdit) else ''
        if not sub or not dd:
            QtWidgets.QMessageBox.warning(self, 'Missing', 'Enter both Subspace & dd_method')
            return

        rec = {'spin_name': spin, 'subspace': sub, 'dd_method': dd}
        # Collect extras from editable items
        for i, col in enumerate(self.extra_columns):
            it = self.table.item(row, 2 + i)
            txt = it.text().strip() if it else ''
            if txt == '':
                rec[col] = NA
            else:
                # Try numeric if likely numeric, else keep string
                try:
                    rec[col] = float(txt)
                except Exception:
                    rec[col] = txt

        # Append to df
        self.df = pd.concat([self.df, pd.DataFrame([rec])], ignore_index=True, sort=False)
        # Keep Register synced and save
        self.register.df = self.df
        self.register.save_to_hdf()

        # Update global choice lists
        self._refresh_choices_from_df()

        # rebuild UI to show new row and updated choices
        self.rebuild_table()

    def _refresh_choices_from_df(self):
        """Update the subspace/dd_method dropdown choices from current dataframe."""
        subs = sorted(self.df['subspace'].dropna().unique().tolist())
        dds = sorted(self.df['dd_method'].dropna().unique().tolist())
        self.subspace_choices = ['_none_'] + subs
        self.dd_method_choices = ['_none_'] + dds

        # Update global combo widgets while preserving selection if possible
        cur_s = self.global_sub.currentText() if self.global_sub.currentText() else '_none_'
        cur_d = self.global_dd.currentText() if self.global_dd.currentText() else '_none_'
        self.global_sub.blockSignals(True)
        self.global_sub.clear()
        self.global_sub.addItems(self.subspace_choices)
        if cur_s in self.subspace_choices:
            self.global_sub.setCurrentText(cur_s)
        self.global_sub.blockSignals(False)

        self.global_dd.blockSignals(True)
        self.global_dd.clear()
        self.global_dd.addItems(self.dd_method_choices)
        if cur_d in self.dd_method_choices:
            self.global_dd.setCurrentText(cur_d)
        self.global_dd.blockSignals(False)

    # ----------------------------
    # Utilities
    # ----------------------------
    def get_spin(self, spin_name, subspace, dd_method):
        """
        Return a DataFrame for spin_name filtered by subspace and dd_method.
        Signature preserved.
        """
        df2 = self.df[self.df['spin_name'] == spin_name]
        if subspace != '_none_':
            df2 = df2[df2['subspace'] == subspace]
        if dd_method != '_none_':
            df2 = df2[df2['dd_method'] == dd_method]
        return df2.copy()

    def apply_global_settings(self):
        gsub = self.global_sub.currentText()
        gdd = self.global_dd.currentText()
        for s in self.unique_spins:
            self.spin_filters[s] = (gsub, gdd)
        self.rebuild_table()


# ------------------ Qt Widget ------------------ #
class ChainFinderWidget(QWidget):
    """
    Qt widget that can be placed inside a tab.
    Provides:
      - CSV load
      - Threshold input
      - Max path length input
      - Target spin input
      - Table of results: Chain | Couplings | Expected time
    """

    def __init__(self, tt, parent=None):
        super().__init__(parent)
        self.df = None
        self.adj = None
        self.get_coupling = None
        self.threshold = 0.5
        self.max_len = None
        self.subspace="-3/2"
        self.tt=tt

        self._make_ui()
        if tt:
            self.load_csv(self.subspace)

    def _make_ui(self):
        layout = QVBoxLayout(self)

        # top row: load csv, threshold, max path length
        top = QHBoxLayout()

        top.addWidget(QLabel("Threshold (> Hz):"))
        self.threshold_input = QLineEdit(str(self.threshold))
        top.addWidget(self.threshold_input)

        top.addWidget(QLabel("Max path length (nodes, empty=unlimited):"))
        self.maxlen_input = QLineEdit("")
        top.addWidget(self.maxlen_input)

        layout.addLayout(top)

        # --- Subspace selection ---
        subspace_layout = QHBoxLayout()
        subspace_layout.addWidget(QLabel("Subspace:"))

        self.subspace_combo = QComboBox()
        self.subspace_combo.addItems(["-3/2", "+3/2"])
        self.subspace_combo.setCurrentText("-3/2")

        # update flag + refresh displayed results
        self.subspace_combo.currentTextChanged.connect(self.load_csv)

        subspace_layout.addWidget(self.subspace_combo)
        layout.addLayout(subspace_layout)

        # avoid spins
        row4 = QHBoxLayout()
        row4.addWidget(QLabel("Avoid spins (comma-separated):"))
        self.avoidspins_input = QLineEdit("")   # default empty = avoid none
        row4.addWidget(self.avoidspins_input)
        layout.addLayout(row4)


        # allowed starting spins
        row3 = QHBoxLayout()
        row3.addWidget(QLabel("Allowed start spins (comma-separated):"))
        self.startspins_input = QLineEdit("Si1")   # default = Si1
        row3.addWidget(self.startspins_input)
        layout.addLayout(row3)

        # target + find
        row2 = QHBoxLayout()
        row2.addWidget(QLabel("Target spin:"))
        self.target_input = QLineEdit()
        row2.addWidget(self.target_input)
        self.find_btn = QPushButton("Find chains")
        self.find_btn.clicked.connect(self.on_find_clicked)
        row2.addWidget(self.find_btn)
        layout.addLayout(row2)




        # results table
        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["Chain", "Couplings", "Expected time (ms)"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        layout.addWidget(self.table)

        
    def load_csv(self,new_val):
        self.subspace = new_val
        try:
            df = [self.tt.couplings.df_m3_2,self.tt.couplings.df_p3_2][self.subspace=="+3/2"]
        except Exception as e:
            print("Failed to load df:", e)
            return
        # check square
        if list(df.index) != list(df.columns):
            print("CSV must be square with identical row/column labels (spins).")
            return
        self.df = df
        self.rebuild_graph()
        print(f"Loaded coupling matrix with {len(df)} spins")

    # # ----------------------------------------
    # #  Handle subspace change
    # # ----------------------------------------
    # def change_subspace(self, new_val):
    #     self.subspace = new_val
    #     self.update_results()   # re-run for consistent UI
    #     # (optional) print or log
    #     # print(f"Subspace changed to {self.subspace}")

    def get_allowed_start_spins(self):
        """
        Returns:
        - []  → meaning "allow all spins"
        - ["Si1", "Si2", ...] → user-specified starting spins
        """
        text = self.startspins_input.text().strip()

        # If empty → allow all spins
        if text == "":
            return []   # special flag: no restriction

        # Parse comma-separated list
        parts = [t.strip() for t in text.split(",") if t.strip() != ""]

        return parts

    def get_avoid_spins(self):
        """
        Returns:
        - [] → avoid nothing
        - ["Si5", "C2"] → avoid these spins
        """
        text = self.avoidspins_input.text().strip()
        if text == "":
            return []

        parts = [t.strip() for t in text.split(",") if t.strip() != ""]
        return parts



    def rebuild_graph(self):
        if self.df is None:
            return
        try:
            thr = float(self.threshold_input.text())
        except Exception:
            thr = 0.5
        self.threshold = thr
        # max length optional
        try:
            ml_text = self.maxlen_input.text().strip()
            if ml_text == "":
                self.max_len = None
            else:
                ml = int(ml_text)
                self.max_len = ml if ml > 0 else None
        except Exception:
            self.max_len = None
        self.adj, self.get_coupling = self.tt.couplings.build_graph_from_df(self.subspace, threshold=self.threshold)

    def on_find_clicked(self):
        if self.subspace is None:
            print("Please load a coupling CSV first.")
            return
        self.rebuild_graph()
        target = self.target_input.text().strip()
        if target == "":
            print("Please enter a target spin.")
            return
        # if target not in self.df.index:
        #     print(f"Target '{target}' not found among spins.")
        #     return
        #paths = self.tt.couplings.find_all_simple_paths_to_target(self.adj, target, max_len=self.max_len)
        allowed_starts = self.get_allowed_start_spins()
        avoid_spins = self.get_avoid_spins()

        paths = self.tt.couplings.find_all_simple_paths_to_target(
            self.adj,
            target,
            max_len=self.max_len,
            allowed_starts=allowed_starts,
            avoid_spins=avoid_spins,
        )

        results = []
        for p in paths:
            couplings, et_s = self.tt.couplings.chain_couplings_and_expected_time(p, self.get_coupling)
            if couplings is None:
                continue
            results.append((p, couplings, et_s))
        # sort by expected time (ascending = faster), then by length
        results.sort(key=lambda x: (x[2] if x[2] is not None else float('inf'), len(x[0])))
        self.populate_table(results)

    def populate_table(self, results):
        self.table.setRowCount(0)
        for p, couplings, et_s in results:
            r = self.table.rowCount()
            self.table.insertRow(r)
            chain_str = "-".join(p)
            couplings_str = "-".join(self.tt.couplings.fmt_hz(c) for c in couplings)
            if et_s is None:
                time_str = "N/A"
            elif math.isinf(et_s):
                time_str = "Inf"
            else:
                time_str = f"{et_s * 1000.0:.2f}"
            self.table.setItem(r, 0, QTableWidgetItem(chain_str))
            self.table.setItem(r, 1, QTableWidgetItem(couplings_str))
            self.table.setItem(r, 2, QTableWidgetItem(time_str))

    


class window(QtWidgets.QMainWindow):
    """ Create the Main Window based on the *.ui file. """

    def __init__(self):
        # Get the path to the *.ui file
        super().__init__()
        # Load it
        this_dir = os.path.dirname(__file__)
        ui_file = os.path.join(this_dir, 'transition_tracker.ui')

        # Load it

        uic.loadUi(ui_file, self)
        self.show()

class TransitionTrackerGui(GUIBase):
    transition_tracker_logic = Connector(interface="TransitionTracker") #class name

    def __init__(self, config, **kwargs):
        super().__init__(config=config, **kwargs)
        self._mw = window()
        #self.show()

    def on_activate(self):
        
        self._transition_tracker = self.transition_tracker_logic()

        self._mw.setObjectName("window")
        self._mw.resize(760, 793)
        self._mw.setWindowOpacity(1.0)
        self._mw.setAutoFillBackground(False)
        #self.button = QtWidgets.QPushButton('start')
        #self._mw.addItem(self.button)
        self.remove_next_script_button = QtWidgets.QPushButton(self._mw)
        self.remove_next_script_button.setGeometry(QtCore.QRect(680, 970, 761, 31))
        self.remove_next_script_button.setObjectName("remove_next_script_button")


        target_tab = self._mw.tabWidget.widget(1)
        self.register_table=DataFrameTableWidget(self._transition_tracker)

        # Set a layout for the tab if it doesn't already have one
        if not target_tab.layout():
            layout = QtWidgets.QVBoxLayout(target_tab)
            target_tab.setLayout(layout)
        else:
            layout = target_tab.layout()

        layout.addWidget(self.register_table)

        target_tab = self._mw.tabWidget.widget(2)
        self.couplings_table=CouplingTabWidget(self._transition_tracker)

        # Set a layout for the tab if it doesn't already have one
        if not target_tab.layout():
            layout = QtWidgets.QVBoxLayout(target_tab)
            target_tab.setLayout(layout)
        else:
            layout = target_tab.layout()

        layout.addWidget(self.couplings_table)

        target_tab = self._mw.tabWidget.widget(3)
        self.find_chain_tab=ChainFinderWidget(self._transition_tracker)

        # Set a layout for the tab if it doesn't already have one
        if not target_tab.layout():
            layout = QtWidgets.QVBoxLayout(target_tab)
            target_tab.setLayout(layout)
        else:
            layout = target_tab.layout()

        layout.addWidget(self.find_chain_tab)


        self._transition_tracker.update_tt_nuclear_gui.connect(self.update_gui_nuclear)
        self._transition_tracker.update_tt_electron_gui.connect(self.update_gui_electron)
        
        self.update_gui_electron()
        self.update_gui_nuclear()
        #self.retranslateUi(self._mw)
        #QtCore.QMetaObject.connectSlotsByName(self._mw)

    def show(self):
        """ Make window visible and put it above all other windows.
        """
        QtWidgets.QMainWindow.show(self._mw)
        self._mw.activateWindow()
        self._mw.raise_()


    def on_deactivate(self):
        self._transition_tracker.register.save_backup_hdf()
        self.couplings_table.tab_m3_2.save_backup_hdf()
        self.couplings_table.tab_p3_2.save_backup_hdf()
        self._mw.close()
        #TODO - clean the memory

    def update_gui_electron(self):
        self._mw.current_local_oscillator_freq_text_field.setText("{:.3f}".format(self._transition_tracker.current_local_oscillator_freq))
        self._mw.mw_mixing_frequency_L_text_field.setText("{:.3f}".format(self._transition_tracker.mw_mixing_frequency_L))
        self._mw.mw_mixing_frequency_C_text_field.setText("{:.3f}".format(self._transition_tracker.mw_mixing_frequency_C))
        self._mw.mw_mixing_frequency_R_text_field.setText("{:.3f}".format(self._transition_tracker.mw_mixing_frequency_R))
        self._mw.zero_field_splitting_text_field.setText("{:.2f}".format(self._transition_tracker.zero_field_splitting))
        self._mw.Bfield_text_field.setText("{:.9f}".format(self._transition_tracker.current_magnetic_field_vector[0]))
        #self._mw.mw_transition_frequency_p1_text_field.setText("{:.10f}".format(self._transition_tracker.mw_transition_frequency_C))
        self._mw.off_axis_B_field_text_field.setText("{:.9f}".format(self._transition_tracker.current_magnetic_field_vector[1]))
        self._mw.ple_A2_text_field.setText("{:.9f}".format(self._transition_tracker.ple_A2))
        self._mw.ple_A1_text_field.setText("{:.9f}".format(self._transition_tracker.ple_A1))
        # self.ple_repump_text_field.setText("{:.10f}".format(self.ple_A1))


    def update_gui_nuclear(self):
        column_names = ['name', 'current_frequency', 'ms_state', 'spin_type', 'start_level', 'end_level']
        print('update gui nulcear Transition Tracker')
        self._mw.script_queue_table.setColumnCount(len(column_names))
        self._mw.script_queue_table.clearSelection()
        self._mw.script_queue_table.clear()
        self._mw.script_queue_table.setHorizontalHeaderLabels(column_names)
        self._mw.script_queue_table.setEnabled(True)
        self._mw.script_queue_table.setRowCount(len(self._transition_tracker.transitions))
        for ridx, t in enumerate(self._transition_tracker.transitions):
            for cidx, attr_name in enumerate(column_names):
                new_item = QTableWidgetItem(str(getattr(t, attr_name)))
                self._mw.script_queue_table.setItem(ridx, cidx, new_item)

    def retranslateUi(self, window):
        _translate = QtCore.QCoreApplication.translate
        window.setWindowTitle(_translate("window", "Form"))
        self.remove_next_script_button.setText(_translate("window", "Remove next script"))
        self.set_stop_request_button.setText(_translate("window", "Set stop_request"))
        self.current_local_oscillator_freq_label.setText(_translate("window", "current_local_oscillator_freq"))
        self.current_local_oscillator_freq_label_2.setText(_translate("window", "current_local_oscillator_freq_p1"))
        self.current_local_oscillator_freq_label_3.setText(_translate("window", "mw_mixing_frequency"))
        self.current_local_oscillator_freq_label_4.setText(_translate("window", "mw_mixing_frequency_p1"))
        self.current_local_oscillator_freq_label_5.setText(_translate("window", "mw_transition_frequency"))
        self.current_local_oscillator_freq_label_6.setText(_translate("window", "mw_transition_frequency_p1"))
        self.current_local_oscillator_freq_label_7.setText(_translate("window", "zero_field_splitting"))
        self.ple_A2_label.setText(_translate("window", "PLE A2"))
        self.ple_A1_label.setText(_translate("window", "PLE A1"))


#from logic.qudip_enhanced.qutip_enhanced.qtgui.custom_widgets import QTableWidgetEnhancedDrop
