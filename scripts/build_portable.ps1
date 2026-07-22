$ErrorActionPreference = "Stop"

$ProductRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$RepoRoot = (Resolve-Path (Join-Path $ProductRoot "..\..")).Path
$Python = Join-Path $RepoRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $Python)) { $Python = "python" }

Push-Location (Join-Path $ProductRoot "frontend")
try {
    npm run build
    if ($LASTEXITCODE -ne 0) { throw "Frontend build failed with exit code $LASTEXITCODE" }
} finally { Pop-Location }

Push-Location $ProductRoot
try {
    & $Python -m PyInstaller --noconfirm --clean VirtualMate.spec
    if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed with exit code $LASTEXITCODE" }
} finally { Pop-Location }

$Portable = Join-Path $ProductRoot "dist\VirtualMate"
New-Item -ItemType Directory -Force -Path (Join-Path $Portable "workspace\knowledge") | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $Portable "data") | Out-Null
$Persona = Join-Path $Portable "workspace\persona.md"
if (-not (Test-Path $Persona)) {
@"
# Persona

Describe the assistant identity, role, communication style, technical preferences,
opinions, characteristic phrases, and uncertainty behavior here.
"@ | Set-Content -Path $Persona -Encoding UTF8
}

& $Python (Join-Path $ProductRoot "scripts\report_portable.py") $Portable

