"""Qudi logic module hosting the Spin Circuit Studio browser application."""
from __future__ import annotations

import copy
import threading

from PySide6 import QtCore

from qudi.core.configoption import ConfigOption
from qudi.core.module import LogicBase
from qudi.core.statusvariable import StatusVar

from .backend.circuit import normalize, qasm2
from .http_server import create_server


class SpinCircuitStudioLogic(LogicBase):
    """Serve the browser studio and publish generic OpenQASM updates."""

    _port = ConfigOption(name="port", default=8765, missing="nothing")

    circuit = StatusVar(name="circuit", default=None)
    openqasm_code = StatusVar(name="openqasm_code", default="")

    sigOpenQasmUpdated = QtCore.Signal(str, dict)

    def __init__(self, qudi_main_weakref, name, config=None, callbacks=None, **kwargs):
        super().__init__(
            qudi_main_weakref,
            name,
            config=config,
            callbacks=callbacks,
            **kwargs,
        )
        self._state_lock = threading.RLock()

    def on_activate(self) -> None:
        self._server = create_server(
            port=self._port,
            on_qasm_export=self._record_qasm,
            on_setup_export=self._log_setup_qasm,
        )
        self._server_thread = threading.Thread(
            target=self._server.serve_forever,
            kwargs={"poll_interval": 0.1},
            name="SpinCircuitStudioHTTPServer",
            daemon=True,
        )
        self._server_thread.start()
        if not self._server.wait_until_serving():
            self._server.server_close()
            self._server = None
            self._server_thread = None
            raise RuntimeError("Spin Circuit Studio HTTP server did not start")
        server_address = self._server.server_address
        address = server_address[0]
        port = server_address[1]
        self.server_url = f"http://{address}:{port}"
        self.log.info("Spin Circuit Studio available at %s", self.server_url)

    def on_deactivate(self) -> None:
        server = getattr(self, "_server", None)
        thread = getattr(self, "_server_thread", None)
        if server is None:
            return

        server.shutdown()
        server.server_close()
        if thread is not None:
            thread.join(timeout=10)
            if thread.is_alive():
                self.log.error("Spin Circuit Studio HTTP server did not stop within 10 seconds")
        self._server = None
        self._server_thread = None
        self.log.info("Spin Circuit Studio stopped")

    def _record_qasm(self, circuit: dict, code: str) -> None:
        normalized = copy.deepcopy(circuit)
        with self._state_lock:
            self.circuit = normalized
            self.openqasm_code = code
        self.sigOpenQasmUpdated.emit(code, copy.deepcopy(normalized))

    def _log_setup_qasm(self, code: str) -> None:
        print("%s", code)
        self.log.info("%s", code)

    def set_circuit(self, circuit: dict) -> str:
        """Normalize and publish a circuit supplied by another logic module."""
        normalized = normalize(circuit)
        code = qasm2(normalized)
        self._record_qasm(normalized, code)
        return code

    def get_circuit(self) -> dict | None:
        """Return a copy of the most recently exported normalized circuit."""
        with self._state_lock:
            return copy.deepcopy(self.circuit)

    def get_openqasm_code(self) -> str:
        """Return the most recently generated OpenQASM 2.0 source."""
        with self._state_lock:
            return self.openqasm_code

    def get_openqasm(self) -> str:
        """Compatibility alias for :meth:`get_openqasm_code`."""
        return self.get_openqasm_code()
