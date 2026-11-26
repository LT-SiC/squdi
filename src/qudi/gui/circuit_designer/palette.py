"""
palette.py  —  Gate palette panel.
Initiates a real QDrag so the circuit grid receives dragEnterEvent/dropEvent.
"""
from typing import Optional

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QListWidget, QListWidgetItem, QAbstractItemView, QFrame
)
from PySide6.QtCore import Qt, QSize, QPoint, QMimeData, Signal
from PySide6.QtGui import QColor, QPixmap, QPainter, QDrag

from models import GateDefinition, CircuitDocument
from library import GateLibrary


def _gate_icon(color_hex: str, size: int = 22) -> QPixmap:
    pix = QPixmap(size, size)
    pix.fill(Qt.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.Antialiasing)
    c = QColor(color_hex)
    p.setBrush(c)
    p.setPen(c.darker(130))
    p.drawRoundedRect(2, 2, size - 4, size - 4, 5, 5)
    p.end()
    return pix


class GatePaletteItem(QWidget):
    def __init__(self, gd: GateDefinition, is_local=False, parent=None):
        super().__init__(parent)
        self.gate_def = gd
        lay = QHBoxLayout(self)
        lay.setContentsMargins(4, 2, 4, 2)
        lay.setSpacing(6)

        swatch = QLabel()
        swatch.setPixmap(_gate_icon(gd.display_color, 20))
        swatch.setFixedSize(20, 20)
        lay.addWidget(swatch)

        lbl = QLabel(gd.name)
        lbl.setStyleSheet("color:#CDD1DB;font-family:Consolas;font-size:11px;font-weight:bold;")
        lay.addWidget(lbl)

        if is_local:
            badge = QLabel("local")
            badge.setStyleSheet(
                "color:#F0A500;font-size:9px;border:1px solid #F0A500;"
                "border-radius:3px;padding:0 3px;")
            lay.addWidget(badge)

        lay.addStretch()

        if len(gd.roles) > 1:
            hint = QLabel(f"{len(gd.roles)}q")
            hint.setStyleSheet("color:#666;font-size:9px;")
            lay.addWidget(hint)

        self.setToolTip(gd.description or gd.name)


class GatePalette(QWidget):
    edit_gate = Signal(str)
    new_gate  = Signal()

    def __init__(self, doc: CircuitDocument, parent=None):
        super().__init__(parent)
        self.doc = doc
        self._drag_start: Optional[QPoint] = None
        self._setup_ui()
        self.refresh()

    def _setup_ui(self):
        self.setStyleSheet("background:#1A1D24;")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        # Header
        hdr = QFrame()
        hdr.setStyleSheet("background:#141720;border-bottom:1px solid #2E3240;")
        hlay = QHBoxLayout(hdr)
        hlay.setContentsMargins(10, 8, 10, 8)
        title = QLabel("Gates")
        title.setStyleSheet("color:#E8EAF0;font-family:Consolas;font-size:12px;font-weight:bold;")
        hlay.addWidget(title)
        hlay.addStretch()
        self.new_btn = QPushButton("+")
        self.new_btn.setToolTip("New gate")
        self.new_btn.setFixedSize(22, 22)
        self.new_btn.setStyleSheet(
            "QPushButton{background:#3A7FD4;color:white;border-radius:11px;"
            "font-size:16px;font-weight:bold;border:none;}"
            "QPushButton:hover{background:#4A9FEA;}")
        self.new_btn.clicked.connect(self.new_gate.emit)
        hlay.addWidget(self.new_btn)
        lay.addWidget(hdr)

        hint = QLabel("  Drag onto grid  ·  Dbl-click to edit")
        hint.setStyleSheet("color:#3A4060;font-size:9px;padding:3px 6px;")
        lay.addWidget(hint)

        self.list_w = QListWidget()
        self.list_w.setStyleSheet(
            "QListWidget{background:#1A1D24;border:none;outline:none;}"
            "QListWidget::item{border-bottom:1px solid #20232B;}"
            "QListWidget::item:selected{background:#262A33;}"
            "QListWidget::item:hover{background:#1E2430;}")
        self.list_w.setSelectionMode(QAbstractItemView.SingleSelection)
        self.list_w.itemDoubleClicked.connect(
            lambda item: self.edit_gate.emit(item.data(Qt.UserRole)))
        # mouse events for drag
        self.list_w.mousePressEvent   = self._lw_press
        self.list_w.mouseMoveEvent    = self._lw_move
        self.list_w.mouseReleaseEvent = self._lw_release
        lay.addWidget(self.list_w)

        edit_btn = QPushButton("✏  Edit selected")
        edit_btn.setStyleSheet(
            "QPushButton{background:#262A33;color:#9AA0AC;border:none;"
            "border-top:1px solid #2E3240;padding:7px;font-size:11px;}"
            "QPushButton:hover{background:#2E3240;color:#CDD1DB;}")
        edit_btn.clicked.connect(self._on_edit_click)
        lay.addWidget(edit_btn)

    # ── List population ───────────────────────────────────────────────────────
    def refresh(self):
        self.list_w.clear()
        lib = GateLibrary.instance()
        local_ids = {g.id for g in self.doc.local_gate_defs}
        for g in self.doc.local_gate_defs:
            self._add_item(g, True)
        for g in lib.all_gates():
            if g.id not in local_ids:
                self._add_item(g, False)

    def _add_item(self, gd: GateDefinition, is_local: bool):
        item = QListWidgetItem()
        item.setData(Qt.UserRole, gd.id)
        item.setSizeHint(QSize(0, 34))
        self.list_w.addItem(item)
        self.list_w.setItemWidget(item, GatePaletteItem(gd, is_local))

    def _selected_id(self) -> Optional[str]:
        item = self.list_w.currentItem()
        return item.data(Qt.UserRole) if item else None

    def _on_edit_click(self):
        gid = self._selected_id()
        if gid:
            self.edit_gate.emit(gid)

    # ── Mouse → QDrag ─────────────────────────────────────────────────────────
    def _lw_press(self, event):
        QListWidget.mousePressEvent(self.list_w, event)
        if event.button() == Qt.LeftButton:
            self._drag_start = event.pos()

    def _lw_move(self, event):
        QListWidget.mouseMoveEvent(self.list_w, event)
        if not (event.buttons() & Qt.LeftButton) or self._drag_start is None:
            return
        if (event.pos() - self._drag_start).manhattanLength() < 10:
            return
        gid = self._selected_id()
        if not gid:
            return
        lib = GateLibrary.instance()
        gd  = lib.get(gid) or next(
            (g for g in self.doc.local_gate_defs if g.id == gid), None)
        if not gd:
            return
        # Build a drag with the gate id as text
        mime = QMimeData()
        mime.setText(gid)
        drag = QDrag(self.list_w)
        drag.setMimeData(mime)
        # Small pixmap preview
        pix = _gate_icon(gd.display_color, 28)
        drag.setPixmap(pix)
        drag.setHotSpot(QPoint(14, 14))
        self._drag_start = None
        drag.exec_(Qt.CopyAction)

    def _lw_release(self, event):
        QListWidget.mouseReleaseEvent(self.list_w, event)
        self._drag_start = None

    # ── Public ────────────────────────────────────────────────────────────────
    def set_document(self, doc: CircuitDocument):
        self.doc = doc
        self.refresh()
