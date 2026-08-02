$ErrorActionPreference = "Stop"

$PolicyPath = "HKLM:\SYSTEM\CurrentControlSet\Control\CI\Policy"
$LogPath = Join-Path $PSScriptRoot "disable_smart_app_control.log"

function Write-Log($Message) {
  $line = "$(Get-Date -Format o) $Message"
  Write-Host $line
  Add-Content -Path $LogPath -Value $line -Encoding UTF8
}

Write-Log "Attempting to disable Smart App Control for local ATANOR alpha execution."
Set-ItemProperty -Path $PolicyPath -Name VerifiedAndReputablePolicyState -Type DWord -Value 0
Set-ItemProperty -Path $PolicyPath -Name SAC_PreviousState -Type DWord -Value 1 -ErrorAction SilentlyContinue
$State = Get-ItemProperty -Path $PolicyPath
Write-Log "VerifiedAndReputablePolicyState=$($State.VerifiedAndReputablePolicyState)"
Write-Log "SAC_PreviousState=$($State.SAC_PreviousState)"
Write-Log "Done. A reboot may be required before Windows fully applies the policy change."
