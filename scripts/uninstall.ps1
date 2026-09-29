# Citrine uninstaller (Windows)
#
# Removes everything scripts\install.ps1 created:
#   - Add/Remove Programs entry
#   - Desktop and Start Menu shortcuts
#   - `citrine` PATH entry
#   - Build output and installed dependencies (out\, node_modules\, backend\.venv)
#
# Your data is preserved by default: the Citrine config, logs, and session
# database live in ~\.citrine and are NOT touched unless you pass -PurgeData.
# The repository itself is kept unless you pass -DeleteSource, so you can
# reinstall with scripts\install.ps1 without re-cloning.
#
#   powershell -ExecutionPolicy Bypass -File scripts\uninstall.ps1
#   ... -PurgeData            # also delete ~\.citrine and %LOCALAPPDATA%\Citrine
#   ... -DeleteSource         # also delete the repository folder
#   ... -KeepDeps             # keep node_modules\.venv\out (faster reinstall)

[CmdletBinding()]
param(
    # Delete user data (~\.citrine, %LOCALAPPDATA%\Citrine logs).
    [switch]$PurgeData,
    # Delete the repository folder itself. Implies removing dependencies.
    [switch]$DeleteSource,
    # Keep node_modules, backend\.venv and out (disk vs reinstall speed).
    [switch]$KeepDeps
)

$ErrorActionPreference = 'Continue'

trap {
    Write-Host ''
    Write-Host ('UNINSTALL ERROR: ' + $_.Exception.Message) -ForegroundColor Red
    exit 1
}

function Write-Step($message) { Write-Host "`n==> $message" -ForegroundColor Cyan }

$root = Split-Path -Parent $PSScriptRoot
if (-not (Test-Path (Join-Path $root 'package.json'))) {
    Write-Warning 'Not running from the Citrine repo; registry/shortcut cleanup only.'
}

Write-Host "Uninstalling Citrine from: $root"

# --- 1. Close a running Citrine ---------------------------------------------

# The dev launcher runs electron/node with the repo path in the command line.
# Match on the path rather than a process name alone so unrelated Electron
# apps are never touched.
Write-Step 'Stopping Citrine if it is running'
Get-CimInstance Win32_Process -Filter "Name = 'electron.exe' OR Name = 'node.exe' OR Name = 'wscript.exe'" |
    Where-Object { $_.CommandLine -and $_.CommandLine.Contains($root) } |
    ForEach-Object {
        Write-Host "  stopping PID $($_.ProcessId)"
        Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
    }

# --- 2. Registry (Add/Remove Programs) ---------------------------------------

Write-Step 'Removing Add/Remove Programs entry'
$regKey = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\Citrine'
if (Test-Path $regKey) {
    Remove-Item $regKey -Force
    Write-Host '  removed.'
} else {
    Write-Host '  not present, skipping.'
}

# --- 3. Shortcuts -------------------------------------------------------------

Write-Step 'Removing shortcuts'
$desktop = [Environment]::GetFolderPath('Desktop')
$startMenu = Join-Path $env:APPDATA 'Microsoft\Windows\Start Menu\Programs'
$shortcutDirs = @($desktop, $startMenu)
foreach ($dir in $shortcutDirs) {
    foreach ($name in @('Citrine.lnk', 'Uninstall Citrine.lnk')) {
        $lnk = Join-Path $dir $name
        if (Test-Path $lnk) {
            Remove-Item $lnk -Force
            Write-Host "  removed $lnk"
        }
    }
}

# --- 4. PATH entry -------------------------------------------------------------

Write-Step 'Removing PATH entry'
$binDir = Join-Path $root 'bin'
$userPath = [Environment]::GetEnvironmentVariable('Path', 'User')
if ($userPath) {
    $kept = ($userPath -split ';') | Where-Object {
        $_ -and ($_.TrimEnd('\') -ne $binDir.TrimEnd('\'))
    }
    if (($kept -join ';') -ne $userPath) {
        [Environment]::SetEnvironmentVariable('Path', ($kept -join ';'), 'User')
        Write-Host "  removed $binDir from user PATH."
    } else {
        Write-Host '  not present, skipping.'
    }
}

# --- 5. Dependencies and build output ------------------------------------------

if ($DeleteSource -or -not $KeepDeps) {
    Write-Step 'Removing dependencies and build output'
    foreach ($rel in @('node_modules', 'out', 'backend\.venv')) {
        $dir = Join-Path $root $rel
        if (Test-Path $dir) {
            Write-Host "  removing $dir"
            Remove-Item $dir -Recurse -Force -ErrorAction SilentlyContinue
        }
    }
}

# --- 6. User data (opt-in) ------------------------------------------------------

if ($PurgeData) {
    Write-Step 'Removing user data (-PurgeData)'
    foreach ($dir in @((Join-Path $env:USERPROFILE '.citrine'), (Join-Path $env:LOCALAPPDATA 'Citrine'))) {
        if (Test-Path $dir) {
            Write-Host "  removing $dir"
            Remove-Item $dir -Recurse -Force -ErrorAction SilentlyContinue
        }
    }
} else {
    Write-Step 'User data preserved'
    Write-Host "  config, logs and sessions are kept in $env:USERPROFILE\.citrine"
    Write-Host '  pass -PurgeData to delete them.'
}

# --- 7. Source (opt-in) ----------------------------------------------------------

if ($DeleteSource) {
    Write-Step 'Removing the repository folder (-DeleteSource)'
    # This script lives inside the folder being deleted, so the deletion has
    # to happen from outside it, after this process exits.
    $parent = Split-Path -Parent $root
    Start-Process -FilePath 'cmd.exe' -ArgumentList @(
        '/c', 'timeout', '/t', '2', '/nobreak', '>', 'nul', '&',
        'rmdir', '/s', '/q', "`"$root`""
    ) -WorkingDirectory $parent -WindowStyle Hidden | Out-Null
    Write-Host "  scheduled removal of $root"
} else {
    Write-Step 'Repository kept'
    Write-Host "  $root is kept so you can reinstall with scripts\install.ps1."
    Write-Host '  pass -DeleteSource to remove it.'
}

Write-Host ''
Write-Host 'Citrine has been uninstalled.' -ForegroundColor Green
