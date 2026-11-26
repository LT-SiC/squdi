# Historical MCAS translator — what we did and did not integrate

Source: https://github.com/maxkeller321/Compiler-mcas-qiskit

The upstream README explicitly calls the program a **Qiskit QuantumCircuit -> MCAS** compiler, not MCAS -> Qiskit. Its `compiler_qiskit_mcas.py` uses a 3-nuclear-spin NV diamond platform:
- q0 = `14n`
- q1 = `13c414`
- q2 = `13c90`

It recognizes `rx`, `ry`, and `cx` after transpilation, then generates lab-specific operations such as `op.rx_nitrogen`, `op.ry_carbon_414`, and `op.crot_pi_x_between_nuclear_spins`. Full output imports a historical `pi3diamond`, `multi_channel_awg_seq`, and `UserScripts.helpers` environment. These are **NOT squdi APIs** and the code is not portable to the PI3 SiC V2 setup.

The new `backend/legacy_mcas.py` reimplements the small supported operation mapping, and generates a Python *template* demonstrating the historical MCAS calls. It rejects DDRF, `rz`, H, SWAP etc. and circuits with non-three wire counts instead of pretending they are compatible. This is a limited adapter, **not the complete legacy compiler**; the historical transpiler and codebase have not been vendored. The generated script needs the original external lab dependencies and is **not runnable in a normal Python environment**.

Review with Erik whether this historic NV backend has any relevance to the current 4H-SiC V2 `squdi` branch before extending the MCAS format. Consider a custom hardware-neutral JSON/IR bridge to a proper qudi Logic module instead of relying on the old MCAS tool.
