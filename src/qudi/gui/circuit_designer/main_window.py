"""
main_window.py — Main application window.
Python 3.6+ compatible.

Working directory is remembered across sessions via QSettings.
All file operations (open, save, export, run) use the remembered folder.
The Run button saves both .py and .circuit, then calls
    self.queuelogic.add_task(path_to_py)
if a queuelogic object has been injected (QUDI mode).
In standalone mode the button still saves both files.
"""
import os
import sys
from typing import Optional, List

from PySide6.QtGui import QAction
from PySide6.QtGui import QShortcut
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QSplitter, QScrollArea,
    QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QFileDialog, QMessageBox, QFrame,
    QStatusBar, QPushButton, QTabWidget,
    QComboBox, QSizePolicy
)
from PySide6.QtCore import Qt, QSettings
from PySide6.QtGui import QKeySequence

from models import (CircuitDocument, Parameter,
                    DEFAULT_PREAMBLE, DEFAULT_FIXED_MIDDLE, DEFAULT_FIXED_END)
from library import GateLibrary
from circuit_grid import CircuitGridWidget
from palette import GatePalette
from param_panel import ParamPanel
from properties_panel import PropertiesPanel
from code_panel import CodePanel
from gate_editor import GateEditorDialog
from ana_seq_panel import AnaSeqPanel
from code_sections_dialog import CodeSectionsDialog

# ── Persistent settings keys ───────────────────────────────────────────────────
SETTINGS_ORG  = "QuantumLab"
SETTINGS_APP  = "QuantumComposer"
KEY_WORKDIRS  = "workdir/history"       # list of recently used folders
KEY_WORKDIR   = "workdir/current"       # current folder
MAX_DIR_HIST  = 8                       # max entries in dropdown

# ── Styles ────────────────────────────────────────────────────────────────────
STYLE = """
QMainWindow{background:#1E2128;}
QMenuBar{background:#141720;color:#9AA0AC;font-family:Consolas;font-size:11px;
    border-bottom:1px solid #2E3240;}
QMenuBar::item:selected{background:#2E3240;}
QMenu{background:#1A1D24;color:#CDD1DB;border:1px solid #3A3F4B;
    font-family:Consolas;font-size:11px;}
QMenu::item:selected{background:#2A3050;}
QMenu::separator{height:1px;background:#2E3240;margin:2px 0;}
QStatusBar{background:#141720;color:#555A66;font-family:Consolas;font-size:10px;
    border-top:1px solid #2E3240;}
QSplitter::handle{background:#2E3240;}
QSplitter::handle:horizontal{width:1px;}
QSplitter::handle:vertical{height:1px;}
QScrollArea{background:#1E2128;border:none;}
QTabWidget::pane{border:none;}
QTabBar::tab{background:#141720;color:#555A66;padding:5px 12px;
    border:none;font-family:Consolas;font-size:11px;}
QTabBar::tab:selected{color:#CDD1DB;border-bottom:2px solid #3A7FD4;}
QTabBar::tab:hover{color:#9AA0AC;}
"""

TITLEBAR_STYLE = """
QFrame{background:#0D1017;border-bottom:2px solid #3A7FD4;}
QLabel{color:#7090B0;font-family:Consolas;font-size:11px;}
QLineEdit{background:#151A24;border:2px solid #3A7FD4;border-radius:5px;
    color:#FFFFFF;font-family:Consolas;font-size:15px;font-weight:bold;
    padding:4px 10px;min-width:220px;}
QLineEdit:focus{background:#0A0E18;border-color:#70BBFF;}
QPushButton{background:#1A2030;color:#7090B0;border:1px solid #2A3A50;
    border-radius:3px;padding:3px 10px;font-size:11px;}
QPushButton:hover{background:#2A3A50;color:#CDD1DB;}
QComboBox{background:#12141A;color:#9AA0AC;border:1px solid #2A3A50;
    border-radius:3px;padding:2px 6px;font-family:Consolas;font-size:10px;
    min-width:240px;}
QComboBox:focus{border-color:#3A7FD4;color:#CDD1DB;}
QComboBox QAbstractItemView{background:#1A1D24;color:#CDD1DB;
    border:1px solid #3A3F4B;selection-background-color:#2A3050;}
QComboBox::drop-down{border:none;width:20px;}
"""


def _default_params():
    return [
        Parameter("sweeps",       "range(20)"),
        Parameter("n_ssr1",       "[3000]"),
        Parameter("n_ssr2",       "[3000]"),
        Parameter("state",        "['0']"),
        Parameter("init_power",   "[1.0]"),
        Parameter("rf_dur_rabi",  "[-1]"),
        Parameter("rf_amp_rabi",  "[*np.linspace(0, 0.9, 10)]"),
        Parameter("cnot_amp",     "[0.5]"),
        Parameter("pi_dur",       "[100]"),
        Parameter("transition",   "['low']"),
        Parameter("ddrf_dur",     "[1000]"),
        Parameter("ddrf_amp",     "[0.3]"),
    ]


class MainWindow(QMainWindow):
    """
    Main application window.

    Can be used standalone (python run_composer.py) or embedded in QUDI.
    When embedded, set  window.queuelogic = <queue_logic_instance>
    before calling show().  The ▶ Run button will then call
        queuelogic.add_task(path_to_py_file)
    """

    def __init__(self, parent=None):
        super(MainWindow, self).__init__(parent)
        self._doc = CircuitDocument()
        self._doc.parameters = _default_params()
        self._filepath = None       # type: Optional[str]
        self._modified = False
        self.queuelogic = None      # injected externally by QUDI circuit_gui

        # Persistent settings
        self._settings = QSettings(SETTINGS_ORG, SETTINGS_APP)
        self._workdir_history = self._load_workdir_history()
        if not self._workdir_history:
            self._workdir_history = [r"C:\src\qudi\notebooks\UserScripts\29Si5"]
        self._workdir = self._settings.value(
            KEY_WORKDIR, self._workdir_history[0])
        # Make sure current dir is first in history
        self._push_workdir(self._workdir)

        self.setWindowTitle("Quantum Composer")
        self.resize(1500, 960)
        self.setStyleSheet(STYLE)
        self._build_ui()
        self._build_menus()
        self._build_shortcuts()
        self._connect_signals()
        self._update_title()

    # ── Persistent working directory ──────────────────────────────────────────
    def _load_workdir_history(self):
        # type: () -> List[str]
        raw = self._settings.value(KEY_WORKDIRS, [])
        if isinstance(raw, str):
            raw = [raw]
        return [d for d in (raw or []) if d]

    def _push_workdir(self, path):
        # type: (str) -> None
        """Add path to top of history, deduplicate, persist."""
        path = path.strip()
        if not path:
            return
        if path in self._workdir_history:
            self._workdir_history.remove(path)
        self._workdir_history.insert(0, path)
        self._workdir_history = self._workdir_history[:MAX_DIR_HIST]
        self._workdir = path
        self._settings.setValue(KEY_WORKDIR, path)
        self._settings.setValue(KEY_WORKDIRS, self._workdir_history)
        # Refresh combo if already built
        if hasattr(self, "_dir_combo"):
            self._refresh_dir_combo()

    def _refresh_dir_combo(self):
        self._dir_combo.blockSignals(True)
        self._dir_combo.clear()
        for d in self._workdir_history:
            self._dir_combo.addItem(d)
        self._dir_combo.setCurrentIndex(0)
        self._dir_combo.blockSignals(False)

    def _on_dir_combo_changed(self, text):
        # type: (str) -> None
        text = text.strip()
        if text and text != self._workdir:
            self._push_workdir(text)
            self._status_lbl.setText("Working directory: {}".format(text))

    def _browse_workdir(self):
        d = QFileDialog.getExistingDirectory(
            self, "Select working directory", self._workdir)
        if d:
            self._push_workdir(d)
            self._status_lbl.setText("Working directory: {}".format(d))

    # ── Path helpers ──────────────────────────────────────────────────────────
    def _circuit_stem(self):
        # type: () -> str
        """Safe filename stem from current circuit title."""
        stem = self._doc.title.strip() or "Untitled"
        # Replace characters invalid in filenames
        for ch in r'\/:*?"<>|':
            stem = stem.replace(ch, "_")
        return stem

    def _auto_circuit_path(self):
        # type: () -> str
        """Full path for .circuit file: workdir/title.circuit"""
        return os.path.join(self._workdir, self._circuit_stem() + ".circuit")

    def _auto_py_path(self):
        # type: () -> str
        """Full path for .py file: workdir/title.py"""
        return os.path.join(self._workdir, self._circuit_stem() + ".py")

    # ── UI ────────────────────────────────────────────────────────────────────
    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Title bar ─────────────────────────────────────────────────────────
        tb = QFrame()
        tb.setStyleSheet(TITLEBAR_STYLE)
        tl = QHBoxLayout(tb)
        tl.setContentsMargins(14, 6, 14, 6)
        tl.setSpacing(8)

        tl.addWidget(QLabel("Circuit:"))
        self.title_edit = QLineEdit(self._doc.title)
        self.title_edit.setToolTip("Circuit name (used as filename)")
        self.title_edit.textChanged.connect(self._on_title_changed)
        tl.addWidget(self.title_edit)

        tl.addWidget(QLabel("  Folder:"))

        # Working directory combo
        self._dir_combo = QComboBox()
        self._dir_combo.setEditable(True)
        self._dir_combo.setInsertPolicy(QComboBox.NoInsert)
        self._dir_combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._dir_combo.setToolTip(
            "Working directory — all files saved here.\n"
            "Edit directly or browse. Persists across sessions.")
        self._refresh_dir_combo()
        self._dir_combo.currentTextChanged.connect(self._on_dir_combo_changed)
        tl.addWidget(self._dir_combo, 2)

        browse_btn = QPushButton("📁")
        browse_btn.setFixedWidth(28)
        browse_btn.setToolTip("Browse for working directory")
        browse_btn.clicked.connect(self._browse_workdir)
        tl.addWidget(browse_btn)

        tl.addWidget(QLabel("  "))  # small spacer

        # Action buttons
        for label, tip, slot in [
            ("📂 Open",     "Ctrl+L — Open circuit from working folder",
             self._open_file),
            ("💾 Save",     "Ctrl+S — Save  workdir/title.circuit  +  .py",
             self._save_file),
            ("📋 Sections", "Edit code sections (preamble, fixed middle, end)",
             self._edit_code_sections),
            ("⬇ Export",   "Ctrl+E — Export .py only",
             lambda: self.code_panel._export()),
        ]:
            btn = QPushButton(label)
            btn.setToolTip(tip)
            btn.clicked.connect(slot)
            tl.addWidget(btn)

        run_btn = QPushButton("▶ Run")
        run_btn.setToolTip(
            "Save both files then queue the experiment via queuelogic.add_task()")
        run_btn.setStyleSheet(
            "QPushButton{background:#1A3020;color:#50C050;"
            "border:1px solid #306030;border-radius:3px;padding:3px 10px;}"
            "QPushButton:hover{background:#204030;color:#70E070;}")
        run_btn.clicked.connect(self._run_experiment)
        tl.addWidget(run_btn)

        self._file_lbl = QLabel("(unsaved)")
        self._file_lbl.setStyleSheet("color:#2A4060;font-size:10px;")
        tl.addWidget(self._file_lbl)
        root.addWidget(tb)

        # ── Main vertical split ────────────────────────────────────────────────
        vsplit = QSplitter(Qt.Vertical)
        vsplit.setHandleWidth(3)
        self._vsplit = vsplit

        top = QWidget()
        tl2 = QHBoxLayout(top)
        tl2.setContentsMargins(0, 0, 0, 0)
        hsplit = QSplitter(Qt.Horizontal)
        hsplit.setHandleWidth(1)
        self._hsplit = hsplit

        self.palette = GatePalette(self._doc)
        self.palette.setMinimumWidth(155)
        self.palette.setMaximumWidth(220)
        hsplit.addWidget(self.palette)

        mid = QSplitter(Qt.Vertical)
        mid.setHandleWidth(1)
        self._midsplit = mid

        self.grid = CircuitGridWidget(self._doc)
        gs = QScrollArea()
        gs.setWidget(self.grid)
        gs.setWidgetResizable(False)
        gs.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        gs.setStyleSheet("QScrollArea{background:#1E2128;border:none;}")
        mid.addWidget(gs)

        self.props = PropertiesPanel(self._doc)
        self.props.setMinimumHeight(150)
        mid.addWidget(self.props)
        mid.setSizes([600, 200])
        hsplit.addWidget(mid)

        right_tabs = QTabWidget()
        right_tabs.setMinimumWidth(240)
        right_tabs.setMaximumWidth(400)

        self.params_panel = ParamPanel(self._doc)
        right_tabs.addTab(self.params_panel, "Parameters")

        self.ana_panel = AnaSeqPanel(self._doc)
        right_tabs.addTab(self.ana_panel, "ana_seq")

        hsplit.addWidget(right_tabs)
        hsplit.setSizes(self._doc.ui_state.get("splitter_sizes", [185, 960, 320]))
        tl2.addWidget(hsplit)
        vsplit.addWidget(top)

        self.code_panel = CodePanel(self._doc)
        self.code_panel.setMinimumHeight(160)
        vsplit.addWidget(self.code_panel)
        vsplit.setSizes([680, 240])

        root.addWidget(vsplit)

        self.status = QStatusBar()
        self.setStatusBar(self.status)
        self._status_lbl = QLabel(
            "Ready  ·  Drag gate onto grid  ·  Middle-click or Del to remove"
            "  ·  Ctrl+C/X/V copy/cut/paste  ·  Scroll on dot to cycle spin state")
        self.status.addWidget(self._status_lbl)

    # ── Menus ─────────────────────────────────────────────────────────────────
    def _build_menus(self):
        mb = self.menuBar()

        fm = mb.addMenu("File")
        self._act(fm, "New",          "Ctrl+N",       self._new_file)
        self._act(fm, "Open…",        "Ctrl+L",       self._open_file)
        fm.addSeparator()
        self._act(fm, "Save",         "Ctrl+S",       self._save_file)
        self._act(fm, "Save As…",     "Ctrl+Shift+S", self._save_as)
        fm.addSeparator()
        self._act(fm, "Export .py…",  "Ctrl+E",       self.code_panel._export)
        fm.addSeparator()
        self._act(fm, "Set working directory…", None, self._browse_workdir)

        cm = mb.addMenu("Circuit")
        self._act(cm, "Edit code sections…", None, self._edit_code_sections)
        self._act(cm, "Clear all gates",     None, self._clear_circuit)

        gm = mb.addMenu("Gates")
        self._act(gm, "New gate…",           None, self._new_gate)
        self._act(gm, "Reload gate library", None, self._reload_library)
        self._act(gm, "Open library file…",  None, self._open_library_file)

    def _act(self, menu, label, shortcut, slot):
        a = QAction(label, self)
        if shortcut:
            a.setShortcut(shortcut)
        a.triggered.connect(slot)
        menu.addAction(a)

    def _build_shortcuts(self):
        QShortcut(QKeySequence("Escape"), self).activated.connect(
            lambda: self.grid._cancel_placing())

    # ── Signal wiring ─────────────────────────────────────────────────────────
    def _connect_signals(self):
        self.palette.new_gate.connect(self._new_gate)
        self.palette.edit_gate.connect(self._edit_gate)
        self.grid.circuit_changed.connect(self._on_changed)
        self.grid.placement_selected.connect(self._on_selected)
        self.grid.placement_deselected.connect(self._on_deselected)
        self.grid.status_message.connect(self._status_lbl.setText)
        self.props.placement_changed.connect(self._on_changed)
        self.params_panel.params_changed.connect(self._on_changed)
        self.ana_panel.changed.connect(self._on_changed)

    # ── Event handlers ─────────────────────────────────────────────────────────
    def _on_title_changed(self, text):
        self._doc.title = text
        self._modified = True
        self._update_title()

    def _on_changed(self):
        self._modified = True
        self._update_title()
        self.code_panel.schedule_refresh()
        self.ana_panel.notify_circuit_changed()

    def _on_selected(self, pid):
        self.props.show_placement(pid)
        pl = next((p for p in self._doc.placements if p.id == pid), None)
        if pl:
            lib = GateLibrary.instance()
            gd  = lib.resolve(pl.gate_def_id, self._doc.local_gate_defs)
            if gd:
                self._status_lbl.setText(
                    "{}  col={}  rows={}  ·  Del/mid-click=remove"
                    "  ·  Drag=move  ·  Ctrl+C/X/V=copy/cut/paste".format(
                        gd.name, pl.col, pl.qubit_rows()))

    def _on_deselected(self):
        self.props.clear()
        self._status_lbl.setText(
            "Ready  ·  Drag gate onto grid  ·  Middle-click or Del to remove"
            "  ·  Ctrl+C/X/V copy/cut/paste  ·  Scroll on dot to cycle spin state")

    # ── Title / window ─────────────────────────────────────────────────────────
    def _update_title(self):
        base = os.path.basename(self._filepath) if self._filepath else self._circuit_stem()
        mod  = "  \u2022" if self._modified else ""
        self.setWindowTitle("Quantum Composer \u2014 {}{}".format(base, mod))
        self._file_lbl.setText(
            self._filepath or "(unsaved \u2014 will save to {})".format(
                self._auto_circuit_path()))

    # ── File operations ────────────────────────────────────────────────────────
    def _confirm_discard(self):
        if not self._modified:
            return True
        r = QMessageBox.question(
            self, "Unsaved changes", "Discard unsaved changes?",
            QMessageBox.Discard | QMessageBox.Cancel)
        return r == QMessageBox.Discard

    def _new_file(self):
        if not self._confirm_discard():
            return
        self._doc = CircuitDocument()
        self._doc.parameters = _default_params()
        self._filepath = None
        self._modified = False
        self.title_edit.blockSignals(True)
        self.title_edit.setText(self._doc.title)
        self.title_edit.blockSignals(False)
        self._reload_all()
        self._update_title()

    def _open_file(self):
        if not self._confirm_discard():
            return
        # Default to working directory
        start_dir = self._workdir if os.path.isdir(self._workdir) else ""
        path, _ = QFileDialog.getOpenFileName(
            self, "Open circuit", start_dir,
            "Circuit files (*.circuit);;All files (*)")
        if not path:
            return
        try:
            self._doc = CircuitDocument.load(path)
            self._filepath = path
            self._modified = False
            # Update working dir to match opened file's folder
            folder = os.path.dirname(os.path.abspath(path))
            self._push_workdir(folder)
            self.title_edit.blockSignals(True)
            self.title_edit.setText(self._doc.title)
            self.title_edit.blockSignals(False)
            self._reload_all()
            self._update_title()
        except Exception as e:
            QMessageBox.critical(self, "Open failed", str(e))

    def _save_file(self):
        """Save to workdir/title.circuit (auto-named). No dialog."""
        # Ensure folder exists
        try:
            os.makedirs(self._workdir, exist_ok=True)
        except Exception as e:
            QMessageBox.critical(self, "Cannot create folder",
                                 "{}:\n{}".format(self._workdir, e))
            return
        path = self._auto_circuit_path()
        self._filepath = path
        self._do_save(path)

    def _save_as(self):
        """Save with explicit path dialog."""
        start_dir = self._workdir if os.path.isdir(self._workdir) else ""
        path, _ = QFileDialog.getSaveFileName(
            self, "Save circuit as", start_dir,
            "Circuit files (*.circuit);;All files (*)")
        if not path:
            return
        if not path.endswith(".circuit"):
            path += ".circuit"
        self._filepath = path
        self._push_workdir(os.path.dirname(os.path.abspath(path)))
        self._do_save(path)

    def _do_save(self, circuit_path):
        self._doc.ui_state["splitter_sizes"] = self._hsplit.sizes()
        try:
            self._doc.save(circuit_path)
            self._modified = False
            self._update_title()
            self._status_lbl.setText("Saved \u2192 {}".format(circuit_path))
        except Exception as e:
            QMessageBox.critical(self, "Save failed", str(e))

    def _save_both(self):
        """
        Save workdir/title.circuit and workdir/title.py.
        Returns (circuit_path, py_path) on success, or (None, None) on error.
        """
        try:
            os.makedirs(self._workdir, exist_ok=True)
        except Exception as e:
            QMessageBox.critical(self, "Cannot create folder",
                                 "{}:\n{}".format(self._workdir, e))
            return None, None

        circuit_path = self._auto_circuit_path()
        py_path      = self._auto_py_path()

        # Save .circuit
        self._filepath = circuit_path
        self._doc.ui_state["splitter_sizes"] = self._hsplit.sizes()
        try:
            self._doc.save(circuit_path)
        except Exception as e:
            QMessageBox.critical(self, "Save failed (.circuit)", str(e))
            return None, None

        # Save .py
        from codegen import generate_full_code
        try:
            code = generate_full_code(self._doc)
            with open(py_path, "w", encoding="utf-8") as f:
                f.write(code)
        except Exception as e:
            QMessageBox.critical(self, "Save failed (.py)", str(e))
            return None, None

        self._modified = False
        self._update_title()
        self._status_lbl.setText(
            "Saved \u2192 {}  +  {}".format(
                os.path.basename(circuit_path), os.path.basename(py_path)))
        return circuit_path, py_path

    # ── Run experiment ─────────────────────────────────────────────────────────
    def _run_experiment(self):
        """
        1. Save workdir/title.circuit and workdir/title.py.
        2. If queuelogic is connected, call queuelogic.add_task(py_path).
        3. Otherwise show a confirmation that files were saved.
        """
        circuit_path, py_path = self._save_both()
        if py_path is None:
            return   # save failed, already showed error dialog

        if self.queuelogic is not None:
            try:
                self.queuelogic.add_task(py_path)
                self._status_lbl.setText(
                    "\u25b6 Queued: {}".format(os.path.basename(py_path)))
            except Exception as e:
                QMessageBox.critical(
                    self, "Queue error",
                    "add_task() failed:\n{}".format(e))
        else:
            # Standalone mode — just confirm files were written
            QMessageBox.information(
                self, "Files saved",
                "\u25b6  Both files saved to:\n\n"
                "  {}\n"
                "  {}\n\n"
                "No queue logic is connected.\n"
                "In QUDI mode, set  window.queuelogic = <logic_instance>  "
                "before calling show().".format(circuit_path, py_path))

    # ── Circuit ops ────────────────────────────────────────────────────────────
    def _reload_all(self):
        self.grid.set_document(self._doc)
        self.palette.set_document(self._doc)
        self.params_panel.set_document(self._doc)
        self.props.set_document(self._doc)
        self.code_panel.set_document(self._doc)
        self.ana_panel.set_document(self._doc)

    def _clear_circuit(self):
        r = QMessageBox.question(self, "Clear", "Remove all gates?",
                                 QMessageBox.Yes | QMessageBox.Cancel)
        if r == QMessageBox.Yes:
            self._doc.placements.clear()
            self.grid._update_size()
            self.grid.update()
            self._on_changed()

    def _edit_code_sections(self):
        dlg = CodeSectionsDialog(self._doc, self)
        dlg.sections_changed.connect(self._on_changed)
        dlg.exec_()

    # ── Gate ops ───────────────────────────────────────────────────────────────
    def _new_gate(self):
        dlg = GateEditorDialog(None, self._doc, self)
        dlg.gate_saved.connect(self._on_gate_saved)
        dlg.exec_()

    def _edit_gate(self, gid):
        lib = GateLibrary.instance()
        gd  = lib.resolve(gid, self._doc.local_gate_defs)
        if gd is None:
            return
        dlg = GateEditorDialog(gd, self._doc, self)
        dlg.gate_saved.connect(self._on_gate_saved)
        dlg.exec_()

    def _on_gate_saved(self, gid):
        self.palette.refresh()
        self.grid.update()
        self._on_changed()
        self._status_lbl.setText("Gate saved to library.")

    def _reload_library(self):
        GateLibrary.reset()
        GateLibrary.instance()
        self.palette.refresh()
        self.grid.update()
        self._status_lbl.setText("Gate library reloaded.")

    def _open_library_file(self):
        from library import LIBRARY_PATH
        import subprocess
        try:
            if sys.platform == "win32":
                os.startfile(LIBRARY_PATH)
            else:
                subprocess.Popen(["xdg-open", LIBRARY_PATH])
        except Exception:
            QMessageBox.information(
                self, "Library file location", LIBRARY_PATH)

    def closeEvent(self, event):
        #if self._confirm_discard():
            event.accept()
        #else:
        #    event.ignore()
