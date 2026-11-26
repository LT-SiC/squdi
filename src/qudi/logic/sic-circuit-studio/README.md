# SiC Circuit Studio v0.3.3

The **Pulse sequence preview** is an expandable panel below the circuit editor. It draws *illustrative*, unitless MW and RF envelopes for the current circuit, with rectangular, Gaussian and smoothed rectangular shapes. GRAPE remains disabled because no optimization or pulse compilation has been implemented. Red `!` badges on DDRF gates remind you to clarify the spin-basis/sign convention with Erik.

The **Measurement & analysis** page is a separate browser page in the same app. It displays a synthetic XY confocal scan with a progress animation, click-to-move crosshair, and X/Y line profiles. It does **not** connect to the real Qudi confocal GUI, the experimental hardware or the group's API.

See [`docs/PREVIEW_MODULES.md`](docs/PREVIEW_MODULES.md) and [`docs/LOCAL_INSTALLATION.md`](docs/LOCAL_INSTALLATION.md) for details.

# SiC Circuit Studio — v0.3.0

Local browser-based circuit editor for a Bachelor's thesis project at PI3, University of Stuttgart.

## What works
- Workspace landing page, system/light/dark themes, and SiC-inspired SVG mark.
- Responsive drag-and-drop circuit editor, 1–25 logical wires, auto-expanding time slots.
- Dedicated Rx / Ry spin rotations and electron-conditioned DDRF Rx / Ry (π/2 or π; up/down sign inversion).
- Collapsible standard gate library and settings sidebar, a drop-to-delete bin, out-of-circuit drag deletion, undo/redo.
- Native OpenQASM 2.0 and Qiskit Python export (includes a **logical decomposition** of the conditioned DDRF gate).
- *Historical NV-only* MCAS Python-template export based on `maxkeller321/Compiler-mcas-qiskit` supported `rx`, `ry`, `cx` semantics with 3 nuclear wires. Rejects unsupported operations.
- Circuit JSON save/import and browser-local autosave. No dependency installation for the editor.

**Important:** This does NOT drive laboratory equipment. The DDRF control convention `|0⟩ = electron up` is provisional and needs confirmation with supervisors. The logical DDRF decomposition in QASM/Qiskit is not the experimentally calibrated DDRF pulse sequence. MCAS is legacy NV-center tooling, NOT a translation to qudi/squdi.

## Quick start (WSL Ubuntu)

In the extracted folder:

```bash
python3 server.py
```

Open `http://127.0.0.1:8765` in Windows. Stop using Ctrl+C.

Or install a convenient launcher once:

```bash
bash scripts/install_launcher.sh
```

Make sure `~/.local/bin` is in PATH (the installer shows what to do if not), then launch the entire app and open the browser with:

```bash
sic-studio
```

An empty port 8765 is required. No conda environment, Node.js, npm, or Qiskit installation is needed to run the editor.

## Updating WITHOUT deleting your working directory

Use `python3 scripts/apply_update.py /path/to/new-release.zip` **while the server is stopped**, from the project folder. For example, from your WSL shell:

```bash
cd ~/Bachelorstudium/Bachelorarbeit/github/sic-circuit-studio
python3 scripts/apply_update.py /mnt/c/Users/YOU/Downloads/sic-circuit-studio-v0.3.0.zip
```

- Copies new release files safely into your current project; **does not delete files** you added.
- Before every release, takes a **full editable-source snapshot**, including your manual code edits and extra small project files, in `sic-circuit-studio-backups/<old-version>/<timestamp>_to_<new-version>/project/` plus a `manifest.json`. Git history, caches, configurations with secrets and large assets are excluded.
- Rejects suspicious paths and ignores `.git`, `.env`, and `.cfg` contents in the zip.
- Does not overwrite the `localStorage` browser circuit but JSON export is the safest backup.
- Existing files not present in the new release are kept, not deleted. Files present in the release are overwritten **after** backup.
- You can use `git diff` to review the updated files.
- Once an update works, release ZIP files can be deleted; keeping one off-machine backup is still recommended.
- Do not rely only on update snapshots: commit your edits with Git for a reliable revision history.

After installing the launcher, subsequent releases can be installed with `sic-studio-update /path/to/release.zip` (stop the server first).

**One-time upgrade from v0.1.x:** Download the separate `sic-studio-update.py` provided alongside v0.2.1, and run it from inside your existing project directory, supplying the new ZIP path. It safely backs up changed files and updates in place. The included updater handles future upgrades.

For a tiny personal code adjustment, just edit the file and increment the patch version:

```bash
python3 scripts/bump_version.py patch
```

Version bumps for **releases** should be deliberate (major/minor/patch). They do not automatically happen simply because a file changed.

### One-time transition from v0.2.0 to v0.2.1

The `sic-studio-update` installed with v0.2.0 still uses the old **overwritten-files-only** backup. To capture a full version-labelled snapshot *on this first upgrade*, download `sic-studio-update-v0.2.1.py` alongside the new ZIP, enter the existing project directory, and run:

```bash
python3 ../sic-studio-update-v0.2.1.py ../sic-circuit-studio-v0.2.1.zip
```

From v0.2.1 onward, the installed `sic-studio-update` command automatically uses the new snapshot system. Save and commit your work before updating when possible. Do not use the old external updater for this transition.

## Small refinements in v0.2.1

- Site-wide hamburger navigation, quieter workspace heading, padded lattice graphic and single card entry action.
- Circuit label, indexed qubits, initially fitting circuit width, small bin next to Undo/Redo.
- Gate dragging outside the circuit deletes it; hovering directly over the bin opens the lid.
- Terminal-style code output with syntax highlighting and a disabled **Export to setup** button.
- Version-labelled full-source snapshots before future updates.


## What changed in v0.3.0

- Gate help text on hover and in Gate settings; color accents by gate family.
- Standard library subdivided into Pauli, phase/inverse, square-root, controlled and measurement/timing sections. Added S†, T†, √X, √X†, I, CY, CH, CRz and a single-wire barrier; backend/export validation and tests cover these gates.
- The sample's **M** is an abstract Z-basis measurement, **not** the optical spin-readout sequence depicted in Erik's reference. Hardware-specific readout requires a dedicated gate/operation definition with the group.
- Optional Windows desktop window that runs the **same source** via `pywebview`, plus an optional standalone EXE build recipe; no change to the existing browser/WSL mode.
- Helper to inspect and remove `:Zone.Identifier` sidecar files.

### One universal updater

Use `sic-studio-update /path/to/new-release.zip` as before. The script inside the project is `scripts/apply_update.py`. The standalone `sic-studio-update.py` supplied with the release is just a convenient copy of that exact script for first-time use. Old one-off `sic-studio-update-v0.2.1.py` and the superseded early updater are not needed after installing the current release. Manually modified source files are backed up (unless excluded in the security rules); use Git as well for real history. Do not publish private `.cfg` or `.env` configurations.

### Removing Windows Zone.Identifier sidecars

From WSL inside the project:

```bash
bash scripts/clean_zone_identifiers.sh          # preview
bash scripts/clean_zone_identifiers.sh --delete # remove sidecar files under github/
```

The script walks the parent `github` folder (including siblings) and deletes only filenames ending with `:Zone.Identifier`. It does NOT disable Windows security features globally. Use only on your trusted files.

### Optional Windows desktop edition

**Option A: launch a native desktop window without compiling an EXE.** On Windows (not inside WSL), install regular Python and run:

```powershell
py -3 -m pip install pywebview
py -3 desktop.py
```

Alternatively double-click `scripts/start_desktop_windows.cmd` using Windows Explorer. This opens the same local app in a native window via WebView2/pywebview and stops its embedded HTTP server when you close it. There is no Qudi integration. **Your Linux Python environment does not install `pywebview` into Windows**; Windows Python must have it installed. You can access your WSL project from Explorer using `explorer.exe .`, though a Windows-local project directory is more robust for EXE builds. The GUI uses the exact same frontend/backend files as browser mode, so edits take effect the next time this desktop launcher is opened.

**Option B: compile a standalone Windows desktop program.** From a Windows-local copy of the project, run `scripts/build_desktop_windows.cmd`. This installs optional Windows build dependencies and builds `dist/SiC-Circuit-Studio/SiC-Circuit-Studio.exe` (PyInstaller `--onedir`). Building a Windows EXE must be done on Windows. **An EXE is a snapshot, not a live view of your source code:** rebuild after updating the app. Do not upload a compiled executable to Git without the group's permission.

**Option C: browser with no WSL terminal.** With Windows Python installed, double-click `scripts/start_server_windows.cmd`. If you want the localhost URL available after Windows login, **optionally** run `scripts/install_windows_startup.ps1` in Windows PowerShell once (explicit opt-in). This installs a removable Startup shortcut; it does not expose the server to the internet. Close the server window to stop it; the Windows startup folder lets you disable automatic launch at any time. If you keep using the WSL server, you must leave its process running instead.

Local address: `http://127.0.0.1:8765`. Some browsers resolve `http://sic-studio.localhost:8765`, but this is browser dependent; a genuinely custom hostname such as `sic-studio.test` requires a Windows hosts entry and still needs a running server. An internal institute name requires IT/DNS configuration and security review.

**Release/update behavior:** The WSL browser service, WSL launcher, and a Windows pywebview launcher pointed at the same *source directory* share code updates. A separate Windows copy or a compiled EXE does NOT automatically update itself; copy/synchronize source files and rebuild the EXE. The installer snapshots only the copy you're updating.

## Source layout

| File | Purpose |
| ---- | ------- |
| `frontend/index.html` | Page structure and form inputs |
| `frontend/styles.css` | Theme, responsive layout, circuit and gate visual styles |
| `frontend/app.js` | Editor state, UI events, drag/drop, local storage, API requests |
| `frontend/favicon.svg` | Geometric SiC-inspired logo / tab icon |
| `server.py` | Loopback-only HTTP server and `/api/export` endpoint |
| `backend/circuit.py` | Validation, logical DDRF decomposition, QASM / Qiskit generation |
| `backend/legacy_mcas.py` | Strict, documented historical NV-only MCAS adapter |
| `scripts/` | Terminal launcher, safe update and version utilities |
| `tests/` | Backend regression tests |
| `docs/` | Export semantics, physics, integration notes |

## Run tests

```bash
python3 -m unittest discover -s tests -v
```

## Export behavior

OpenQASM2/Qiskit use the following *logical* identity for DDRF on electronic control `c`, nuclear target `t`:

`U = |0><0| ⊗ R_axis(s*theta) + |1><1| ⊗ R_axis(-s*theta)`

For Y use `CX(c,t); Ry(s*theta,t); CX(c,t)`. For X use `H(t); CX(c,t); Rz(s*theta,t); CX(c,t); H(t)`.

This is **not** an optimized pulse implementation. See `docs/PHYSICS_AND_EXPORTS.md`.

## Local address / internal deployment

Local launch uses `127.0.0.1` by design. A friendly institutional hostname needs an IT-managed DNS entry, an authorized server with HTTPS and authentication, and approval from PI3. Buying a `.de` domain is neither required nor sufficient for institute-only access. Do not expose `server.py` to a public interface or connect it directly to instruments.

## Legacy source and attribution

See `docs/LEGACY_MCAS.md`: the historical converter translates **Qiskit -> MCAS** for a specific NV register and requires old pi3diamond dependencies. No upstream code was bundled. The legacy adapter here reimplements its limited, documented mapping. Review repository license before incorporating third-party files.


## v0.3.2 — geometry / envelope fixes and synthetic register viewer

- Corrected circuit gate positioning regression caused by an accidental CSS override.
- Genuine subscript labels and mathematical angle fractions in palette and circuit.
- Rectangle envelopes now show rising and falling edges; DDRF illustrative electron pulses are also shaped.
- Simultaneous circuit columns are represented as notional simultaneous pulse slots across separate spin-wire lanes. These are **not** experimental pulse schedules.
- New demonstration register: fabricated 25-spin coordinates and synthetic distance links, with 2D/3D interaction; not positions or couplings measured by PI3.
- Compact editor-code preview on the measurement page; no code transmission to squdi.
- Retired VBS installer because of third-party security-software warnings.


## v0.3.3 — streamlined measurement layout and open pulse waveforms
- The pulse preview no longer renders a closing stroke along the bottom of each envelope.
- The measurement page shows the compact spin register beside circuit source, with a full-width confocal workbench below (scan settings, XY map, vertically stacked X/Y profiles). No changes to synthetic data calculations or backend exports.
- `scripts/start_server_background.sh` starts the localhost server detached, with a log and health check. This is for a scheduled task; WSL persistence can depend on Windows/WSL configuration.
