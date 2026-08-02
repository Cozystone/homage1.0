param(
  [Parameter(Mandatory = $false)]
  [string]$FilePath
)

$ErrorActionPreference = "Stop"

$PrepareScript = Join-Path $PSScriptRoot "prepare_windows_signing.ps1"
$SubjectCommonName = "ATANOR Local Developer"
$RunningOnWindows = [System.Environment]::OSVersion.Platform -eq "Win32NT" -or $env:OS -eq "Windows_NT"

function Write-SignLog($Message) {
  Write-Host "[security-kernel] $Message"
}

if (-not $FilePath -and $args.Count -gt 0) {
  $FilePath = ($args -join " ")
}

if (-not $FilePath) {
  throw "No file path was supplied for Authenticode signing."
}

$Target = $FilePath.Trim('"')
if (-not [System.IO.Path]::IsPathRooted($Target)) {
  $Target = Join-Path (Get-Location) $Target
}
$ResolvedTarget = Resolve-Path -LiteralPath $Target

if (-not $RunningOnWindows) {
  Write-SignLog "Non-Windows platform detected. Skipping Authenticode signing for $ResolvedTarget"
  exit 0
}

& $PrepareScript

$Cert = Get-ChildItem Cert:\CurrentUser\My |
  Where-Object { $_.Subject -like "*CN=$SubjectCommonName*" -and $_.HasPrivateKey } |
  Sort-Object NotAfter -Descending |
  Select-Object -First 1

if (-not $Cert) {
  throw "Could not locate the ATANOR developer code-signing certificate."
}

Write-SignLog "Authenticode signing started: $ResolvedTarget"
try {
  $Signature = Set-AuthenticodeSignature `
    -FilePath $ResolvedTarget `
    -Certificate $Cert `
    -HashAlgorithm SHA256 `
    -TimestampServer "http://timestamp.digicert.com"
} catch {
  Write-SignLog "Timestamp signing failed, retrying local signature only: $($_.Exception.Message)"
  $Signature = Set-AuthenticodeSignature `
    -FilePath $ResolvedTarget `
    -Certificate $Cert `
    -HashAlgorithm SHA256
}

if (-not $Signature.SignerCertificate) {
  throw "Signing completed without a signer certificate in the result."
}

Write-SignLog "Authenticode signing complete: $($Signature.Status) / $($Signature.SignerCertificate.Thumbprint)"
