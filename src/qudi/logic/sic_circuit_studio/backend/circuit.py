"""Hardware-independent circuit model, validation and semantic exporters.

DDRF: U = |0><0|_e ⊗ R_axis(s*theta) + |1><1|_e ⊗ R_axis(-s*theta).
Electronics convention |0>=up is a UI assumption pending PI3 confirmation.
"""
from __future__ import annotations
import math
from typing import Any

VERSION = "0.3.3"
MAX_QUBITS = 25
MAX_COLUMNS = 300
STANDARD = {"h", "x", "y", "z", "s", "sdg", "t", "tdg", "sx", "sxdg", "id", "rz", "cx", "cy", "cz", "ch", "crz", "swap", "measure", "reset", "barrier"}
NATIVE = {"rx", "ry", "ddrf"}
GATES = STANDARD | NATIVE
TWO_QUBIT = {"cx", "cy", "cz", "ch", "crz", "swap", "ddrf"}
PARAM_GATES = {"rx", "ry", "rz", "crz", "ddrf"}

class CircuitError(ValueError):
    pass

def integer(value: Any, name: str, start: int, end: int):
    if isinstance(value, bool) or not isinstance(value, int) or not start <= value <= end:
        raise CircuitError(f"{name} must be an integer from {start} to {end}.")
    return value

def normalize(data: Any) -> dict:
    if not isinstance(data, dict):
        raise CircuitError("Circuit must be a JSON object.")
    n = integer(data.get("qubits"), "qubits", 1, MAX_QUBITS)
    columns = integer(data.get("columns", 12), "columns", 1, MAX_COLUMNS)
    raw = data.get("gates", [])
    if not isinstance(raw, list) or len(raw) > n * columns:
        raise CircuitError("Invalid gate list.")
    occupied: set[tuple[int, int]] = set()
    result = []
    for index, g in enumerate(raw):
        if not isinstance(g, dict):
            raise CircuitError(f"Gate {index}: expected an object.")
        typ = g.get("type")
        if typ not in GATES:
            raise CircuitError(f"Gate {index}: unknown gate {typ!r}.")
        row = integer(g.get("row"), "row", 0, n - 1)
        col = integer(g.get("col"), "column", 0, columns - 1)
        item = {"type": typ, "row": row, "col": col}
        if typ in TWO_QUBIT:
            target = integer(g.get("target"), "target", 0, n - 1)
            if target == row:
                raise CircuitError("Control and target must be different.")
            item["target"] = target
        if typ == "ddrf":
            axis = g.get("axis", "x")
            if axis not in {"x", "y"}:
                raise CircuitError("DDRF axis must be x or y.")
            item["axis"] = axis
            sign = integer(g.get("sign", 1), "DDRF sign", -1, 1)
            if sign == 0:
                raise CircuitError("DDRF sign must be +1 or -1.")
            item["sign"] = sign
        if typ in PARAM_GATES:
            try:
                angle = float(g.get("angle", math.pi / 2))
            except (TypeError, ValueError, OverflowError) as exc:
                raise CircuitError("Invalid rotation angle.") from exc
            if not math.isfinite(angle) or abs(angle) > 4 * math.pi:
                raise CircuitError("Angle must be finite and within ±4π.")
            item["angle"] = angle
        # A two-qubit gate spans its entire interval and must not overlap intermediate gate cells.
        blocked = range(min(row, item.get("target", row)), max(row, item.get("target", row)) + 1)
        for r in blocked:
            if (col, r) in occupied:
                raise CircuitError(f"Collision at time slot {col + 1}, wire {r}.")
        for r in blocked:
            occupied.add((col, r))
        result.append(item)
    result.sort(key=lambda x: (x["col"], x["row"]))
    return {"version": 2, "qubits": n, "columns": columns, "gates": result}

def angle_text(v: float) -> str:
    for coeff, label in [(2, "2*pi"), (1, "pi"), (0.5, "pi/2"), (-0.5, "-pi/2"), (-1, "-pi"), (-2, "-2*pi")]:
        if math.isclose(v, coeff * math.pi, abs_tol=1e-9):
            return label
    return f"{v:.12g}"

def _operations(c: dict) -> list[tuple[str, list]]:
    """Return standard gate ops; DDRF is decomposed to standard controlled rotations."""
    ops = []
    for g in c["gates"]:
        typ, r = g["type"], g["row"]
        if typ == "ddrf":
            target, theta = g["target"], g["angle"] * g["sign"]
            if g["axis"] == "y":
                ops.extend([("cx", [r, target]), ("ry", [theta, target]), ("cx", [r, target])])
            else:
                ops.extend([("h", [target]), ("cx", [r, target]), ("rz", [theta, target]), ("cx", [r, target]), ("h", [target])])
        elif typ in {"rx", "ry", "rz"}:
            ops.append((typ, [g["angle"], r]))
        elif typ == "crz":
            ops.append((typ, [g["angle"], r, g["target"]]))
        elif typ in TWO_QUBIT:
            ops.append((typ, [r, g["target"]]))
        else:
            ops.append((typ, [r]))
    return ops

def qasm2(raw: dict) -> str:
    c = normalize(raw)
    result = ["OPENQASM 2.0;", 'include "qelib1.inc";', f'qreg q[{c["qubits"]}];', f'creg c[{c["qubits"]}];', ""]
    for typ, params in _operations(c):
        if typ == "measure":
            result.append(f"measure q[{params[0]}] -> c[{params[0]}];")
        elif typ in {"cx", "cy", "cz", "ch", "swap"}:
            result.append(f"{typ} q[{params[0]}],q[{params[1]}];")
        elif typ == "crz":
            result.append(f"crz({angle_text(params[0])}) q[{params[1]}],q[{params[2]}];")
        elif typ in {"rx", "ry", "rz"}:
            result.append(f"{typ}({angle_text(params[0])}) q[{params[1]}];")
        else:
            result.append(f"{typ} q[{params[0]}];")
    return "\n".join(result) + "\n"

def qiskit_python(raw: dict) -> str:
    c = normalize(raw)
    out = ["# Python / Qiskit circuit (requires: pip install qiskit)", "from math import pi", "from qiskit import QuantumCircuit", "", f'qc = QuantumCircuit({c["qubits"]}, {c["qubits"]})', ""]
    for typ, p in _operations(c):
        if typ == "measure":
            out.append(f"qc.measure({p[0]}, {p[0]})")
        elif typ in {"cx", "cy", "cz", "ch", "swap"}:
            out.append(f"qc.{typ}({p[0]}, {p[1]})")
        elif typ == "crz":
            out.append(f"qc.crz({angle_text(p[0])}, {p[1]}, {p[2]})")
        elif typ in {"rx", "ry", "rz"}:
            out.append(f"qc.{typ}({angle_text(p[0])}, {p[1]})")
        else:
            out.append(f"qc.{typ}({p[0]})")
    out.append("")
    out.append("print(qc.draw(output='text'))")
    return "\n".join(out) + "\n"

def export(raw: dict, fmt: str) -> str:
    if fmt == "qasm":
        return qasm2(raw)
    if fmt == "qiskit":
        return qiskit_python(raw)
    if fmt == "mcas":
        from .legacy_mcas import export_mcas
        return export_mcas(raw)
    raise CircuitError(f"Unsupported export format: {fmt!r}")

def summarize(raw: dict) -> dict:
    c = normalize(raw)
    return {"qubits": c["qubits"], "operations": len(c["gates"]), "ddrf": sum(g["type"] == "ddrf" for g in c["gates"])}
