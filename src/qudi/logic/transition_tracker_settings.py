"""Persistent OPX setup settings owned by TransitionTracker (no hardware imports)."""
import copy
import json
import math
import os
import tempfile
import threading
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace


@dataclass(frozen=True)
class Setting:
    default: object
    unit: str = ""
    minimum: float = 0
    maximum: float = 2_147_483_647
    step: int = 0
    choices: tuple = ()
    description: str = ""


def ns(value, minimum=20, step=4):
    return Setting(value, "ns", minimum, step=step)


def power(value):
    return Setting(float(value), "nW")


# These are migration seeds, not another runtime source of settings. Values
# from setup_parameters.json take precedence on every subsequent activation.
SCHEMA = {
    "general": {
        "override_operation_powers": Setting(True, description=(
            "Use general A1/B2 powers for CRC, CSR, SSR, electron initialization and PLE refocus. "
            "Stored group values are retained. Repump and optical-pi powers are separate.")),
        "laser_power_A1": power(25), "laser_power_B2": power(25),
        "pause_after_power": ns(1000), "tt_trigger_length": ns(20),
    },
    "smiq": {
        "frequency_ghz": Setting(4.0, "GHz", 0.000001, 100),
        "power_dbm": Setting(-14.0, "dBm", -150, 30),
        "frequency_tolerance_hz": Setting(1.0, "Hz"),
        "power_tolerance_dbm": Setting(0.01, "dBm"),
    },
    "electron": {
        "IQ_freq": Setting(221_100_000, "Hz", 1, 500_000_000),
        "electron_rabi_period": ns(208, minimum=80, step=16),
        "electron_rabi_opx_amp": Setting(100.0, "%", 0.000001, 100),
    },
    "crc": {
        "laser_power_A1": power(25), "laser_power_B2": power(25),
        "repump_laser": Setting("Laser_520", choices=("Laser_520", "Laser_450"),
                                description="Laser used for CRC repumping below threshold_repump."),
        "laser_power_repump": power(100_000),
        "laser_power_repump_450": Setting(0.0, "nW", description="450 nm CRC repump power. Set the desired power before selecting Laser_450."),
        "probe_len": ns(200_000), "repump_len": ns(100_000),
        "threshold": Setting(7, "counts"), "threshold_repump": Setting(2, "counts"),
        "wait_before_repump": ns(200), "wait_after_repump": ns(200),
        "max_attempts": Setting(1000, "", 1),
        "SPCM_channel": Setting("SPCM1", choices=("SPCM1", "SPCM2")),
    },
    "csr": {
        "duration": ns(200_000), "laser_power_A1": power(25),
        "laser_power_B2": power(25),
        "csr_threshold": Setting(7, "counts", description="CSR postselection threshold used when Use CRC threshold is unchecked."),
        "use_crc_threshold": Setting(False, description="Use crc.threshold for CSR postselection; retain the independent CSR value."),
    },
    "ssr": {
        "threshold": Setting(1, "counts", description="Final SSR readout analysis threshold."),
        "init_threshold": Setting(1, "counts", description="Postselection threshold for the SSR check after electron initialization."),
        "state": Setting("e1", choices=("e1", "e2")),
        "duration": ns(400_000), "laser_power_A1": power(25), "laser_power_B2": power(25),
    },
    "electron_init": {
        "state": Setting("e1", choices=("e1", "e2")),
        "duration": ns(600_000), "laser_power_A1": power(25), "laser_power_B2": power(25),
    },
    "ple_refocus": {
        "use_gui_powers": Setting(False), "do_green_repump": Setting(True),
        "laser_power_A1": power(25), "laser_power_B2": power(25),
        "laser_power_repump": power(10_000),
    },
    "optical_pi_pulse": {
        # Retain the public helper's historical spelling and effective defaults.
        "couting_duration": ns(16, minimum=4),
        "laser_power": power(50), "pulse_duration": ns(50, step=0),
    },
}


def validate(group, name, value):
    spec = SCHEMA[group][name]
    label = f"{group}.{name}"
    if spec.choices:
        if value not in spec.choices:
            raise ValueError(f"{label}: choose one of {spec.choices}")
    elif isinstance(spec.default, bool):
        if type(value) is not bool:
            raise ValueError(f"{label}: expected a boolean")
    else:
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            raise ValueError(f"{label}: expected a finite number")
        if not spec.minimum <= value <= spec.maximum:
            raise ValueError(f"{label}: must be between {spec.minimum} and {spec.maximum} {spec.unit}")
        if isinstance(spec.default, int):
            if value != int(value):
                raise ValueError(f"{label}: expected an integer")
            value = int(value)
        if spec.step and value % spec.step:
            raise ValueError(f"{label}: must be a multiple of {spec.step} {spec.unit}")
    return value


class ParameterValues(SimpleNamespace):
    def update(self, **overrides):
        """Allow scan keys/QUA values only as explicit call-local overrides."""
        for name, value in overrides.items():
            if name not in vars(self):
                raise KeyError(name)
            if value is not None:
                setattr(self, name, value)
        return self


class SetupSnapshot:
    """Detached snapshot; group access returns copies, never mutable live state."""
    def __init__(self, values):
        self._values = copy.deepcopy(values)

    def __getattr__(self, group):
        if group not in self._values:
            raise AttributeError(group)
        values = copy.deepcopy(self._values[group])
        if group == "csr" and values.get("use_crc_threshold", False):
            values["csr_threshold"] = self._values["crc"]["threshold"]
        general = self._values["general"]
        if group != "general" and general.get("override_operation_powers", True):
            for name in ("laser_power_A1", "laser_power_B2"):
                if name in values:
                    values[name] = general[name]
        return ParameterValues(**values)

    def to_dict(self):
        return copy.deepcopy(self._values)

    def save(self, path):
        atomic_json(path, {"version": 1, "parameters": self.to_dict()})


def atomic_json(path, payload):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                         prefix=path.name + ".", suffix=".tmp", delete=False) as stream:
            temporary = stream.name
            json.dump(payload, stream, indent=2, ensure_ascii=False, allow_nan=False)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary and os.path.exists(temporary):
            os.unlink(temporary)


class SetupParameterStore:
    def __init__(self, path, initial_frequency_mhz=221.1):
        self.path = Path(path)
        self._lock = threading.RLock()
        self._values = {g: {k: s.default for k, s in fields.items()} for g, fields in SCHEMA.items()}
        self._values["electron"]["IQ_freq"] = validate("electron", "IQ_freq", round(initial_frequency_mhz * 1e6))
        if self.path.exists():
            with self.path.open(encoding="utf-8") as stream:
                document = json.load(stream)
            if document.get("version") != 1:
                raise ValueError(f"Unsupported setup parameter version in {self.path}")
            self._values = self._merged(document["parameters"])
        else:
            self.snapshot().save(self.path)

    def _merged(self, changes):
        result = copy.deepcopy(self._values)
        for group, fields in changes.items():
            if group not in SCHEMA:
                raise ValueError(f"Unknown setup parameter group: {group}")
            for name, value in fields.items():
                if name not in SCHEMA[group]:
                    raise ValueError(f"Unknown setup parameter: {group}.{name}")
                result[group][name] = validate(group, name, value)
        return result

    def snapshot(self):
        with self._lock:
            return SetupSnapshot(self._values)

    def update(self, changes):
        with self._lock:
            values = self._merged(changes)
            SetupSnapshot(values).save(self.path)
            self._values = values
            return self.snapshot()
