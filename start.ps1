# One-click entry point for the KY bracket scraper (szky1688.com/ky/).
# Usage:
#   .\start.ps1                 # run the full sampled pipeline
#   .\start.ps1 brackets        # route A only
#   .\start.ps1 catalog         # route B1 only
#   .\start.ps1 products        # route B2 (sampled)
#   .\start.ps1 images          # download photos and logos
#   .\start.ps1 crosscheck      # cross-validate route A against route B
#   .\start.ps1 stats           # print database summary

param(
    [string]$Stage = "all",
    [double]$Sample = 0.2,
    [int]$Workers = 3,
    [double]$Interval = 0.5
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path

# Desktop application launcher:  .\start.ps1 app
if ($Stage -eq "app") {
    $python = Join-Path $root ".venv\Scripts\python.exe"
    if (-not (Test-Path $python)) {
        Write-Host "ERROR venv not found. Run: python -m venv .venv"
        Write-Host "Then: .venv\Scripts\python -m pip install PySide6-Essentials"
        exit 1
    }
    $appDir = Join-Path $root "app"
    Push-Location $appDir
    try {
        & $python main.py
        exit $LASTEXITCODE
    }
    finally {
        Pop-Location
    }
}

$scraper = Join-Path $root "scraper"

if (-not (Test-Path $scraper)) {
    Write-Host "ERROR scraper folder not found: $scraper"
    exit 1
}

Push-Location $scraper
try {
    & python -X utf8 run.py $Stage --sample $Sample --workers $Workers --interval $Interval
    $code = $LASTEXITCODE
    if ($code -ne 0) {
        Write-Host "FAILED stage=$Stage exit=$code"
        exit $code
    }
    Write-Host "DONE stage=$Stage"
}
finally {
    Pop-Location
}
