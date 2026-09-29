# Citrine installer (Windows)
#
# One command that takes a fresh machine to a working Citrine:
#   powershell -ExecutionPolicy Bypass -File scripts\install.ps1
#
# It verifies (and offers to install) the two prerequisites, installs the
# Node and Python dependencies, validates the build, and registers the app
# with Windows: PATH entry, desktop + Start Menu shortcuts, and a real
# Add/Remove Programs entry whose uninstaller is scripts\uninstall.ps1.
#
# Idempotent: safe to re-run over an existing install; every step is either
# a no-op or converges to the same end state.

[CmdletBinding()]
param(
    # Skip the validation build. Use when you know the tree builds and just
    # want the wiring (shortcuts, PATH, registry) redone.
    [switch]$SkipBuild,
    # Assume "yes" to any prerequisite install prompts.
    [switch]$Yes
)

$ErrorActionPreference = 'Stop'

# ---------------------------------------------------------------- helpers ---

function Write-Step($message) { Write-Host "`n==> $message" -ForegroundColor Cyan }

function Test-Command($name) {
    return [bool](Get-Command $name -ErrorAction SilentlyContinue)
}

function Test-Winget {
    # winget may exist but be broken inside non-interactive sessions; the
    # version call is the cheap way to know it actually works.
    try { winget --version *> $null; return $true } catch { return $false }
}

function Find-RepoRoot {
    $root = Split-Path -Parent $PSScriptRoot
    if (-not (Test-Path (Join-Path $root 'package.json'))) {
        throw "This script must run from the Citrine repo (scripts\install.ps1)."
    }
    return $root
}

function Confirm-Install($label) {
    if ($Yes) { return $true }
    $answer = Read-Host "$label is required but missing. Install it now? [y/N]"
    return ($answer -match '^[Yy]')
}

# ------------------------------------------------------------------- main ---

$root = Find-RepoRoot
$binDir = Join-Path $root 'bin'
Write-Host "Installing Citrine from: $root"

# --- 1. Prerequisites ------------------------------------------------------

Write-Step 'Checking prerequisites'

$haveNode = Test-Command 'node'
if ($haveNode) {
    $nodeMajor = [int]((node --version) -replace '^v(\d+)\..*$', '$1')
    if ($nodeMajor -lt 22) { $haveNode = $false }
}
if (-not $haveNode) {
    if ((Test-Winget) -and (Confirm-Install 'Node.js 22+')) {
        winget install --id OpenJS.NodeJS.LTS -e --accept-package-agreements --accept-source-agreements
        if ($LASTEXITCODE -ne 0) { throw 'winget failed to install Node.js. Install Node 22+ from https://nodejs.org and re-run.' }
        # The current session will not see the new PATH until it is refreshed.
        $env:Path = [Environment]::GetEnvironmentVariable('Path', 'Machine') + ';' + [Environment]::GetEnvironmentVariable('Path', 'User')
        if (-not (Test-Command 'node')) {
            throw 'Node.js was installed but is not visible in this session. Open a new terminal and re-run this script.'
        }
    } else {
        throw 'Node.js 22+ is required. Install it from https://nodejs.org and re-run this script.'
    }
}
Write-Host "Node: $(node --version)"

$haveUv = Test-Command 'uv'
if (-not $haveUv) {
    if ((Test-Winget) -and (Confirm-Install 'uv (Python manager)')) {
        winget install --id astral-sh.uv -e --accept-package-agreements --accept-source-agreements
        if ($LASTEXITCODE -ne 0) { throw 'winget failed to install uv. Install it from https://docs.astral.sh/uv/ and re-run.' }
        $env:Path = [Environment]::GetEnvironmentVariable('Path', 'Machine') + ';' + [Environment]::GetEnvironmentVariable('Path', 'User')
        if (-not (Test-Command 'uv')) {
            throw 'uv was installed but is not visible in this session. Open a new terminal and re-run this script.'
        }
    } else {
        throw 'uv is required to manage the Python backend. Install it from https://docs.astral.sh/uv/ and re-run this script.'
    }
}
Write-Host "uv:   $((uv --version) -join '')"

# --- 2. Node dependencies --------------------------------------------------

Write-Step 'Installing Node dependencies'
Push-Location $root
try {
    if (Test-Path 'node_modules') {
        # Already installed; npm ci would delete and re-fetch everything.
        # npm install converges to the lockfile state and is a fast no-op here.
        npm install --no-audit --no-fund
    } elseif (Test-Path 'package-lock.json') {
        npm ci --no-audit --no-fund
        if ($LASTEXITCODE -ne 0) {
            Write-Host 'npm ci failed (lockfile drift?), falling back to npm install' -ForegroundColor Yellow
            npm install --no-audit --no-fund
        }
    } else {
        npm install --no-audit --no-fund
    }
    if ($LASTEXITCODE -ne 0) { throw 'npm install failed.' }
} finally { Pop-Location }

# --- 3. Python backend -----------------------------------------------------

Write-Step 'Setting up the Python backend'
Push-Location (Join-Path $root 'backend')
try {
    if (-not (Test-Path '.venv')) {
        uv venv --python 3.11
        if ($LASTEXITCODE -ne 0) { throw 'uv venv failed.' }
    }
    uv sync --extra dev
    if ($LASTEXITCODE -ne 0) { throw 'uv sync failed.' }
} finally { Pop-Location }

# --- 4. Validation build ---------------------------------------------------

if (-not $SkipBuild) {
    Write-Step 'Building the app (validation)'
    Push-Location $root
    try {
        npm run build
        if ($LASTEXITCODE -ne 0) { throw 'Build failed. Fix the error above and re-run.' }
    } finally { Pop-Location }
} else {
    Write-Host 'Skipping build (-SkipBuild).' -ForegroundColor Yellow
}

# --- 5. Windows integration -------------------------------------------------

Write-Step 'Registering Citrine with Windows'

# 5a. `citrine` on PATH (User scope, append only if absent).
$userPath = [Environment]::GetEnvironmentVariable('Path', 'User')
$segments = $userPath -split ';'
if (($segments -notcontains $binDir) -and ($segments -notcontains ($binDir.TrimEnd('\')))) {
    [Environment]::SetEnvironmentVariable('Path', ($userPath.TrimEnd(';') + ';' + $binDir), 'User')
    Write-Host "Added to user PATH: $binDir"
} else {
    Write-Host 'PATH entry already present.'
}

# 5b. Shortcuts (desktop + Start Menu).
$ws = New-Object -ComObject WScript.Shell
$icon = Join-Path $root 'build\icon.ico'
$uninstallScript = Join-Path $PSScriptRoot 'uninstall.ps1'

$targets = @(
    @{ Name = 'Citrine'; Path = (Join-Path $root 'bin\citrine-launch.vbs'); Dir = $root },
    @{ Name = 'Uninstall Citrine'; Path = $uninstallScript; Dir = $root }
)

$desktop = [Environment]::GetFolderPath('Desktop')
$startMenu = Join-Path $env:APPDATA 'Microsoft\Windows\Start Menu\Programs'
$shortcutDirs = @($desktop, $startMenu)

foreach ($dir in $shortcutDirs) {
    foreach ($target in $targets) {
        $lnk = Join-Path $dir ($target.Name + '.lnk')
        $sc = $ws.CreateShortcut($lnk)
        if ($target.Name -eq 'Citrine') {
            $sc.TargetPath = 'wscript.exe'
            $sc.Arguments = "`"$($target.Path)`""
        } else {
            $sc.TargetPath = 'powershell.exe'
            $sc.Arguments = "-NoProfile -ExecutionPolicy Bypass -File `"$($target.Path)`""
        }
        $sc.WorkingDirectory = $target.Dir
        if (Test-Path $icon) { $sc.IconLocation = $icon }
        $sc.Save()
    }
}
Write-Host 'Desktop and Start Menu shortcuts created.'

# 5c. Add/Remove Programs entry, so "Citrine" shows in Settings > Apps.
$regKey = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\Citrine'
if (-not (Test-Path $regKey)) { New-Item -Path $regKey -Force | Out-Null }
$pkg = Get-Content (Join-Path $root 'package.json') -Raw | ConvertFrom-Json
New-ItemProperty -Path $regKey -Name 'DisplayName'    -Value 'Citrine' -PropertyType String -Force | Out-Null
New-ItemProperty -Path $regKey -Name 'DisplayVersion' -Value $pkg.version -PropertyType String -Force | Out-Null
New-ItemProperty -Path $regKey -Name 'Publisher'      -Value 'Citrine' -PropertyType String -Force | Out-Null
New-ItemProperty -Path $regKey -Name 'DisplayIcon'    -Value $icon -PropertyType String -Force | Out-Null
New-ItemProperty -Path $regKey -Name 'InstallLocation' -Value $root -PropertyType String -Force | Out-Null
New-ItemProperty -Path $regKey -Name 'UninstallString' -Value ("powershell.exe -NoProfile -ExecutionPolicy Bypass -File `"$uninstallScript`"") -PropertyType String -Force | Out-Null
New-ItemProperty -Path $regKey -Name 'NoModify' -Value 1 -PropertyType DWord -Force | Out-Null
New-ItemProperty -Path $regKey -Name 'NoRepair' -Value 1 -PropertyType DWord -Force | Out-Null
Write-Host 'Add/Remove Programs entry created.'

# --- 6. Done ----------------------------------------------------------------

Write-Host ''
Write-Host 'Citrine is installed.' -ForegroundColor Green
Write-Host ''
Write-Host '  Start it:      Citrine            (any terminal)'
Write-Host '                 double-click the Citrine desktop shortcut'
Write-Host '  Set up:        citrine setup      (providers, keys, search)'
Write-Host '  Uninstall:     Settings > Apps, or scripts\uninstall.ps1'
Write-Host ''
Write-Host 'Note: a terminal opened before this install will not have the'
Write-Host '"citrine" command yet. Open a fresh one.'
