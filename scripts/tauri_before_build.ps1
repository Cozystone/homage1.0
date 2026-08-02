$ErrorActionPreference = "Stop"

$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $Root

& (Join-Path $PSScriptRoot "prepare_windows_signing.ps1")
if (-not $?) {
  throw "prepare_windows_signing.ps1 failed"
}

python (Join-Path $PSScriptRoot "build_sidecar.py")
if ($LASTEXITCODE -ne 0) {
  throw "build_sidecar.py failed with exit code $LASTEXITCODE"
}

npm --workspace apps/web run build:desktop
if ($LASTEXITCODE -ne 0) {
  throw "apps/web build:desktop failed with exit code $LASTEXITCODE"
}
