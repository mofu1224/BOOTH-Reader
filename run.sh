#!/bin/sh
# Generic single entry point (POSIX stub).
# BOOTH-Reader is Windows x64 only by design (BAT launcher, Windows ACL,
# win-x64 vendored runtime in vendor/windows-x64). This stub exists so that
# `./run.sh` fails with a clear message instead of an obscure error.
# Ordinary use on Windows: run.cmd (cmd) or run.ps1 (PowerShell), or start-web.bat.
set -u
echo "BOOTH-Reader is Windows x64 only. On Windows run: run.cmd  (or: run.ps1 / start-web.bat)" >&2
echo "Reason: portable runtime, browser snapshot and ACL handling target windows-x86_64 (see PORTABLE.md)." >&2
exit 1
