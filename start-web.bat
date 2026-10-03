@echo off
setlocal
call "%~dp0tools\portable-env.bat"
rem Usage: start-web.bat [port]; open the printed URL in your browser.
set "PLAYWRIGHT_BROWSERS_PATH=%~dp0.playwright-browsers"
"%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe" -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0tools\bootstrap.ps1" -Mode web %*
set "RESULT=%ERRORLEVEL%"
endlocal & exit /b %RESULT%
