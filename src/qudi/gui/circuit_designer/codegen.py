"""
codegen.py - Generates Python experiment code from a CircuitDocument.
Python 3.6+ compatible.

Full code structure with indentation levels:
  preamble                      (fixed, no indent)
  [circuit sequence]            (3 tabs = 12 spaces)
  fixed_middle                  (fixed, no indent)
  [ana_seq block]               (1 tab = 4 spaces)
  pre_parameters                (fixed, no indent)
  [parameters block]            (1 tab = 4 spaces, inside OrderedDict)
  fixed_end                     (fixed, no indent)

The "for _I_ in parameter_iterator(...)" line is NOT emitted here;
it lives in the preamble or fixed sections so the user controls it.
"""
from typing import List, Optional

from models import (CircuitDocument, GatePlacement, Parameter,
                    DEFAULT_ANA_SEQ_CODE)
from library import GateLibrary

try:
    from gui.circuit_designer.parser import resolve_gate_code, gate_context
except ImportError:
    from parser import resolve_gate_code, gate_context

# Default fixed sections — used when a document has no saved values
DEFAULT_PRE_PARAMS = (
    "nuclear.parameters = OrderedDict(\n"
    "    (\n"
)
DEFAULT_POST_PARAMS = (
    "    )\n"
    ")\n"
)


def generate_parameter_lines(doc, indent="    "):
    # type: (CircuitDocument, str) -> str
    """
    Generates the parameter entries at 1-tab indent.
    These sit INSIDE the OrderedDict(...) call that lives in pre_parameters
    and the closing bracket in fixed_end (or post_parameters).
    """
    lines = []
    for p in doc.parameters:
        lines.append("{}({!r}, {}),".format(indent, p.name, p.value_expr))
    return "\n".join(lines)


def generate_parameter_block(doc):
    # type: (CircuitDocument) -> str
    """
    Full self-contained parameters block for the standalone code preview.
    (Used by code_panel live preview only — not by generate_full_code.)
    """
    lines = ["from collections import OrderedDict", "import numpy as np", ""]
    lines.append("nuclear.parameters = OrderedDict(")
    lines.append("    (")
    for p in doc.parameters:
        lines.append("        ({!r}, {}),".format(p.name, p.value_expr))
    lines.append("    )")
    lines.append(")")
    return "\n".join(lines)


def generate_ana_seq_block(doc, indent="    "):
    # type: (CircuitDocument, str) -> str
    """Generates ana_seq list at 1-tab indent."""
    if not doc.ana_seq:
        return DEFAULT_ANA_SEQ_CODE
    lines = ["{}ana_seq = [".format(indent)]
    for entry in doc.ana_seq:
        lst = repr(entry.to_list())
        suffix = "  # {}".format(entry.comment) if entry.comment else ""
        lines.append("{}    {},{}" .format(indent, lst, suffix))
    lines.append("{}]".format(indent))
    return "\n".join(lines)


def generate_circuit_code(doc, indent="            "):
    # type: (CircuitDocument, str) -> str
    """
    Generates gate calls at 3-tab (12-space) indent.
    No for-loop header — that belongs in the preamble.
    """
    lib = GateLibrary.instance()
    swept = set(doc.swept_params())
    sorted_pl = sorted(doc.placements, key=lambda p: (p.col, p.min_row()))
    lines = []         # type: List[str]
    cur_col = None     # type: Optional[int]

    for pl in sorted_pl:
        if cur_col is not None and pl.col != cur_col:
            lines.append("")
        cur_col = pl.col

        gd = lib.resolve(pl.gate_def_id, doc.local_gate_defs)
        if gd is None:
            lines.append("{}# [MISSING GATE id={}]".format(
                indent, pl.gate_def_id[:8]))
            continue

        ctx      = gate_context(pl, gd, doc)
        arg_vals = ctx["arg_vals"]
        code     = resolve_gate_code(pl, gd, doc)

        # Build inline comment
        comments = []
        swept_here = [k for k, v in arg_vals.items()
                      if any('_I_["{}"]'.format(s) in v
                             or "_I_['{}']".format(s) in v
                             for s in swept)]
        if swept_here:
            comments.append("swept: {}".format(", ".join(swept_here)))
        if ctx["control_states"]:
            strs = ["{r}|1>={s}".format(r=rn, s=st)
                    for rn, st in ctx["control_states"].items() if st]
            if strs:
                comments.append("ctrl: {}".format(", ".join(strs)))
        if comments:
            code += "  # " + "  |  ".join(comments)

        lines.append("{}{}".format(indent, code))

    return "\n".join(lines)


def generate_full_code(doc):
    # type: (CircuitDocument) -> str
    """
    Assemble the complete experiment script.

    Structure:
        preamble            (no indent, user-editable)
        circuit sequence    (3 tabs, no for-loop header)
        fixed_middle        (no indent, user-editable)
        ana_seq             (1 tab)
        pre_parameters      (no indent — from fixed_middle tail or separate)
        parameters          (1 tab, inside OrderedDict)
        fixed_end           (no indent, user-editable)
    """
    parts = [
        "# Circuit: {}".format(doc.title),
        "# Generated by Quantum Composer",
        "",
    ]

    # 1. Preamble (fixed, no indent)
    parts.append("# -- Preamble " + "-" * 50)
    parts.append(doc.preamble.rstrip("\n"))
    parts.append("")

    # 2. Circuit sequence (3 tabs, no for-loop header)
    parts.append("# -- Circuit sequence " + "-" * 42)
    body = generate_circuit_code(doc, indent="            ")
    if body.strip():
        parts.append(body)
    else:
        parts.append("            pass  # (empty circuit)")
    parts.append("")

    # 3. Fixed middle (no indent)
    parts.append("# -- Middle " + "-" * 51)
    parts.append(doc.fixed_middle.rstrip("\n"))
    parts.append("")

    # 4. Analysis sequence (1 tab)
    parts.append("# -- Analysis sequence " + "-" * 41)
    parts.append(generate_ana_seq_block(doc, indent="    "))
    parts.append("")

    # 5. Pre-parameters section (fixed, no indent)
    #    doc.pre_parameters holds the opening of the OrderedDict call
    pre_params = getattr(doc, "pre_parameters", DEFAULT_PRE_PARAMS)
    parts.append("# -- Parameters " + "-" * 47)
    parts.append(pre_params.rstrip("\n"))

    # 6. Parameter entries (1 tab)
    param_lines = generate_parameter_lines(doc, indent="        ")
    if param_lines:
        parts.append(param_lines)

    # 7. Post-parameters closing bracket (part of fixed_end or hardcoded)
    post_params = getattr(doc, "post_parameters", DEFAULT_POST_PARAMS)
    parts.append(post_params.rstrip("\n"))
    parts.append("")

    # 8. Fixed end (no indent)
    parts.append("# -- End " + "-" * 54)
    parts.append(doc.fixed_end.rstrip("\n"))

    return "\n".join(parts)
