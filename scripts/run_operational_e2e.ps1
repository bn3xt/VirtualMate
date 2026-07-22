$ErrorActionPreference = "Stop"

$ProductRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$RepoRoot = (Resolve-Path (Join-Path $ProductRoot "..\..")).Path
$env:PYTHONPATH = (Join-Path $ProductRoot "backend")
$env:VSA_RUN_OPERATIONAL = "1"
$Python = Join-Path $RepoRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $Python)) {
    $Python = "python"
}

Set-Location $RepoRoot
& $Python -m pytest -c standalone/virtual_mate/pytest.ini --collect-only -q standalone/virtual_mate/tests/e2e_operational
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& $Python -m pytest -c standalone/virtual_mate/pytest.ini -q standalone/virtual_mate/tests/e2e_operational
exit $LASTEXITCODE

