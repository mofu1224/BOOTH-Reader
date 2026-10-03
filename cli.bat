@echo off
setlocal
call "%~dp0tools\portable-env.bat"
rem No system Python fallback; missing or relocated environments repair locally.
set "PLAYWRIGHT_BROWSERS_PATH=%~dp0.playwright-browsers"
"%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe" -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0tools\bootstrap.ps1" -Mode cli %*
set "RESULT=%ERRORLEVEL%"
if "%~1"=="" pause
endlocal & exit /b %RESULT%
