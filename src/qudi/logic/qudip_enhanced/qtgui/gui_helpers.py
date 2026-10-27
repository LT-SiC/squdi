# coding=utf-8
from __future__ import print_function, absolute_import, division
__metaclass__ = type

import traceback
import sys
import os

import subprocess
import xml.etree.ElementTree as ET

import PySide6.QtWidgets
import PySide6.QtCore
from PySide6 import QtUiTools

from PySide6.QtWidgets import QApplication

from . import custom_widgets

# # Check if an application already exists
# app = QApplication.instance()
# if app is None:
#     app = QApplication(sys.argv)

def compile_ui_file(ui_filepath):
    # PySide6 has no uic.compileUi(); use the pyside6-uic command line tool instead
    name = os.path.basename(ui_filepath).split('.')[0] + '.py'
    py_filepath = os.path.join(os.path.dirname(ui_filepath), name)
    subprocess.run(['pyside6-uic', ui_filepath, '-o', py_filepath], check=True)


# Custom widgets used in the .ui files (promoted widgets), by class name.
_CUSTOM_WIDGETS = {
    name: cls for name, cls in vars(custom_widgets).items()
    if isinstance(cls, type)
    and issubclass(cls, PySide6.QtWidgets.QWidget)
    and cls.__module__ == custom_widgets.__name__
}


class _UiLoader(QtUiTools.QUiLoader):
    """
    PySide6 replacement for PyQt5.uic.loadUi(ui_file, baseinstance):
    builds the .ui into an existing widget and makes every named child available as an attribute of it.
    Promoted widgets are created directly from custom_widgets, so the <header> entry of the .ui file is not used.
    """

    def __init__(self, baseinstance, custom_widgets=None, toplevel=None):
        super().__init__()
        self.baseinstance = baseinstance
        # widget that is used as the top-level widget of the .ui (default: the baseinstance itself)
        self.toplevel = baseinstance if toplevel is None else toplevel
        self.custom_widgets = custom_widgets or {}
        for cls in self.custom_widgets.values():
            self.registerCustomWidget(cls)

    def _register(self, obj, name):
        if self.baseinstance is not None and name:
            setattr(self.baseinstance, name, obj)
        return obj

    def createWidget(self, class_name, parent=None, name=''):
        if parent is None and self.toplevel is not None:
            return self.toplevel  # the top-level widget of the .ui
        if class_name in self.custom_widgets:
            widget = self.custom_widgets[class_name](parent)
            widget.setObjectName(name)
        else:
            widget = super().createWidget(class_name, parent, name)
        return self._register(widget, name)

    def createLayout(self, class_name, parent=None, name=''):
        return self._register(super().createLayout(class_name, parent, name), name)

    def createAction(self, parent=None, name=''):
        return self._register(super().createAction(parent, name), name)

    def createActionGroup(self, parent=None, name=''):
        return self._register(super().createActionGroup(parent, name), name)


def load_ui(ui_filepath, baseinstance=None):
    """
    Build a .ui file into ``baseinstance`` (PySide6 replacement for PyQt5.uic.loadUi(ui_filepath, baseinstance)).

    If the root widget of the .ui is a plain QWidget (with a layout) but baseinstance is a QMainWindow, the
    layout can not be installed on the main window (Qt refuses and would drop the whole content). The content is
    then built into a separate widget, which becomes the central widget of the main window.
    """
    root = ET.parse(ui_filepath).getroot().find('widget')
    root_name = root.get('name')
    names = [e.get('name') for e in root.iter() if e.tag in ('widget', 'layout', 'action') and e.get('name')]

    toplevel = baseinstance
    use_container = (isinstance(baseinstance, PySide6.QtWidgets.QMainWindow)
                     and root.get('class') != 'QMainWindow')
    if use_container:
        toplevel = PySide6.QtWidgets.QWidget()

    loader = _UiLoader(baseinstance, _CUSTOM_WIDGETS, toplevel=toplevel)
    loader.setWorkingDirectory(PySide6.QtCore.QDir(os.path.dirname(os.path.abspath(ui_filepath))))
    ui_file = PySide6.QtCore.QFile(ui_filepath)
    if not ui_file.open(PySide6.QtCore.QIODevice.OpenModeFlag.ReadOnly):
        raise IOError('Cannot open ui file {}'.format(ui_filepath))
    try:
        widget = loader.load(ui_file)
    finally:
        ui_file.close()
    if widget is None:
        raise RuntimeError('Could not load {}: {}'.format(ui_filepath, loader.errorString()))

    if use_container:
        baseinstance.setCentralWidget(toplevel)
        if toplevel.windowTitle():
            baseinstance.setWindowTitle(toplevel.windowTitle())
        baseinstance.resize(toplevel.size())

    if baseinstance is not None:
        missing = [n for n in names if n != root_name and not hasattr(baseinstance, n)]
        if missing:
            print('Warning: {} was loaded, but these named objects were not created: {}'.format(
                os.path.basename(ui_filepath), missing))
    return widget


class WithQt:

    def __init__(self, parent=None, gui=None, QtGuiClass=None, **kwargs):
        super(WithQt, self).__init__()
        if gui:
            self.QtGuiClass = QtGuiClass
            self.init_gui(parent)
            self.gui.show()

    def init_gui(self, parent=None):
        self._gui = self.QtGuiClass(no_qt=self, parent=parent)

    @property
    def window_title(self):
        try:
            return self._window_title
        except:
            exc_type, exc_value, exc_tb = sys.exc_info()
            traceback.print_exception(exc_type, exc_value, exc_tb)

    def update_window_title(self, val):
        try:
            self._window_title = str(val)
            if hasattr(self, '_gui'):
                self.gui.update_window_title(self.window_title)
        except:
            exc_type, exc_value, exc_tb = sys.exc_info()
            traceback.print_exception(exc_type, exc_value, exc_tb)

    @property
    def gui(self):
        try:
            return self._gui
        except:
            exc_type, exc_value, exc_tb = sys.exc_info()
            traceback.print_exception(exc_type, exc_value, exc_tb)


class QtGuiClass(PySide6.QtWidgets.QMainWindow):
    clear_signal = PySide6.QtCore.Signal()
    show_signal = PySide6.QtCore.Signal()
    close_signal = PySide6.QtCore.Signal()
    update_window_title_signal = PySide6.QtCore.Signal(str)

    def __init__(self, parent=None, no_qt=None, ui_filepath=None):
        super(QtGuiClass, self).__init__(parent=parent)
        self.no_qt = no_qt
        self.ui_filepath = ui_filepath

        load_ui(self.ui_filepath, self)
        # It was working! But not connected to the Fields...
        # widget = PySide6.QtWidgets.QWidget()
        #load_ui(self.ui_filepath, widget)
        #self.setCentralWidget(widget)
        #self.setCentralWidget(self.parameter_tab)
        self.init_gui()


    def init_gui(self):
        for name in [
            'clear',
            'update_window_title',
        ]:
            getattr(getattr(self, "{}_signal".format(name)), 'connect')(getattr(self, "{}_signal_emitted".format(name)))

        self.show_signal.connect(self.show)
        self.close_signal.connect(self.close)

    def clear(self):
        self.clear_signal.emit()

    def show_gui(self):
        self.show_signal.emit()

    def close_gui(self):
        self.close_signal.emit()

    def update_window_title(self, val):
        self.update_window_title_signal.emit(val)

    def update_window_title_signal_emitted(self, val):
        self.setWindowTitle(val)