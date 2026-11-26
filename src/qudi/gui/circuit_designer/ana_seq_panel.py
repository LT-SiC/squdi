"""
ana_seq_panel.py — Panel for editing the ana_seq analysis list.

Shows:
  - Count of SSR gates detected in the circuit
  - Table with one row per AnaSeqEntry
  - "Auto-populate from SSR count" button
  - Code preview of the generated ana_seq block
"""
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView,
    QFrame, QAbstractItemView, QComboBox, QSizePolicy
)
from PySide6.QtCore import Qt, pyqtSignal
from PySide6.QtGui import QColor, QFont

from models import CircuitDocument, AnaSeqEntry
from codegen import generate_ana_seq_block

STYLE = """
QWidget{background:#1A1D24;color:#CDD1DB;font-family:Consolas;font-size:11px;}
QFrame{background:#1A1D24;}
QLabel{color:#9AA0AC;}
QTableWidget{background:#12141A;border:none;gridline-color:#2E3240;
    color:#CDD1DB;selection-background-color:#2A3050;}
QTableWidget::item{padding:2px 4px;}
QHeaderView::section{background:#141720;color:#666;border:none;
    border-bottom:1px solid #2E3240;padding:3px;}
QPushButton{background:#262A33;color:#9AA0AC;border:1px solid #2E3240;
    border-radius:3px;padding:4px 10px;}
QPushButton:hover{background:#2E3240;color:#CDD1DB;}
QComboBox{background:#12141A;border:1px solid #2E3240;color:#CDD1DB;padding:2px;}
QComboBox QAbstractItemView{background:#1A1D24;color:#CDD1DB;}
"""

# Column indices
C_KIND=0; C_CMP=1; C_THRESH=2; C_NLP=3; C_DELTA=4; C_NRES=5; C_COMMENT=6


class AnaSeqPanel(QWidget):
    """Panel for editing ana_seq entries."""
    changed = pyqtSignal()

    def __init__(self, doc: CircuitDocument, parent=None):
        super().__init__(parent)
        self.doc = doc
        self._updating = False
        self.setStyleSheet(STYLE)
        self._setup_ui()
        self.refresh()

    def _setup_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0,0,0,0); root.setSpacing(0)

        # Header
        hdr = QFrame()
        hdr.setStyleSheet("background:#141720;border-bottom:1px solid #2E3240;")
        hl = QHBoxLayout(hdr); hl.setContentsMargins(10,7,10,7)
        title = QLabel("Analysis sequence (ana_seq)")
        title.setStyleSheet("color:#E8EAF0;font-size:12px;font-weight:bold;")
        hl.addWidget(title)
        hl.addStretch()
        self._ssr_lbl = QLabel("SSR gates: 0")
        self._ssr_lbl.setStyleSheet("color:#6DAF6D;font-size:10px;")
        hl.addWidget(self._ssr_lbl)
        root.addWidget(hdr)

        # Info bar
        info = QLabel("  Each SSR gate in the circuit should have a row here.")
        info.setStyleSheet("color:#3A6090;font-size:9px;padding:3px 6px;")
        root.addWidget(info)

        # Table
        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels(
            ["kind", "cmp", "thresh", "nlp", "delta", "n_res", "comment"])
        hh = self.table.horizontalHeader()
        for i in range(7):
            hh.setSectionResizeMode(i,
                QHeaderView.Stretch if i == 6
                else QHeaderView.ResizeToContents)
        self.table.verticalHeader().setDefaultSectionSize(26)
        self.table.verticalHeader().hide()
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.itemChanged.connect(self._on_item_changed)
        root.addWidget(self.table)

        # Buttons
        bf = QFrame()
        bf.setStyleSheet("background:#141720;border-top:1px solid #2E3240;")
        bl = QHBoxLayout(bf); bl.setContentsMargins(8,5,8,5); bl.setSpacing(6)
        add_btn  = QPushButton("+ Add row");   add_btn.clicked.connect(self._add_row)
        del_btn  = QPushButton("− Remove");    del_btn.clicked.connect(self._del_row)
        auto_btn = QPushButton("⟳ From SSR count")
        auto_btn.setToolTip("Auto-populate rows to match number of SSR gates")
        auto_btn.clicked.connect(self._auto_populate)
        up_btn   = QPushButton("▲"); up_btn.setFixedWidth(28); up_btn.clicked.connect(self._move_up)
        dn_btn   = QPushButton("▼"); dn_btn.setFixedWidth(28); dn_btn.clicked.connect(self._move_down)
        for w in [add_btn, del_btn, auto_btn]: bl.addWidget(w)
        bl.addStretch()
        bl.addWidget(up_btn); bl.addWidget(dn_btn)
        root.addWidget(bf)

        # Code preview
        prev_lbl = QLabel("  Generated code:")
        prev_lbl.setStyleSheet("color:#3A3F4B;font-size:9px;padding:2px 6px;")
        root.addWidget(prev_lbl)
        self._preview = QLabel()
        self._preview.setFont(QFont("Consolas", 9))
        self._preview.setWordWrap(True)
        self._preview.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self._preview.setStyleSheet(
            "background:#0D0F14;color:#82AAFF;padding:6px 8px;"
            "border-top:1px solid #2E3240;")
        root.addWidget(self._preview)

    # ── Data ──────────────────────────────────────────────────────────────────
    def refresh(self):
        self._updating = True
        self.table.setRowCount(0)
        for entry in self.doc.ana_seq:
            self._insert_row(entry)
        self._updating = False
        self._update_ssr_count()
        self._update_preview()

    def _insert_row(self, e: AnaSeqEntry):
        r = self.table.rowCount()
        self.table.insertRow(r)

        # kind combo
        kind_cb = QComboBox(); kind_cb.addItems(["result","init"])
        kind_cb.setCurrentText(e.kind)
        kind_cb.currentTextChanged.connect(self._sync_from_table)
        self.table.setCellWidget(r, C_KIND, kind_cb)

        # cmp combo
        cmp_cb = QComboBox(); cmp_cb.addItems([">","<"])
        cmp_cb.setCurrentText(e.comparison)
        cmp_cb.currentTextChanged.connect(self._sync_from_table)
        self.table.setCellWidget(r, C_CMP, cmp_cb)

        for col, val in [(C_THRESH, e.threshold),(C_NLP, e.nlp),
                         (C_DELTA, e.delta),(C_NRES, e.n_results)]:
            self.table.setItem(r, col, QTableWidgetItem(str(val)))

        self.table.setItem(r, C_COMMENT, QTableWidgetItem(e.comment))

    def _sync_from_table(self):
        if self._updating: return
        self._updating = True
        entries = []
        for r in range(self.table.rowCount()):
            kind_cb = self.table.cellWidget(r, C_KIND)
            cmp_cb  = self.table.cellWidget(r, C_CMP)
            def _text(col): return (self.table.item(r,col) or QTableWidgetItem("0")).text()
            try:
                e = AnaSeqEntry(
                    kind       = kind_cb.currentText() if kind_cb else "result",
                    comparison = cmp_cb.currentText()  if cmp_cb  else ">",
                    threshold  = int(_text(C_THRESH) or 0),
                    nlp        = int(_text(C_NLP)    or 0),
                    delta      = int(_text(C_DELTA)  or 0),
                    n_results  = int(_text(C_NRES)   or 1),
                    comment    = _text(C_COMMENT),
                )
                entries.append(e)
            except ValueError:
                pass
        self.doc.ana_seq = entries
        self._updating = False
        self._update_preview()
        self.changed.emit()

    def _on_item_changed(self, item):
        if not self._updating:
            self._sync_from_table()

    def _update_preview(self):
        self._preview.setText(generate_ana_seq_block(self.doc))

    def _update_ssr_count(self):
        n = self.doc.ssr_count()
        color = "#6DAF6D" if n == len(self.doc.ana_seq) else "#E05050"
        self._ssr_lbl.setText(f"SSR calls in code: {n}")
        self._ssr_lbl.setStyleSheet(f"color:{color};font-size:10px;")

    # ── Actions ───────────────────────────────────────────────────────────────
    def _add_row(self):
        self.doc.ana_seq.append(AnaSeqEntry())
        self._updating = True
        self._insert_row(self.doc.ana_seq[-1])
        self._updating = False
        self._update_preview(); self.changed.emit()

    def _del_row(self):
        rows = sorted({i.row() for i in self.table.selectedItems()}, reverse=True)
        for r in rows:
            self.table.removeRow(r)
        self._sync_from_table()

    def _auto_populate(self):
        """Replace table with one row per SSR call, preserving existing entries."""
        n_ssr = self.doc.ssr_count()
        while len(self.doc.ana_seq) < n_ssr:
            self.doc.ana_seq.append(AnaSeqEntry())
        while len(self.doc.ana_seq) > n_ssr:
            self.doc.ana_seq.pop()
        self.refresh()
        self.changed.emit()

    def _move_up(self):
        r = self.table.currentRow()
        if r <= 0: return
        self.doc.ana_seq[r], self.doc.ana_seq[r-1] = \
            self.doc.ana_seq[r-1], self.doc.ana_seq[r]
        self.refresh(); self.table.setCurrentCell(r-1, 0)

    def _move_down(self):
        r = self.table.currentRow()
        if r < 0 or r >= len(self.doc.ana_seq)-1: return
        self.doc.ana_seq[r], self.doc.ana_seq[r+1] = \
            self.doc.ana_seq[r+1], self.doc.ana_seq[r]
        self.refresh(); self.table.setCurrentCell(r+1, 0)

    # ── Public ────────────────────────────────────────────────────────────────
    def set_document(self, doc: CircuitDocument):
        self.doc = doc
        self.refresh()

    def notify_circuit_changed(self):
        """Called when the circuit changes so we can update the SSR count."""
        self._update_ssr_count()
