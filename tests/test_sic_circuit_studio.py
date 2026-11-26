"""Focused tests for the Qudi SiC Circuit Studio module and API."""
from __future__ import annotations

import json
import math
from pathlib import Path
import sys
import threading
import unittest
from urllib.error import URLError
from urllib.request import Request, urlopen

from PySide6 import QtCore

LOGIC_ROOT = Path(__file__).resolve().parents[1] / "src" / "qudi" / "logic"
sys.path.insert(0, str(LOGIC_ROOT))

from sic_circuit_studio.backend.circuit import export, normalize
from sic_circuit_studio.http_server import create_server
from sic_circuit_studio.sic_circuit_studio_logic import SicCircuitStudioLogic


class StudioBackendTests(unittest.TestCase):
    def test_qasm_export_normalizes_and_decomposes_ddrf(self):
        raw = {
            "qubits": 2,
            "columns": 3,
            "gates": [
                {
                    "type": "ddrf",
                    "row": 0,
                    "target": 1,
                    "col": 0,
                    "axis": "x",
                    "angle": math.pi / 2,
                    "sign": 1,
                }
            ],
        }

        circuit = normalize(raw)
        code = export(circuit, "qasm")

        self.assertEqual(circuit["version"], 2)
        self.assertEqual(circuit["gates"][0]["type"], "ddrf")
        self.assertIn("OPENQASM 2.0;", code)
        self.assertIn("rz(pi/2) q[1];", code)


class StudioHTTPTests(unittest.TestCase):
    def setUp(self):
        self.exports = []
        self.server = create_server(
            port=0,
            on_qasm_export=lambda circuit, code: self.exports.append((circuit, code)),
        )
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base_url = f"http://127.0.0.1:{self.server.server_address[1]}"
        self.assertEqual(self.server.server_address[0], "127.0.0.1")

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)

    def test_health_and_export_endpoint(self):
        with urlopen(self.base_url) as response:
            self.assertIn(b"SiC Circuit Studio", response.read())

        with urlopen(f"{self.base_url}/api/health") as response:
            health = json.load(response)
        self.assertTrue(health["ok"])
        self.assertFalse(health["hardware_connected"])

        request = Request(
            f"{self.base_url}/api/export",
            data=json.dumps(
                {"circuit": {"qubits": 1, "gates": [{"type": "h", "row": 0, "col": 0}]},
                 "format": "qasm"}
            ).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(request) as response:
            result = json.load(response)

        self.assertEqual(result["circuit"]["qubits"], 1)
        self.assertIn("h q[0];", result["code"])
        self.assertEqual(len(self.exports), 1)
        self.assertEqual(self.exports[0][0], result["circuit"])
        self.assertEqual(self.exports[0][1], result["code"])

    def test_only_qasm_exports_are_published(self):
        request = Request(
            f"{self.base_url}/api/export",
            data=json.dumps(
                {"circuit": {"qubits": 1, "gates": []}, "format": "qiskit"}
            ).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(request):
            pass
        self.assertEqual(self.exports, [])


class StudioLogicTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.qt_app = QtCore.QCoreApplication.instance() or QtCore.QCoreApplication([])

    def make_logic(self, port=0):
        return SicCircuitStudioLogic(None, "test_studio", config={"port": port})

    def test_activation_and_deactivation_control_server_lifecycle(self):
        logic = self.make_logic()
        logic.on_activate()
        url = logic.server_url

        with urlopen(f"{url}/api/health") as response:
            self.assertEqual(response.status, 200)

        logic.on_deactivate()
        with self.assertRaises(URLError):
            urlopen(f"{url}/api/health", timeout=1)

    def test_browser_qasm_export_emits_signal_and_updates_getters(self):
        logic = self.make_logic()
        updates = []
        logic.sigOpenQasmUpdated.connect(lambda code, circuit: updates.append((code, circuit)))
        raw = {"qubits": 1, "gates": [{"type": "h", "row": 0, "col": 0}]}
        logic.on_activate()
        try:
            request = Request(
                f"{logic.server_url}/api/export",
                data=json.dumps({"circuit": raw, "format": "qasm"}).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urlopen(request) as response:
                result = json.load(response)
            self.qt_app.processEvents()

            expected_circuit = normalize(raw)
            self.assertEqual(logic.get_openqasm_code(), result["code"])
            self.assertEqual(logic.get_openqasm(), result["code"])
            self.assertEqual(logic.get_circuit(), expected_circuit)
            self.assertEqual(updates, [(result["code"], expected_circuit)])
        finally:
            logic.on_deactivate()


if __name__ == "__main__":
    unittest.main()
