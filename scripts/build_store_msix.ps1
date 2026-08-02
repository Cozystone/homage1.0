param(
  [switch]$SkipDesktopBuild,
  [switch]$SkipSign,
  [string]$Configuration = "release"
)

$ErrorActionPreference = "Stop"

function Write-Step([string]$Message) {
  Write-Host "[ATANOR MSIX] $Message"
}

function Find-WindowsSdkTool([string]$Name) {
  $roots = @(
    "${env:ProgramFiles(x86)}\Windows Kits\10\bin",
    "${env:ProgramFiles}\Windows Kits\10\bin"
  ) | Where-Object { $_ -and (Test-Path -LiteralPath $_) }

  foreach ($root in $roots) {
    $matches = Get-ChildItem -LiteralPath $root -Recurse -Filter $Name -ErrorAction SilentlyContinue |
      Where-Object { $_.FullName -match "\\x64\\$([regex]::Escape($Name))$" } |
      Sort-Object FullName -Descending
    if ($matches) {
      return $matches[0].FullName
    }
  }

  $command = Get-Command $Name -ErrorAction SilentlyContinue
  if ($command) {
    return $command.Source
  }
  throw "Could not find Windows SDK tool: $Name"
}

function Convert-ToMsixVersion([string]$Version) {
  $parts = $Version.Split(".") | ForEach-Object { [int]$_ }
  while ($parts.Count -lt 4) {
    $parts += 0
  }
  return ($parts[0..3] -join ".")
}

function Copy-AssetIfExists([string]$Source, [string]$Target) {
  if (Test-Path -LiteralPath $Source) {
    Copy-Item -LiteralPath $Source -Destination $Target -Force
  }
}

function Ensure-StoreSigningCertificate([string]$Publisher) {
  $subject = $Publisher
  $existing = Get-ChildItem Cert:\CurrentUser\My -CodeSigningCert |
    Where-Object { $_.Subject -eq $subject } |
    Sort-Object NotAfter -Descending |
    Select-Object -First 1
  if ($existing) {
    return $existing
  }

  Write-Step "Creating local Store-upload signing certificate for $subject"
  return New-SelfSignedCertificate `
    -Type Custom `
    -Subject $subject `
    -KeyUsage DigitalSignature `
    -KeyAlgorithm RSA `
    -KeyLength 2048 `
    -HashAlgorithm SHA256 `
    -CertStoreLocation Cert:\CurrentUser\My `
    -FriendlyName "ATANOR Store MSIX Upload Signing"
}

$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
$IdentityPath = Join-Path $Root "packaging\windows-msix\store-identity.json"
$ManifestTemplatePath = Join-Path $Root "packaging\windows-msix\AppxManifest.xml.template"
$TauriConfigPath = Join-Path $Root "src-tauri\tauri.conf.json"
$ReleaseDir = Join-Path $Root "src-tauri\target\$Configuration"
$StageRoot = Join-Path $Root "build\msix"
$StageDir = Join-Path $StageRoot "stage"
$OutputDir = Join-Path $Root "dist-artifacts\windows-store"

if (!(Test-Path -LiteralPath $IdentityPath)) {
  throw "Store identity file not found: $IdentityPath"
}
if (!(Test-Path -LiteralPath $ManifestTemplatePath)) {
  throw "Manifest template not found: $ManifestTemplatePath"
}

$Identity = Get-Content -LiteralPath $IdentityPath -Raw | ConvertFrom-Json
$TauriConfig = Get-Content -LiteralPath $TauriConfigPath -Raw | ConvertFrom-Json
$PackageVersion = Convert-ToMsixVersion $TauriConfig.version
$Architecture = "x64"

if (!$SkipDesktopBuild) {
  Write-Step "Building desktop runtime before MSIX staging"
  & npm run desktop:build
  if ($LASTEXITCODE -ne 0) {
    throw "desktop build failed"
  }
}

$DesktopExeCandidates = @(
  (Join-Path $ReleaseDir "atanor-desktop.exe"),
  (Join-Path $ReleaseDir "ATANOR.exe"),
  (Join-Path $ReleaseDir "homage-desktop.exe")
)
$DesktopExe = $DesktopExeCandidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
$SidecarExe = Join-Path $ReleaseDir "homage-api.exe"
$SidecarFallback = Join-Path $Root "src-tauri\binaries\homage-api-x86_64-pc-windows-msvc.exe"

if (!$DesktopExe) {
  throw "Tauri desktop executable not found. Checked: $($DesktopExeCandidates -join ', ')"
}
if (!(Test-Path -LiteralPath $SidecarExe)) {
  if (Test-Path -LiteralPath $SidecarFallback) {
    $SidecarExe = $SidecarFallback
  } else {
    throw "ATANOR sidecar executable not found in release or binaries directory."
  }
}

Remove-Item -LiteralPath $StageDir -Recurse -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force -Path $StageDir | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $StageDir "Assets") | Out-Null
New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null

Write-Step "Copying ATANOR binaries into MSIX stage"
Copy-Item -LiteralPath $DesktopExe -Destination (Join-Path $StageDir "ATANOR.exe") -Force
Copy-Item -LiteralPath $SidecarExe -Destination (Join-Path $StageDir "homage-api.exe") -Force

$ResourcesDir = Join-Path $ReleaseDir "resources"
if (Test-Path -LiteralPath $ResourcesDir) {
  Copy-Item -LiteralPath $ResourcesDir -Destination (Join-Path $StageDir "resources") -Recurse -Force
}

$IconDir = Join-Path $Root "src-tauri\icons"
$AssetsDir = Join-Path $StageDir "Assets"
Copy-AssetIfExists (Join-Path $IconDir "StoreLogo.png") (Join-Path $AssetsDir "StoreLogo.png")
Copy-AssetIfExists (Join-Path $IconDir "Square44x44Logo.png") (Join-Path $AssetsDir "Square44x44Logo.png")
Copy-AssetIfExists (Join-Path $IconDir "Square71x71Logo.png") (Join-Path $AssetsDir "Square71x71Logo.png")
Copy-AssetIfExists (Join-Path $IconDir "Square150x150Logo.png") (Join-Path $AssetsDir "Square150x150Logo.png")
Copy-AssetIfExists (Join-Path $IconDir "Square310x310Logo.png") (Join-Path $AssetsDir "Square310x310Logo.png")
Copy-AssetIfExists (Join-Path $IconDir "Square284x284Logo.png") (Join-Path $AssetsDir "Wide310x150Logo.png")
Copy-AssetIfExists (Join-Path $IconDir "Square310x310Logo.png") (Join-Path $AssetsDir "SplashScreen.png")

$RequiredAssets = @(
  "StoreLogo.png",
  "Square44x44Logo.png",
  "Square71x71Logo.png",
  "Square150x150Logo.png",
  "Square310x310Logo.png",
  "Wide310x150Logo.png",
  "SplashScreen.png"
)
foreach ($asset in $RequiredAssets) {
  $assetPath = Join-Path $AssetsDir $asset
  if (!(Test-Path -LiteralPath $assetPath)) {
    throw "Required MSIX visual asset missing: $assetPath"
  }
}

$Manifest = Get-Content -LiteralPath $ManifestTemplatePath -Raw
$Manifest = $Manifest.Replace("{{PACKAGE_IDENTITY_NAME}}", $Identity.packageIdentityName)
$Manifest = $Manifest.Replace("{{PACKAGE_IDENTITY_PUBLISHER}}", $Identity.packageIdentityPublisher)
$Manifest = $Manifest.Replace("{{PACKAGE_VERSION}}", $PackageVersion)
$Manifest = $Manifest.Replace("{{PROCESSOR_ARCHITECTURE}}", $Architecture)
$Manifest = $Manifest.Replace("{{DISPLAY_NAME}}", $Identity.productName)
$Manifest = $Manifest.Replace("{{PUBLISHER_DISPLAY_NAME}}", $Identity.publisherDisplayName)
$Manifest = $Manifest.Replace("{{DESCRIPTION}}", "Transparent Anomy neuro-symbolic local AI engine.")
[System.IO.File]::WriteAllText((Join-Path $StageDir "AppxManifest.xml"), $Manifest, [System.Text.UTF8Encoding]::new($false))

$MakePri = Find-WindowsSdkTool "makepri.exe"
$MakeAppx = Find-WindowsSdkTool "makeappx.exe"
$SignTool = Find-WindowsSdkTool "signtool.exe"

Write-Step "Generating resources.pri"
$PriConfig = Join-Path $StageRoot "priconfig.xml"
Remove-Item -LiteralPath $PriConfig -Force -ErrorAction SilentlyContinue
& $MakePri createconfig /cf $PriConfig /dq en-US /pv 10.0.0
if ($LASTEXITCODE -ne 0) {
  throw "makepri createconfig failed"
}
$PriOutput = Join-Path $StageDir "resources.pri"
Remove-Item -LiteralPath $PriOutput -Force -ErrorAction SilentlyContinue
& $MakePri new /pr $StageDir /cf $PriConfig /mn (Join-Path $StageDir "AppxManifest.xml") /of $PriOutput /o
if ($LASTEXITCODE -ne 0) {
  throw "makepri new failed"
}

$MsixName = "ATANOR_${PackageVersion}_${Architecture}.msix"
$MsixPath = Join-Path $OutputDir $MsixName
$UploadPath = Join-Path $OutputDir "ATANOR_${PackageVersion}_${Architecture}.msixupload"
Remove-Item -LiteralPath $MsixPath, $UploadPath -Force -ErrorAction SilentlyContinue

Write-Step "Packing MSIX with MakeAppx"
& $MakeAppx pack /d $StageDir /p $MsixPath /o
if ($LASTEXITCODE -ne 0) {
  throw "makeappx pack failed"
}

if (!$SkipSign) {
  $Cert = Ensure-StoreSigningCertificate $Identity.packageIdentityPublisher
  Write-Step "Signing MSIX using certificate $($Cert.Thumbprint)"
  & $SignTool sign /fd SHA256 /sha1 $Cert.Thumbprint /tr "http://timestamp.digicert.com" /td SHA256 $MsixPath
  if ($LASTEXITCODE -ne 0) {
    Write-Step "Timestamp signing failed; retrying without timestamp"
    & $SignTool sign /fd SHA256 /sha1 $Cert.Thumbprint $MsixPath
    if ($LASTEXITCODE -ne 0) {
      throw "signtool sign failed"
    }
  }
  & $SignTool verify /pa /v $MsixPath
  if ($LASTEXITCODE -ne 0) {
    $Signature = Get-AuthenticodeSignature -LiteralPath $MsixPath
    if (!$Signature.SignerCertificate) {
      throw "signtool verification failed and no signer certificate was found on the MSIX."
    }
    if ($Signature.SignerCertificate.Subject -ne $Identity.packageIdentityPublisher) {
      throw "MSIX signer subject does not match Partner Center publisher. Signer=$($Signature.SignerCertificate.Subject) Expected=$($Identity.packageIdentityPublisher)"
    }
    Write-Step "Signature is present and matches Partner Center publisher. Public trust verification is expected to fail for local Store-upload self-signed packages."
  }
}

Write-Step "Creating Partner Center upload container"
$UploadStage = Join-Path $StageRoot "upload"
Remove-Item -LiteralPath $UploadStage -Recurse -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force -Path $UploadStage | Out-Null
Copy-Item -LiteralPath $MsixPath -Destination (Join-Path $UploadStage $MsixName) -Force
Add-Type -AssemblyName System.IO.Compression.FileSystem
[System.IO.Compression.ZipFile]::CreateFromDirectory($UploadStage, $UploadPath, [System.IO.Compression.CompressionLevel]::NoCompression, $false)

Write-Step "MSIX ready: $MsixPath"
Write-Step "Partner Center upload ready: $UploadPath"
Write-Step "Store product: $($Identity.productId) / $($Identity.storeUrl)"
