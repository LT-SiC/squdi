"""Readout progress towards the next NuclearOps data update."""
from PySide2 import QtCore, QtWidgets


class AcquisitionProgressBar(QtWidgets.QProgressBar):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumWidth(400)
        self.setRange(0, 1000)
        self.setValue(0)
        self.setFormat("Next data update: idle")
        self.setToolTip(
            "Progress within the current acquisition block, not the whole experiment. "
            "Uses the same filled-entry estimate as the terminal; trailing zero-count "
            "readouts can make it lag. Completion is confirmed by the counters.")
        self._phase = "idle"

    @QtCore.Slot(object)
    def update_progress(self, payload):
        phase = payload["phase"]
        if self._phase == "failed" and phase == "stopped":
            return
        self._phase = phase
        self.setRange(0, 1000)
        if phase == "acquiring":
            completed = max(0, int(payload.get("completed", 0)))
            total = max(0, int(payload.get("total", 0)))
            completed = min(completed, total)
            self.setValue(round(1000 * completed / total) if total else 0)
            prefix = "~" if payload.get("estimated") else ""
            self.setFormat(f"Next data: %p% | {prefix}{total-completed:,} / {total:,} readouts remaining")
        elif phase == "processing":
            self.setValue(1000)
            self.setFormat("Readouts complete; processing data...")
        elif phase == "data_arrived":
            self.setValue(1000)
            self.setFormat("New data arrived")
        elif phase == "preparing":
            self.setValue(0)
            self.setFormat("Preparing next data block (refocus / sequence setup)")
        elif phase == "failed":
            self.setFormat("Failed: " + str(payload.get("message", "measurement error")))
        elif phase == "paused":
            self.setValue(0)
            self.setFormat(str(payload.get("message", "Scheduled pause")))
        elif phase == "stopping":
            self.setFormat("Stopping measurement...")
        elif phase == "stopped":
            self.setFormat("Stopped before the next data update")
