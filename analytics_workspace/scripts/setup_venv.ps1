# Set up analytics_workspace/.venv with the pinned stack + Natural Earth 110m basemap.
# Run from repo root or analytics_workspace/:
#   powershell -File analytics_workspace/scripts/setup_venv.ps1

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

Write-Host "== analytics workspace: $Root"

if (-not (Test-Path ".venv")) {
    Write-Host "== creating .venv"
    python -m venv .venv
}

$Py = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $Py)) {
    Write-Error "venv python missing at $Py"
}

Write-Host "== upgrading pip"
& $Py -m pip install -U pip wheel

Write-Host "== installing requirements.txt"
& $Py -m pip install -r requirements.txt

Write-Host "== downloading Natural Earth 110m basemap"
& $Py scripts\download_basemap.py

Write-Host "== smoke test"
& $Py scripts\smoke_test.py

Write-Host "== done. Use: $Py"
