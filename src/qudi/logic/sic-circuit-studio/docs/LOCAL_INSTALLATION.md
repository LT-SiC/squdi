# Local installation and launch options (Windows + WSL)

Choose ONE canonical project directory and ONE server process at a time. A browser tab, a Chrome-installed web app and a pywebview window are different windows accessing the **same** HTML/JS/backend files; they do not require three codebases.

## A. Existing WSL setup (simplest)

Inside WSL:

```bash
cd ~/Bachelorstudium/Bachelorarbeit/github/sic-circuit-studio
python3 -m unittest discover -s tests -v
sic-studio
```

The existing `sic-studio` command starts the Python server and opens the URL `http://127.0.0.1:8765`. The terminal remains occupied because it is hosting the HTTP server; open **another** WSL terminal tab for normal work. `Ctrl+C` stops the local site. The server listens only on `127.0.0.1` (not the institute LAN).

### Install the site as a Chrome app

1. Start the server (`sic-studio`) and visit `http://127.0.0.1:8765` in **Windows Chrome**.
2. Chrome `⋮` → `Cast, save and share` → `Install page as app...` (wording may differ by Chrome version). Confirm `SiC Circuit Studio`.
3. In Chrome, open `chrome://apps`, right-click SiC Circuit Studio to create desktop/taskbar shortcuts if desired.
4. Open the app shortcut. It is a standalone **Chrome window**, not a compiled Windows `.exe`.
5. Important: the Chrome icon by itself **does not start** the Python server. Start `sic-studio` first, or enable Windows-login autostart as below. When the server is running, the app window and normal browser tab access the same source.

### Automatically start the WSL server on Windows sign-in (optional)

Inside WSL:

```bash
cd ~/Bachelorstudium/Bachelorarbeit/github/sic-circuit-studio
bash scripts/install_wsl_windows_autostart.sh
```

The script adds a small Visual Basic Script to the **current Windows user's Startup folder**. On each Windows sign-in it launches `wsl.exe` and the project's `python3 server.py` with a hidden console. It does **not** grant Internet access and does not alter system-wide services. It depends on the default WSL-to-Windows localhost forwarding feature and enabled Windows interoperability. If something else already occupies port 8765 the new server will not start; avoid manually starting a second server. You can test by signing out/in, visiting `/api/health`, and examining the Python process with `ps aux | grep '[p]ython3 server.py'` in WSL. For errors inspect `tail -n 40 /tmp/sic-studio-autostart.log` in WSL.

To remove: press `Win + R`, run `shell:startup`, and delete **SiC Circuit Studio WSL Server.vbs**. To manually stop a running WSL server:

```bash
pkill -f '[p]ython3 server.py'  # only if sure this is your Studio server
```

If you prefer not to kill by name, find the PID with `ps aux | grep '[s]erver.py'` and run `kill <PID>`.

## B. Friendly local hostname (recommended: `sic-studio.localhost`)

The **recommended address** is `http://sic-studio.localhost:8765/`. Modern Chrome versions commonly resolve subdomains of `.localhost` to loopback without configuration, and these names are treated as potentially trustworthy origins. First, start the server and try that URL in Windows Chrome. If it works, skip editing any system files.

If it does not resolve, explicitly add the name to the local Windows `hosts` file:

1. Launch **Notepad as administrator**.
2. In Notepad choose File → Open, paste `C:\Windows\System32\drivers\etc\hosts`. Change file type to `All Files` if necessary.
3. Append this line exactly:

   ```
   127.0.0.1 sic-studio.localhost
   ```

4. Save. In Windows PowerShell run `ping sic-studio.localhost` to confirm local name resolution (should resolve to 127.0.0.1). If it does not, try `ipconfig /flushdns`.
5. Start the server (manual WSL command or optional Windows-login launcher) and visit **http://sic-studio.localhost:8765/** in Chrome.

The **`:8765` is necessary** unless you separately configure a local reverse proxy on port 80. The URL is HTTP on your own loopback, which is fine for development, not a network deployment. Prefer `.localhost` instead of `.project` or `.test`: browser APIs such as clipboard copying require a secure context, and localhost-like names are treated as potentially trustworthy. If the copy button does not work despite this, use `http://127.0.0.1:8765` or `http://localhost:8765`. Chrome can create an app shortcut for any of these addresses. If a Chrome app shortcut was installed at an old address, install a new one at your chosen address.

## C. Optional Windows pywebview desktop application

`desktop.py` wraps the *same frontend* and the *same Python server handler* in a native window; no WSL browser shortcut is necessary.

1. Install Windows Python 3 and ensure the `py` launcher works in a Windows **PowerShell**, not inside WSL: `py -3 --version`.
2. Install `pywebview` once in that Windows Python interpreter:

   ```powershell
   py -3 -m pip install pywebview
   ```

3. If your project is only inside WSL, consider using Explorer to copy the project to a **Windows development location** like `%USERPROFILE%\Documents\sic-circuit-studio`. This is a second project copy which **does not update automatically** from WSL. The preferred long-term solution is a Git repository and one shared primary source location. Alternatively try launching the Windows script directly from Explorer through `\\wsl.localhost\<Distro>\home\...`, but behavior depends on Windows and WSL permissions. Do not assume it works untested.
4. In Windows Explorer inside that project, double-click `scripts\start_desktop_windows.cmd`. This launches the desktop window and an ephemeral loopback server; closing the window shuts it down.
5. Optional compiled executable: `scripts\build_desktop_windows.cmd` requires PyInstaller, and must be executed **on Windows**. Rebuild the `.exe` after any code update; a frozen `.exe` does not read changed source files.

Chrome-app vs pywebview: both have their own window and icon, but are different implementations. The Chrome app uses the server started by `sic-studio`; the pywebview desktop app starts its own server and needs Windows Python + pywebview. Only one canonical source tree will truly be updated by one ZIP update command.

## Updates and backups

1. Keep your existing WSL project (`sic-circuit-studio`) and old backups intact.
2. Place `sic-circuit-studio-v0.3.1.zip` next to the WSL project.
3. **While no Studio server is running**, run:

   ```bash
   cd ~/Bachelorstudium/Bachelorarbeit/github/sic-circuit-studio
   sic-studio-update ../sic-circuit-studio-v0.3.1.zip
   python3 -m unittest discover -s tests -v
   sic-studio
   ```

4. The updater snapshots existing project files in a version-labelled backup directory; it does not alter your existing `squdi` project.
5. Chrome app and browser refresh to pick up the new source files automatically; reload the window (`Ctrl+R`) after the backend restarts. Pywebview from the same source directory does too. A separate Windows source copy or compiled `.exe` must be updated/rebuilt independently.


### v0.3.2 — AVG IDP.Generic and Windows sign-in

The old `install_wsl_windows_autostart.sh` made a VBScript in Windows Startup. It is retired. If AVG detects `SiC Circuit Studio WSL Server.vbs`, do **not** create a blanket exclusion. Remove the VBS in `Win+R -> shell:startup`, use quarantine when appropriate and run a security scan.

For an optional non-VBS startup use Windows **Task Scheduler**: Create Task, name `SiC Studio Local Server`, Trigger `At log on` (your account), Action `Start a program`, Program `wsl.exe`, Arguments `-d <YourDistributionName> -e bash -lc "cd /home/dennis/Bachelorstudium/Bachelorarbeit/github/sic-circuit-studio && exec python3 server.py"` (replace your own WSL distribution name and Linux path). Set to run **only when logged on** and don't grant elevated privileges. Check `wsl.exe --list --quiet` in PowerShell first. Only configure this after reviewing the exact task action; it creates a localhost server on port 8765. A scheduled task may also trigger security software: do not suppress AV warnings without investigating.

A Chrome app installed from `http://127.0.0.1:8765` and one installed from `http://sic-studio.localhost:8765` have different origins. Export your saved circuit JSON first, uninstall the older app at `chrome://apps`, then browse to the new URL and use Chrome's **Install page as app**. The URL only works while the local server is running. Windows Python is not needed for a WSL/Chrome-only workflow.

## v0.3.3: Start the WSL server without a persistent terminal

`bash scripts/start_server_background.sh` uses `nohup` and redirects stdin, stdout
and stderr so its invoking shell can finish. Logs go to
`~/.local/state/sic-studio/server.log`. A check of `/api/health` avoids starting
another server if the expected local Studio service is already running.

For Windows Task Scheduler, set a trigger **At log on** and configure **Action:
Start a program** with Program `C:\Windows\System32\wsl.exe` and arguments
(adjust distro using `wsl --list --quiet`):

```
-d Ubuntu -e bash /home/dennis/Bachelorstudium/Bachelorarbeit/github/sic-circuit-studio/scripts/start_server_background.sh
```

Replace the existing task action (which executes `server.py` in the foreground);
do not create two tasks for the same port. A terminal window may appear briefly
when WSL starts but should not stay open. Some WSL configurations shut down the
distribution after its last interactive session exits; after reboot check
`http://sic-studio.localhost:8765/api/health`. If background WSL is stopped,
consult Microsoft WSL documentation and use the terminal launcher until you
have a tested, approved local service setup. Do not disable antivirus protection
or create an exception merely to hide a console window.

This task and the Chrome shortcut are Windows account settings. They do NOT move
when you copy the project folder to another PC.

## Moving the project to a second PC

Copy only `sic-circuit-studio/` and optionally `sic-circuit-studio-backups/`,
not unrelated `squdi/` or `qudi-core/` Git repositories unless their state is
explicitly reconciled. A source archive can preserve your whole Studio folder:

```bash
cd ~/Bachelorstudium/Bachelorarbeit/github
tar -czf ~/sic-studio-sync.tar.gz sic-circuit-studio sic-circuit-studio-backups
```

Transfer the archive through a trusted channel. On the destination, stop its
server, preserve/rename the existing Studio folders, extract the archive into
that machine's `github/` folder, then run
`bash scripts/install_launcher.sh` and `python3 -m unittest discover -s tests -v`.
Never move Windows-specific Chrome, Task Scheduler or hosts settings by copying
only a WSL source folder.
