@echo off
setlocal
call "%~dp0tools\portable-env.bat"
rem OS-only setup; supports --repair --offline --skip-browser --check --update.
rem All dependencies are supplied in vendor/; no network or system installs.
set "PLAYWRIGHT_BROWSERS_PATH=%~dp0.playwright-browsers"
"%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe" -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0tools\bootstrap.ps1" -Mode setup %*
set "RESULT=%ERRORLEVEL%"
endlocal & exit /b %RESULT%
