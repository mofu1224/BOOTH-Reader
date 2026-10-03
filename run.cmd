@echo off
setlocal
call "%~dp0tools\portable-env.bat"
rem Generic single entry point (Windows cmd). Same as start-web.bat:
rem clone -> run.cmd -> automatic first-run setup -> web UI.
rem Usage: run.cmd [port]
set "PLAYWRIGHT_BROWSERS_PATH=%~dp0.playwright-browsers"
"%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe" -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0tools\bootstrap.ps1" -Mode web %*
set "RESULT=%ERRORLEVEL%"
endlocal & exit /b %RESULT%
