#Requires -Version 5.1
<#
.SYNOPSIS
  Generic single entry point (Windows PowerShell). Same as start-web.bat / run.cmd.
  Clone -> run.ps1 -> automatic first-run setup -> web UI.
.EXAMPLE
  & .\run.ps1
  & .\run.ps1 8080
#>
[CmdletBinding()]
param(
    [Parameter(ValueFromRemainingArguments = $true)][string[]]$ForwardArgs
)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot
$env:HOME = Join-Path $root '.cache\home'
$env:USERPROFILE = $env:HOME
$env:APPDATA = Join-Path $env:HOME 'AppData\Roaming'
$env:LOCALAPPDATA = Join-Path $env:HOME 'AppData\Local'
$env:TEMP = Join-Path $root '.cache\tmp'
$env:TMP = $env:TEMP
$env:PSModuleAnalysisCachePath = Join-Path $root '.cache\powershell\ModuleAnalysisCache'
$env:PYTHONHOME = $null
$env:PYTHONPATH = $null
$env:PYTHONNOUSERSITE = '1'
$env:PYTHONUTF8 = '1'
$env:PYTHONIOENCODING = 'utf-8'
$env:PLAYWRIGHT_BROWSERS_PATH = Join-Path $root '.playwright-browsers'
$bootstrap = Join-Path $root 'tools\bootstrap.ps1'
& "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe" -NoLogo -NoProfile -ExecutionPolicy Bypass -File $bootstrap -Mode web @ForwardArgs
exit $LASTEXITCODE
