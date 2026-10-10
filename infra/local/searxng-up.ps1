# Run Ohmega's SearXNG on THIS laptop (Docker Desktop) using the same compose file as the server.
# Optional: without it, search degrades to DDG/Bing/Google News, then capped paid engines (still works).
#
#   powershell -File infra/local/searxng-up.ps1          # start (idempotent)
#   powershell -File infra/local/searxng-up.ps1 -Down    # stop
#
# Listens on 127.0.0.1:8080 -- the same default ALGENT_SEARXNG_URL, so no env change is needed.
# Close any SSH tunnel to the server's SearXNG first (it would hold port 8080).
param([switch]$Down)
$ErrorActionPreference = 'Stop'
$dir = Join-Path $PSScriptRoot '..\server\searxng' | Resolve-Path
Push-Location $dir
try {
    if ($Down) { docker compose down; return }
    $envFile = Join-Path $dir '.env'
    if (-not (Test-Path $envFile)) {
        $bytes = New-Object byte[] 32
        [System.Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes)
        "SEARXNG_SECRET=$(($bytes | ForEach-Object { $_.ToString('x2') }) -join '')" | Set-Content -Encoding ascii $envFile
    }
    docker compose up -d
    Write-Host 'SearXNG starting on http://127.0.0.1:8080 -- verify with: python -m algent_backend.cli newsroom doctor'
} finally { Pop-Location }
