"""Legacy NV/MCAS exporter based on maxkeller321's Qiskit-to-MCAS gate mapping.

This is NOT a SiC/squdi backend and intentionally refuses to translate DDRF.
See docs/LEGACY_MCAS.md for provenance, limitations and requirements.
"""
from __future__ import annotations
import math
from .circuit import CircuitError, normalize

LEGACY_SPINS = {0: "nitrogen", 1: "carbon_414", 2: "carbon_90"}

def export_mcas(raw: dict) -> str:
    c = normalize(raw)
    if c["qubits"] != 3:
        raise CircuitError("Legacy MCAS only maps three NV nuclei (14N, 13C414, 13C90). Choose three wires or QASM/Qiskit.")
    for gate in c["gates"]:
        if gate["type"] not in {"rx", "ry", "cx"}:
            raise CircuitError(f"Legacy MCAS does not support {gate['type']!r}, especially not SiC DDRF. Select QASM or Qiskit.")
    lines = [
        "# LEGACY NV/MCAS TEMPLATE — NOT for SiC/squdi; not standalone.",
        "# Adapted gate mapping from maxkeller321/Compiler-mcas-qiskit (2020/21).",
        "# Requires the historical pi3diamond / UserScripts / multi_channel_awg_seq environment.",
        "# The mapping is FIXED: q0=14N, q1=13C414, q2=13C90.",
        "# Review carefully with laboratory staff before execution.",
        "from math import pi",
        "from pi3diamond import pi3d",
        "import multi_channel_awg_seq as MCAS",
        "import UserScripts.helpers.operations as op",
        "",
        "def build_mcas():",
        "    mcas = MCAS.MultiChSeq(seq_name='sic_export', ch_dict={'2g': [1, 2], '128m': [1, 2]})",
        "    op.full_initialisation(mcas, '+++')",
    ]
    for g in c["gates"]:
        typ, row = g["type"], g["row"]
        if typ == "cx":
            ids = {0: "14n", 1: "13c414", 2: "13c90"}
            # historical translator accepts controlled_qubit (target) then controlling_qubit (control)
            lines.append(f"    op.crot_pi_x_between_nuclear_spins(mcas, '{ids[g['target']]}', '{ids[row]}')")
        else:
            name = f"{typ}_{LEGACY_SPINS[row]}"
            theta = g["angle"] / math.pi
            angle = "pi" if math.isclose(theta, 1) else "pi/2" if math.isclose(theta, 0.5) else "-pi/2" if math.isclose(theta, -0.5) else f"({theta:.12g})*pi"
            if row > 0:
                lines.append("    op.electron_pi_pulse(mcas)")
            lines.append(f"    op.{name}(mcas, {angle}, ms={0 if row == 0 else -1})")
            if row > 0:
                lines.append("    op.electron_pi_pulse(mcas)")
    lines.extend(["    op.readout_nuclear_spin_state(mcas, '+++')", "    pi3d.gated_counter.set_n_values(mcas)", "    return mcas", "", "# Call build_mcas() only inside a correctly configured legacy measurement environment."])
    return "\n".join(lines) + "\n"
