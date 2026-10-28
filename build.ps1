# Build the KY bracket desktop app.
#
#   .\build.ps1                    app bundle only     -> dist\KYBracket\
#   .\build.ps1 -Portable          bundle + portable   -> dist\KYBracket-portable.zip
#   .\build.ps1 -Setup             bundle + installer  -> dist\KYBracket-Setup.exe
#   .\build.ps1 -Portable -Setup   bundle + both outputs
#   .\build.ps1 -NoData            bundle without db/images (quick test build)
#
# Requirements: .venv with PySide6 + pyinstaller; Inno Setup 6 for -Setup.
# Note: keep this file ASCII-only. Windows PowerShell 5.1 decodes scripts
# without a BOM as ANSI, and non-ASCII comments can swallow line breaks.

param(
    [switch]$Setup,
    [switch]$NoData,
    [switch]$Portable
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$python = Join-Path $root ".venv\Scripts\python.exe"
$dist = Join-Path $root "dist"
$work = Join-Path $root "build\pyinstaller"
$target = Join-Path $dist "KYBracket"
$normalize = Join-Path $root "scraper\normalize.py"
$entry = Join-Path $root "app\main.py"
$zipOut = Join-Path $dist "KYBracket-portable.zip"

# Locate ISCC.exe. Inno Setup 6 installed per-user by winget lives under
# %LOCALAPPDATA%\Programs, so the registry lookup comes first and the well-known
# paths only act as a fallback.
function Find-Iscc {
    $keys = @(
        "HKCU:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\Inno Setup 6_is1",
        "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\Inno Setup 6_is1",
        "HKLM:\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\Inno Setup 6_is1"
    )
    foreach ($key in $keys) {
        if (-not (Test-Path $key)) { continue }
        $loc = (Get-ItemProperty -Path $key -Name InstallLocation -ErrorAction SilentlyContinue).InstallLocation
        if (-not $loc) { continue }
        $candidate = Join-Path $loc "ISCC.exe"
        if (Test-Path $candidate) { return $candidate }
    }
    $paths = @(
        "C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
        "C:\Program Files\Inno Setup 6\ISCC.exe"
    )
    if ($env:LOCALAPPDATA) {
        $paths = @((Join-Path $env:LOCALAPPDATA "Programs\Inno Setup 6\ISCC.exe")) + $paths
    }
    foreach ($path in $paths) {
        if (Test-Path $path) { return $path }
    }
    return $null
}

if (-not (Test-Path $python)) {
    Write-Host "ERROR venv not found: $python"
    exit 1
}

Write-Host "== 1/3 PyInstaller bundle =="
if (Test-Path $target) {
    Remove-Item $target -Recurse -Force
}
Push-Location $root
try {
    & $python -m PyInstaller `
        --noconfirm `
        --clean `
        --windowed `
        --name KYBracket `
        --distpath $dist `
        --workpath $work `
        --specpath $work `
        --collect-all pypinyin `
        $entry
    if ($LASTEXITCODE -ne 0) {
        Write-Host "PyInstaller FAILED exit=$LASTEXITCODE"
        exit $LASTEXITCODE
    }
}
finally {
    Pop-Location
}

# scraper/normalize.py is imported at runtime through sys.path, so PyInstaller
# cannot see it. Copy it into _internal\scraper (the frozen sys._MEIPASS\scraper).
Write-Host "== 2/3 data payload =="
$internal = Join-Path $target "_internal"
if (-not (Test-Path $internal)) {
    $internal = $target
}
$scraperDir = Join-Path $internal "scraper"
New-Item -ItemType Directory -Force -Path $scraperDir | Out-Null
Copy-Item $normalize $scraperDir -Force
Write-Host "   normalize.py -> $scraperDir"

if (-not $NoData) {
    $payload = Join-Path $target "data"
    New-Item -ItemType Directory -Force -Path $payload | Out-Null
    Copy-Item (Join-Path $root "scraper\data\ky.db") $payload -Force
    foreach ($name in @("images", "thumbs")) {
        $source = Join-Path $root ("scraper\data\" + $name)
        if (Test-Path $source) {
            Copy-Item $source (Join-Path $payload $name) -Recurse -Force
        }
    }
    $payloadSize = (Get-ChildItem $payload -Recurse -File |
        Measure-Object -Sum Length).Sum / 1MB
    Write-Host ("   data payload: {0:N1} MB" -f $payloadSize)
}
else {
    Write-Host "   skipped (-NoData)"
}

$exe = Join-Path $target "KYBracket.exe"
if (-not (Test-Path $exe)) {
    Write-Host "ERROR exe not produced: $exe"
    exit 1
}
$bundleSize = (Get-ChildItem $target -Recurse -File |
    Measure-Object -Sum Length).Sum / 1MB
Write-Host ("   bundle: {0:N1} MB -> {1}" -f $bundleSize, $exe)

Write-Host "== 3/3 output package =="
if (-not $Setup -and -not $Portable) {
    Write-Host "   skipped (no -Setup / -Portable)"
    Write-Host "DONE (app bundle only)"
    exit 0
}

if ($Portable) {
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    if (Test-Path $zipOut) {
        Remove-Item $zipOut -Force
    }
    # includeBaseDirectory = true: the archive holds a single top level folder.
    [IO.Compression.ZipFile]::CreateFromDirectory(
        $target,
        $zipOut,
        [IO.Compression.CompressionLevel]::Optimal,
        $true)
    if (-not (Test-Path $zipOut)) {
        Write-Host "ERROR portable zip not produced: $zipOut"
        exit 1
    }
    $zipSize = (Get-Item $zipOut).Length / 1MB
    Write-Host ("   portable: {0} ({1:N1} MB)" -f $zipOut, $zipSize)
}

if ($Setup) {
    $iscc = Find-Iscc
    if (-not $iscc) {
        Write-Host "ERROR Inno Setup not found."
        Write-Host "Install it with: winget install --id JRSoftware.InnoSetup -e"
        exit 1
    }
    Write-Host "   iscc: $iscc"
    & $iscc (Join-Path $root "installer.iss")
    if ($LASTEXITCODE -ne 0) {
        Write-Host "ISCC FAILED exit=$LASTEXITCODE"
        exit $LASTEXITCODE
    }
    $setupExe = Join-Path $dist "KYBracket-Setup.exe"
    if (-not (Test-Path $setupExe)) {
        Write-Host "ERROR installer not produced"
        exit 1
    }
    $setupSize = (Get-Item $setupExe).Length / 1MB
    Write-Host ("   installer: {0} ({1:N1} MB)" -f $setupExe, $setupSize)
}

Write-Host "DONE"
exit 0
