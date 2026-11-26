"""
gui/param_panel.py
Right-side parameter panel.
Table: name | value_expr | evaluated preview
Supports np.linspace / np.arange / range / literal lists.
"""
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QFrame,
    QAbstractItemView, QSizePolicy
)
from PySide6.QtCore import Qt, pyqtSignal, QTimer
from PySide6.QtGui import QColor, QFont

from models import CircuitDocument, Parameter

PANEL_STYLE = """
QWidget { background:#1A1D24; color:#CDD1DB; font-family:Consolas; font-size:11px; }
QFrame { background:#1A1D24; }
QTableWidget {
    background:#12141A; border:none; gridline-color:#2E3240;
    color:#CDD1DB; selection-background-color:#2A3050;
}
QTableWidget::item { padding:2px 4px; }
QHeaderView::section {
    background:#141720; color:#666; border:none;
    border-bottom:1px solid #2E3240; padding:4px;
}
QLineEdit {
    background:#12141A; border:none; color:#CDD1DB;
}
QPushButton {
    background:#262A33; color:#9AA0AC; border:1px solid #2E3240;
    border-radius:3px; padding:4px 10px;
}
QPushButton:hover { background:#2E3240; color:#CDD1DB; }
"""

ERROR_COLOR = QColor("#FF6B6B")
OK_COLOR    = QColor("#6DAF6D")
WARN_COLOR  = QColor("#F0A500")


def _eval_expr(expr: str):
    import numpy as np
    safe_builtins = {
        "range": range, "len": len, "list": list,
        "int": int, "float": float, "str": str,
        "__import__": __import__,
    }
    return eval(expr, {"np": np, "numpy": np, "__builtins__": safe_builtins})


def _preview(expr):
    # type: (str) -> tuple
    """Return (display_string, ok)."""
    try:
        val = _eval_expr(expr)
        if hasattr(val, '__iter__') and not isinstance(val, str):
            lst = list(val)
            n = len(lst)
            if n == 0:
                return "[]  (0 values)", True
            if n <= 4:
                return f"{lst}  ({n} val{'s' if n>1 else ''})", True
            return f"[{lst[0]!r}, …, {lst[-1]!r}]  ({n} values)", True
        return repr(val), True
    except Exception as e:
        return f"⚠ {e}", False


class ParamPanel(QWidget):
    """Parameter list panel."""
    params_changed = pyqtSignal()

    def __init__(self, doc: CircuitDocument, parent=None):
        super().__init__(parent)
        self.doc = doc
        self._updating = False
        self.setStyleSheet(PANEL_STYLE)
        self._setup_ui()
        self._refresh()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Header
        header = QFrame()
        header.setStyleSheet("background:#141720; border-bottom:1px solid #2E3240;")
        hlay = QHBoxLayout(header)
        hlay.setContentsMargins(10, 8, 10, 8)
        title = QLabel("Parameters")
        title.setStyleSheet("color:#E8EAF0; font-size:12px; font-weight:bold;")
        hlay.addWidget(title)
        hlay.addStretch()
        layout.addWidget(header)

        # Hint
        hint = QLabel("  Values: list, np.linspace(a,b,n), np.arange(a,b,s), range(n)")
        hint.setWordWrap(True)
        hint.setStyleSheet("color:#3A6090; font-size:9px; padding:4px 6px;")
        layout.addWidget(hint)

        # Table: Name | Value expression | Preview
        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["Name", "Value expression", "Preview"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.table.verticalHeader().setDefaultSectionSize(26)
        self.table.verticalHeader().hide()
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.itemChanged.connect(self._on_item_changed)
        layout.addWidget(self.table)

        # Buttons
        btn_frame = QFrame()
        btn_frame.setStyleSheet("background:#141720; border-top:1px solid #2E3240;")
        blay = QHBoxLayout(btn_frame)
        blay.setContentsMargins(8, 6, 8, 6)
        blay.setSpacing(6)
        add_btn = QPushButton("+ Add")
        add_btn.clicked.connect(self._add_param)
        del_btn = QPushButton("− Remove")
        del_btn.clicked.connect(self._del_param)
        up_btn  = QPushButton("▲")
        up_btn.setFixedWidth(28)
        up_btn.clicked.connect(self._move_up)
        dn_btn  = QPushButton("▼")
        dn_btn.setFixedWidth(28)
        dn_btn.clicked.connect(self._move_down)
        blay.addWidget(add_btn)
        blay.addWidget(del_btn)
        blay.addStretch()
        blay.addWidget(up_btn)
        blay.addWidget(dn_btn)
        layout.addWidget(btn_frame)

    # ------------------------------------------------------------------ data
    def _refresh(self):
        self._updating = True
        self.table.setRowCount(0)
        for param in self.doc.parameters:
            self._insert_row(param)
        self._updating = False

    def _insert_row(self, param: Parameter):
        r = self.table.rowCount()
        self.table.insertRow(r)

        name_item = QTableWidgetItem(param.name)
        self.table.setItem(r, 0, name_item)

        val_item = QTableWidgetItem(param.value_expr)
        self.table.setItem(r, 1, val_item)

        preview_text, ok = _preview(param.value_expr)
        preview_item = QTableWidgetItem(preview_text)
        preview_item.setFlags(Qt.ItemIsEnabled)   # not editable
        preview_item.setForeground(OK_COLOR if ok else ERROR_COLOR)
        self.table.setItem(r, 2, preview_item)

    def _sync_doc(self):
        params = []
        for r in range(self.table.rowCount()):
            n = (self.table.item(r, 0) or QTableWidgetItem("")).text().strip()
            v = (self.table.item(r, 1) or QTableWidgetItem("[1]")).text().strip()
            if n:
                params.append(Parameter(name=n, value_expr=v or "[1]"))
        self.doc.parameters = params
        self.params_changed.emit()

    def _update_preview(self, row: int):
        val_item = self.table.item(row, 1)
        if val_item is None:
            return
        preview_text, ok = _preview(val_item.text())
        preview_item = self.table.item(row, 2)
        if preview_item is None:
            preview_item = QTableWidgetItem()
            preview_item.setFlags(Qt.ItemIsEnabled)
            self.table.setItem(row, 2, preview_item)
        preview_item.setText(preview_text)
        preview_item.setForeground(OK_COLOR if ok else ERROR_COLOR)

    def _on_item_changed(self, item: QTableWidgetItem):
        if self._updating:
            return
        self._update_preview(item.row())
        self._sync_doc()

    # ------------------------------------------------------------------ actions
    def _add_param(self):
        p = Parameter(name="new_param", value_expr="[1]")
        self.doc.parameters.append(p)
        self._updating = True
        self._insert_row(p)
        self._updating = False
        self.params_changed.emit()
        # Select the new row name for quick editing
        last = self.table.rowCount() - 1
        self.table.setCurrentCell(last, 0)
        self.table.editItem(self.table.item(last, 0))

    def _del_param(self):
        rows = sorted({i.row() for i in self.table.selectedItems()}, reverse=True)
        for r in rows:
            self.table.removeRow(r)
        self._sync_doc()

    def _move_up(self):
        row = self.table.currentRow()
        if row <= 0:
            return
        self._swap_rows(row, row - 1)
        self.table.setCurrentCell(row - 1, self.table.currentColumn())
        self._sync_doc()

    def _move_down(self):
        row = self.table.currentRow()
        if row < 0 or row >= self.table.rowCount() - 1:
            return
        self._swap_rows(row, row + 1)
        self.table.setCurrentCell(row + 1, self.table.currentColumn())
        self._sync_doc()

    def _swap_rows(self, a: int, b: int):
        self._updating = True
        for col in range(self.table.columnCount()):
            ia = self.table.takeItem(a, col)
            ib = self.table.takeItem(b, col)
            self.table.setItem(a, col, ib)
            self.table.setItem(b, col, ia)
        self._updating = False

    # ------------------------------------------------------------------ public
    def set_document(self, doc: CircuitDocument):
        self.doc = doc
        self._refresh()

    def generate_ordered_dict_text(self) -> str:
        """Return the OrderedDict parameter block as a string."""
        from codegen import generate_parameter_block
        return generate_parameter_block(self.doc)
