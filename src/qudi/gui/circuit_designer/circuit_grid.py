"""
circuit_grid.py — 2D circuit grid widget.

New in this version:
  - Click-to-assign qubits for multi-qubit gates (1st click = role 0, 2nd = role 1 …)
  - Status bar hint shows which role to click next
  - Drag existing gate to move it
  - Right-click → Insert space (shifts all gates in col ≥ N right by 1)
  - Right-click → Copy / Paste gate
  - Control-qubit roles drawn as filled dot + vertical line (CNOT style)
  - Rotation gates show axis arc icon
  - Swept parameter indicator on gate cell (chevron stripe)
  - Spin label shown on qubit row header
  - Middle-click deletes
  - Ghost row for adding qubits
"""
from typing import Optional, Dict, Tuple, List
import math

from PyQt5.QtWidgets import (
    QWidget, QSizePolicy, QToolTip, QMenu, QAction, QInputDialog, QApplication
)
from PyQt5.QtCore import Qt, QRect, QPoint, QPointF, pyqtSignal, QMimeData
from PyQt5.QtGui import (
    QPainter, QColor, QPen, QFont, QBrush,
    QLinearGradient, QPainterPath, QDrag, QRadialGradient
)

from models import CircuitDocument, GatePlacement, GateDefinition, QubitRole, PREFILL_LAST_GATE_ARGS
from library import GateLibrary

# ── Palette ───────────────────────────────────────────────────────────────────
BG_COLOR       = QColor("#1E2128")
GRID_LINE      = QColor("#2A2D38")
WIRE_COLOR     = QColor("#4A5060")
LABEL_BG       = QColor("#16181F")
LABEL_FG       = QColor("#CDD1DB")
FIXED_FG       = QColor("#7EB8F7")
GHOST_BG       = QColor("#1A1D24")
GHOST_FG       = QColor("#3A3F4B")
SELECT_COLOR   = QColor("#F0A500")
PENDING_COLOR  = QColor("#00CFFF")
CONN_COLOR     = QColor("#DDDDDD")
CELL_RADIUS    = 8
MIN_COLS       = 18
MOVE_DRAG_DIST = 8   # pixels before a move-drag starts


class CircuitGridWidget(QWidget):
    placement_selected   = pyqtSignal(str)
    placement_deselected = pyqtSignal()
    circuit_changed      = pyqtSignal()
    status_message       = pyqtSignal(str)   # for the main window status bar

    def __init__(self, doc: CircuitDocument, parent=None):
        super().__init__(parent)
        self.doc = doc
        self._selected_id: Optional[str] = None

        # ── Palette-drag: placing a new gate by clicking ──────────────
        self._placing_gate_id: Optional[str] = None   # gate being placed
        self._placing_roles:   List[str]     = []     # role names in order
        self._placing_col:     Optional[int] = None   # column locked on first click
        self._placing_done:    Dict[str,int] = {}     # role_name → row already assigned
        self._drag_cur_pos:    Optional[QPoint] = None

        # ── QDrag drop (from palette drag) ───────────────────────────
        self._drop_gate_id: Optional[str] = None

        # ── Move existing gate by dragging ───────────────────────────
        self._move_pid:        Optional[str]   = None  # placement being moved
        self._move_start_pos:  Optional[QPoint] = None
        self._move_dragging:   bool             = False
        self._move_preview_col: Optional[int]  = None
        self._move_preview_row: Optional[int]  = None

        # ── Copy/paste clipboard ─────────────────────────────────────
        self._clipboard: Optional[GatePlacement] = None

        self.setMouseTracking(True)
        self.setAcceptDrops(True)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self._update_size()

    # ── Geometry ──────────────────────────────────────────────────────────────
    @property
    def cell_w(self): return self.doc.ui_state.get("cell_width", 110)
    @property
    def cell_h(self): return self.doc.ui_state.get("cell_height", 60)
    @property
    def label_w(self): return 118
    @property
    def n_data_rows(self): return len(self.doc.qubit_labels)
    @property
    def n_display_rows(self): return self.n_data_rows + 1
    @property
    def n_cols(self):
        used = max((p.col for p in self.doc.placements), default=-1) + 1
        return max(used + 4, MIN_COLS)

    def _total_w(self): return self.label_w + self.n_cols * self.cell_w + 20
    def _total_h(self): return self.n_display_rows * self.cell_h + 10

    def _update_size(self):
        self.setMinimumSize(self._total_w(), self._total_h())
        self.update()

    def _cell_rect(self, col: int, row: int) -> QRect:
        x = self.label_w + col * self.cell_w + 4
        y = row * self.cell_h + 4
        return QRect(x, y, self.cell_w - 8, self.cell_h - 8)

    def _pos_to_cell(self, pos: QPoint) -> Tuple[int, int]:
        col = (pos.x() - self.label_w) // self.cell_w
        row = pos.y() // self.cell_h
        return int(col), int(row)

    def _wire_y(self, row: int) -> int:
        return row * self.cell_h + self.cell_h // 2

    def _col_center_x(self, col: int) -> int:
        return self.label_w + col * self.cell_w + self.cell_w // 2

    # ── Paint ─────────────────────────────────────────────────────────────────
    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.fillRect(self.rect(), BG_COLOR)
        self._draw_grid(p)
        self._draw_labels(p)
        self._draw_wires(p)
        self._draw_placements(p)
        self._draw_move_preview(p)
        self._draw_placing_preview(p)
        self._draw_ghost_row(p)

    def _draw_grid(self, p):
        p.setPen(QPen(GRID_LINE, 1))
        for col in range(self.n_cols + 1):
            x = self.label_w + col * self.cell_w
            p.drawLine(x, 0, x, self._total_h())
        for row in range(self.n_display_rows + 1):
            y = row * self.cell_h
            p.drawLine(self.label_w, y, self._total_w(), y)

    def _draw_labels(self, p):
        p.fillRect(0, 0, self.label_w, self._total_h(), LABEL_BG)
        # Thin right border
        p.setPen(QPen(QColor("#2E3240"), 1))
        p.drawLine(self.label_w - 1, 0, self.label_w - 1, self._total_h())

        for row in range(self.n_data_rows):
            label = self.doc.qubit_labels[row]
            meta  = self.doc.get_meta(row)
            fixed = row < 2
            y0    = row * self.cell_h

            # Colored left accent bar by spin
            spin_colors = {"1/2": "#6DAF6D", "3/2": "#7EB8F7",
                           "1":   "#D97A5B", "5/2": "#B05FD4"}
            accent = QColor(spin_colors.get(meta.spin, "#555A66"))
            p.fillRect(0, y0 + 2, 4, self.cell_h - 4, accent)

            # Name label (upper portion)
            name_rect = QRect(6, y0, self.label_w - 8, self.cell_h - 17)
            p.setFont(QFont("Consolas", 10, QFont.Bold if fixed else QFont.Normal))
            p.setPen(FIXED_FG if fixed else LABEL_FG)
            p.drawText(name_rect, Qt.AlignVCenter | Qt.AlignLeft, label)

            # Spin badge (bottom strip)
            spin_rect = QRect(0, y0 + self.cell_h - 17, self.label_w, 17)
            spin_bg = QColor("#1A1D24")
            p.fillRect(spin_rect, spin_bg)
            p.setFont(QFont("Consolas", 8))
            p.setPen(accent)
            hint = "  dbl→rename" if not fixed else ""
            p.drawText(spin_rect, Qt.AlignCenter, f"s={meta.spin}{hint}")


    def _draw_ghost_row(self, p):
        row = self.n_data_rows
        p.fillRect(0, row * self.cell_h, self.label_w, self.cell_h, GHOST_BG)
        p.setPen(QPen(GHOST_FG, 1, Qt.DashLine))
        p.drawRect(4, row * self.cell_h + 4, self.label_w - 8, self.cell_h - 8)
        p.setFont(QFont("Consolas", 9))
        p.setPen(GHOST_FG)
        p.drawText(QRect(0, row * self.cell_h, self.label_w, self.cell_h),
                   Qt.AlignCenter, "+ add qubit")

    def _draw_wires(self, p):
        p.setPen(QPen(WIRE_COLOR, 2))
        for row in range(self.n_data_rows):
            y = self._wire_y(row)
            p.drawLine(self.label_w, y, self._total_w(), y)

    def _draw_placements(self, p):
        lib = GateLibrary.instance()
        swept = set(self.doc.swept_params())
        for pl in self.doc.placements:
            if self._move_dragging and pl.id == self._move_pid:
                continue   # drawn as preview instead
            gd = lib.resolve(pl.gate_def_id, self.doc.local_gate_defs)
            if gd is None:
                continue
            is_sel = (pl.id == self._selected_id)
            self._draw_one(p, pl, gd, is_sel, swept, pl.arg_values)

    def _draw_one(self, p, pl, gd: GateDefinition, selected: bool,
                  swept_params: set, arg_vals: dict,
                  col_override=None, alpha=255):
        col  = col_override if col_override is not None else pl.col
        rows = pl.qubit_rows()
        base = QColor(gd.display_color)
        base.setAlpha(alpha)

        row_to_role = {v: k for k, v in pl.role_to_row.items()}

        # Connector line between rows
        if len(rows) > 1:
            xm = self._col_center_x(col)
            pen = QPen(CONN_COLOR, 3)
            pen.setCapStyle(Qt.RoundCap)
            p.setPen(pen)
            p.drawLine(xm, self._wire_y(rows[0]),
                       xm, self._wire_y(rows[-1]))

        for row in rows:
            role_name = row_to_role.get(row, "")
            role_obj  = next((r for r in gd.roles if r.name == role_name), None)
            is_ctrl   = role_obj.is_control if role_obj else False

            if is_ctrl:
                # ── Control dot ───────────────────────────────────────
                # Determine which state is |1⟩ for this placement
                ctrl_state = pl.control_states.get(role_name, "") if pl else ""
                row_idx    = pl.role_to_row.get(role_name, 0) if pl else 0
                spin_str   = self.doc.get_meta(row_idx).spin

                from models import spin_states, spin_state_color, SPIN_STATE_COLORS
                states = spin_states(spin_str)

                # Pick dot color from the chosen state
                if ctrl_state and ctrl_state in states:
                    dot_color = QColor(spin_state_color(spin_str, ctrl_state))
                elif role_obj and role_obj.control_color != "#FFFFFF":
                    dot_color = QColor(role_obj.control_color)
                else:
                    dot_color = QColor("#FFFFFF")
                dot_color.setAlpha(alpha)

                xm = self._col_center_x(col)
                ym = self._wire_y(row)

                n_states = len(states)
                if n_states <= 2:
                    # Simple filled dot (spin-1/2)
                    p.setBrush(QBrush(dot_color))
                    p.setPen(Qt.NoPen)
                    p.drawEllipse(QPointF(xm, ym), 8, 8)
                else:
                    # Multi-state dot: outer ring shows all states as arc segments,
                    # chosen state filled solid
                    outer_r = 11
                    inner_r = 5
                    arc_span = 360 * 16 // n_states
                    for si, st in enumerate(states):
                        sc = QColor(SPIN_STATE_COLORS[si % len(SPIN_STATE_COLORS)])
                        sc.setAlpha(alpha)
                        start_angle = si * arc_span
                        if st == ctrl_state:
                            # Filled wedge for selected state
                            p.setBrush(QBrush(sc))
                            p.setPen(Qt.NoPen)
                            pie_path = QPainterPath()
                            pie_path.moveTo(xm, ym)
                            pie_path.arcTo(xm - outer_r, ym - outer_r,
                                           2*outer_r, 2*outer_r,
                                           start_angle / 16, arc_span / 16)
                            pie_path.closeSubpath()
                            p.drawPath(pie_path)
                        else:
                            # Thin arc for unselected states
                            dim = QColor(sc); dim.setAlpha(max(60, alpha // 2))
                            p.setPen(QPen(dim, 2))
                            p.setBrush(Qt.NoBrush)
                            p.drawArc(int(xm - outer_r), int(ym - outer_r),
                                      2*outer_r, 2*outer_r,
                                      start_angle, arc_span)
                    # Inner white circle
                    p.setBrush(QBrush(QColor(30, 33, 40, alpha)))
                    p.setPen(Qt.NoPen)
                    p.drawEllipse(QPointF(xm, ym), inner_r, inner_r)

                # Selection ring
                if selected:
                    p.setPen(QPen(SELECT_COLOR, 2))
                    p.setBrush(Qt.NoBrush)
                    p.drawEllipse(QPointF(xm, ym), 14, 14)

                # State label below dot (if state chosen)
                if ctrl_state:
                    p.setFont(QFont("Consolas", 7))
                    p.setPen(dot_color)
                    lbl_r = QRect(int(xm) - 25, int(ym) + 13, 50, 12)
                    p.drawText(lbl_r, Qt.AlignCenter, ctrl_state)
            else:
                rect = self._cell_rect(col, row)
                self._draw_gate_cell(p, rect, gd, role_name, base, selected,
                                     swept_params, arg_vals, alpha)

    def _draw_gate_cell(self, p, rect: QRect, gd: GateDefinition,
                        role_name: str, base: QColor, selected: bool,
                        swept_params: set, arg_vals: dict, alpha=255):
        # Gradient background
        grad = QLinearGradient(rect.topLeft(), rect.bottomLeft())
        light = base.lighter(130); light.setAlpha(alpha)
        dark  = base.darker(110);  dark.setAlpha(alpha)
        grad.setColorAt(0, light)
        grad.setColorAt(1, dark)
        p.setBrush(QBrush(grad))
        p.setPen(QPen(SELECT_COLOR, 2.5) if selected
                 else QPen(base.darker(160), 1.5))
        path = QPainterPath()
        path.addRoundedRect(rect.x(), rect.y(), rect.width(), rect.height(),
                            CELL_RADIUS, CELL_RADIUS)
        p.drawPath(path)

        # Find which params are swept in this gate's args
        swept_here = []
        for s in swept_params:
            for v in arg_vals.values():
                if f'_I_["{s}"]' in v or f"_I_['{s}']" in v:
                    if s not in swept_here:
                        swept_here.append(s)
        any_swept = bool(swept_here)

        if any_swept:
            p.save()
            p.setClipPath(path)
            stripe = QColor("#F0C500"); stripe.setAlpha(22)
            p.setPen(QPen(stripe, 3))
            for i in range(-20, rect.width() + 40, 10):
                p.drawLine(rect.left() + i, rect.top(),
                           rect.left() + i + rect.height(), rect.bottom())
            p.restore()

        # Icon / label — upper portion of cell
        p.setPen(QColor("#FFFFFF"))
        symbol = gd.gate_symbol or gd.name

        # Reserve bottom strip for role name when gate spans multiple qubits
        has_role_strip = bool(role_name) and len(gd.roles) > 1
        strip_h = 13 if has_role_strip else 0
        icon_rect = QRect(rect.x(), rect.y(), rect.width(), rect.height() - strip_h)

        if gd.rotation_axis:
            self._draw_rotation_icon(p, icon_rect, gd, arg_vals)
        else:
            p.setFont(QFont("Consolas", 9, QFont.Bold))
            p.drawText(icon_rect, Qt.AlignCenter, symbol)

        # Role name strip
        if has_role_strip:
            strip = QRect(rect.x(), rect.bottom() - strip_h + 1, rect.width(), strip_h)
            role_bg = base.darker(140)
            role_bg.setAlpha(alpha)
            p.fillRect(strip, role_bg)
            p.setFont(QFont("Consolas", 7))
            p.setPen(QColor("#AAAACC"))
            p.drawText(strip, Qt.AlignCenter, role_name)

        # Swept indicator: small "~" + param name(s) in top-right
        if any_swept:
            label_parts = ["~" + s for s in swept_here[:2]]  # max 2 names
            sweep_txt = " ".join(label_parts)
            p.setFont(QFont("Consolas", 6))
            p.setPen(QColor("#F0C500"))
            # Draw in top-right corner, above role strip
            sw_rect = QRect(rect.x(), rect.top() + 2, rect.width() - 2, 10)
            p.drawText(sw_rect, Qt.AlignRight | Qt.AlignTop, sweep_txt)

    def _draw_rotation_icon(self, p, rect: QRect, gd: GateDefinition, arg_vals: dict):
        """Draw R_axis(angle) with a coloured arc and angle text."""
        axis = gd.rotation_axis
        axis_colors = {"X": QColor("#FF6060"), "Y": QColor("#60CC60"),
                       "Z": QColor("#6090FF"), "phi": QColor("#FFAA00")}
        arc_color = axis_colors.get(axis, QColor("#FFFFFF"))

        cx = rect.center().x()
        cy = rect.center().y() - 4
        r  = min(rect.width(), rect.height()) // 2 - 6

        # Coloured arc
        p.setPen(QPen(arc_color, 2.5))
        p.setBrush(Qt.NoBrush)
        p.drawArc(cx - r, cy - r, 2*r, 2*r, 20*16, 320*16)

        # Arrow tip on arc end
        p.setBrush(arc_color)
        p.setPen(Qt.NoPen)
        import math
        tip_angle = math.radians(360 - 20)
        tx = cx + r * math.cos(tip_angle)
        ty = cy - r * math.sin(tip_angle)
        arrow = QPainterPath()
        arrow.moveTo(tx, ty)
        arrow.lineTo(tx - 5, ty - 3)
        arrow.lineTo(tx - 5, ty + 3)
        arrow.closeSubpath()
        p.drawPath(arrow)

        # ── Angle display ─────────────────────────────────────────────────────
        # rotation_angle_arg is either:
        #   (a) the name of an arg in gd.args  → look up live value / default
        #   (b) a literal display string (e.g. "π/2", "\theta") → use directly
        angle_arg   = gd.rotation_angle_arg
        display_val = ""
        if angle_arg:
            arg_names = {a.name for a in gd.args}
            if angle_arg in arg_names:
                # Case (a): resolve via live value then default
                display_val = arg_vals.get(angle_arg, "")
                if not display_val:
                    display_val = next(
                        (a.default for a in gd.args if a.name == angle_arg), "")
            else:
                # Case (b): literal display label
                display_val = angle_arg

            # Pretty-print common math expressions
            if display_val:
                display_val = (display_val
                    .replace("3.14159265358979", "π")
                    .replace("3.14159265", "π")
                    .replace("3.14159", "π")
                    .replace("math.pi", "π")
                    .replace("np.pi", "π")
                    .replace("\\pi", "π"))
                if len(display_val) > 10:
                    display_val = display_val[:9] + "…"

        # "R{axis}(val)" label centred on arc
        p.setPen(QColor("#FFFFFF"))
        p.setFont(QFont("Consolas", 8, QFont.Bold))
        if display_val:
            full_label = f"R{axis}({display_val})"
        else:
            full_label = f"R{axis}"
        lbl_rect = QRect(rect.x(), cy - 6, rect.width(), 14)
        p.drawText(lbl_rect, Qt.AlignCenter, full_label)

    def _draw_move_preview(self, p):
        if not self._move_dragging or not self._drag_cur_pos:
            return
        col, row = self._pos_to_cell(self._drag_cur_pos)
        col = max(0, col); row = max(0, min(row, self.n_data_rows - 1))
        pl  = next((x for x in self.doc.placements if x.id == self._move_pid), None)
        if pl is None:
            return
        lib = GateLibrary.instance()
        gd  = lib.resolve(pl.gate_def_id, self.doc.local_gate_defs)
        if gd is None:
            return
        # draw ghost at new position
        self._draw_one(p, pl, gd, False, set(), pl.arg_values,
                       col_override=col, alpha=140)

    def _draw_placing_preview(self, p):
        if not self._placing_gate_id or not self._drag_cur_pos:
            return
        col, row = self._pos_to_cell(self._drag_cur_pos)
        col = self._placing_col if self._placing_col is not None else col
        lib = GateLibrary.instance()
        gd  = lib.get(self._placing_gate_id)
        if not gd or row < 0 or row >= self.n_data_rows:
            return

        # Show already-assigned roles
        for role_name, assigned_row in self._placing_done.items():
            rect = self._cell_rect(col, assigned_row)
            c = QColor(gd.display_color); c.setAlpha(180)
            p.setBrush(QBrush(c))
            p.setPen(QPen(PENDING_COLOR, 2))
            path = QPainterPath()
            path.addRoundedRect(rect.x(), rect.y(), rect.width(), rect.height(),
                                CELL_RADIUS, CELL_RADIUS)
            p.drawPath(path)
            p.setPen(QColor("#FFFFFF"))
            p.setFont(QFont("Consolas", 8))
            p.drawText(rect, Qt.AlignCenter, f"{gd.name}\n[{role_name}]")

        # Show current hover cell for next role
        next_idx  = len(self._placing_done)
        if next_idx < len(gd.roles):
            next_role = gd.roles[next_idx].name
            rect = self._cell_rect(col, row)
            c = QColor(gd.display_color); c.setAlpha(110)
            p.setBrush(QBrush(c))
            p.setPen(QPen(PENDING_COLOR, 2, Qt.DashLine))
            path = QPainterPath()
            path.addRoundedRect(rect.x(), rect.y(), rect.width(), rect.height(),
                                CELL_RADIUS, CELL_RADIUS)
            p.drawPath(path)
            p.setPen(PENDING_COLOR)
            p.setFont(QFont("Consolas", 8))
            p.drawText(rect, Qt.AlignCenter, f"← {next_role}")

        # Connector between done rows
        done_rows = list(self._placing_done.values())
        if done_rows:
            xm = self._col_center_x(col)
            all_rows = sorted(done_rows + [row])
            p.setPen(QPen(QColor("#FFFFFF88"), 2, Qt.DashLine))
            p.drawLine(xm, self._wire_y(all_rows[0]),
                       xm, self._wire_y(all_rows[-1]))

    # ── Mouse ─────────────────────────────────────────────────────────────────
    def mousePressEvent(self, event):
        col, row = self._pos_to_cell(event.pos())

        # Middle-click → delete
        if event.button() == Qt.MiddleButton:
            pl = self._placement_at(col, row)
            if pl:
                self._delete_placement(pl.id)
            return

        # Ghost row → add qubit
        if event.button() == Qt.LeftButton and row == self.n_data_rows:
            self._add_qubit()
            return

        # Right-click
        if event.button() == Qt.RightButton:
            pl = self._placement_at(col, row)
            self._context_menu(event.globalPos(), col, row, pl)
            return

        if event.button() != Qt.LeftButton:
            return

        # ── Click-to-place multi-qubit gate ──────────────────────────
        if self._placing_gate_id:
            if 0 <= row < self.n_data_rows:
                self._placing_click(col, row)
            return

        # ── Begin move of existing gate ───────────────────────────────
        pl = self._placement_at(col, row)
        if pl:
            self._selected_id = pl.id
            self.placement_selected.emit(pl.id)
            self._move_pid       = pl.id
            self._move_start_pos = event.pos()
            self._move_dragging  = False
            self.update()
            return

        # ── Deselect ─────────────────────────────────────────────────
        self._selected_id = None
        self.placement_deselected.emit()
        self.update()

    def mouseMoveEvent(self, event):
        col, row = self._pos_to_cell(event.pos())
        self._drag_cur_pos = event.pos()

        # Tooltip
        if not self._placing_gate_id and not self._move_dragging:
            pl = self._placement_at(col, row)
            if pl:
                lib = GateLibrary.instance()
                gd  = lib.resolve(pl.gate_def_id, self.doc.local_gate_defs)
                if gd:
                    args_preview = ", ".join(
                        f"{k}={v}" for k, v in pl.arg_values.items()
                        if v and k in {a.name for a in gd.args}
                    )
                    QToolTip.showText(event.globalPos(),
                        f"<b>{gd.name}</b>  col {pl.col} rows {pl.qubit_rows()}"
                        + (f"<br>{args_preview}" if args_preview else ""), self)

        # Move drag
        if (self._move_pid and self._move_start_pos
                and not self._placing_gate_id):
            dist = (event.pos() - self._move_start_pos).manhattanLength()
            if dist >= MOVE_DRAG_DIST:
                self._move_dragging = True

        self.update()

    def mouseReleaseEvent(self, event):
        if event.button() != Qt.LeftButton:
            return

        if self._move_dragging and self._move_pid:
            col, row = self._pos_to_cell(event.pos())
            col = max(0, col)
            self._finish_move(col, row)
            return

        # Reset move state if no drag happened (was just a click)
        self._move_pid       = None
        self._move_start_pos = None
        self._move_dragging  = False

    def _ctrl_dot_at(self, pos: QPoint):
        """Return (placement, role_name) if pos hits a control dot, else (None, None)."""
        lib = GateLibrary.instance()
        for pl in self.doc.placements:
            gd = lib.resolve(pl.gate_def_id, self.doc.local_gate_defs)
            if not gd:
                continue
            row_to_role = {v: k for k, v in pl.role_to_row.items()}
            for row, role_name in row_to_role.items():
                role_obj = next((r for r in gd.roles if r.name == role_name), None)
                if not role_obj or not role_obj.is_control:
                    continue
                xm = self._col_center_x(pl.col)
                ym = self._wire_y(row)
                dist = ((pos.x() - xm)**2 + (pos.y() - ym)**2) ** 0.5
                if dist <= 14:   # generous hit area
                    return pl, role_name
        return None, None

    def _cycle_ctrl_state(self, pl, role_name: str):
        """Advance the |1⟩ state for role_name to the next spin state."""
        from models import spin_states
        row_idx  = pl.role_to_row.get(role_name, 0)
        spin_str = self.doc.get_meta(row_idx).spin
        states   = spin_states(spin_str)
        if not states:
            return
        cur = pl.control_states.get(role_name, "")
        try:
            idx = states.index(cur)
            nxt = states[(idx + 1) % len(states)]
        except ValueError:
            nxt = states[0]
        pl.control_states[role_name] = nxt
        self.circuit_changed.emit()
        self.update()
        # Also emit selection so properties panel refreshes
        if self._selected_id == pl.id:
            self.placement_selected.emit(pl.id)

    def wheelEvent(self, event):
        """Scroll wheel on a control dot → cycle |1⟩ state."""
        pl, role_name = self._ctrl_dot_at(event.pos())
        if pl and role_name:
            # Forward = next state, backward = previous state
            from models import spin_states
            row_idx  = pl.role_to_row.get(role_name, 0)
            spin_str = self.doc.get_meta(row_idx).spin
            states   = spin_states(spin_str)
            if not states:
                return
            cur = pl.control_states.get(role_name, "")
            try:    idx = states.index(cur)
            except: idx = -1
            delta = -1 if event.angleDelta().y() > 0 else 1
            nxt = states[(idx + delta) % len(states)]
            pl.control_states[role_name] = nxt
            self.circuit_changed.emit()
            self.update()
            if self._selected_id == pl.id:
                self.placement_selected.emit(pl.id)
            event.accept()
        else:
            super().wheelEvent(event)

    def mouseDoubleClickEvent(self, event):
        col, row = self._pos_to_cell(event.pos())

        # Double-click on control dot → cycle |1⟩ state
        if event.button() == Qt.LeftButton:
            pl, role_name = self._ctrl_dot_at(event.pos())
            if pl:
                self._cycle_ctrl_state(pl, role_name)
                return

        # Double-click on label area → rename (non-fixed rows only)
        if event.x() < self.label_w and 2 <= row < self.n_data_rows:
            self._rename_qubit(row)

    def keyPressEvent(self, event):
        mod = event.modifiers()
        key = event.key()

        # Ctrl+C — copy selected gate
        if mod == Qt.ControlModifier and key == Qt.Key_C:
            if self._selected_id:
                pl = next((p for p in self.doc.placements if p.id == self._selected_id), None)
                if pl:
                    self._copy_placement(pl)
            return

        # Ctrl+X — cut selected gate
        if mod == Qt.ControlModifier and key == Qt.Key_X:
            if self._selected_id:
                pl = next((p for p in self.doc.placements if p.id == self._selected_id), None)
                if pl:
                    self._copy_placement(pl)
                    self._delete_placement(pl.id)
            return

        # Ctrl+V — paste at column after last selected gate
        if mod == Qt.ControlModifier and key == Qt.Key_V:
            if self._clipboard:
                # Paste one column after the currently selected gate, or at col 0
                if self._selected_id:
                    sel = next((p for p in self.doc.placements if p.id == self._selected_id), None)
                    col = (sel.col + 1) if sel else 0
                    row = sel.min_row() if sel else 0
                else:
                    col = max((p.col for p in self.doc.placements), default=-1) + 1
                    row = 0
                self._paste_placement(col, row)
            return

        if key in (Qt.Key_Delete, Qt.Key_Backspace):
            if self._selected_id:
                self._delete_placement(self._selected_id)
        elif key == Qt.Key_Escape:
            self._cancel_placing()

    # ── QDrag drop protocol ───────────────────────────────────────────────────
    def dragEnterEvent(self, event):
        if event.mimeData().hasText():
            self._drop_gate_id = event.mimeData().text()
            event.acceptProposedAction()

    def dragMoveEvent(self, event):
        self._drag_cur_pos = event.pos()
        self.update()
        event.acceptProposedAction()

    def dragLeaveEvent(self, _):
        self._drop_gate_id = None
        self._drag_cur_pos = None
        self.update()

    def dropEvent(self, event):
        if not event.mimeData().hasText():
            return
        gate_id = event.mimeData().text()
        col, row = self._pos_to_cell(event.pos())
        self._drop_gate_id = None
        if col < 0 or row < 0 or row >= self.n_data_rows:
            return
        lib = GateLibrary.instance()
        gd  = lib.get(gate_id)
        if gd is None:
            return
        if len(gd.roles) == 1:
            self._place_gate(gate_id, col, {gd.roles[0].name: row})
        else:
            # Start click-to-assign mode
            self._begin_placing(gate_id, col, row)
        self._drag_cur_pos = None
        self.update()
        event.acceptProposedAction()

    # ── Click-to-place logic ──────────────────────────────────────────────────
    def _begin_placing(self, gate_id: str, col: int, first_row: int):
        """Enter click-to-assign mode for a multi-qubit gate."""
        lib = GateLibrary.instance()
        gd  = lib.get(gate_id)
        if gd is None:
            return
        self._placing_gate_id = gate_id
        self._placing_roles   = [r.name for r in gd.roles]
        self._placing_col     = col
        self._placing_done    = {}
        # Assign first role immediately
        self._placing_done[self._placing_roles[0]] = first_row
        self._emit_placing_hint()
        self.update()

    def _placing_click(self, col: int, row: int):
        """Handle a click while in click-to-assign mode."""
        if self._placing_col is None:
            self._placing_col = col

        next_idx = len(self._placing_done)
        if next_idx >= len(self._placing_roles):
            return

        role_name = self._placing_roles[next_idx]
        self._placing_done[role_name] = row

        if len(self._placing_done) >= len(self._placing_roles):
            # All roles assigned — place the gate
            self._place_gate(self._placing_gate_id, self._placing_col,
                             dict(self._placing_done))
            self._cancel_placing()
        else:
            self._emit_placing_hint()
            self.update()

    def _emit_placing_hint(self):
        if not self._placing_gate_id:
            return
        lib = GateLibrary.instance()
        gd  = lib.get(self._placing_gate_id)
        if not gd:
            return
        done = len(self._placing_done)
        total = len(gd.roles)
        if done < total:
            next_role = gd.roles[done].name
            self.status_message.emit(
                f"Placing {gd.name}  —  click row for role '{next_role}' "
                f"({done+1}/{total})  ·  Esc to cancel")

    def _cancel_placing(self):
        self._placing_gate_id = None
        self._placing_roles   = []
        self._placing_col     = None
        self._placing_done    = {}
        self._drag_cur_pos    = None
        self.setCursor(Qt.ArrowCursor)
        self.status_message.emit("Ready")
        self.update()

    # ── Move existing gate ────────────────────────────────────────────────────
    def _finish_move(self, new_col: int, new_row: int):
        pl = next((x for x in self.doc.placements if x.id == self._move_pid), None)
        if pl:
            lib = GateLibrary.instance()
            gd  = lib.resolve(pl.gate_def_id, self.doc.local_gate_defs)
            if gd:
                # Shift all rows by (new_row - old_min_row)
                old_min = pl.min_row()
                delta   = new_row - old_min
                new_r2r = {}
                for rname, rrow in pl.role_to_row.items():
                    nr = max(0, min(rrow + delta, self.n_data_rows - 1))
                    new_r2r[rname] = nr
                pl.col       = new_col
                pl.role_to_row = new_r2r
                self.circuit_changed.emit()

        self._move_pid       = None
        self._move_start_pos = None
        self._move_dragging  = False
        self._move_preview_col = None
        self._update_size()

    # ── Place gate ────────────────────────────────────────────────────────────
    def _place_gate(self, gate_def_id: str, col: int, role_to_row: Dict[str, int]):
        if col < 0:
            return
        lib = GateLibrary.instance()
        gd  = lib.get(gate_def_id) or next(
            (g for g in self.doc.local_gate_defs if g.id == gate_def_id), None)

        pl = GatePlacement()
        pl.gate_def_id = gate_def_id
        pl.col         = col
        pl.role_to_row = role_to_row

        if gd:
            pl.arg_values  = {a.name: a.default for a in gd.args}
            pl.use_default = {a.name: True for a in gd.args}
            if PREFILL_LAST_GATE_ARGS:
                last = lib.get_last_used_args(gate_def_id)
                if last:
                    for k, v in last.items():
                        if k in pl.arg_values:
                            pl.arg_values[k]  = v
                            pl.use_default[k] = False  # they had an explicit value

        self.doc.placements.append(pl)
        self._selected_id = pl.id
        self.placement_selected.emit(pl.id)
        self.circuit_changed.emit()
        self._update_size()

    # ── Context menu ──────────────────────────────────────────────────────────
    def _context_menu(self, global_pos: QPoint, col: int, row: int,
                      pl: Optional[GatePlacement]):
        menu = QMenu(self)
        menu.setStyleSheet(
            "QMenu{background:#262A33;color:#CDD1DB;border:1px solid #3A3F4B;}"
            "QMenu::item:selected{background:#3A3F4B;}"
            "QMenu::separator{height:1px;background:#3A3F4B;}")

        if pl:
            edit = QAction("✏  Edit arguments", self)
            edit.triggered.connect(lambda: self._select_for_edit(pl.id))
            menu.addAction(edit)

            copy_a = QAction("⧉  Copy gate", self)
            copy_a.triggered.connect(lambda: self._copy_placement(pl))
            menu.addAction(copy_a)

            del_a = QAction("🗑  Delete  (middle-click)", self)
            del_a.triggered.connect(lambda: self._delete_placement(pl.id))
            menu.addAction(del_a)
            menu.addSeparator()

        if self._clipboard:
            cname = self._clipboard_name()
            paste_a = QAction(f'⧉  Paste  "{cname}"  here', self)
            paste_a.triggered.connect(lambda: self._paste_placement(col, row))
            menu.addAction(paste_a)
            menu.addSeparator()

        ins_a = QAction(f"⇥  Insert space before col {col}", self)
        ins_a.triggered.connect(lambda: self._insert_space(col))
        menu.addAction(ins_a)

        add_q = QAction("+ Add qubit row", self)
        add_q.triggered.connect(self._add_qubit)
        menu.addAction(add_q)

        if 0 <= row < self.n_data_rows:
            spin_a = QAction(
                f"  Set spin for '{self.doc.qubit_labels[row]}' "
                f"(s={self.doc.get_meta(row).spin})", self)
            spin_a.triggered.connect(lambda: self._set_spin(row))
            menu.addAction(spin_a)
        if row >= 2 and row < self.n_data_rows:
            rename_q = QAction(f"✎  Rename '{self.doc.qubit_labels[row]}'", self)
            rename_q.triggered.connect(lambda: self._rename_qubit(row))
            menu.addAction(rename_q)
            del_q = QAction(f"🗑  Delete qubit '{self.doc.qubit_labels[row]}'", self)
            del_q.triggered.connect(lambda: self._delete_qubit(row))
            menu.addAction(del_q)

        menu.exec_(global_pos)

    def _clipboard_name(self) -> str:
        if not self._clipboard:
            return ""
        lib = GateLibrary.instance()
        gd  = lib.resolve(self._clipboard.gate_def_id, self.doc.local_gate_defs)
        return gd.name if gd else "?"

    # ── Helpers ───────────────────────────────────────────────────────────────
    def _placement_at(self, col: int, row: int) -> Optional[GatePlacement]:
        for pl in self.doc.placements:
            if pl.col == col and row in pl.qubit_rows():
                return pl
        return None

    def _delete_placement(self, pid: str):
        self.doc.placements = [p for p in self.doc.placements if p.id != pid]
        if self._selected_id == pid:
            self._selected_id = None
            self.placement_deselected.emit()
        self.circuit_changed.emit()
        self._update_size()

    def _select_for_edit(self, pid: str):
        self._selected_id = pid
        self.placement_selected.emit(pid)
        self.update()

    def _copy_placement(self, pl: GatePlacement):
        self._clipboard = pl.copy_new()
        lib = GateLibrary.instance()
        gd  = lib.resolve(pl.gate_def_id, self.doc.local_gate_defs)
        self.status_message.emit(
            f"Copied {gd.name if gd else '?'} — right-click to paste")

    def _paste_placement(self, col: int, row: int):
        if not self._clipboard:
            return
        c = self._clipboard.copy_new()
        c.col = col
        # Shift rows so min_row lands on clicked row
        old_min = c.min_row()
        delta   = row - old_min
        c.role_to_row = {k: max(0, min(v + delta, self.n_data_rows - 1))
                         for k, v in c.role_to_row.items()}
        self.doc.placements.append(c)
        self._selected_id = c.id
        self.placement_selected.emit(c.id)
        self.circuit_changed.emit()
        self._update_size()

    def _insert_space(self, before_col: int):
        """Shift all placements at col >= before_col right by 1."""
        for pl in self.doc.placements:
            if pl.col >= before_col:
                pl.col += 1
        self.circuit_changed.emit()
        self._update_size()

    def _delete_qubit(self, row: int):
        from PyQt5.QtWidgets import QMessageBox
        label = self.doc.qubit_labels[row]
        r = QMessageBox.question(self, "Delete qubit",
            f"Delete qubit '{label}'? All gates on this row will be removed.",
            QMessageBox.Yes | QMessageBox.Cancel)
        if r == QMessageBox.Yes:
            self.doc.delete_qubit(row)
            self.circuit_changed.emit()
            self._update_size()

    def _add_qubit(self):
        name, ok = QInputDialog.getText(self, "Add qubit", "Qubit name:")
        if ok and name.strip():
            self.doc.qubit_labels.append(name.strip())
            self.doc.ensure_fixed_rows()
            self.circuit_changed.emit()
            self._update_size()

    def _rename_qubit(self, row: int):
        old = self.doc.qubit_labels[row]
        name, ok = QInputDialog.getText(self, "Rename qubit", "New name:", text=old)
        if ok and name.strip():
            self.doc.qubit_labels[row] = name.strip()
            self.circuit_changed.emit()
            self.update()

    def _set_spin(self, row: int):
        from PyQt5.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QComboBox, QPushButton
        meta  = self.doc.get_meta(row)
        label = self.doc.qubit_labels[row]
        dlg   = QDialog(self)
        dlg.setWindowTitle(f"Spin for '{label}'")
        dlg.setStyleSheet(
            "QDialog{background:#1E2128;color:#CDD1DB;font-family:Consolas;}"
            "QLabel{color:#9AA0AC;} QComboBox,QLineEdit{"
            "background:#12141A;border:1px solid #3A3F4B;color:#CDD1DB;padding:3px;}")
        lay = QVBoxLayout(dlg); lay.setSpacing(10)
        from PyQt5.QtWidgets import QLabel as QL, QLineEdit
        lay.addWidget(QL(f"Set spin quantum number for qubit '{label}':"))

        combo = QComboBox()
        common = ["1/2", "3/2", "5/2", "7/2", "1", "2", "3"]
        combo.addItems(common)
        combo.setEditable(True)
        idx = combo.findText(meta.spin)
        if idx >= 0:
            combo.setCurrentIndex(idx)
        else:
            combo.setCurrentText(meta.spin)
        lay.addWidget(combo)

        note = QL("Common values: 1/2 (electron, C, Si), 3/2 (electron in high field)")
        note.setWordWrap(True)
        note.setStyleSheet("color:#3A6090;font-size:9px;")
        lay.addWidget(note)

        brow = QHBoxLayout()
        cancel = QPushButton("Cancel"); cancel.clicked.connect(dlg.reject)
        ok     = QPushButton("Apply")
        ok.setStyleSheet("background:#3A7FD4;color:white;border:none;"
                         "padding:5px 14px;border-radius:4px;")
        ok.clicked.connect(dlg.accept)
        brow.addStretch(); brow.addWidget(cancel); brow.addWidget(ok)
        lay.addLayout(brow)

        if dlg.exec_():
            new_spin = combo.currentText().strip()
            if new_spin:
                while len(self.doc.qubit_meta) <= row:
                    from models import QubitRowMeta
                    self.doc.qubit_meta.append(QubitRowMeta())
                self.doc.qubit_meta[row].spin = new_spin
                self.update()

    # ── Public API ────────────────────────────────────────────────────────────
    def set_document(self, doc: CircuitDocument):
        self.doc = doc
        self._selected_id = None
        self._cancel_placing()
        self._update_size()

    def begin_placing(self, gate_def_id: str):
        """Called by palette when user starts dragging a gate."""
        lib = GateLibrary.instance()
        gd  = lib.get(gate_def_id)
        if gd and len(gd.roles) == 1:
            # Will be placed on drop — just set cursor
            self._placing_gate_id = gate_def_id
            self._placing_roles   = [gd.roles[0].name]
            self._placing_col     = None
            self._placing_done    = {}
        self.setCursor(Qt.CrossCursor)
        self.setFocus()
