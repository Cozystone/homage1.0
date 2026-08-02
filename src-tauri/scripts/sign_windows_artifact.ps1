param(
  [Parameter(Mandatory = $false)]
  [string]$FilePath
)

$ErrorActionPreference = "Stop"

$RootSignScript = Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..\..\scripts\sign_windows_artifact.ps1")
& $RootSignScript -FilePath $FilePath
