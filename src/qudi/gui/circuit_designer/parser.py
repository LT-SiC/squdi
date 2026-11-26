"""
parser.py — Gate code resolver with full spin/state context.

Reserved template placeholders (auto-injected, no need to declare as GateArg):
  {role_spin}    → spin string of the qubit assigned to that role
                   e.g. {control_spin} → "3/2",  {target_spin} → "1/2"
  {role_label}   → qubit label assigned to that role  (same as {role_name})
                   e.g. {control_label} → "electron"
  {role_state}   → the chosen |1⟩ state for a control role
                   e.g. {control_state} → "ms=-1/2"  (empty string if not set)
  {qubits}       → tuple of all qubit labels in role order (from render_code)
  {spins}        → repr of {qubit_label: spin} dict for all roles
  {spin_list}    → repr of [spin, ...] list in role order

Example template:
  cnot({control}, {target},
       control_spin={control_spin}, target_spin={target_spin},
       condition={control_state})
"""
from typing import Dict, List, Tuple


def resolve_gate_code(placement, gate_def, doc) -> str:
    role_map, arg_vals, _ = _build_context(placement, gate_def, doc)
    return gate_def.render_code(role_map, arg_vals)


def gate_context(placement, gate_def, doc) -> Dict:
    role_map, arg_vals, ctx = _build_context(placement, gate_def, doc)
    return {"role_map": role_map, "arg_vals": arg_vals, **ctx}


def _build_context(placement, gate_def, doc) -> Tuple[Dict, Dict, Dict]:
    from models import spin_state_color, spin_states

    # ── Role → qubit label ────────────────────────────────────────────────────
    role_map: Dict[str, str] = {}
    for rname, ridx in placement.role_to_row.items():
        role_map[rname] = (doc.qubit_labels[ridx]
                           if 0 <= ridx < len(doc.qubit_labels) else f"q{ridx}")

    # ── Spin info per role / qubit ─────────────────────────────────────────────
    spins: Dict[str, str] = {}      # qubit_label → spin_string
    spin_list: List[str] = []       # in role order
    role_spins: Dict[str, str] = {} # role_name → spin_string

    for rname, qlabel in role_map.items():
        ridx     = placement.role_to_row.get(rname, 0)
        spin_str = doc.get_meta(ridx).spin
        spins[qlabel]    = spin_str
        role_spins[rname] = spin_str
        spin_list.append(spin_str)

    # ── Control states / colors ────────────────────────────────────────────────
    control_states: Dict[str, str] = {}
    control_colors: Dict[str, str] = {}
    for role in gate_def.roles:
        if not role.is_control:
            continue
        state = placement.control_states.get(role.name, "")
        control_states[role.name] = state
        qlabel   = role_map.get(role.name, "")
        spin_str = spins.get(qlabel, "1/2")
        control_colors[role.name] = (spin_state_color(spin_str, state)
                                     if state else role.control_color)

    # ── Effective arg values (honouring use_default) ───────────────────────────
    arg_vals = placement.effective_args(gate_def)

    # ── Inject reserved spin/label/state placeholders ─────────────────────────
    # These are auto-available in any template as {role_spin}, {role_label},
    # {role_state} without declaring them as GateArg entries.
    reserved: Dict[str, str] = {}
    for rname, qlabel in role_map.items():
        spin_str = role_spins[rname]
        state    = placement.control_states.get(rname, "")
        reserved[f"{rname}_spin"]  = repr(spin_str)   # e.g. '3/2'
        reserved[f"{rname}_label"] = qlabel           # e.g. 'electron'
        reserved[f"{rname}_state"] = repr(state)      # e.g. 'ms=-1/2'

    # Also inject aggregate placeholders
    reserved["spins"]     = repr(spins)
    reserved["spin_list"] = repr(spin_list)

    # Reserved values are lower priority than explicit arg_vals —
    # only inject if the arg is not already set by the gate definition
    declared_arg_names = {a.name for a in gate_def.args}
    for k, v in reserved.items():
        if k not in declared_arg_names and k not in arg_vals:
            arg_vals[k] = v

    ctx = {
        "qubit_labels":   list(role_map.values()),
        "spins":          spins,
        "spin_list":      spin_list,
        "role_spins":     role_spins,
        "control_states": control_states,
        "control_colors": control_colors,
        "reserved":       reserved,
    }

    # ── FUTURE DISPATCH HOOK ──────────────────────────────────────────────────
    # Inspect ctx["role_spins"], ctx["control_states"], ctx["qubit_labels"]
    # to choose between different underlying functions.
    # Example:
    # if gate_def.name == "CeNot_n":
    #     target_spin = ctx["role_spins"].get("nuclear", "1/2")
    #     if target_spin == "1/2":
    #         arg_vals["__func__"] = "sna.cnot"
    #     else:
    #         arg_vals["__func__"] = "ddrf"
    # ──────────────────────────────────────────────────────────────────────────

    return role_map, arg_vals, ctx
