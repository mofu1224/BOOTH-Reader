#Requires -Version 5.1
# OS-only bootstrap. ASCII literals keep Windows PowerShell 5.1 interoperable.
param(
    [ValidateSet('setup', 'cli', 'web')][string]$Mode = 'setup'
)
# Advanced binding consumes --db as the common -Debug alias before forwarding.
# A basic script leaves all remaining CLI arguments intact in $args.
$ForwardArgs = @($args)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$scratch = $null
$oldRuntime = $null
function ArchiveHash([string]$Path) {
    $stream = [IO.File]::OpenRead($Path)
    $sha = [Security.Cryptography.SHA256]::Create()
    try { return ([BitConverter]::ToString($sha.ComputeHash($stream))).Replace('-', '').ToLowerInvariant() }
    finally { $sha.Dispose(); $stream.Dispose() }
}
function AssertOwnedPath([string]$Path) {
    $full = [IO.Path]::GetFullPath($Path)
    if (-not $full.StartsWith($root + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) {
        throw 'Generated path escapes the repository.'
    }
    $current = $full
    while ($current -and $current -ne $root) {
        if (Test-Path -LiteralPath $current) {
            $item = Get-Item -LiteralPath $current -Force
            if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) {
                throw 'Portable generated paths must not use junctions or symlinks.'
            }
        }
        $current = Split-Path -Parent $current
    }
}
function RestoreVendorAsset([string]$Name) {
    $vendor = Join-Path $root 'vendor\windows-x64'
    $index = [IO.File]::ReadAllText((Join-Path $vendor 'manifest.json')) | ConvertFrom-Json
    $asset = $index.assets.$Name
    $destination = Join-Path $root $asset.destination
    AssertOwnedPath $destination
    [IO.Directory]::CreateDirectory((Split-Path -Parent $destination)) | Out-Null
    $temporary = Join-Path $env:TEMP ('vendor-' + [Guid]::NewGuid().ToString('N'))
    $output = [IO.File]::Create($temporary)
    try {
        foreach ($part in $asset.parts) {
            $source = [IO.Path]::GetFullPath((Join-Path $vendor $part.file))
            if (-not $source.StartsWith($vendor + '\', [StringComparison]::OrdinalIgnoreCase)) {
                throw 'Vendor chunk escapes its directory.'
            }
            AssertOwnedPath $source
            if ((ArchiveHash $source) -ne $part.sha256) { throw 'Vendored chunk SHA-256 mismatch.' }
            $input = [IO.File]::OpenRead($source)
            try { $input.CopyTo($output) } finally { $input.Dispose() }
        }
    } finally { $output.Dispose() }
    try {
        if ((ArchiveHash $temporary) -ne $asset.sha256) { throw 'Vendored archive SHA-256 mismatch.' }
        Move-Item -LiteralPath $temporary -Destination $destination -Force
    } finally {
        if (Test-Path -LiteralPath $temporary) { Remove-Item -LiteralPath $temporary -Force }
    }
}
function Expand-TarGz([string]$Archive, [string]$Destination) {
    # Unicode-safe tar.gz extraction with OS PowerShell and .NET only. Windows
    # tar.exe cannot open archives under paths the active code page cannot
    # represent, so the pinned runtime is unpacked here instead.
    Add-Type -AssemblyName System.IO.Compression | Out-Null
    $buffer = New-Object byte[] (4 * 1024 * 1024)
    $header = New-Object byte[] 512
    function Skip-Bytes([System.IO.Stream]$Stream, [long]$Count) {
        while ($Count -gt 0) {
            $chunk = [int][Math]::Min($Count, [long]$buffer.Length)
            $read = $Stream.Read($buffer, 0, $chunk)
            if ($read -le 0) { throw 'Unexpected end of archive.' }
            $Count -= $read
        }
    }
    $source = [IO.File]::OpenRead($Archive)
    $stream = New-Object IO.Compression.GZipStream($source, [IO.Compression.CompressionMode]::Decompress)
    try {
        while ($true) {
            $offset = 0
            while ($offset -lt 512) {
                $read = $stream.Read($header, $offset, 512 - $offset)
                if ($read -le 0) { break }
                $offset += $read
            }
            if ($offset -lt 512 -or $header[0] -eq 0) { break }
            $name = [Text.Encoding]::UTF8.GetString($header, 0, 100).TrimEnd([char]0)
            $sizeText = [Text.Encoding]::ASCII.GetString($header, 124, 12).Trim([char]0, [char]32)
            $size = if ($sizeText.Length -gt 0) { [Convert]::ToInt64($sizeText, 8) } else { [long]0 }
            $typeByte = $header[156]
            $prefix = [Text.Encoding]::UTF8.GetString($header, 345, 155).TrimEnd([char]0)
            if ($prefix.Length -gt 0) { $name = $prefix + '/' + $name }
            if ($typeByte -ne 0x30 -and $typeByte -ne 0x35 -and $typeByte -ne 0x00) {
                throw 'Unsupported tar entry; the vendored runtime must be a plain ustar archive.'
            }
            $relative = $name.Replace('/', [IO.Path]::DirectorySeparatorChar)
            $full = [IO.Path]::GetFullPath((Join-Path $Destination $relative))
            AssertOwnedPath $full
            $extended = '\\?\' + $full
            if ($typeByte -eq 0x35) {
                [IO.Directory]::CreateDirectory($extended) | Out-Null
            } else {
                $parent = [IO.Path]::GetDirectoryName($full)
                [IO.Directory]::CreateDirectory('\\?\' + $parent) | Out-Null
                $output = [IO.File]::Create($extended)
                try {
                    $remaining = $size
                    while ($remaining -gt 0) {
                        $chunk = [int][Math]::Min($remaining, [long]$buffer.Length)
                        $read = $stream.Read($buffer, 0, $chunk)
                        if ($read -le 0) { throw 'Unexpected end of archive.' }
                        $output.Write($buffer, 0, $read)
                        $remaining -= $read
                    }
                } finally { $output.Dispose() }
            }
            $padding = [long]((512 - ($size % 512)) % 512)
            if ($padding -gt 0) { Skip-Bytes $stream $padding }
        }
    } finally {
        $stream.Dispose()
        $source.Dispose()
    }
}
try {
    $manifest = [IO.File]::ReadAllText((Join-Path $root 'portable-manifest.json')) | ConvertFrom-Json
    $arch = $env:PROCESSOR_ARCHITECTURE
    if ($env:PROCESSOR_ARCHITEW6432) { $arch = $env:PROCESSOR_ARCHITEW6432 }
    if ($arch -ne 'AMD64') { throw 'Portable target is Windows x64 (AMD64) only.' }
    if ([Environment]::OSVersion.Version.Build -lt $manifest.minimumWindowsBuild) {
        throw 'Windows 10 build 17763 or later is required.'
    }
    # Process-local environment; the parent shell and persistent state are untouched.
    $env:PYTHONHOME = $null
    $env:PYTHONPATH = $null
    $env:PYTHONNOUSERSITE = '1'
    $env:PYTHONUTF8 = '1'
    $env:PYTHONIOENCODING = 'utf-8'
    $env:TEMP = Join-Path $root '.cache\tmp'
    $env:TMP = $env:TEMP
    $env:HOME = Join-Path $root '.cache\home'
    $env:USERPROFILE = $env:HOME
    $env:APPDATA = Join-Path $env:HOME 'AppData\Roaming'
    $env:LOCALAPPDATA = Join-Path $env:HOME 'AppData\Local'
    $env:HOMEDRIVE = [IO.Path]::GetPathRoot($env:HOME).TrimEnd('\')
    $env:HOMEPATH = $env:HOME.Substring($env:HOMEDRIVE.Length)
    foreach ($path in @($env:TEMP, $env:HOME, $env:APPDATA, $env:LOCALAPPDATA,
                        (Join-Path $root '.tools'), (Join-Path $root '.venv'),
                        (Join-Path $root '.playwright-browsers'))) {
        AssertOwnedPath $path
    }
    foreach ($path in @($env:TEMP, $env:HOME, $env:APPDATA, $env:LOCALAPPDATA)) {
        [IO.Directory]::CreateDirectory($path) | Out-Null
    }
    # Shell file dialogs resolve standard folders beneath the isolated profile.
    foreach ($name in @('Desktop', 'Documents', 'Downloads', 'Pictures', 'Music', 'Videos')) {
        $path = Join-Path $env:HOME $name
        AssertOwnedPath $path
        [IO.Directory]::CreateDirectory($path) | Out-Null
    }
    $target = Join-Path $root '.tools\python'
    AssertOwnedPath $target
    $exe = Join-Path $target 'python.exe'
    $usable = $false
    if (Test-Path -LiteralPath $exe) {
        $probe = New-Object Diagnostics.Process
        $probe.StartInfo.FileName = $exe
        $probe.StartInfo.Arguments = '-E -s -c "import sys,ssl,sqlite3,venv,ensurepip; print(sys.version.split()[0])"'
        $probe.StartInfo.UseShellExecute = $false
        $probe.StartInfo.CreateNoWindow = $true
        $probe.StartInfo.RedirectStandardOutput = $true
        $probe.StartInfo.RedirectStandardError = $true
        try {
            $probe.Start() | Out-Null
            $version = $probe.StandardOutput.ReadToEnd().Trim()
            $probe.StandardError.ReadToEnd() | Out-Null
            if (-not $probe.WaitForExit(120000)) { $probe.Kill(); throw 'Runtime probe timed out.' }
            $usable = ($probe.ExitCode -eq 0 -and $version -eq $manifest.python.version)
        } catch { $usable = $false } finally { $probe.Dispose() }
    }
    if (-not $usable -and $ForwardArgs -contains '--check') { exit 1 }
    if (-not $usable) {
        $downloads = Join-Path $root '.cache\downloads'
        [IO.Directory]::CreateDirectory($downloads) | Out-Null
        $archive = Join-Path $downloads $manifest.python.asset
        $valid = (Test-Path -LiteralPath $archive) -and
            ((ArchiveHash $archive) -eq $manifest.python.sha256)
        if (-not $valid) {
            RestoreVendorAsset 'python'
            if ((ArchiveHash $archive) -ne $manifest.python.sha256) { throw 'Python publisher SHA-256 mismatch.' }
        }
        $scratch = Join-Path $env:TEMP ('bootstrap-' + [Guid]::NewGuid().ToString('N'))
        [IO.Directory]::CreateDirectory($scratch) | Out-Null
        Expand-TarGz $archive $scratch
        $inner = Join-Path $scratch 'python'
        $candidate = Join-Path $inner 'python.exe'
        & $candidate -E -s -c "import ssl, sqlite3, venv, ensurepip"
        if ($LASTEXITCODE -ne 0) { throw 'Python self-check failed.' }
        [IO.Directory]::CreateDirectory((Split-Path -Parent $target)) | Out-Null
        if (Test-Path -LiteralPath $target) {
            $oldRuntime = Join-Path $env:TEMP ('python-backup-' + [Guid]::NewGuid().ToString('N'))
            Move-Item -LiteralPath $target -Destination $oldRuntime
        }
        Move-Item -LiteralPath $inner -Destination $target
    }
    & $exe -E -s -X utf8 (Join-Path $PSScriptRoot 'manage_portable.py') $Mode @ForwardArgs
    $result = $LASTEXITCODE
    if ($result -eq 0 -and $oldRuntime) {
        Remove-Item -LiteralPath $oldRuntime -Recurse -Force
    }
    exit $result
} catch {
    [Console]::Error.WriteLine('[ERROR] ' + $_.Exception.Message)
    exit 1
} finally {
    if ($scratch -and (Test-Path -LiteralPath $scratch)) {
        Remove-Item -LiteralPath $scratch -Recurse -Force
    }
}
