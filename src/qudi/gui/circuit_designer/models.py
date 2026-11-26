"""
models.py - Pure data structures, no GUI imports.
Compatible with Python 3.6+
"""
import json
import uuid
import copy
import re
from typing import Any, Dict, List, Optional

FIXED_ROW_NAMES = ["electron", "Si1"]
PREFILL_LAST_GATE_ARGS = True

DEFAULT_PREAMBLE = "# --- Experiment preamble ---\n"
DEFAULT_FIXED_MIDDLE = "results = run_experiment(nuclear.parameters)\n"
DEFAULT_PRE_PARAMS = (
    "    nuclear.parameters = OrderedDict(\n"
    "        (\n"
)
DEFAULT_POST_PARAMS = (
    "        )\n"
    "    )\n"
)
DEFAULT_ANA_SEQ_CODE = (
    "    ana_seq = [\n"
    "    ['init',   '<', 9, 0, 0, 1],  # SSR1 - postselection\n"
    "    ['result', '>', 9, 0, 0, 1],  # SSR2 - readout\n"
    "    ['init',   '>', 6, 1, 0, 1],  # CRC\n"
    "    ]\n"
)
DEFAULT_FIXED_END = "# --- End of experiment ---\n"


def spin_states(spin_str):
    # type: (str) -> List[str]
    try:
        if "/" in spin_str:
            num, den = spin_str.split("/")
            s = int(num.strip()) / int(den.strip())
        else:
            s = float(spin_str)
        n = int(round(2 * s))
        states = []
        for k in range(n + 1):
            ms_num = -n + 2 * k
            if s == int(s):
                ms_int = ms_num // 2
                label = "ms={:+d}".format(ms_int) if ms_int != 0 else "ms=0"
                states.append(label)
            else:
                states.append("ms={:+d}/2".format(ms_num))
        return states
    except Exception:
        return ["ms=0", "ms=1"]


SPIN_STATE_COLORS = [
    "#7EB8F7", "#6DAF6D", "#F0A500", "#E05050",
    "#B05FD4", "#50C0C0", "#E08030", "#C0C040",
]


def spin_state_color(spin_str, state):
    # type: (str, str) -> str
    states = spin_states(spin_str)
    try:
        return SPIN_STATE_COLORS[states.index(state) % len(SPIN_STATE_COLORS)]
    except ValueError:
        return "#FFFFFF"


class QubitRole(object):
    def __init__(self, name="", description="", is_control=False,
                 control_color="#FFFFFF"):
        self.name = name
        self.description = description
        self.is_control = is_control
        self.control_color = control_color

    def to_dict(self):
        return {"name": self.name, "description": self.description,
                "is_control": self.is_control,
                "control_color": self.control_color}

    @staticmethod
    def from_dict(d):
        return QubitRole(
            name=d["name"], description=d.get("description", ""),
            is_control=d.get("is_control", False),
            control_color=d.get("control_color", "#FFFFFF"))


class GateArg(object):
    def __init__(self, name="", default=""):
        self.name = name
        self.default = default

    def to_dict(self):
        return {"name": self.name, "default": self.default}

    @staticmethod
    def from_dict(d):
        return GateArg(name=d["name"], default=d.get("default", ""))


class QubitRowMeta(object):
    def __init__(self, spin="1/2"):
        self.spin = spin

    def to_dict(self):
        return {"spin": self.spin}

    @staticmethod
    def from_dict(d):
        return QubitRowMeta(spin=d.get("spin", "1/2"))


class AnaSeqEntry(object):
    def __init__(self, kind="result", comparison=">", threshold=9,
                 nlp=0, delta=0, n_results=1, comment=""):
        self.kind = kind
        self.comparison = comparison
        self.threshold = threshold
        self.nlp = nlp
        self.delta = delta
        self.n_results = n_results
        self.comment = comment

    def to_dict(self):
        return {"kind": self.kind, "comparison": self.comparison,
                "threshold": self.threshold, "nlp": self.nlp,
                "delta": self.delta, "n_results": self.n_results,
                "comment": self.comment}

    @staticmethod
    def from_dict(d):
        return AnaSeqEntry(
            kind=d.get("kind", "result"),
            comparison=d.get("comparison", ">"),
            threshold=int(d.get("threshold", 9)),
            nlp=int(d.get("nlp", 0)),
            delta=int(d.get("delta", 0)),
            n_results=int(d.get("n_results", 1)),
            comment=d.get("comment", ""))

    def to_list(self):
        return [self.kind, self.comparison,
                self.threshold, self.nlp, self.delta, self.n_results]

    def to_code_line(self):
        lst = repr(self.to_list())
        suffix = "  # {}".format(self.comment) if self.comment else ""
        return "    {}{}".format(lst, suffix)


class GateDefinition(object):
    """
    Template placeholders:
      {role_name}       -> qubit label
      {role_name_spin}  -> spin of that qubit e.g. '3/2'
      {role_name_state} -> chosen |1> state e.g. 'ms=-1/2'
      {role_name_label} -> qubit label (explicit)
      {qubits}          -> tuple of all qubit labels
      {spins}           -> {qubit: spin} dict repr
      {spin_list}       -> [spin,...] list repr
      {arg_name}        -> arg value (brace style)
      bare arg_name     -> arg value (word-boundary)
      _I_["param"]      -> left as-is
    """
    def __init__(self):
        self.id = str(uuid.uuid4())
        self.name = "NewGate"
        self.display_color = "#4A90D9"
        self.gate_symbol = ""
        self.roles = []          # type: List[QubitRole]
        self.args = []           # type: List[GateArg]
        self.code_template = "# {gate_name}"
        self.description = ""
        self.is_global = True
        self.rotation_axis = ""
        self.rotation_angle_arg = ""

    def to_dict(self):
        return {
            "id": self.id, "name": self.name,
            "display_color": self.display_color,
            "gate_symbol": self.gate_symbol,
            "roles": [r.to_dict() for r in self.roles],
            "args":  [a.to_dict() for a in self.args],
            "code_template": self.code_template,
            "description": self.description,
            "is_global": self.is_global,
            "rotation_axis": self.rotation_axis,
            "rotation_angle_arg": self.rotation_angle_arg,
        }

    @staticmethod
    def from_dict(d):
        g = GateDefinition()
        g.id = d.get("id", str(uuid.uuid4()))
        g.name = d.get("name", "Gate")
        g.display_color = d.get("display_color", "#4A90D9")
        g.gate_symbol = d.get("gate_symbol", "")
        g.roles = [QubitRole.from_dict(r) for r in d.get("roles", [])]
        g.args  = [GateArg.from_dict(a)  for a in d.get("args", [])]
        g.code_template = d.get("code_template", "")
        g.description   = d.get("description", "")
        g.is_global     = d.get("is_global", True)
        g.rotation_axis = d.get("rotation_axis", "")
        # back-compat: angle_display was removed, rotate_angle_arg takes its place
        g.rotation_angle_arg = d.get("rotation_angle_arg",
                                     d.get("angle_display", ""))
        return g

    def render_code(self, role_map, arg_values=None):
        # type: (Dict[str,str], Optional[Dict[str,str]]) -> str
        text = self.code_template
        text = text.replace("{gate_name}", self.name)
        qlist = tuple(role_map.values())
        text = text.replace("{qubits}", repr(qlist))

        for rname, qlabel in role_map.items():
            text = text.replace("{" + rname + "}", qlabel)

        if not arg_values:
            return text

        brace_args = set(re.findall(r'\{(\w+)\}', self.code_template))
        brace_args -= set(role_map.keys())
        brace_args -= {"gate_name", "qubits"}

        default_map = {a.name: a.default for a in self.args}
        effective = {}
        for k, v in arg_values.items():
            effective[k] = v if v else default_map.get(k, "")

        for k, v in effective.items():
            if k in brace_args and v:
                text = text.replace("{" + k + "}", v)

        bare_subs = {k: v for k, v in effective.items()
                     if k not in brace_args and v}
        if bare_subs:
            sorted_keys = sorted(bare_subs.keys(), key=len, reverse=True)
            pat = (r'(?<!["\'\w.])('
                   + '|'.join(re.escape(k) for k in sorted_keys)
                   + r')(?!["\'\w\[])')
            text = re.sub(pat, lambda m: bare_subs[m.group(1)], text)

        brace_roles = (set(re.findall(r'\{(\w+)\}', self.code_template))
                       & set(role_map.keys()))
        bare_roles = {k: v for k, v in role_map.items()
                      if k not in brace_roles}
        if bare_roles:
            sroles = sorted(bare_roles.keys(), key=len, reverse=True)
            rp = (r'(?<!["\'\w.<])('
                  + '|'.join(re.escape(k) for k in sroles)
                  + r')(?!["\'\w\[])')
            text = re.sub(rp, lambda m: bare_roles[m.group(1)], text)

        return text


class GatePlacement(object):
    def __init__(self):
        self.id = str(uuid.uuid4())
        self.gate_def_id = ""
        self.col = 0
        self.role_to_row = {}       # type: Dict[str,int]
        self.arg_values = {}        # type: Dict[str,str]
        self.use_default = {}       # type: Dict[str,bool]
        self.control_states = {}    # type: Dict[str,str]

    def qubit_rows(self):
        # type: () -> List[int]
        return sorted(self.role_to_row.values())

    def min_row(self):
        # type: () -> int
        r = self.qubit_rows()
        return r[0] if r else 0

    def max_row(self):
        # type: () -> int
        r = self.qubit_rows()
        return r[-1] if r else 0

    def effective_arg(self, arg_name, gate_def):
        # type: (str, GateDefinition) -> str
        if self.use_default.get(arg_name, True):
            for a in gate_def.args:
                if a.name == arg_name:
                    return a.default
            return ""
        return self.arg_values.get(arg_name, "")

    def effective_args(self, gate_def):
        # type: (GateDefinition) -> Dict[str,str]
        return {a.name: self.effective_arg(a.name, gate_def)
                for a in gate_def.args}

    def to_dict(self):
        return {
            "id": self.id, "gate_def_id": self.gate_def_id,
            "col": self.col, "role_to_row": self.role_to_row,
            "arg_values": self.arg_values, "use_default": self.use_default,
            "control_states": self.control_states,
        }

    @staticmethod
    def from_dict(d):
        p = GatePlacement()
        p.id = d.get("id", str(uuid.uuid4()))
        p.gate_def_id = d.get("gate_def_id", "")
        p.col = d.get("col", 0)
        p.role_to_row = {k: int(v)
                         for k, v in d.get("role_to_row", {}).items()}
        p.arg_values = d.get("arg_values", d.get("arg_overrides", {}))
        p.use_default = {k: bool(v)
                         for k, v in d.get("use_default", {}).items()}
        p.control_states = d.get("control_states", {})
        return p

    def copy_new(self):
        # type: () -> GatePlacement
        c = copy.deepcopy(self)
        c.id = str(uuid.uuid4())
        return c


class Parameter(object):
    def __init__(self, name="new_param", value_expr="[1]"):
        self.name = name
        self.value_expr = value_expr

    def to_dict(self):
        return {"name": self.name, "value_expr": self.value_expr}

    @staticmethod
    def from_dict(d):
        return Parameter(name=d["name"], value_expr=d.get("value_expr", "[1]"))

    def evaluate(self):
        import numpy as np
        safe = {
            "range": range, "len": len, "list": list,
            "int": int, "float": float, "str": str,
            "__import__": __import__,
        }
        return eval(self.value_expr,
                    {"np": np, "numpy": np, "__builtins__": safe})

    def is_swept(self):
        # type: () -> bool
        try:
            v = self.evaluate()
            try:
                return len(v) > 1
            except TypeError:
                pass
            count = 0
            for _ in v:
                count += 1
                if count > 1:
                    return True
        except Exception:
            pass
        return False


class CircuitDocument(object):
    def __init__(self):
        self.version = "1.0"
        self.title = "Untitled"
        self.qubit_labels = ["electron", "Si1"]  # type: List[str]
        self.qubit_meta = []         # type: List[QubitRowMeta]
        self.local_gate_defs = []    # type: List[GateDefinition]
        self.placements = []         # type: List[GatePlacement]
        self.parameters = []         # type: List[Parameter]
        self.ana_seq = []            # type: List[AnaSeqEntry]
        self.ui_state = {
            "cell_width": 110, "cell_height": 60,
            "splitter_sizes": [180, 920, 280],
        }                            # type: Dict[str,Any]
        self.preamble = DEFAULT_PREAMBLE
        self.fixed_middle = DEFAULT_FIXED_MIDDLE
        self.pre_parameters = DEFAULT_PRE_PARAMS
        self.post_parameters = DEFAULT_POST_PARAMS
        self.fixed_end = DEFAULT_FIXED_END

    def ensure_fixed_rows(self):
        while len(self.qubit_labels) < 2:
            self.qubit_labels.append(
                FIXED_ROW_NAMES[len(self.qubit_labels)])
        self.qubit_labels[0] = "electron"
        self.qubit_labels[1] = "Si1"
        while len(self.qubit_meta) < len(self.qubit_labels):
            spin = "3/2" if len(self.qubit_meta) == 0 else "1/2"
            self.qubit_meta.append(QubitRowMeta(spin=spin))

    def get_meta(self, row):
        # type: (int) -> QubitRowMeta
        self.ensure_fixed_rows()
        if row < len(self.qubit_meta):
            return self.qubit_meta[row]
        return QubitRowMeta()

    def swept_params(self):
        # type: () -> List[str]
        return [p.name for p in self.parameters if p.is_swept()]

    def ssr_count(self):
        # type: () -> int
        from library import GateLibrary
        lib = GateLibrary.instance()
        count = 0
        for pl in self.placements:
            gd = lib.resolve(pl.gate_def_id, self.local_gate_defs)
            if gd is None:
                continue
            matches = re.findall(r'\b\w*ssr\w*\s*\(',
                                 gd.code_template, re.IGNORECASE)
            count += len(matches)
        return count

    def delete_qubit(self, row):
        # type: (int) -> None
        if row < 2 or row >= len(self.qubit_labels):
            return
        self.qubit_labels.pop(row)
        if row < len(self.qubit_meta):
            self.qubit_meta.pop(row)
        new_placements = []
        for pl in self.placements:
            if row in pl.role_to_row.values():
                continue
            pl.role_to_row = {
                rn: (ri - 1 if ri > row else ri)
                for rn, ri in pl.role_to_row.items()
            }
            new_placements.append(pl)
        self.placements = new_placements

    def to_dict(self):
        return {
            "version": self.version, "title": self.title,
            "qubit_labels": self.qubit_labels,
            "qubit_meta": [m.to_dict() for m in self.qubit_meta],
            "local_gate_defs": [g.to_dict() for g in self.local_gate_defs],
            "placements": [p.to_dict() for p in self.placements],
            "parameters": [p.to_dict() for p in self.parameters],
            "ana_seq": [a.to_dict() for a in self.ana_seq],
            "ui_state": self.ui_state,
            "preamble": self.preamble,
            "fixed_middle": self.fixed_middle,
            "pre_parameters": self.pre_parameters,
            "post_parameters": self.post_parameters,
            "fixed_end": self.fixed_end,
        }

    @staticmethod
    def from_dict(d):
        doc = CircuitDocument()
        doc.version = d.get("version", "1.0")
        doc.title = d.get("title", "Untitled")
        doc.qubit_labels = d.get("qubit_labels", ["electron", "Si1"])
        doc.qubit_meta = [QubitRowMeta.from_dict(m)
                          for m in d.get("qubit_meta", [])]
        doc.local_gate_defs = [GateDefinition.from_dict(g)
                               for g in d.get("local_gate_defs", [])]
        doc.placements = [GatePlacement.from_dict(p)
                          for p in d.get("placements", [])]
        doc.parameters = [Parameter.from_dict(p)
                          for p in d.get("parameters", [])]
        doc.ana_seq = [AnaSeqEntry.from_dict(a)
                       for a in d.get("ana_seq", [])]
        doc.ui_state = d.get("ui_state", doc.ui_state)
        doc.preamble = d.get("preamble", DEFAULT_PREAMBLE)
        doc.fixed_middle = d.get(
            "fixed_middle", d.get("fixed_end", DEFAULT_FIXED_MIDDLE))
        doc.pre_parameters = d.get("pre_parameters", DEFAULT_PRE_PARAMS)
        doc.post_parameters = d.get("post_parameters", DEFAULT_POST_PARAMS)
        doc.fixed_end = d.get("fixed_end", DEFAULT_FIXED_END)
        doc.ensure_fixed_rows()
        return doc

    def save(self, path):
        # type: (str) -> None
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2)

    @staticmethod
    def load(path):
        # type: (str) -> CircuitDocument
        with open(path, "r", encoding="utf-8") as f:
            return CircuitDocument.from_dict(json.load(f))
