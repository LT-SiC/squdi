#!/usr/bin/env bash
# The former VBS autostart installer has been retired: some AV behavior shields flag it.
printf '%s\n' 'This installer is retired: it no longer writes VBScript into Windows Startup.' 'Use Windows Task Scheduler to launch wsl.exe directly at logon, or start sic-studio manually.' 'Details: docs/LOCAL_INSTALLATION.md.'
exit 0
