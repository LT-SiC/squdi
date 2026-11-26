# Spin Circuit Studio Qudi logic

`SpinCircuitStudioLogic` serves the standalone Spin Circuit Studio frontend and its
hardware-independent circuit export backend from a loopback-only HTTP server.
It does not connect to instruments or deliver code to a specific consumer.

## Activation

Add the logic module to a Qudi configuration:

```yaml
logic:
    spin_circuit_studio_logic:
        module.Class: 'spin_circuit_studio.spin_circuit_studio_logic.SpinCircuitStudioLogic'
        options:
            port: 8765
```

The sample hardware-free configuration is
`src/qudi/configs/spin_circuit_studio_dummy.cfg`. Start Qudi with that
configuration, activate `spin_circuit_studio_logic`, then open
`http://127.0.0.1:8765` in a browser. Deactivating the logic stops the HTTP
server. The listener is fixed to `127.0.0.1`; there is no host option.

## HTTP API

- `GET /api/health` returns `ok`, the studio version, and
  `hardware_connected: false`.
- `POST /api/export` accepts a JSON object with `circuit` and optional `format`
  (`qasm`, `qiskit`, or `mcas`; defaults to `qasm`). A successful response
  contains the normalized `circuit`, generated `code`, and an operation
  `summary`. Invalid input is rejected with HTTP 400. Requests are limited to
  1 MiB.
- The frontend and static assets are served from the same origin. The server
  binds only to IPv4 loopback.

## Logic API and signal

On a browser `qasm` export, the module stores the normalized circuit in the
`circuit` status variable and generated source in `openqasm_code`, then emits:

```python
sigOpenQasmUpdated(str_code, normalized_circuit_dict)
```

Other logic modules may connect to `sigOpenQasmUpdated(str, dict)`, call
`get_openqasm_code()` (or `get_openqasm()`) and `get_circuit()`, or pass a
circuit to `set_circuit(circuit)`. Returned circuits are copies. No MCAS,
pulsed, Queue, or other module-specific integration is installed.

The existing validation and exporters remain in `backend/`; the browser UI
remains in `frontend/`. The historical MCAS option continues to produce a
legacy template only and does not control hardware.
