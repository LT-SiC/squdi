# Integration into current squdi branch

1. Confirm the current exact gate definitions, chosen electron manifold, nuclear targets and allowed pulse parameter ranges with Erik.
2. Inspect `V2_nuclearSetup` in `LT-SiC/squdi` locally, identify Logic interfaces and the dummy testing config; do not assume the historical NV-MCAS code is compatible.
3. Implement a validated `Circuit -> squdi Logic` mapping, separate from QASM and Qiskit representations.
4. Prototype offline / dummy before any real hardware connection. Review with the lab the permissions and safety conditions for queueing measurements.
5. For institutional access, move hosting behind an authenticated, IT-managed reverse proxy and HTTPS, not by exposing this local development server.
