$ErrorActionPreference = "Stop"
$workspaceRoot = $PSScriptRoot
$pythonPath = Join-Path $workspaceRoot "work/venv/Scripts/python.exe"
if (-not (Test-Path -LiteralPath $pythonPath)) {
    throw "Run this from the original MESH workspace with its configured Python environment."
}
$backendRoot = Join-Path $workspaceRoot "outputs/mesh"
$env:PYTHONPATH = Join-Path $backendRoot "backend"
Push-Location -LiteralPath $backendRoot
try {
    & $pythonPath scripts/seed_presentation.py --organization 1f389719-0a9c-4b54-9516-bfc43055df07 --apply-demo-data --report docs/presentation-data-results.json
    if ($LASTEXITCODE -ne 0) { throw "Demo data was not committed. Check Supabase connectivity and the JSON error type above." }
    Write-Host "Presentation records saved. Refresh MESH. Security records are synthetic."
} finally {
    Pop-Location
}
