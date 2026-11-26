#!/usr/bin/env python3
"""
Quantum Composer — entry point.

Works from VS Code, Jupyter, or plain terminal:
    python run_composer.py

From a Jupyter cell:
    %run run_composer.py
"""
from __future__ import print_function
import sys
import os

# Add THIS file's directory to sys.path so all sibling .py files are importable
HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont

from main_window import MainWindow

# ---- QUDI imports ----
from qudi.core.connector import Connector


from qudi.core.module import GuiBase
#from logic.qudip_enhanced import *   # legacy QUDI API requires star import

def main():
    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName("Quantum Composer")

    font = QFont("Segoe UI", 10)
    app.setFont(font)
    app.setAttribute(Qt.AA_UseHighDpiPixmaps, True)

    window = MainWindow()
    window.show()

    # In Jupyter don't sys.exit — just run the event loop
    if 'ipykernel' in sys.modules:
        app.exec_()
    else:
        sys.exit(app.exec_())


class CircuitGui(GuiBase):
    # Connect to the Queue.
    queue_logic = Connector(interface="QueueLogic")  # class name

    def on_activate(self):
        self._win = MainWindow()
        self._win.setWindowTitle("Qudi: Circuit designer")
        self._mw = self._win
        self._queue_logic = self.queue_logic()
        # Wire the queue logic into the window so ▶ Run can call add_task()
        self._win.queuelogic = self._queue_logic
        self._win.show()

    def on_deactivate(self):
        self._mw.close()
