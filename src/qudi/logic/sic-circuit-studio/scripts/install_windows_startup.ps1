# Optional: start local server whenever you log in to Windows.
# Run on Windows PowerShell with: powershell -ExecutionPolicy Bypass -File .\scripts\install_windows_startup.ps1
# The Python server will run only on your computer (127.0.0.1).
$project = Split-Path -Parent $PSScriptRoot
$serverCmd = Join-Path $PSScriptRoot 'start_server_windows.cmd'
$startup = [Environment]::GetFolderPath('Startup')
$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut((Join-Path $startup 'SiC Circuit Studio Server.lnk'))
$shortcut.TargetPath = $serverCmd
$shortcut.WorkingDirectory = $project
$shortcut.WindowStyle = 7
$shortcut.Description = 'Starts the local-only SiC Circuit Studio server at Windows sign-in'
$shortcut.Save()
Write-Host "Startup shortcut created at $startup"
Write-Host "Remove 'SiC Circuit Studio Server.lnk' from Startup to disable it."
