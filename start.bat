@echo off
setlocal
call "%~dp0tools\portable-env.bat"
rem Single entry point. Just double-click or run without arguments.
rem Setup, repairs, the port and the browser are handled automatically.
rem   start.bat              Web UI; the browser opens by itself
rem   start.bat 8080         Web UI on a chosen port
rem   start.bat --repair     rebuild the pinned local environment
rem   start.bat --check      report whether setup is needed, then exit
rem   start.bat doctor       CLI commands run through the same setup
rem   start.bat cli --help   explicit CLI mode
set "PLAYWRIGHT_BROWSERS_PATH=%~dp0.playwright-browsers"
"%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe" -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0tools\bootstrap.ps1" -Mode auto %*
set "RESULT=%ERRORLEVEL%"
rem Keep the window open only when a plain double-click fails, not on Ctrl+C.
if not "%RESULT%"=="0" if not "%RESULT%"=="130" if "%~1"=="" pause >nul
endlocal & exit /b %RESULT%
