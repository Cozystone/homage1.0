$ErrorActionPreference = "Stop"

$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
$CertDir = Join-Path $Root "src-tauri\certs"
$PfxPath = Join-Path $CertDir "homage-dev-code-signing.pfx"
$KeyPath = Join-Path $CertDir "homage-dev-code-signing.key"
$CerPath = Join-Path $CertDir "homage-dev-code-signing.cer"
$MetaPath = Join-Path $CertDir "homage-dev-code-signing.json"
$OpenSslConfigPath = Join-Path $CertDir "openssl.cnf"
$SubjectCommonName = "ATANOR Local Developer"
$Password = if ($env:ATANOR_DEV_CERT_PASSWORD) { $env:ATANOR_DEV_CERT_PASSWORD } elseif ($env:HOMAGE_DEV_CERT_PASSWORD) { $env:HOMAGE_DEV_CERT_PASSWORD } else { "atanor-local-dev-only" }
$RunningOnWindows = [System.Environment]::OSVersion.Platform -eq "Win32NT" -or $env:OS -eq "Windows_NT"

function Write-Telemetry($Message) {
  Write-Host "[security-kernel] $Message"
}

if (-not $RunningOnWindows) {
  Write-Telemetry "Non-Windows platform detected. Skipping Authenticode developer signing."
  exit 0
}

$OpenSsl = Get-Command openssl -ErrorAction SilentlyContinue
if (-not $OpenSsl) {
  throw "OpenSSL is required to generate the ATANOR local developer certificate."
}

New-Item -ItemType Directory -Force -Path $CertDir | Out-Null

if ($env:ATANOR_FORCE_REGEN_DEV_CERT -eq "1" -or $env:HOMAGE_FORCE_REGEN_DEV_CERT -eq "1") {
  Remove-Item -LiteralPath $PfxPath, $KeyPath, $CerPath, $MetaPath -Force -ErrorAction SilentlyContinue
}

if (-not (Test-Path -LiteralPath $PfxPath)) {
  Write-Telemetry "Generating OpenSSL self-signed developer code-signing certificate."
  @"
[ req ]
distinguished_name = req_distinguished_name
x509_extensions = v3_req
prompt = no

[ req_distinguished_name ]
CN = $SubjectCommonName
O = ATANOR
C = US

[ v3_req ]
basicConstraints = CA:FALSE
keyUsage = digitalSignature
extendedKeyUsage = codeSigning
"@ | Set-Content -Path $OpenSslConfigPath -Encoding ASCII

  & $OpenSsl.Source req `
    -x509 `
    -newkey rsa:3072 `
    -sha256 `
    -nodes `
    -days 365 `
    -config $OpenSslConfigPath `
    -keyout $KeyPath `
    -out $CerPath | Out-Host
  if ($LASTEXITCODE -ne 0) {
    throw "OpenSSL req failed with exit code $LASTEXITCODE."
  }

  & $OpenSsl.Source pkcs12 `
    -export `
    -inkey $KeyPath `
    -in $CerPath `
    -out $PfxPath `
    -name $SubjectCommonName `
    -password "pass:$Password" | Out-Host
  if ($LASTEXITCODE -ne 0) {
    throw "OpenSSL pkcs12 export failed with exit code $LASTEXITCODE."
  }
}

$SecurePassword = ConvertTo-SecureString -String $Password -AsPlainText -Force
try {
  $Imported = Import-PfxCertificate -FilePath $PfxPath -CertStoreLocation Cert:\CurrentUser\My -Password $SecurePassword -Exportable
} catch {
  if ($env:ATANOR_DEV_CERT_REGEN_RETRY -ne "1") {
    Write-Telemetry "Existing developer certificate could not be imported. Regenerating local signing material."
    Remove-Item -LiteralPath $PfxPath, $KeyPath, $CerPath, $MetaPath -Force -ErrorAction SilentlyContinue
    $env:ATANOR_FORCE_REGEN_DEV_CERT = "1"
    $env:ATANOR_DEV_CERT_REGEN_RETRY = "1"
    & $PSCommandPath
    exit $LASTEXITCODE
  }
  throw
}
if (-not $Imported) {
  throw "Failed to import developer code-signing certificate into CurrentUser\My."
}

$Cert = Get-ChildItem Cert:\CurrentUser\My |
  Where-Object { $_.Subject -like "*CN=$SubjectCommonName*" -and $_.HasPrivateKey } |
  Sort-Object NotAfter -Descending |
  Select-Object -First 1

if (-not $Cert) {
  throw "Could not locate the imported developer code-signing certificate."
}

if ($env:ATANOR_TRUST_SELF_SIGNED_CERT -eq "1" -or $env:HOMAGE_TRUST_SELF_SIGNED_CERT -eq "1") {
  Import-Certificate -FilePath $CerPath -CertStoreLocation Cert:\CurrentUser\Root | Out-Null
  Import-Certificate -FilePath $CerPath -CertStoreLocation Cert:\CurrentUser\TrustedPublisher | Out-Null
  Write-Telemetry "Developer certificate trusted in CurrentUser Root and TrustedPublisher stores."
} else {
  Write-Telemetry "Skipping local trust import. Set ATANOR_TRUST_SELF_SIGNED_CERT=1 for local trusted builds."
}

$Metadata = [ordered]@{
  subject = $Cert.Subject
  thumbprint = $Cert.Thumbprint
  not_after = $Cert.NotAfter.ToString("o")
  pfx_path = $PfxPath
  store = "Cert:\CurrentUser\My"
  trust_scope = "CurrentUser"
  production_note = "Self-signed certificates are for local developer builds only. Public releases need a trusted code signing certificate or Azure Trusted Signing."
}
$Metadata | ConvertTo-Json -Depth 4 | Set-Content -Path $MetaPath -Encoding UTF8

Write-Telemetry "Smart App Control developer certificate mapping complete."
Write-Telemetry "Signing certificate thumbprint: $($Cert.Thumbprint)"
