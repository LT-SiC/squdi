"""
code_sections_dialog.py - Tabbed editor for all fixed/editable code sections.
Python 3.6+ compatible.

Tabs:
  Preamble          (no indent in output)
  Fixed middle      (no indent in output)
  Pre-parameters    (no indent - opens the OrderedDict call)
  Post-parameters   (no indent - closes the OrderedDict call)
  Fixed end         (no indent in output)

Hint labels show the indentation context for each section.
"""
import re
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QTabWidget,
    QTextEdit, QPushButton, QLabel, QWidget, QFrame
)
from PySide6.QtCore import Signal
from PySide6.QtGui import QFont, QColor, QSyntaxHighlighter, QTextCharFormat

from models import (CircuitDocument,
                    DEFAULT_PREAMBLE, DEFAULT_FIXED_MIDDLE,
                    DEFAULT_PRE_PARAMS, DEFAULT_POST_PARAMS,
                    DEFAULT_FIXED_END)


class _PyHighlighter(QSyntaxHighlighter):
    def __init__(self, parent):
        super(_PyHighlighter, self).__init__(parent)
        def f(col, bold=False):
            fmt = QTextCharFormat()
            fmt.setForeground(QColor(col))
            if bold:
                fmt.setFontWeight(700)
            return fmt
        self._rules = [
            (r'\b(?:for|in|if|else|def|return|import|from|as|pass|while|'
             r'with|class|try|except|finally|yield|lambda|not|and|or|'
             r'True|False|None)\b', f("#C792EA", True)),
            (r'"[^"]*"',        f("#C3E88D")),
            (r"'[^']*'",        f("#C3E88D")),
            (r'\b\d+\.?\d*\b', f("#F78C6C")),
            (r'#[^\n]*',        f("#546E7A")),
            (r'\b\w+(?=\()',    f("#82AAFF")),
        ]

    def highlightBlock(self, text):
        for pattern, fmt in self._rules:
            for m in re.finditer(pattern, text):
                self.setFormat(m.start(), m.end() - m.start(), fmt)


def _make_editor(text):
    ed = QTextEdit()
    ed.setFont(QFont("Consolas", 11))
    ed.setPlainText(text)
    ed.setStyleSheet(
        "QTextEdit{background:#0D0F14;color:#CDD1DB;border:none;padding:8px;}")
    _PyHighlighter(ed.document())
    return ed


DIALOG_STYLE = """
QDialog{background:#1E2128;color:#CDD1DB;}
QTabWidget::pane{border:none;background:#0D0F14;}
QTabBar::tab{background:#141720;color:#555A66;
    padding:6px 14px;border:none;font-family:Consolas;font-size:11px;}
QTabBar::tab:selected{color:#CDD1DB;border-bottom:2px solid #3A7FD4;}
QPushButton{background:#262A33;color:#CDD1DB;
    border:1px solid #3A3F4B;border-radius:4px;padding:5px 12px;}
QPushButton:hover{background:#2E3240;}
QLabel{color:#3A6090;font-size:9px;padding:3px 8px;}
"""

# (label, attr, hint, indent_note)
_SECTIONS = [
    ("Preamble",
     "preamble",
     "Runs before the circuit. No indentation applied.",
     "Output indent: none"),

    ("Fixed middle",
     "fixed_middle",
     "Runs after the circuit sequence (e.g. run_experiment call). No indentation.",
     "Output indent: none"),

    ("Pre-parameters",
     "pre_parameters",
     "Opens the OrderedDict/parameter block. "
     "Typically ends with the opening '(' of OrderedDict.",
     "Output indent: none  |  Next block (params) is at 2 tabs"),

    ("Post-parameters",
     "post_parameters",
     "Closes the OrderedDict/parameter block. "
     "Typically '    )\\n)\\n' to close the dict.",
     "Output indent: none  |  Follows the parameter entries"),

    ("Fixed end",
     "fixed_end",
     "Final section after all parameters (save results, close devices, etc.).",
     "Output indent: none"),
]


class CodeSectionsDialog(QDialog):
    """Modal dialog to edit all fixed code sections of a CircuitDocument."""
    sections_changed = Signal()

    def __init__(self, doc, parent=None):
        super(CodeSectionsDialog, self).__init__(parent)
        self.doc = doc
        self.setWindowTitle("Edit code sections")
        self.setStyleSheet(DIALOG_STYLE)
        self.resize(820, 560)
        self._editors = {}  # type: dict
        self._setup_ui()

    def _setup_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 8)

        header = QLabel(
            "  Edit the fixed code sections. "
            "Changes apply when you click Apply. "
            "Indentation notes are shown per tab.")
        header.setStyleSheet("color:#3A6090;font-size:10px;padding:6px 10px;")
        root.addWidget(header)

        self.tabs = QTabWidget()
        root.addWidget(self.tabs, 1)

        for label, attr, hint, indent_note in _SECTIONS:
            tab = QWidget()
            tl = QVBoxLayout(tab)
            tl.setContentsMargins(0, 0, 0, 0)
            tl.setSpacing(0)

            # Hint row
            hint_frame = QFrame()
            hint_frame.setStyleSheet(
                "QFrame{background:#141720;border-bottom:1px solid #2E3240;}")
            hlay = QHBoxLayout(hint_frame)
            hlay.setContentsMargins(8, 4, 8, 4)
            h1 = QLabel(hint)
            h1.setWordWrap(True)
            hlay.addWidget(h1, 1)
            h2 = QLabel(indent_note)
            h2.setStyleSheet("color:#F0A500;font-size:9px;")
            hlay.addWidget(h2)
            tl.addWidget(hint_frame)

            ed = _make_editor(getattr(self.doc, attr, ""))
            tl.addWidget(ed)
            self.tabs.addTab(tab, label)
            self._editors[attr] = ed

        # Buttons
        brow = QHBoxLayout()
        brow.setContentsMargins(10, 4, 10, 0)
        brow.addStretch()

        reset_btn = QPushButton("Reset to defaults")
        reset_btn.setToolTip("Restore all sections to their default values")
        reset_btn.clicked.connect(self._reset_defaults)
        brow.addWidget(reset_btn)

        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        brow.addWidget(cancel)

        apply = QPushButton("Apply")
        apply.setStyleSheet(
            "background:#3A7FD4;color:white;border:none;"
            "padding:6px 18px;border-radius:4px;")
        apply.clicked.connect(self._apply)
        brow.addWidget(apply)

        root.addLayout(brow)

    def _apply(self):
        for attr, ed in self._editors.items():
            setattr(self.doc, attr, ed.toPlainText())
        self.sections_changed.emit()
        self.accept()

    def _reset_defaults(self):
        defaults = {
            "preamble":        DEFAULT_PREAMBLE,
            "fixed_middle":    DEFAULT_FIXED_MIDDLE,
            "pre_parameters":  DEFAULT_PRE_PARAMS,
            "post_parameters": DEFAULT_POST_PARAMS,
            "fixed_end":       DEFAULT_FIXED_END,
        }
        for attr, ed in self._editors.items():
            if attr in defaults:
                ed.setPlainText(defaults[attr])
