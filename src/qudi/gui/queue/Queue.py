#!/usr/bin/env python3
"""
QueueLogic GUI (Hybrid Version) — cleaned and fixed
- QueueManager uses a QObject "signals" proxy so it does not need to inherit QObject
  (avoids metaclass/MRO conflicts)
- ScriptThread runs embedded classes safely and reports via signals
- MainWindow is a wrapper around a real QMainWindow (no direct inheritance)
- Safe table rebuild (reorder) and stable signal/slot wiring
"""
from __future__ import print_function

# The legacy star import is done first on purpose: it must not be able to overwrite the explicit Qt / qudi names
# imported below (PyQt6: a re-exported PyQt5 QtCore/QtWidgets would silently mix two Qt bindings).
#from logic.qudip_enhanced import *   # legacy QUDI API requires star import

# ---- Standard library imports ----
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from datetime import datetime          # keep class import
from typing import Optional

# ---- Third-party imports ----

#from qtpy import QtCore, QtWidgets, QtGui
from PySide6 import QtCore, QtWidgets, QtGui

from PySide6.QtWidgets import (
    QMessageBox,
)
# from qtpy.QtWidgets import (
#     QMessageBox,
# )

# try:
#     import psutil
# except Exception:
#     psutil = None

#import sip

# ---- QUDI imports ----
#import logic.misc
#import logic.misc as misc
#from logic.generic_logic import GenericLogic
from qudi.core.connector import Connector
#from core.util.mutex import Mutex

# import logic.ODMR_nops as odmr
# importlib.reload(odmr)

from qudi.core.module import GuiBase
from qudi.core.statusvariable import StatusVar


QUEUE_DIR = Path.cwd() / "queue"
QUEUE_DIR.mkdir(exist_ok=True)
#CURRENT_RUNNING_NAME = "queuelogic.cun"
import os
QUDI_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

class Status(Enum):
    QUEUED = "Queued"
    RUNNING = "Running"
    PAUSED = "Paused"
    COMPLETED = "Completed"
    ERROR = "Error"
    ABORTED = "Aborted"


@dataclass
class ScriptTask:
    id: str
    original_path: Path
    queued_path: Path
    status: Status = Status.QUEUED
    process: Optional[QtCore.QProcess] = None
    thread: Optional[QtCore.QThread] = None
    worker: Optional[object] = None
    pid: Optional[int] = None
    stdout: str = ""
    stderr: str = ""
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    accumulated_time: float = 0.0
    pause_start: Optional[datetime] = None
    is_embedded: bool = False


# ---------------------------
# MainWindow wrapper (no direct inheritance)
# ---------------------------
class QueueGui(GuiBase):
    """
    Wrapper around QMainWindow so the class itself does not directly inherit from QMainWindow.
    Exposes show(), resize(), setWindowTitle(), raise_(), and makes widget attributes
    available as attributes on this wrapper.
    """
    # Connect to the Queue.
    queue_logic = Connector(interface="QueueLogic")  # class name
    scripts_folder=StatusVar('scripts_folder', "C:/src/squdi/src/qudi/notebooks/UserScripts")#r"C:\src\qudi\notebooks\UserScripts"
    #scripts_folder=StatusVar('scripts_folder', QUDI_DIR+"/notebooks/UserScripts")#r"C:\src\qudi\notebooks\UserScripts"
    # def __init__(self):
    #     # real internal QMainWindow
    #     self._win = QtWidgets.QMainWindow()
    #     #self._init_ui()
    #     #self._queue_logic = QueueManager()

    #     # set a fixed window title / size like before
    #     self._win.setWindowTitle("QueueLogic")
    #     self._win.resize(1100, 650)

    def on_activate(self):
        self._win = QtWidgets.QMainWindow()
        self._win.setWindowTitle("QueueLogic")
        self._win.resize(1100, 650)
        self._mw = self._win
        self._queue_logic = self.queue_logic()
        self._init_ui()
        self._connect_signals()
        #self.apply_theme()
        self.show()

    def on_deactivate(self):
        self._mw.close()

    def manuel_pause(self,value):
        print("Manuel pause:",value)
        if hasattr(self._queue_logic,"cun"):
            self._queue_logic.cun.manual_pause=value

    # --- convenience API that mirrors the real QMainWindow ---
    def show(self):
        return self._win.show()

    def resize(self, w, h):
        return self._win.resize(w, h)

    def setWindowTitle(self, title):
        return self._win.setWindowTitle(title)

    def raise_(self):
        try:
            return self._win.raise_()
        except Exception:
            return None

    def _init_ui(self):
        # Build the UI elements and attach central widget to the internal QMainWindow
        central = QtWidgets.QWidget()
        self._win.setCentralWidget(central)
        v = QtWidgets.QVBoxLayout(central)

        # --- Row 1: folder selector ---
        row1 = QtWidgets.QHBoxLayout()
        self.folder_line = QtWidgets.QLineEdit()
        self.folder_btn = QtWidgets.QPushButton("Select Folder")
        self.refresh_btn = QtWidgets.QPushButton("Refresh .py list")
        row1.addWidget(self.folder_line)
        row1.addWidget(self.folder_btn)
        row1.addWidget(self.refresh_btn)
        v.addLayout(row1)

        # --- Row 2: script selection + add button ---
        row2 = QtWidgets.QHBoxLayout()
        self.file_combo = QtWidgets.QComboBox()
        self.file_combo.setMinimumHeight(35)
        self.file_combo.setMaxVisibleItems(50)  # show 50 items at most
        self.file_combo.setSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding,
                                    QtWidgets.QSizePolicy.Policy.Fixed)
        self.add_btn = QtWidgets.QPushButton("Add to Queue")
        row2.addWidget(self.file_combo, stretch=1)
        row2.addWidget(self.add_btn)
        v.addLayout(row2)


        self.queue_table = QtWidgets.QTableWidget(0, 7)
        self.queue_table.setHorizontalHeaderLabels(
            ["Name", "Status", "Actions", "Start Time", "End Time", "Exec Time (s)", "ID"]
        )
        self.queue_table.setColumnHidden(6, True)
        self.queue_table.verticalHeader().setVisible(False)
        self.queue_table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
        self.queue_table.setColumnWidth(2, 500)
        self.queue_table.verticalHeader().setDefaultSectionSize(45)
        # --- Splitter between table and log ---
        self.log_widget = QtWidgets.QTextEdit()
        self.log_widget.setReadOnly(True)

        splitter = QtWidgets.QSplitter(QtCore.Qt.Orientation.Vertical)
        splitter.addWidget(self.queue_table)
        splitter.addWidget(self.log_widget)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 1)

        v.addWidget(splitter)


    def apply_theme(self):
        self._win.setStyleSheet("QWidget { background-color: #2b2b2b; color: #e6e6e6; }")

    def _connect_signals(self):
        # UI event wiring
        self.folder_btn.clicked.connect(self.select_folder)
        self.refresh_btn.clicked.connect(self.refresh_py_list)
        self.add_btn.clicked.connect(self.add_selected_to_queue)

        # QueueManager signals (proxy)
        s = self._queue_logic.signals
        s.task_added.connect(self.on_task_added)
        s.task_updated.connect(self.on_task_updated)
        s.log_output.connect(self.append_log)

    # ---- UI callbacks ----
    def select_folder(self):
        d = QtWidgets.QFileDialog.getExistingDirectory(self._win, "Select Folder", r"C:/src/squdi/src/qudi/notebooks/UserScripts")#str(Path.cwd())
        if d:
            self.folder_line.setText(d)
            self.refresh_py_list()

    def refresh_py_list(self):
        folder = Path(self.folder_line.text())
        self.file_combo.clear()
        if not folder.exists() or not folder.is_dir():
            return
        for p in sorted(folder.glob("*.py")):
            self.file_combo.addItem(str(p.name), str(p))

    def add_selected_to_queue(self):
        idx = self.file_combo.currentIndex()
        if idx < 0:
            return
        path = self.file_combo.currentData()
        if not path:
            return
        self._queue_logic.add_task(Path(path))

    # ---- table management ----
    def on_task_added(self, task: ScriptTask):
        row = self.queue_table.rowCount()
        self.queue_table.insertRow(row)
        self.queue_table.setItem(row, 0, QtWidgets.QTableWidgetItem(task.queued_path))
        self.queue_table.setItem(row, 1, QtWidgets.QTableWidgetItem(task.status.value))
        for col in range(3, 6):
            self.queue_table.setItem(row, col, QtWidgets.QTableWidgetItem(""))
        id_item = QtWidgets.QTableWidgetItem(task.id)
        self.queue_table.setItem(row, 6, id_item)

        w = QtWidgets.QWidget()
        h = QtWidgets.QHBoxLayout(w)
        h.setContentsMargins(2, 2, 2, 2)
        btn_pause = QtWidgets.QPushButton("Pause")
        btn_run = QtWidgets.QPushButton("Run")
        btn_abort = QtWidgets.QPushButton("Abort")
        btn_delete= QtWidgets.QPushButton("Delete Measurement")
        btn_pause.clicked.connect(lambda _, tid=task.id: self._queue_logic.pause_task(tid))
        btn_run.clicked.connect(lambda _, t=task: self._queue_logic.start_task(t))
        btn_abort.clicked.connect(lambda _, tid=task.id: self._queue_logic.abort_task(tid))
        btn_delete.clicked.connect(lambda _, tid=task.id: self.Delete_measurement(tid))
        h.addWidget(btn_pause)
        h.addWidget(btn_run)
        h.addWidget(btn_delete)
        h.addWidget(btn_abort)
        self.queue_table.setCellWidget(row, 2, w)

    def Delete_measurement(self,tid):
        tsk=self._queue_logic._find_task_by_id(tid)
        reply = QMessageBox.question(
            None, 
            "Delete File",
            f"Are you sure you want to delete the measurement data for: \n{tsk.saved_dir}?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )

        if reply == QMessageBox.StandardButton.Yes:
            try:
                self._queue_logic.Delete_measurement(tid)
            except OSError:
                QMessageBox.warning(None, "Error", "Failed to delete the file.")

    def on_task_updated(self, task: ScriptTask):
        # Update row cells
        for r in range(self.queue_table.rowCount()):
            id_item = self.queue_table.item(r, 6)
            if id_item and id_item.text() == task.id:
                self.queue_table.item(r, 1).setText(task.status.value)
                start_str = task.start_time.strftime("%H:%M:%S") if task.start_time else ""
                end_str = task.end_time.strftime("%H:%M:%S") if task.end_time else ""
                exec_time = "{:.1f}".format(task.accumulated_time) if task.accumulated_time else ""
                self.queue_table.item(r, 3).setText(start_str)
                self.queue_table.item(r, 4).setText(end_str)
                self.queue_table.item(r, 5).setText(exec_time)
                break

        # schedule a safe reorder of the whole table in the next event loop pass
        #QtCore.QTimer.singleShot(0, self.reorder_queue_table)

    def reorder_queue_table(self):
        """Rebuild table from authoritative manager.tasks; keep active tasks on top."""
        try:
            order = {
                Status.RUNNING: 0,
                Status.PAUSED: 1,
                Status.QUEUED: 2,
                Status.ERROR: 3,
                Status.COMPLETED: 4,
                Status.ABORTED: 5,
            }

            self.queue_table.setSortingEnabled(False)
            self.queue_table.blockSignals(True)
            self.queue_table.setUpdatesEnabled(False)
            self.queue_table.viewport().setAttribute(QtCore.Qt.WidgetAttribute.WA_TransparentForMouseEvents)
            QtWidgets.QApplication.instance().processEvents()

            # detach & schedule deletion of any current action widgets
            old_widgets = []
            for r in range(self.queue_table.rowCount()):
                w = self.queue_table.cellWidget(r, 2)
                if w is not None:
                    # disconnect buttons inside to be safe
                    for btn in w.findChildren(QtWidgets.QPushButton):
                        try:
                            btn.clicked.disconnect()
                        except Exception:
                            pass
                    w.setParent(None)
                    old_widgets.append(w)
                    w.deleteLater()

            # Sort tasks from manager
            tasks_sorted = sorted(
                list(self._queue_logic.tasks),
                key=lambda t: (order.get(t.status, 99), getattr(t, "start_time") or datetime.min),
            )

            self.queue_table.setRowCount(0)
            for task in tasks_sorted:
                r = self.queue_table.rowCount()
                self.queue_table.insertRow(r)
                self.queue_table.setItem(r, 0, QtWidgets.QTableWidgetItem(task.queued_path.name if task.queued_path else ""))
                self.queue_table.setItem(r, 1, QtWidgets.QTableWidgetItem(task.status.value))

                # New action widgets (fresh)
                w = QtWidgets.QWidget()
                h = QtWidgets.QHBoxLayout(w)
                h.setContentsMargins(2, 2, 2, 2)
                btn_pause = QtWidgets.QPushButton("Pause")
                btn_run = QtWidgets.QPushButton("Run")
                btn_abort = QtWidgets.QPushButton("Abort")
                btn_pause.clicked.connect(lambda _, tid=task.id: self._queue_logic.pause_task(tid))
                btn_run.clicked.connect(lambda _, t=task: self._queue_logic.start_task(t))
                btn_abort.clicked.connect(lambda _, tid=task.id: self._queue_logic.abort_task(tid))
                h.addWidget(btn_pause)
                h.addWidget(btn_run)
                h.addWidget(btn_abort)
                self.queue_table.setCellWidget(r, 2, w)

                start_str = task.start_time.strftime("%H:%M:%S") if task.start_time else ""
                end_str = task.end_time.strftime("%H:%M:%S") if task.end_time else ""
                exec_time = "{:.1f}".format(task.accumulated_time) if task.accumulated_time else ""
                self.queue_table.setItem(r, 3, QtWidgets.QTableWidgetItem(start_str))
                self.queue_table.setItem(r, 4, QtWidgets.QTableWidgetItem(end_str))
                self.queue_table.setItem(r, 5, QtWidgets.QTableWidgetItem(exec_time))
                id_item = QtWidgets.QTableWidgetItem(task.id)
                self.queue_table.setItem(r, 6, id_item)

            self.queue_table.viewport().setAttribute(QtCore.Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)
        except Exception as e:
            try:
                self.append_log("[ERROR] reorder_queue_table failed: {}\n".format(e))
            except Exception:
                pass
        finally:
            self.queue_table.setUpdatesEnabled(True)
            self.queue_table.blockSignals(False)
            self.queue_table.setSortingEnabled(True)
            QtWidgets.QApplication.instance().processEvents()

    # ---- logging ----
    def append_log(self, text: str):
        self.log_widget.moveCursor(QtGui.QTextCursor.MoveOperation.End)
        self.log_widget.insertPlainText(text)
        self.log_widget.moveCursor(QtGui.QTextCursor.MoveOperation.End)