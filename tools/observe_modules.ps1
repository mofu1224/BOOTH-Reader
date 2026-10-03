#Requires -Version 5.1
param([Parameter(Mandatory=$true)][string]$Root,
      [Parameter(Mandatory=$true)][string]$Out)
$ErrorActionPreference = 'Stop'
$rows = @()
foreach ($process in [Diagnostics.Process]::GetProcesses()) {
    try {
        $exe = $process.MainModule.FileName
        if (-not $exe) { continue }
        if (-not $exe.StartsWith($Root, [StringComparison]::OrdinalIgnoreCase)) { continue }
        $modules = @($process.Modules | ForEach-Object { $_.FileName })
        $rows += @{pid=$process.Id; executable=$exe; modules=$modules}
    } catch [ComponentModel.Win32Exception] {
        # Other-user/system processes aren't in the project's observation scope.
    } catch [InvalidOperationException] {
        # A short-lived child may have exited between enumeration and inspection.
    } finally { $process.Dispose() }
}
$json = ConvertTo-Json -InputObject @($rows) -Depth 6
[IO.File]::WriteAllText($Out, $json, (New-Object Text.UTF8Encoding($false)))
