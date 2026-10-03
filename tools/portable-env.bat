@echo off
rem Internal helper. Call from a setlocal launcher BEFORE starting PowerShell.
for %%R in ("%~dp0..") do set "PORTABLE_ROOT=%%~fR"
set "HOME=%PORTABLE_ROOT%\.cache\home"
set "USERPROFILE=%HOME%"
set "APPDATA=%HOME%\AppData\Roaming"
set "LOCALAPPDATA=%HOME%\AppData\Local"
set "TEMP=%PORTABLE_ROOT%\.cache\tmp"
set "TMP=%TEMP%"
set "PSModuleAnalysisCachePath=%PORTABLE_ROOT%\.cache\powershell\ModuleAnalysisCache"
set "PYTHONHOME="
set "PYTHONPATH="
set "PYTHONNOUSERSITE=1"
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"
exit /b 0
