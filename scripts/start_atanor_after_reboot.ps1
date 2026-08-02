param(
    [switch]$RepairGitIndex = $true,
    [switch]$StartApi = $true,
    [switch]$StartWeb = $true,
    [switch]$OpenBrowser = $false,
    [int]$ApiPort = 8502,
    [int]$WebPort = 3031
)

$ErrorActionPreference = "Continue"

$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$StartupLogDir = Join-Path $ProjectRoot "logs\startup"
New-Item -ItemType Directory -Force -Path $StartupLogDir | Out-Null

$Timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$TranscriptPath = Join-Path $StartupLogDir "atanor_reboot_recovery_$Timestamp.log"
Start-Transcript -Path $TranscriptPath -Append | Out-Null

function Write-Step {
    param([string]$Message)
    Write-Output "[$(Get-Date -Format o)] $Message"
}

function Test-PortListening {
    param([int]$Port)
    $connection = Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue
    return $null -ne $connection
}

function Wait-HttpOk {
    param(
        [string]$Url,
        [int]$TimeoutSeconds = 45
    )
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        try {
            $response = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 5
            if ($response.StatusCode -ge 200 -and $response.StatusCode -lt 500) {
                return $true
            }
        } catch {
            Start-Sleep -Seconds 2
        }
    }
    return $false
}

function Repair-GitIndexIfNeeded {
    if (-not $RepairGitIndex) {
        Write-Step "Git index repair skipped by parameter."
        return
    }

    Push-Location $ProjectRoot
    try {
        git status --short *> $null
        if ($LASTEXITCODE -eq 0) {
            Write-Step "Git index looks healthy."
            return
        }

        $indexPath = Join-Path $ProjectRoot ".git\index"
        if (-not (Test-Path $indexPath)) {
            Write-Step "Git status failed, but no .git/index file exists. Running git reset --mixed."
            git reset --mixed
            return
        }

        $backupPath = Join-Path $ProjectRoot (".git\index.corrupt." + (Get-Date -Format "yyyyMMdd_HHmmss"))
        Move-Item -LiteralPath $indexPath -Destination $backupPath
        Write-Step "Moved corrupt Git index to $backupPath"
        git reset --mixed
        Write-Step "Rebuilt Git index with git reset --mixed. Worktree files were not reverted."
    } finally {
        Pop-Location
    }
}

function Start-AtanorApi {
    if (-not $StartApi) {
        Write-Step "API start skipped by parameter."
        return
    }
    if (Test-PortListening -Port $ApiPort) {
        Write-Step "API port $ApiPort already listening; not starting another API."
        return
    }

    $packageRoots = Get-ChildItem -Path (Join-Path $ProjectRoot "packages") -Directory | ForEach-Object { $_.FullName }
    $pythonPath = (@($ProjectRoot) + $packageRoots) -join ";"
    $apiOut = Join-Path $StartupLogDir "api_$ApiPort.out.log"
    $apiErr = Join-Path $StartupLogDir "api_$ApiPort.err.log"
    $command = "`$env:PYTHONPATH='$pythonPath'; python -m uvicorn app.main:app --host 127.0.0.1 --port $ApiPort --app-dir apps/api"

    Write-Step "Starting ATANOR API on 127.0.0.1:$ApiPort"
    Start-Process -FilePath "powershell.exe" `
        -ArgumentList @("-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", $command) `
        -WorkingDirectory $ProjectRoot `
        -RedirectStandardOutput $apiOut `
        -RedirectStandardError $apiErr `
        -WindowStyle Hidden

    if (Wait-HttpOk -Url "http://127.0.0.1:$ApiPort/health" -TimeoutSeconds 60) {
        Write-Step "API health OK on port $ApiPort."
    } else {
        Write-Step "API health did not become ready on port $ApiPort. See $apiErr"
    }
}

function Start-AtanorWeb {
    if (-not $StartWeb) {
        Write-Step "Web start skipped by parameter."
        return
    }
    if (Test-PortListening -Port $WebPort) {
        Write-Step "Web port $WebPort already listening; not starting another web server."
        return
    }

    $webOut = Join-Path $StartupLogDir "web_$WebPort.out.log"
    $webErr = Join-Path $StartupLogDir "web_$WebPort.err.log"
    $apiBase = "http://127.0.0.1:$ApiPort"
    $command = "`$env:ATANOR_GATEWAY_API='$apiBase'; npm --workspace apps/web run dev:local -- --port $WebPort"

    Write-Step "Starting ATANOR web on 127.0.0.1:$WebPort with ATANOR_GATEWAY_API=$apiBase"
    Start-Process -FilePath "powershell.exe" `
        -ArgumentList @("-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", $command) `
        -WorkingDirectory $ProjectRoot `
        -RedirectStandardOutput $webOut `
        -RedirectStandardError $webErr `
        -WindowStyle Hidden

    if (Wait-HttpOk -Url "http://127.0.0.1:$WebPort/" -TimeoutSeconds 90) {
        Write-Step "Web server responded on port $WebPort."
    } else {
        Write-Step "Web server did not become ready on port $WebPort. See $webErr"
    }
}

function Write-RecoverySummary {
    $summary = [ordered]@{
        timestamp = (Get-Date).ToString("o")
        project_root = $ProjectRoot
        api_port = $ApiPort
        web_port = $WebPort
        api_listening = Test-PortListening -Port $ApiPort
        web_listening = Test-PortListening -Port $WebPort
        cloud_lab_url = "http://127.0.0.1:$WebPort/?lang=ko&section=cloud&workspace=lab&memory_stability=1&strategic_status=1"
        candidate_daemon_started_by_script = $false
        production_store_mutated_by_script = $false
        local_brain_write_by_script = $false
    }
    $summaryPath = Join-Path $StartupLogDir "latest_reboot_recovery_status.json"
    ($summary | ConvertTo-Json -Depth 4) | Set-Content -Path $summaryPath -Encoding UTF8
    Write-Step "Wrote recovery summary: $summaryPath"

    if ($OpenBrowser) {
        Start-Process $summary.cloud_lab_url
    }
}

Write-Step "ATANOR reboot recovery started."
Write-Step "This script starts only API/web and never starts candidate learning, promotion, or production mutation."
Repair-GitIndexIfNeeded
Start-AtanorApi
Start-AtanorWeb
Write-RecoverySummary
Write-Step "ATANOR reboot recovery finished."

Stop-Transcript | Out-Null
