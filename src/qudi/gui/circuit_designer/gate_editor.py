"""
gate_editor.py — Create / edit gate definitions.

Features:
  - Qubit spinner auto-generates role rows
  - Each role: name, description, is_control checkbox, control_color picker
  - "Parse from code" auto-detects {placeholders} and function args
  - Arg table: name | default value (both editable, changes reflected live in preview)
  - Rotation axis / angle-arg fields for rotation icon rendering
  - Always saves to global library (persistent across sessions)
"""
import copy, re
from typing import Optional, List

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QTextEdit, QTableWidget, QTableWidgetItem,
    QHeaderView, QFrame, QColorDialog, QSplitter, QWidget,
    QMessageBox, QSpinBox, QCheckBox, QComboBox
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QFont, QSyntaxHighlighter, QTextCharFormat

from models import GateDefinition, GateArg, QubitRole, CircuitDocument
from library import GateLibrary

STYLE = """
QDialog,QWidget{background:#1E2128;color:#CDD1DB;
    font-family:Consolas,monospace;font-size:11px;}
QLabel{color:#9AA0AC;}
QLineEdit,QTextEdit,QSpinBox{
    background:#12141A;border:1px solid #3A3F4B;
    border-radius:4px;color:#CDD1DB;padding:4px;}
QLineEdit:focus,QTextEdit:focus,QSpinBox:focus{border-color:#3A7FD4;}
QPushButton{background:#262A33;color:#CDD1DB;
    border:1px solid #3A3F4B;border-radius:4px;padding:5px 10px;}
QPushButton:hover{background:#2E3240;}
QTableWidget{background:#12141A;border:1px solid #3A3F4B;
    gridline-color:#2E3240;color:#CDD1DB;}
QTableWidget::item:selected{background:#2A3050;}
QHeaderView::section{background:#1A1D24;color:#888;border:none;
    border-bottom:1px solid #3A3F4B;padding:3px;}
QCheckBox{color:#9AA0AC;}
QComboBox{background:#12141A;border:1px solid #3A3F4B;
    border-radius:3px;color:#CDD1DB;padding:2px 4px;}
QComboBox QAbstractItemView{background:#1A1D24;color:#CDD1DB;}
"""


class PyHighlighter(QSyntaxHighlighter):
    def __init__(self, parent):
        super().__init__(parent)
        def fmt(col, bold=False):
            f = QTextCharFormat()
            f.setForeground(QColor(col))
            if bold: f.setFontWeight(700)
            return f
        self._rules = [
            (r'\b(?:for|in|if|else|def|return|import|from|as|pass)\b', fmt("#C792EA", True)),
            (r'"[^"]*"',        fmt("#C3E88D")),
            (r"'[^']*'",        fmt("#C3E88D")),
            (r'\b\d+\.?\d*\b', fmt("#F78C6C")),
            (r'#[^\n]*',        fmt("#546E7A")),
            (r'\{[^}]+\}',      fmt("#F0A500", True)),
            (r'_I_\[',          fmt("#F0C500", True)),
            (r'\b\w+(?=\()',    fmt("#82AAFF")),
        ]

    def highlightBlock(self, text):
        for pattern, fmt in self._rules:
            for m in re.finditer(pattern, text):
                self.setFormat(m.start(), m.end() - m.start(), fmt)


def _parse_args_from_template(template: str) -> List[str]:
    found = list(re.findall(r'\{(\w+)\}', template))
    bare  = re.findall(r'(?:^|[\(,\s])([a-zA-Z_]\w*)(?:\s*[=,\)])', template)
    seen, names = set(), []
    for n in found + bare:
        if n in ("gate_name", "qubits") or n in seen:
            continue
        seen.add(n); names.append(n)
    return names


class ColorButton(QPushButton):
    color_changed = Signal(str)

    def __init__(self, color="#4A90D9", parent=None):
        super().__init__(parent)
        self._color = color
        self.setFixedSize(44, 22)
        self._refresh()
        self.clicked.connect(self._pick)

    def _refresh(self):
        self.setStyleSheet(
            f"background:{self._color};border:1px solid #555;border-radius:3px;")

    def _pick(self):
        c = QColorDialog.getColor(QColor(self._color), self)
        if c.isValid():
            self._color = c.name()
            self._refresh()
            self.color_changed.emit(self._color)

    @property
    def color(self): return self._color

    @color.setter
    def color(self, v):
        self._color = v; self._refresh()


class GateEditorDialog(QDialog):
    gate_saved = Signal(str)

    def __init__(self, gate_def: Optional[GateDefinition],
                 doc: CircuitDocument, parent=None):
        super().__init__(parent)
        self.doc = doc
        self.setStyleSheet(STYLE)
        self.setWindowTitle("Gate Editor")
        self.resize(800, 620)
        self._gate = copy.deepcopy(gate_def) if gate_def else GateDefinition()
        if gate_def is None:
            self._gate.roles = [QubitRole("qubit", "Target qubit")]
        self._setup_ui()
        self._populate()

    def _setup_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(8)

        # ── Row 1: name / symbol / color / qubits ────────────────────
        r1 = QHBoxLayout()
        r1.addWidget(QLabel("Name:"))
        self.name_edit = QLineEdit(); r1.addWidget(self.name_edit, 3)
        r1.addWidget(QLabel("Symbol:"))
        self.symbol_edit = QLineEdit()
        self.symbol_edit.setFixedWidth(52)
        self.symbol_edit.setToolTip("Short text shown inside the gate cell (e.g. Rz, X, RF)")
        r1.addWidget(self.symbol_edit)
        r1.addWidget(QLabel("Color:"))
        self.color_btn = ColorButton(); r1.addWidget(self.color_btn)
        r1.addWidget(QLabel("Qubits:"))
        self.n_spin = QSpinBox()
        self.n_spin.setRange(1, 8); self.n_spin.setFixedWidth(48)
        self.n_spin.valueChanged.connect(self._on_n_changed)
        r1.addWidget(self.n_spin)
        root.addLayout(r1)

        # ── Row 2: description ────────────────────────────────────────
        r2 = QHBoxLayout()
        r2.addWidget(QLabel("Description:"))
        self.desc_edit = QLineEdit(); r2.addWidget(self.desc_edit)
        root.addLayout(r2)

        # ── Row 3: rotation (optional) ───────────────────────────────
        r3 = QHBoxLayout()
        r3.addWidget(QLabel("Rotation axis (optional):"))
        self.rot_axis = QComboBox()
        self.rot_axis.addItems(["(none)", "X", "Y", "Z", "phi"])
        self.rot_axis.setFixedWidth(80)
        r3.addWidget(self.rot_axis)
        r3.addWidget(QLabel("Angle arg name:"))
        self.rot_arg = QLineEdit()
        self.rot_arg.setPlaceholderText("e.g. theta")
        self.rot_arg.setToolTip(
            "Name of the argument whose value is shown in the gate icon.\n"
            "e.g. if template uses 'theta', enter 'theta' here.\n"
            "The icon shows RX(theta_value) — use π/2, θ, etc. as the arg default.")
        self.rot_arg.setFixedWidth(90)
        r3.addStretch()
        r3.addWidget(self.rot_arg)
        root.addLayout(r3)

        # ── Splitter: left (roles + args) | right (template + preview)
        splitter = QSplitter(Qt.Horizontal)

        # Left
        left = QFrame()
        ll = QVBoxLayout(left); ll.setContentsMargins(0,0,6,0); ll.setSpacing(5)

        ll.addWidget(self._sec("Qubit roles"))
        # Roles table: name | desc | is_control | ctrl_color
        self.roles_tbl = QTableWidget(0, 4)
        self.roles_tbl.setHorizontalHeaderLabels(
            ["Role name", "Description", "Control?", "Dot color"])
        self.roles_tbl.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.roles_tbl.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.roles_tbl.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.roles_tbl.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.roles_tbl.setMaximumHeight(140)
        ll.addWidget(self.roles_tbl)

        ll.addWidget(self._sec("Arguments  (name | default value)"))
        self.args_tbl = QTableWidget(0, 2)
        self.args_tbl.setHorizontalHeaderLabels(["Argument", "Default value"])
        self.args_tbl.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.args_tbl.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.args_tbl.itemChanged.connect(self._refresh_preview)
        ll.addWidget(self.args_tbl)

        btn_row = QHBoxLayout()
        add_a = QPushButton("+ Arg"); add_a.clicked.connect(self._add_arg)
        del_a = QPushButton("− Del"); del_a.clicked.connect(self._del_arg)
        parse = QPushButton("⚙ Parse"); parse.setToolTip("Detect args from template")
        parse.clicked.connect(self._parse)
        btn_row.addWidget(add_a); btn_row.addWidget(del_a); btn_row.addWidget(parse)
        ll.addLayout(btn_row)

        self.hint_lbl = QLabel()
        self.hint_lbl.setWordWrap(True)
        self.hint_lbl.setStyleSheet("color:#F0A500;font-size:9px;")
        ll.addWidget(self.hint_lbl)
        ll.addStretch()
        splitter.addWidget(left)

        # Right
        right = QFrame()
        rl = QVBoxLayout(right); rl.setContentsMargins(6,0,0,0); rl.setSpacing(4)
        rl.addWidget(self._sec("Code template"))
        self.tmpl = QTextEdit()
        self.tmpl.setFont(QFont("Consolas", 11))
        PyHighlighter(self.tmpl.document())
        self.tmpl.textChanged.connect(self._refresh_preview)
        rl.addWidget(self.tmpl, 3)

        rl.addWidget(self._sec("Preview (with defaults)"))
        self.preview_lbl = QLabel()
        self.preview_lbl.setWordWrap(True)
        self.preview_lbl.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.preview_lbl.setStyleSheet(
            "background:#0D0F14;color:#C3E88D;font-family:Consolas;"
            "font-size:10px;padding:8px;border-radius:4px;"
            "border:1px solid #2E3240;min-height:48px;")
        rl.addWidget(self.preview_lbl, 1)
        splitter.addWidget(right)
        splitter.setSizes([300, 480])
        root.addWidget(splitter)

        # ── Bottom buttons ────────────────────────────────────────────
        btns = QHBoxLayout(); btns.addStretch()
        cancel = QPushButton("Cancel"); cancel.clicked.connect(self.reject)
        btns.addWidget(cancel)
        save = QPushButton("Save gate")
        save.setStyleSheet(
            "background:#3A7FD4;color:white;border:none;"
            "padding:6px 18px;border-radius:4px;")
        save.clicked.connect(self._save)
        btns.addWidget(save)
        root.addLayout(btns)

    def _sec(self, text):
        l = QLabel(text)
        l.setStyleSheet(
            "color:#E8EAF0;font-weight:bold;font-size:11px;"
            "border-bottom:1px solid #2E3240;padding-bottom:2px;margin-top:4px;")
        return l

    # ── Populate ──────────────────────────────────────────────────────────────
    def _populate(self):
        g = self._gate
        self.name_edit.setText(g.name)
        self.symbol_edit.setText(g.gate_symbol)
        self.color_btn.color = g.display_color
        self.desc_edit.setText(g.description)
        self.n_spin.blockSignals(True)
        self.n_spin.setValue(max(1, len(g.roles)))
        self.n_spin.blockSignals(False)
        for r in g.roles:
            self._add_role_row(r.name, r.description, r.is_control, r.control_color)
        for a in g.args:
            self._add_arg_row(a.name, a.default)
        self.tmpl.setPlainText(g.code_template)
        # Rotation
        axis_idx = {"": 0, "X": 1, "Y": 2, "Z": 3, "phi": 4}.get(g.rotation_axis, 0)
        self.rot_axis.setCurrentIndex(axis_idx)
        self.rot_arg.setText(g.rotation_angle_arg)
        self._refresh_hints()

    # ── Roles table ───────────────────────────────────────────────────────────
    def _on_n_changed(self, n: int):
        cur = self.roles_tbl.rowCount()
        for i in range(cur, n):
            self._add_role_row(f"qubit_{i}" if i > 0 else "qubit", "")
        while self.roles_tbl.rowCount() > n:
            self.roles_tbl.removeRow(self.roles_tbl.rowCount() - 1)
        self._refresh_hints()

    def _add_role_row(self, name="new_role", desc="",
                      is_control=False, ctrl_color="#FFFFFF"):
        r = self.roles_tbl.rowCount()
        self.roles_tbl.insertRow(r)
        self.roles_tbl.setRowHeight(r, 28)
        self.roles_tbl.setItem(r, 0, QTableWidgetItem(name))
        self.roles_tbl.setItem(r, 1, QTableWidgetItem(desc))
        chk = QCheckBox(); chk.setChecked(is_control)
        chk.stateChanged.connect(self._refresh_hints)
        self.roles_tbl.setCellWidget(r, 2, chk)
        cb = ColorButton(ctrl_color); cb.setFixedHeight(22)
        self.roles_tbl.setCellWidget(r, 3, cb)

    # ── Args table ────────────────────────────────────────────────────────────
    def _add_arg(self): self._add_arg_row("new_arg", "")

    def _add_arg_row(self, name="", default=""):
        r = self.args_tbl.rowCount()
        self.args_tbl.insertRow(r)
        self.args_tbl.setRowHeight(r, 26)
        self.args_tbl.setItem(r, 0, QTableWidgetItem(name))
        self.args_tbl.setItem(r, 1, QTableWidgetItem(default))

    def _del_arg(self):
        row = self.args_tbl.currentRow()
        if row >= 0:
            self.args_tbl.removeRow(row)
        self._refresh_preview()

    def _parse(self):
        template = self.tmpl.toPlainText()
        detected = _parse_args_from_template(template)
        role_names = set()
        for r in range(self.roles_tbl.rowCount()):
            it = self.roles_tbl.item(r, 0)
            if it: role_names.add(it.text())

        # Build reserved placeholder names to skip
        reserved = {"qubits", "gate_name", "spins", "spin_list"}
        for rn in role_names:
            reserved |= {f"{rn}_spin", f"{rn}_label", f"{rn}_state"}

        existing = set()
        for r in range(self.args_tbl.rowCount()):
            it = self.args_tbl.item(r, 0)
            if it: existing.add(it.text())

        added = 0
        for n in detected:
            if n not in role_names and n not in existing and n not in reserved:
                self._add_arg_row(n, ""); existing.add(n); added += 1
        self.hint_lbl.setText(
            f"Parsed {len(detected)} tokens — added {added} new args.")
        self._refresh_hints()

    # ── Live preview ──────────────────────────────────────────────────────────
    def _refresh_preview(self):
        self._refresh_hints()
        template = self.tmpl.toPlainText()

        # Collect roles
        role_map = {}
        for r in range(self.roles_tbl.rowCount()):
            it = self.roles_tbl.item(r, 0)
            if it: role_map[it.text()] = f"<{it.text()}>"

        # Collect arg defaults
        arg_vals = {}
        for r in range(self.args_tbl.rowCount()):
            n = (self.args_tbl.item(r, 0) or QTableWidgetItem("")).text()
            v = (self.args_tbl.item(r, 1) or QTableWidgetItem("")).text()
            if n: arg_vals[n] = v or f"{{{n}}}"

        # Inject reserved spin/state dummy values for preview
        for rname in role_map:
            arg_vals.setdefault(f"{rname}_spin",  repr("?/2"))
            arg_vals.setdefault(f"{rname}_label", f"<{rname}>")
            arg_vals.setdefault(f"{rname}_state", repr("ms=?"))
        arg_vals.setdefault("spins",     "{'<role>': '?/2'}")
        arg_vals.setdefault("spin_list", "['?/2']")

        # Render
        text = template.replace("{gate_name}", self.name_edit.text() or "Gate")
        qlist = tuple(role_map.values())
        text = text.replace("{qubits}", repr(qlist))
        for rname, rlabel in role_map.items():
            text = text.replace("{" + rname + "}", rlabel)
        for k, v in arg_vals.items():
            text = text.replace("{" + k + "}", v)
        self.preview_lbl.setText(text)

    def _refresh_hints(self):
        roles, args = [], []
        for r in range(self.roles_tbl.rowCount()):
            it = self.roles_tbl.item(r, 0)
            if it: roles.append(it.text())
        for r in range(self.args_tbl.rowCount()):
            it = self.args_tbl.item(r, 0)
            if it: args.append(it.text())

        # Standard placeholders
        std   = [f"{{{n}}}" for n in roles] + [f"{{{n}}}" for n in args]
        std  += ["{qubits}", "{gate_name}", '_I_["param"]']
        # Reserved spin/state placeholders (auto-injected by parser per role)
        rsvd  = []
        for rn in roles:
            rsvd += [f"{{{rn}_spin}}", f"{{{rn}_state}}"]

        all_parts = std + rsvd
        # Show up to 14, then a count
        shown   = "  ".join(all_parts[:14])
        overflow = f"  … +{len(all_parts)-14}" if len(all_parts) > 14 else ""
        self.hint_lbl.setText(f"Placeholders:  {shown}{overflow}")

    # ── Collect & save ────────────────────────────────────────────────────────
    def _collect(self) -> bool:
        name = self.name_edit.text().strip()
        if not name:
            QMessageBox.warning(self, "Invalid", "Name cannot be empty.")
            return False
        self._gate.name          = name
        self._gate.gate_symbol   = self.symbol_edit.text().strip()
        self._gate.display_color = self.color_btn.color
        self._gate.description   = self.desc_edit.text().strip()
        self._gate.code_template = self.tmpl.toPlainText()
        self._gate.is_global     = True
        ax = self.rot_axis.currentText()
        self._gate.rotation_axis      = "" if ax == "(none)" else ax
        self._gate.rotation_angle_arg = self.rot_arg.text().strip()

        roles = []
        for r in range(self.roles_tbl.rowCount()):
            rn  = (self.roles_tbl.item(r, 0) or QTableWidgetItem("")).text().strip()
            rd  = (self.roles_tbl.item(r, 1) or QTableWidgetItem("")).text().strip()
            chk = self.roles_tbl.cellWidget(r, 2)
            cb  = self.roles_tbl.cellWidget(r, 3)
            if rn:
                roles.append(QubitRole(
                    name=rn, description=rd,
                    is_control=chk.isChecked() if chk else False,
                    control_color=cb.color if cb else "#FFFFFF"))
        if not roles:
            QMessageBox.warning(self, "Invalid",
                "At least one qubit role is required.")
            return False
        self._gate.roles = roles

        args = []
        for r in range(self.args_tbl.rowCount()):
            an = (self.args_tbl.item(r, 0) or QTableWidgetItem("")).text().strip()
            ad = (self.args_tbl.item(r, 1) or QTableWidgetItem("")).text().strip()
            if an: args.append(GateArg(an, ad))
        self._gate.args = args
        return True

    def _save(self):
        if not self._collect():
            return
        GateLibrary.instance().add_or_update(self._gate)
        self.doc.local_gate_defs = [
            g for g in self.doc.local_gate_defs if g.id != self._gate.id]
        self.gate_saved.emit(self._gate.id)
        self.accept()
