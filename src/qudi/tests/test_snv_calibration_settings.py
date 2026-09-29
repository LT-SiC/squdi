"""Persistence and snapshot regression tests, without hardware or Qt."""
import ast
import json
from pathlib import Path
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))
from qudi.logic.transition_tracker_settings import SetupParameterStore


class SettingsTests(unittest.TestCase):
    def test_crc_repump_settings_migrate_and_persist(self):
        document = json.loads(self.path.read_text())
        del document["parameters"]["crc"]["repump_laser"]
        del document["parameters"]["crc"]["laser_power_repump_450"]
        self.path.write_text(json.dumps(document))
        store = SetupParameterStore(self.path)
        before = store.snapshot()
        self.assertEqual(before.crc.repump_laser, "Laser_520")
        store.update({"crc": {"repump_laser": "Laser_450", "laser_power_repump_450": 1234}})
        loaded = SetupParameterStore(self.path).snapshot()
        self.assertEqual(loaded.crc.repump_laser, "Laser_450")
        self.assertEqual(loaded.crc.laser_power_repump_450, 1234)
        self.assertEqual(before.crc.repump_laser, "Laser_520")
        for changes in ({"repump_laser": "Laser_620"}, {"laser_power_repump_450": -1}):
            with self.assertRaises(ValueError):
                store.update({"crc": changes})

    def test_threshold_link_persistence_and_snapshot_isolation(self):
        self.store.update({"ssr": {"init_threshold": 2, "threshold": 3},
                           "csr": {"csr_threshold": 9, "use_crc_threshold": True},
                           "crc": {"threshold": 12}})
        snapshot = self.store.snapshot()
        self.assertEqual(snapshot.csr.csr_threshold, 12)
        self.assertEqual(snapshot.to_dict()["csr"]["csr_threshold"], 9)
        restarted = SetupParameterStore(self.path)
        self.assertEqual(restarted.snapshot().ssr.init_threshold, 2)
        self.assertEqual(restarted.snapshot().ssr.threshold, 3)
        self.assertEqual(restarted.snapshot().csr.csr_threshold, 12)
        self.store.update({"crc": {"threshold": 15}})
        self.assertEqual(self.store.snapshot().csr.csr_threshold, 15)
        self.assertEqual(snapshot.csr.csr_threshold, 12)
        self.store.update({"csr": {"use_crc_threshold": False}})
        self.assertEqual(self.store.snapshot().csr.csr_threshold, 9)
        for changes in ({"ssr": {"threshold": -1}}, {"ssr": {"init_threshold": 1.5}},
                        {"csr": {"use_crc_threshold": 1}}):
            with self.assertRaises(ValueError):
                self.store.update(changes)

    def test_existing_settings_gain_threshold_defaults(self):
        document = json.loads(self.path.read_text())
        del document["parameters"]["ssr"]["threshold"]
        del document["parameters"]["ssr"]["init_threshold"]
        del document["parameters"]["csr"]["use_crc_threshold"]
        document["parameters"]["csr"]["csr_threshold"] = 13
        self.path.write_text(json.dumps(document))
        settings = SetupParameterStore(self.path).snapshot()
        self.assertEqual(settings.ssr.threshold, 1)
        self.assertEqual(settings.ssr.init_threshold, 1)
        self.assertFalse(settings.csr.use_crc_threshold)
        self.assertEqual(settings.csr.csr_threshold, 13)

    def test_qinu_analysis_uses_resolved_thresholds(self):
        snapshot = self.store.update({"ssr": {"init_threshold": 11, "threshold": 12},
                                      "csr": {"use_crc_threshold": True},
                                      "crc": {"threshold": 13}})
        nuclear = SimpleNamespace(setup_parameters=snapshot)
        common = SimpleNamespace(init=lambda op, threshold: ["init", op, threshold, 1, 0, 1],
                                 result=lambda op, threshold: ["result", op, threshold, 1, 0, 1])
        optical_results = {"ODMR_SnV.py", "ODMR_SnV_SMIQ.py", "optical_power_rabi.py",
                           "optical_puls_crosstalk_check.py", "align_b_field.py", "test_pulses.py"}
        checked = 0
        for path in (ROOT / "UserScripts/Qinu").glob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if not isinstance(node, ast.Assign) or not any(
                        isinstance(target, ast.Name) and target.id == "ana_seq" for target in node.targets):
                    continue
                rows = eval(compile(ast.Expression(node.value), str(path), "eval"),
                            {"nuclear": nuclear, "qinu_common": common})
                for row in rows:
                    if len(row) == 6 and row[0] == "init":
                        self.assertEqual(row[2], 11 if row[1] == "<" else 13, path.name)
                    elif row[0] == "result" and path.name not in optical_results:
                        self.assertEqual(row[2], 12, path.name)
                    elif len(row) == 7 and row[0] == "init":
                        self.assertEqual(row[2], 0, "Photon postselection must stay independent")
                checked += 1
        self.assertEqual(checked, 19)

    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.path = Path(folder.name, "setup_parameters.json")
        self.store = SetupParameterStore(self.path, initial_frequency_mhz=223.456)

    def test_migration_restart_and_snapshot_isolation(self):
        before = self.store.snapshot()
        self.assertEqual(before.electron.IQ_freq, 223456000)
        self.store.update({"electron": {"IQ_freq": 230000000}, "crc": {"threshold": 11}})
        restarted = SetupParameterStore(self.path, initial_frequency_mhz=111)
        self.assertEqual(restarted.snapshot().electron.IQ_freq, 230000000)
        self.assertEqual(before.crc.threshold, 7)
        group = restarted.snapshot().crc
        group.update(threshold="scan_key")
        self.assertEqual(restarted.snapshot().crc.threshold, 11)
        saved = self.path.parent / "run" / "setup_parameters.json"
        before.save(saved)
        self.assertEqual(json.loads(saved.read_text())["parameters"]["electron"]["IQ_freq"], 223456000)

    def test_invalid_edits_are_atomic(self):
        before = self.path.read_bytes()
        for changes in (
            {"crc": {"threshold": -1}}, {"electron": {"electron_rabi_period": 210}},
            {"electron": {"electron_rabi_opx_amp": 101}}, {"smiq": {"power_dbm": float("nan")}},
            {"crc": {"probe_len": "scan_key"}}, {"ple_refocus": {"do_green_repump": 1}},
            {"ssr": {"state": "-1.5"}}, {"unknown": {}}, {"crc": {"typo": 2}},
        ):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                self.store.update({"general": {"laser_power_A1": 30}, **changes})
            self.assertEqual(self.path.read_bytes(), before)
            self.assertEqual(self.store.snapshot().general.laser_power_A1, 25)

    def test_general_power_override_preserves_group_values_and_restarts(self):
        self.store.update({"general": {"laser_power_A1": 32, "laser_power_B2": 43},
                           "crc": {"laser_power_A1": 12}, "ssr": {"laser_power_B2": 16}})
        snapshot = self.store.snapshot()
        for group in ("crc", "csr", "ssr", "electron_init", "ple_refocus"):
            self.assertEqual(getattr(snapshot, group).laser_power_A1, 32)
            self.assertEqual(getattr(snapshot, group).laser_power_B2, 43)
        self.assertEqual(snapshot.to_dict()["crc"]["laser_power_A1"], 12)
        self.assertEqual(snapshot.crc.laser_power_repump, 100000)
        self.assertEqual(snapshot.optical_pi_pulse.laser_power, 50)
        self.store.update({"general": {"override_operation_powers": False}})
        restarted = SetupParameterStore(self.path).snapshot()
        self.assertEqual(restarted.crc.laser_power_A1, 12)
        self.assertEqual(restarted.ssr.laser_power_B2, 16)
        self.assertEqual(snapshot.crc.laser_power_A1, 32)

    def test_old_settings_enable_override_without_losing_values(self):
        old = self.store.snapshot().to_dict()
        del old["general"]["override_operation_powers"]
        old["csr"]["laser_power_A1"] = 19
        self.path.write_text(json.dumps({"version": 1, "parameters": old}), encoding="utf-8")
        migrated = SetupParameterStore(self.path)
        self.assertTrue(migrated.snapshot().general.override_operation_powers)
        self.assertEqual(migrated.snapshot().csr.laser_power_A1, 25)
        self.assertEqual(migrated.snapshot().to_dict()["csr"]["laser_power_A1"], 19)

    def test_failed_disk_write_keeps_previous_file_and_memory(self):
        before = self.path.read_bytes()
        with patch("qudi.logic.transition_tracker_settings.os.replace", side_effect=OSError("disk error")):
            with self.assertRaises(OSError):
                self.store.update({"crc": {"threshold": 9}})
        self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual(self.store.snapshot().crc.threshold, 7)
        self.assertEqual(list(self.path.parent.glob("*.tmp")), [])

    def test_corrupt_file_is_not_overwritten(self):
        self.path.write_text('{"version": 999}', encoding="utf-8")
        with self.assertRaises(ValueError):
            SetupParameterStore(self.path)
        self.assertEqual(self.path.read_text(), '{"version": 999}')

    def test_qinu_migration_syntax_and_no_stale_snippet_defaults(self):
        for path in (ROOT / "UserScripts/Qinu").glob("*.py"):
            with self.subTest(path=path.name):
                text = path.read_text(encoding="utf-8")
                tree = ast.parse(text, filename=str(path))
                for node in ast.walk(tree):
                    if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and node.value.id == "sna":
                        self.assertFalse(node.attr.endswith("_PARAMS") or node.attr.startswith("GENERAL_POWER"))
                if 'nuclear.queue = kwargs["queue"]' in text:
                    self.assertLess(text.index("nuclear.capture_setup_parameters()"), text.index("settings()", text.index("def run_fun")))

    def test_qinu_power_setup_is_outside_repeating_qua_loops(self):
        paths = list((ROOT / "UserScripts/Qinu").glob("*.py")) + [ROOT / "logic/snv_calibration_nops.py"]
        for path in paths:
            tree = ast.parse(path.read_text(encoding="utf-8"))
            parents = {child: parent for parent in ast.walk(tree) for child in ast.iter_child_nodes(parent)}
            startup, initialization = [], []
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
                    continue
                if node.func.attr == "init_program":
                    initialization.append(node)
                if node.func.attr == "setup_laser_powers":
                    startup.append(node)
                if node.func.attr in ("setup_laser_powers", "set_laser_power"):
                    parent = parents.get(node)
                    while parent is not None:
                        if isinstance(parent, ast.With):
                            for item in parent.items:
                                expr = item.context_expr
                                if isinstance(expr, ast.Call):
                                    name = getattr(expr.func, "id", getattr(expr.func, "attr", ""))
                                    self.assertNotIn(name, ("infinite_loop_", "for_", "for_each_", "while_"), f"Power write inside repeating loop: {path}:{node.lineno}")
                        parent = parents.get(parent)
                if isinstance(node.func.value, ast.Name) and node.func.value.id == "sna":
                    for keyword in node.keywords:
                        if keyword.arg == "set_laser_power":
                            self.assertIsInstance(keyword.value, ast.Constant)
                            self.assertFalse(keyword.value.value, f"Pulse-local power write: {path}:{node.lineno}")
            self.assertEqual(len(initialization), len(startup), str(path))


if __name__ == "__main__":
    unittest.main()
