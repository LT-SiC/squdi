"""
library.py — Global gate library, persisted to ~/.quantum_composer/gates.json
"""
import json, os
from typing import Dict, List, Optional
from models import GateDefinition, GateArg, QubitRole

LIBRARY_PATH = os.path.expanduser("~/.quantum_composer/gates.json")


def _default_gates() -> List[GateDefinition]:
    gates = []

    def single(name, color, template, desc="", args=None, symbol=""):
        g = GateDefinition()
        g.name = name; g.display_color = color; g.description = desc
        g.code_template = template; g.gate_symbol = symbol
        g.roles = [QubitRole("qubit", "Target qubit")]
        g.args = args or []
        g.is_global = True
        return g

    # ── Standard single-qubit ────────────────────────────────────────────────
    gates.append(single("e_init", "#5B8DD9",
        'sna.electron_init({state}, max_power, _I_["init_power"])',
        "Electron initialisation",
        args=[GateArg("state", '_I_["state"]')], symbol="I"))

    gates.append(single("SSR_nuc_init", "#6DAF6D",
        'sna.ssr({freqs}, {read_dur}, n_ssr=_I_["n_ssr1"])',
        "Single-shot readout — nuclear init",
        args=[GateArg("freqs", "nuc_freqs"), GateArg("read_dur", "1024")], symbol="R"))

    gates.append(single("SSR_on_nuc", "#4A9A6A",
        'sna.ssr({freqs}, {read_dur}, n_ssr=_I_["n_ssr2"])',
        "Single-shot readout — readout",
        args=[GateArg("freqs", "nuc_freqs"), GateArg("read_dur", "1024")], symbol="R"))

    gates.append(single("CRC", "#B05FD4",
        "sna.crc({dur})", "Charge resonance check",
        args=[GateArg("dur", "100")], symbol="C"))

    gates.append(single("MW_pulse", "#D9A25B",
        "mw_pulse({freq}, {dur}, {amp}, {phase})",
        "Microwave pulse on electron",
        args=[GateArg("freq", "mw_freq"), GateArg("dur", '_I_["mw_dur"]'),
              GateArg("amp", '_I_["mw_amp"]'), GateArg("phase", "0")], symbol="μW"))

    gates.append(single("rabi_on_nuc", "#D97A5B",
        'rf_pulse({freq}, _I_["rf_dur_rabi"], _I_["rf_amp_rabi"], {phase})',
        "RF Rabi pulse on nuclear spin",
        args=[GateArg("freq", "nuc_freq"), GateArg("phase", "0")], symbol="RF"))

    # ── Unconditional DDRF ───────────────────────────────────────────────────
    ddrf1 = single("DDRF", "#E8A020",
        'ddrf({seq}, {freq}, {dur}, {amp}, {phase}, qubits={qubits})',
        "Unconditional dynamical decoupling RF pulse",
        args=[GateArg("seq", '"xy4"'), GateArg("freq", "nuc_freq"),
              GateArg("dur", '_I_["ddrf_dur"]'), GateArg("amp", '_I_["ddrf_amp"]'),
              GateArg("phase", "0")], symbol="DD")
    gates.append(ddrf1)

    # ── Custom code ──────────────────────────────────────────────────────────
    custom = single("Custom", "#607080",
        "{code}",
        "Arbitrary custom code snippet",
        args=[GateArg("code", "# write your code here")], symbol="?")
    gates.append(custom)

    # ── Rotation gates ───────────────────────────────────────────────────────
    for axis, color in [("X", "#E05050"), ("Y", "#50C050"), ("Z", "#5080E0")]:
        g = single(f"R{axis}", color,
            f"rotate_{axis.lower()}({{qubit}}, {{theta}})",
            f"Rotation around {axis}-axis",
            args=[GateArg("theta", "3.14159/2")],
            symbol=f"R{axis}")
        g.rotation_axis = axis
        # Use "theta" as arg name, but the icon will show the live value (3.14159/2 → π/2)
        g.rotation_angle_arg = "theta"
        gates.append(g)

    # Conditional rotation
    for axis, color in [("X", "#C03030"), ("Y", "#309030"), ("Z", "#3060C0")]:
        g = GateDefinition()
        g.name = f"CR{axis}"
        g.display_color = color
        g.description = f"Conditional rotation around {axis}-axis"
        g.gate_symbol = f"R{axis}"
        g.rotation_axis = axis
        g.rotation_angle_arg = "theta"
        g.roles = [
            QubitRole("control", "Control qubit", is_control=True, control_color="#FFFFFF"),
            QubitRole("target", "Target qubit"),
        ]
        g.args = [GateArg("theta", "3.14159/2"), GateArg("phi", "0")]
        g.code_template = (f"cond_rotate_{axis.lower()}({{control}}, {{target}}, "
                           f"theta={{theta}}, phi={{phi}}, qubits={{qubits}})")
        g.is_global = True
        gates.append(g)

    # ── Two-qubit: CeNot_n ───────────────────────────────────────────────────
    g = GateDefinition()
    g.name = "CeNot_n"; g.display_color = "#C0392B"; g.gate_symbol = "X"
    g.roles = [
        QubitRole("electron", "Electron (control)", is_control=True, control_color="#7EB8F7"),
        QubitRole("nuclear",  "Nuclear spin (target)"),
    ]
    g.args = [GateArg("si1_freq", "si1_freq"),
              GateArg("freq1", "nuc_freq"),
              GateArg("amp1", '_I_["rf_amp_rabi"]'),
              GateArg("dur1", '_I_["rf_dur_rabi"]'),
              GateArg("phase", "0")]
    g.code_template = ("rf_pulse({si1_freq}, qubits={qubits}) if {nuclear} == 'Si1' "
                       "else rf_pulse({freq1}, amp={amp1}, dur={dur1}, phase={phase}, qubits={qubits})")
    g.description = "Controlled-NOT: electron controls nuclear"
    g.is_global = True
    gates.append(g)

    # ── Two-qubit: CnNot_e ───────────────────────────────────────────────────
    g = GateDefinition()
    g.name = "CnNot_e"; g.display_color = "#A93226"; g.gate_symbol = "X"
    g.roles = [
        QubitRole("nuclear",  "Nuclear spin (control)", is_control=True, control_color="#6DAF6D"),
        QubitRole("electron", "Electron (target)"),
    ]
    g.args = [GateArg("amp", '_I_["cnot_amp"]'),
              GateArg("pi_dur", '_I_["pi_dur"]'),
              GateArg("transition", '"low"')]
    g.code_template = "cnot({amp}, {pi_dur}, trans[{transition}], qubits={qubits})"
    g.description = "Controlled-NOT: nuclear spin controls electron"
    g.is_global = True
    gates.append(g)

    # ── Two-qubit: Conditional DDRF ──────────────────────────────────────────
    g = GateDefinition()
    g.name = "Cond_DDRF"; g.display_color = "#C87820"; g.gate_symbol = "DD"
    g.roles = [
        QubitRole("control", "Control qubit", is_control=True, control_color="#E8A020"),
        QubitRole("target",  "Target qubit"),
    ]
    g.args = [GateArg("seq", '"xy4"'), GateArg("freq", "nuc_freq"),
              GateArg("dur", '_I_["ddrf_dur"]'), GateArg("amp", '_I_["ddrf_amp"]'),
              GateArg("phase", "0"), GateArg("condition", '"ms=+1"')]
    g.code_template = ('cond_ddrf({control}, {target}, {seq}, {freq}, {dur}, '
                       '{amp}, {phase}, condition={condition}, qubits={qubits})')
    g.description = "Conditional dynamical decoupling RF pulse"
    g.is_global = True
    gates.append(g)

    return gates


class GateLibrary:
    _instance: Optional["GateLibrary"] = None
    # last-used arg values per gate id: {gate_id: {arg_name: value}}
    _last_used: Dict[str, Dict[str, str]] = {}

    def __init__(self):
        self._gates: Dict[str, GateDefinition] = {}
        self._load()

    @classmethod
    def instance(cls) -> "GateLibrary":
        if cls._instance is None:
            cls._instance = GateLibrary()
        return cls._instance

    @classmethod
    def reset(cls):
        cls._instance = None

    def _load(self):
        if os.path.exists(LIBRARY_PATH):
            try:
                with open(LIBRARY_PATH, "r", encoding="utf-8") as f:
                    data = json.load(f)
                for d in data:
                    g = GateDefinition.from_dict(d)
                    self._gates[g.id] = g
                return
            except Exception:
                pass
        for g in _default_gates():
            self._gates[g.id] = g
        self.save()

    def save(self):
        os.makedirs(os.path.dirname(LIBRARY_PATH), exist_ok=True)
        with open(LIBRARY_PATH, "w", encoding="utf-8") as f:
            json.dump([g.to_dict() for g in self._gates.values()], f, indent=2)

    def all_gates(self) -> List[GateDefinition]:
        return list(self._gates.values())

    def get(self, gate_id: str) -> Optional[GateDefinition]:
        return self._gates.get(gate_id)

    def add_or_update(self, gate: GateDefinition):
        self._gates[gate.id] = gate
        self.save()

    def remove(self, gate_id: str):
        self._gates.pop(gate_id, None)
        self.save()

    def resolve(self, gate_id: str, local_defs) -> Optional[GateDefinition]:
        for g in local_defs:
            if g.id == gate_id:
                return g
        return self._gates.get(gate_id)

    def record_used_args(self, gate_id: str, arg_values: Dict[str, str]):
        """Remember the arg values for the next placement of this gate."""
        GateLibrary._last_used[gate_id] = dict(arg_values)

    def get_last_used_args(self, gate_id: str) -> Optional[Dict[str, str]]:
        return GateLibrary._last_used.get(gate_id)
