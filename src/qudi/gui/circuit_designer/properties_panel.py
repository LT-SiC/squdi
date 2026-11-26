"""
properties_panel.py — Shows/edits args of the selected gate placement.

New:
  - Each arg row has a "Use default" checkbox (on by default).
    When checked the edit field is greyed out and the default is used.
    When unchecked the edit field is active.
  - Rendered code preview updates live (400 ms debounce).
  - Control state picker with cycle button (⟳).
"""
from typing import Optional

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QFrame, QScrollArea, QComboBox, QPushButton, QCheckBox
)
from PySide6.QtCore import Qt, Signal, QTimer

from models import (CircuitDocument,
                    PREFILL_LAST_GATE_ARGS, spin_states, spin_state_color)
from library import GateLibrary

STYLE = """
QWidget{background:#1A1D24;color:#CDD1DB;font-family:Consolas;font-size:11px;}
QLabel{color:#9AA0AC;}
QLineEdit{background:#12141A;border:1px solid #3A3F4B;
    border-radius:3px;color:#CDD1DB;padding:3px 5px;}
QLineEdit:focus{border-color:#3A7FD4;}
QCheckBox{color:#7090B0;font-size:10px;}
QComboBox{background:#12141A;border:1px solid #3A3F4B;
    border-radius:3px;color:#CDD1DB;padding:2px 4px;}
QComboBox QAbstractItemView{background:#1A1D24;color:#CDD1DB;}
"""


class PropertiesPanel(QWidget):
    placement_changed = Signal()

    def __init__(self, doc: CircuitDocument, parent=None):
        super().__init__(parent)
        self.doc  = doc
        self._pid: Optional[str] = None
        self.setStyleSheet(STYLE)
        self._setup_ui()
        self._show_empty()

    def _setup_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0,0,0,0); root.setSpacing(0)
        hdr = QFrame()
        hdr.setStyleSheet("background:#141720;border-bottom:1px solid #2E3240;")
        hl = QHBoxLayout(hdr); hl.setContentsMargins(10,7,10,7)
        self.title_lbl = QLabel("Properties")
        self.title_lbl.setStyleSheet("color:#E8EAF0;font-size:12px;font-weight:bold;")
        hl.addWidget(self.title_lbl)
        root.addWidget(hdr)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True); scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet("QScrollArea{background:#1A1D24;border:none;}")
        self.content = QWidget(); self.content.setStyleSheet("background:#1A1D24;")
        self.cl = QVBoxLayout(self.content)
        self.cl.setContentsMargins(10,10,10,10); self.cl.setSpacing(6)
        scroll.setWidget(self.content)
        root.addWidget(scroll)

    def _clear(self):
        while self.cl.count():
            item = self.cl.takeAt(0)
            if item.widget(): item.widget().deleteLater()

    def _show_empty(self):
        self._clear()
        self.title_lbl.setText("Properties")
        l = QLabel("Select a gate to edit its arguments.")
        l.setStyleSheet("color:#3A3F4B;"); l.setAlignment(Qt.AlignCenter)
        self.cl.addWidget(l); self.cl.addStretch()

    def _sec(self, text):
        l = QLabel(text)
        l.setStyleSheet("color:#E8EAF0;font-weight:bold;"
                        "border-bottom:1px solid #2E3240;"
                        "padding-bottom:2px;margin-top:4px;")
        return l

    # ── Main display ──────────────────────────────────────────────────────────
    def show_placement(self, pid: str):
        self._pid = pid
        pl = next((p for p in self.doc.placements if p.id == pid), None)
        if not pl: self._show_empty(); return
        lib = GateLibrary.instance()
        gd  = lib.resolve(pl.gate_def_id, self.doc.local_gate_defs)
        if not gd: self._show_empty(); return

        self._clear()
        self.title_lbl.setText(f"Gate: {gd.name}")

        badge = QLabel(gd.name)
        badge.setStyleSheet(
            f"color:white;font-weight:bold;font-size:13px;"
            f"background:{gd.display_color};padding:5px 10px;border-radius:5px;")
        self.cl.addWidget(badge)
        if gd.description:
            dl = QLabel(gd.description)
            dl.setWordWrap(True)
            dl.setStyleSheet("color:#666;font-size:10px;")
            self.cl.addWidget(dl)

        # ── Qubit assignments ─────────────────────────────────────────
        self.cl.addWidget(self._sec("Qubit assignments"))
        for role in gd.roles:
            rw = QWidget(); rl = QHBoxLayout(rw); rl.setContentsMargins(0,0,0,0)
            lbl = QLabel(f"{role.name}:"); lbl.setFixedWidth(90)
            rl.addWidget(lbl)
            combo = QComboBox()
            for i, ql in enumerate(self.doc.qubit_labels):
                combo.addItem(f"[{i}] {ql}", i)
            cur = pl.role_to_row.get(role.name, 0)
            idx = combo.findData(cur)
            if idx >= 0: combo.setCurrentIndex(idx)
            rn = role.name
            combo.currentIndexChanged.connect(
                lambda _, r=rn, c=combo: self._update_role(r, c))
            rl.addWidget(combo)
            self.cl.addWidget(rw)

            # Control state picker
            if role.is_control:
                row_idx  = pl.role_to_row.get(role.name, 0)
                spin_str = self.doc.get_meta(row_idx).spin
                states   = spin_states(spin_str)

                sw = QWidget(); sl = QHBoxLayout(sw)
                sl.setContentsMargins(14,0,0,0); sl.setSpacing(4)
                sl.addWidget(QLabel("|1⟩:"))

                sc = QComboBox()
                sc.addItem("(default)", "")
                for st in states: sc.addItem(st, st)
                cur_state = pl.control_states.get(role.name, "")
                si = sc.findData(cur_state)
                if si >= 0: sc.setCurrentIndex(si)
                rn2 = role.name
                sc.currentIndexChanged.connect(
                    lambda _, r=rn2, c=sc: self._update_ctrl_state(r, c))
                sl.addWidget(sc, 1)

                # Color swatch
                chosen_color = (spin_state_color(spin_str, cur_state)
                                if cur_state else role.control_color)
                clbl = QLabel()
                clbl.setFixedSize(16,16)
                clbl.setStyleSheet(f"background:{chosen_color};border-radius:8px;")
                sl.addWidget(clbl)

                # Cycle button
                btn = QPushButton("⟳")
                btn.setFixedSize(22,22)
                btn.setToolTip("Cycle |1⟩ state  (also: dbl-click or scroll on dot)")
                btn.setStyleSheet(
                    "QPushButton{background:#2A3050;color:#7EB8F7;"
                    "border:1px solid #3A4070;border-radius:3px;font-size:13px;}"
                    "QPushButton:hover{background:#3A4070;}")
                rn3 = role.name
                btn.clicked.connect(
                    lambda _, r=rn3, c=sc, ss=states: self._cycle_ctrl_state(r,c,ss))
                sl.addWidget(btn)
                self.cl.addWidget(sw)

        # ── Arguments ─────────────────────────────────────────────────
        if gd.args:
            self.cl.addWidget(self._sec("Arguments"))
            # Show swept params hint
            swept = self.doc.swept_params()
            if swept:
                sh = QLabel("Swept: " + "  ".join(f'_I_["{s}"]' for s in swept))
                sh.setWordWrap(True)
                sh.setStyleSheet("color:#F0A500;font-size:9px;")
                self.cl.addWidget(sh)
            # Header row
            hrow = QWidget(); hlay = QHBoxLayout(hrow)
            hlay.setContentsMargins(0,0,0,0)
            h1 = QLabel("Arg"); h1.setFixedWidth(110)
            h2 = QLabel("Value"); h2.setStyleSheet("color:#9AA0AC;font-size:9px;")
            h3 = QLabel("Use default"); h3.setStyleSheet("color:#9AA0AC;font-size:9px;")
            hlay.addWidget(h1); hlay.addWidget(h2,1); hlay.addWidget(h3)
            self.cl.addWidget(hrow)

        self._arg_edits:   dict = {}
        self._arg_checks:  dict = {}
        self._arg_timers:  dict = {}

        for arg in gd.args:
            use_def = pl.use_default.get(arg.name, True)
            cur_val = pl.arg_values.get(arg.name, "")

            rw = QWidget(); rl = QHBoxLayout(rw); rl.setContentsMargins(0,0,0,0); rl.setSpacing(4)

            lbl = QLabel(f"{arg.name}:"); lbl.setFixedWidth(110)
            rl.addWidget(lbl)

            edit = QLineEdit()
            edit.setText(cur_val if not use_def else arg.default)
            edit.setPlaceholderText(arg.default or f"…{arg.name}")
            # Always enabled — typing auto-unchecks "use default"
            rl.addWidget(edit, 1)

            chk = QCheckBox("default")
            chk.setChecked(use_def)
            rl.addWidget(chk)
            self.cl.addWidget(rw)

            # Wire up — typing auto-unchecks "use default"
            an = arg.name
            timer = QTimer(); timer.setSingleShot(True); timer.setInterval(400)

            def _on_text(text, a=an, e=edit, c=chk, t=timer):
                # If user is typing and "use default" is checked, uncheck it
                if c.isChecked() and text != next(
                        (x.default for x in gd.args if x.name == a), ""):
                    c.blockSignals(True)
                    c.setChecked(False)
                    c.blockSignals(False)
                    e.setEnabled(True)
                    pl_ = self._get_pl()
                    if pl_: pl_.use_default[a] = False
                t.start()

            def _on_commit(a=an, e=edit): self._update_arg(a, e)

            def _on_check(state, a=an, e=edit, gd_=gd):
                use = bool(state)
                pl_ = self._get_pl()
                if pl_:
                    pl_.use_default[a] = use
                    e.setEnabled(not use)
                    if use:
                        dflt = next((x.default for x in gd_.args if x.name==a), "")
                        e.blockSignals(True)
                        e.setText(dflt)
                        e.blockSignals(False)
                self._emit_and_preview()

            timer.timeout.connect(_on_commit)
            edit.textChanged.connect(_on_text)
            edit.editingFinished.connect(lambda a=an, e=edit: self._update_arg(a,e))
            chk.stateChanged.connect(_on_check)

            self._arg_edits[arg.name]  = edit
            self._arg_checks[arg.name] = chk
            self._arg_timers[arg.name] = timer

        # ── Rendered code preview ──────────────────────────────────────
        self.cl.addWidget(self._sec("Rendered code"))
        self._preview = QLabel()
        self._preview.setWordWrap(True)
        self._preview.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self._preview.setStyleSheet(
            "background:#0D0F14;color:#C3E88D;font-family:Consolas;"
            "font-size:10px;padding:8px;border-radius:4px;"
            "border:1px solid #2E3240;")
        self.cl.addWidget(self._preview)
        self._refresh_preview(pl, gd)
        self.cl.addStretch()

    # ── Update handlers ───────────────────────────────────────────────────────
    def _update_role(self, role_name, combo):
        pl = self._get_pl()
        if pl:
            pl.role_to_row[role_name] = combo.currentData()
            self._emit_and_preview()

    def _update_arg(self, arg_name, edit):
        pl = self._get_pl()
        if pl and not pl.use_default.get(arg_name, True):
            pl.arg_values[arg_name] = edit.text().strip()
            self._emit_and_preview()

    def _update_ctrl_state(self, role_name, combo):
        pl = self._get_pl()
        if pl:
            state = combo.currentData()
            if state: pl.control_states[role_name] = state
            else:     pl.control_states.pop(role_name, None)
            self._emit_and_preview()

    def _cycle_ctrl_state(self, role_name, combo, states):
        cur = combo.currentData()
        try:    nxt = states[(states.index(cur)+1) % len(states)]
        except: nxt = states[0] if states else ""
        ni = combo.findData(nxt)
        if ni >= 0: combo.setCurrentIndex(ni)

    def _emit_and_preview(self):
        pl = self._get_pl()
        if PREFILL_LAST_GATE_ARGS and pl:
            GateLibrary.instance().record_used_args(pl.gate_def_id, pl.arg_values)
        self.placement_changed.emit()
        if pl:
            lib = GateLibrary.instance()
            gd  = lib.resolve(pl.gate_def_id, self.doc.local_gate_defs)
            if gd and hasattr(self, '_preview'):
                self._refresh_preview(pl, gd)

    def _refresh_preview(self, pl, gd):
        try:
            from gui.circuit_designer.parser import resolve_gate_code
        except ImportError:
            from parser import resolve_gate_code
        try:
            code = resolve_gate_code(pl, gd, self.doc)
        except Exception as e:
            code = "# error: {}".format(e)
        if hasattr(self, '_preview'):
            self._preview.setText(code)

    def _get_pl(self):
        return next((p for p in self.doc.placements if p.id == self._pid), None)

    def clear(self):
        self._pid = None
        self._show_empty()

    def set_document(self, doc):
        self.doc = doc
        self.clear()
