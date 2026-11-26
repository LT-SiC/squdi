"""
gui/code_panel.py
Live code preview panel with syntax highlighting and export button.
"""
import re
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTextEdit, QTabWidget, QFrame, QFileDialog, QSizePolicy
)
from PySide6.QtCore import Qt, pyqtSignal, QTimer
from PySide6.QtGui import (
    QFont, QColor, QSyntaxHighlighter, QTextCharFormat,
    QTextCursor
)

from models import CircuitDocument
from codegen import (
    generate_full_code, generate_circuit_code, generate_parameter_block
)


PANEL_STYLE = """
QWidget { background:#1A1D24; }
QTabWidget::pane { border:none; background:#0D0F14; }
QTabBar::tab {
    background:#141720; color:#555A66;
    padding:6px 14px; border:none;
    font-family:Consolas; font-size:11px;
}
QTabBar::tab:selected { color:#CDD1DB; border-bottom:2px solid #3A7FD4; }
QTabBar::tab:hover { color:#9AA0AC; }
QPushButton {
    background:#262A33; color:#9AA0AC;
    border:1px solid #2E3240; border-radius:3px;
    padding:4px 12px; font-family:Consolas; font-size:11px;
}
QPushButton:hover { background:#2E3240; color:#CDD1DB; }
QPushButton.export {
    background:#3A7FD4; color:white; border:none;
}
QPushButton.export:hover { background:#4A9FEA; }
"""


class PythonHighlighter(QSyntaxHighlighter):
    """Syntax highlighter tuned for generated experiment code."""

    def __init__(self, parent):
        super().__init__(parent)
        self._rules = []  # type: list

        def fmt(color, bold=False, italic=False) -> QTextCharFormat:
            f = QTextCharFormat()
            f.setForeground(QColor(color))
            if bold:
                f.setFontWeight(700)
            if italic:
                f.setFontItalic(True)
            return f

        kw = fmt("#C792EA", bold=True)
        for kw_word in ["for", "in", "if", "else", "def", "return",
                        "import", "from", "as", "pass", "with", "class"]:
            self._rules.append((rf"\b{kw_word}\b", kw))

        self._rules.append((r'"[^"]*"', fmt("#C3E88D")))
        self._rules.append((r"'[^']*'", fmt("#C3E88D")))
        self._rules.append((r"\b\d+\.?\d*\b", fmt("#F78C6C")))
        self._rules.append((r"#[^\n]*", fmt("#546E7A", italic=True)))
        self._rules.append((r"\b\w+(?=\()", fmt("#82AAFF")))
        self._rules.append((r"_I_\[", fmt("#F0A500", bold=True)))
        self._rules.append((r"nuclear\.parameters", fmt("#F0A500", bold=True)))

    def highlightBlock(self, text: str):
        for pattern, fmt in self._rules:
            for m in re.finditer(pattern, text):
                self.setFormat(m.start(), m.end() - m.start(), fmt)


def _make_editor() -> QTextEdit:
    ed = QTextEdit()
    ed.setReadOnly(True)
    ed.setFont(QFont("Consolas", 11))
    ed.setStyleSheet("""
        QTextEdit {
            background:#0D0F14; color:#CDD1DB;
            border:none; padding:8px;
        }
    """)
    return ed


class CodePanel(QWidget):
    """Tabbed live code output panel."""

    def __init__(self, doc: CircuitDocument, parent=None):
        super().__init__(parent)
        self.doc = doc
        self.setStyleSheet(PANEL_STYLE)
        self._debounce = QTimer()
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(300)
        self._debounce.timeout.connect(self._refresh)
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
        hlay.setContentsMargins(10, 6, 10, 6)
        title = QLabel("Generated Code")
        title.setStyleSheet("color:#E8EAF0; font-size:12px; font-weight:bold; font-family:Consolas;")
        hlay.addWidget(title)
        hlay.addStretch()
        self.export_btn = QPushButton("⬇  Export .py")
        self.export_btn.setStyleSheet("""
            background:#3A7FD4; color:white; border:none;
            border-radius:3px; padding:4px 12px;
            font-family:Consolas; font-size:11px;
        """)
        self.export_btn.clicked.connect(self._export)
        hlay.addWidget(self.export_btn)
        layout.addWidget(header)

        # Tabs
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)

        # Full output
        self.full_editor = _make_editor()
        PythonHighlighter(self.full_editor.document())
        self.tabs.addTab(self.full_editor, "Full output")

        # Circuit only
        self.circuit_editor = _make_editor()
        PythonHighlighter(self.circuit_editor.document())
        self.tabs.addTab(self.circuit_editor, "Circuit body")

        # Parameters only
        self.params_editor = _make_editor()
        PythonHighlighter(self.params_editor.document())
        self.tabs.addTab(self.params_editor, "Parameters")

    def _refresh(self):
        try:
            full = generate_full_code(self.doc)
            circ = generate_circuit_code(self.doc, indent="    ")
            params = generate_parameter_block(self.doc)
        except Exception as e:
            full = circ = params = f"# Error generating code:\n# {e}"

        self.full_editor.setPlainText(full)
        self.circuit_editor.setPlainText(circ)
        self.params_editor.setPlainText(params)

    def schedule_refresh(self):
        """Debounced refresh — call on any circuit change."""
        self._debounce.start()

    def _export(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "Export Python script", "", "Python files (*.py)"
        )
        if path:
            if not path.endswith(".py"):
                path += ".py"
            try:
                code = generate_full_code(self.doc)
                with open(path, "w", encoding="utf-8") as f:
                    f.write(code)
            except Exception as e:
                from PyQt5.QtWidgets import QMessageBox
                QMessageBox.critical(self, "Export failed", str(e))

    def set_document(self, doc: CircuitDocument):
        self.doc = doc
        self._refresh()
