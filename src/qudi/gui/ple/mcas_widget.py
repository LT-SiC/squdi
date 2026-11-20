
from PySide6 import QtCore, QtWidgets
import qudi.util.uic as uic
import os

class McasWidget(QtWidgets.QWidget):
    sig_mcas_params_updated = QtCore.Signal(dict)
    params = {}

    def __init__(self, name, *args, **kwargs):
        this_dir = os.path.dirname(__file__)
        ui_file = os.path.join(this_dir, 'mcas_widget.ui')
        super(McasWidget, self).__init__(*args, **kwargs)
        uic.loadUi(ui_file, self)

    def update_params(self):
        pass
    def update_gui(self, params):
        pass
    def set_constraints(self, constraints=None):
        pass


