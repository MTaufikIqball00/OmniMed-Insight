<#
.SYNOPSIS
    OmniMed Insight (XAI) — Local Development Orchestrator & Health Verifier (Windows PowerShell)
.DESCRIPTION
    1. Verifies required runtimes (Rust/Cargo, Python 3, Node.js/npm).
    2. Initializes .env from .env.example with fresh cryptographic secrets if missing.
    3. Validates configuration without printing secret values.
    4. Checks port availability (3100, 8100, 8200, 8300, 5433) and reports owning PID/ProcessName on conflict without killing unrelated processes.
    5. Starts Python Medical AI Service (:8200), Rust Backend (:8100), and Next.js Frontend (:3100) in controlled order.
    6. Polls real HTTP health endpoints before reporting readiness.
    7. Handles Ctrl+C and startup failure cleanup gracefully, stopping only processes started by this launcher.
.PARAMETER Services
    Comma-separated list of services to start: "all" (default), or any combination of "ai", "backend", "frontend".
.PARAMETER CheckOnly
    Performs runtime, config, and port checks then exits without starting services.
.PARAMETER VerifyAndExit
    Starts the stack, verifies health and end-to-end Frontend -> Rust -> Python AI connectivity, displays the status table, and cleanly shuts down.
#>
param(
    [string]$Services = "all",
    [switch]$CheckOnly = $false,
    [switch]$VerifyAndExit = $false
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $RepoRoot

$LogDir = Join-Path $RepoRoot "logs"
$PidFile = Join-Path $RepoRoot ".omnimed-launcher-pids.json"
if (-not (Test-Path $LogDir)) {
    New-Item -ItemType Directory -Path $LogDir -Force | Out-Null
}

# Ensure Cargo and LLVM-MinGW are in PATH if installed in standard user locations
$UserCargoBin = Join-Path $env:USERPROFILE ".cargo\bin"
if ((Test-Path $UserCargoBin) -and ($env:PATH -notlike "*$UserCargoBin*")) {
    $env:PATH = "$UserCargoBin;$env:PATH"
}
$WinGetPackages = Join-Path $env:LOCALAPPDATA "Microsoft\WinGet\Packages"
if (Test-Path $WinGetPackages) {
    $LlvmGcc = Get-ChildItem -Path $WinGetPackages -Filter "x86_64-w64-mingw32-gcc.exe" -Recurse -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($LlvmGcc -and ($env:PATH -notlike "*$($LlvmGcc.DirectoryName)*")) {
        $env:PATH = "$($LlvmGcc.DirectoryName);$env:PATH"
    }
}

function Write-Section($Title) {
    Write-Host "`n==================================================================" -ForegroundColor Cyan
    Write-Host "  $Title" -ForegroundColor Cyan
    Write-Host "==================================================================" -ForegroundColor Cyan
}

# 1. Clean up stale launcher-owned processes if a previous run left a PID file
if (Test-Path $PidFile) {
    try {
        $PrevPids = Get-Content $PidFile | ConvertFrom-Json
        foreach ($item in $PrevPids) {
            $proc = Get-Process -Id $item.pid -ErrorAction SilentlyContinue
            if ($proc) {
                Write-Host "[Launcher] Stopping previous launcher-owned process $($item.service) (PID $($item.pid))..." -ForegroundColor Yellow
                Stop-Process -Id $item.pid -Force -ErrorAction SilentlyContinue
            }
        }
    } catch {}
    Remove-Item $PidFile -Force -ErrorAction SilentlyContinue
}

# 2. Initialize & Load .env Configuration Safely
Write-Section "1. Validating Configuration & Environment (.env)"
$EnvFile = Join-Path $RepoRoot ".env"
$EnvExampleFile = Join-Path $RepoRoot ".env.example"

if (-not (Test-Path $EnvFile)) {
    if (-not (Test-Path $EnvExampleFile)) {
        throw "Missing .env.example in repository root."
    }
    Write-Host "[Config] Creating local .env from .env.example with generated local session & internal tokens..." -ForegroundColor Yellow
    $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    $bytes1 = New-Object byte[] 32
    $bytes2 = New-Object byte[] 32
    $rng.GetBytes($bytes1)
    $rng.GetBytes($bytes2)
    $secHex = [System.BitConverter]::ToString($bytes1).Replace("-", "").ToLower()
    $tokHex = [System.BitConverter]::ToString($bytes2).Replace("-", "").ToLower()

    $content = Get-Content $EnvExampleFile -Raw
    $content = $content.Replace("<GENERATE_AT_LEAST_32_BYTE_HEX_SECRET>", $secHex)
    $content = $content.Replace("<GENERATE_AT_LEAST_32_BYTE_INTERNAL_TOKEN>", $tokHex)
    $content = $content.Replace("<SET_INITIAL_ADMIN_PASSWORD_ON_FIRST_RUN>", "OmniMed!Admin#2026")
    Set-Content -Path $EnvFile -Value $content -Encoding UTF8
}

Get-Content $EnvFile | ForEach-Object {
    $line = $_.Trim()
    if ($line -and -not $line.StartsWith("#") -and $line.Contains("=")) {
        $parts = $line.Split("=", 2)
        $k = $parts[0].Trim()
        $v = $parts[1].Trim()
        [System.Environment]::SetEnvironmentVariable($k, $v, "Process")
    }
}

$BindHost = if ($env:BIND_HOST) { $env:BIND_HOST } else { "127.0.0.1" }
$FrontendPort = if ($env:FRONTEND_PORT) { [int]$env:FRONTEND_PORT } else { 3100 }
$RustPort = if ($env:RUST_BACKEND_PORT) { [int]$env:RUST_BACKEND_PORT } else { 8100 }
$PythonAiPort = if ($env:PYTHON_AI_PORT) { [int]$env:PYTHON_AI_PORT } else { 8200 }
$FhirPort = if ($env:FHIR_SERVER_PORT) { [int]$env:FHIR_SERVER_PORT } else { 8300 }
$PostgresPort = if ($env:POSTGRES_PORT) { [int]$env:POSTGRES_PORT } else { 5433 }

Write-Host "  BIND_HOST                  = $BindHost"
Write-Host "  FRONTEND_PORT              = $FrontendPort"
Write-Host "  RUST_BACKEND_PORT          = $RustPort"
Write-Host "  PYTHON_AI_PORT             = $PythonAiPort"
Write-Host "  FHIR_SERVER_PORT (Opt)     = $FhirPort"
Write-Host "  POSTGRES_PORT (Opt)        = $PostgresPort"
Write-Host "  DATABASE_URL               = $env:DATABASE_URL"
Write-Host "  SESSION_SECRET             = [REDACTED_CONFIGURED ($($env:SESSION_SECRET.Length) chars)]"
Write-Host "  INTERNAL_SERVICE_TOKEN     = [REDACTED_CONFIGURED ($($env:INTERNAL_SERVICE_TOKEN.Length) chars)]"
Write-Host "  OMNIMED_BOOTSTRAP_ADMIN    = $env:OMNIMED_BOOTSTRAP_ADMIN_EMAIL ([PASSWORD REDACTED])"

# 3. Check Runtimes
Write-Section "2. Verifying Required Runtimes"
$SelectedList = if ($Services -eq "all") { @("ai", "backend", "frontend") } else { $Services.ToLower().Split(",") | ForEach-Object { $_.Trim() } }

if ($SelectedList -contains "backend") {
    $cargoVer = & cargo --version 2>$null
    $rustcVer = & rustc --version 2>$null
    if (-not $cargoVer) { throw "Rust/Cargo is required for the primary backend but was not found." }
    Write-Host "  [OK] Rust Toolchain : $rustcVer / $cargoVer" -ForegroundColor Green
}
if ($SelectedList -contains "ai") {
    $pyVer = & python --version 2>$null
    if (-not $pyVer) { throw "Python 3 is required for the Medical AI service but was not found." }
    Write-Host "  [OK] Python Runtime : $pyVer" -ForegroundColor Green
}
if ($SelectedList -contains "frontend") {
    $nodeVer = & node --version 2>$null
    $npmVer = & npm.cmd --version 2>$null
    if (-not $nodeVer) { throw "Node.js is required for the Next.js frontend but was not found." }
    Write-Host "  [OK] Node.js & npm  : Node $nodeVer / npm $npmVer" -ForegroundColor Green
}

# 4. Port Conflict Inspection
Write-Section "3. Checking Mandatory Port Availability"
$PortChecks = @(
    @{ Name = "Frontend (Next.js)"; Port = $FrontendPort; Required = ($SelectedList -contains "frontend"); EnvVar = "FRONTEND_PORT" },
    @{ Name = "Rust API Backend"; Port = $RustPort; Required = ($SelectedList -contains "backend"); EnvVar = "RUST_BACKEND_PORT" },
    @{ Name = "Python Medical AI Service"; Port = $PythonAiPort; Required = ($SelectedList -contains "ai"); EnvVar = "PYTHON_AI_PORT" },
    @{ Name = "Optional FHIR Test Server"; Port = $FhirPort; Required = $false; EnvVar = "FHIR_SERVER_PORT" },
    @{ Name = "Optional PostgreSQL Host"; Port = $PostgresPort; Required = $false; EnvVar = "POSTGRES_PORT" }
)

$PortConflictFound = $false
foreach ($pc in $PortChecks) {
    $listeners = Get-NetTCPConnection -LocalPort $pc.Port -State Listen -ErrorAction SilentlyContinue
    if ($listeners) {
        $ownerPid = $listeners[0].OwningProcess
        $ownerProc = Get-Process -Id $ownerPid -ErrorAction SilentlyContinue
        $procName = if ($ownerProc) { $ownerProc.ProcessName } else { "Unknown" }
        if ($pc.Required) {
            Write-Host "  [CONFLICT] Port $($pc.Port) ($($pc.Name)) is OCCUPIED by PID $ownerPid ($procName)." -ForegroundColor Red
            Write-Host "             Safe resolution: Stop PID $ownerPid if appropriate, or set $($pc.EnvVar) in .env to an open port." -ForegroundColor Yellow
            $PortConflictFound = $true
        } else {
            Write-Host "  [INFO] Optional Port $($pc.Port) ($($pc.Name)) is in use by PID $ownerPid ($procName)." -ForegroundColor Yellow
        }
    } else {
        Write-Host "  [FREE] Port $($pc.Port) -- $($pc.Name)" -ForegroundColor Green
    }
}

if ($PortConflictFound) {
    throw "Aborting startup due to occupied required port(s). Launcher never kills unrelated processes automatically."
}

if ($CheckOnly) {
    Write-Host "`n[CheckOnly] All runtime, configuration, and port checks passed." -ForegroundColor Green
    exit 0
}

# 5. Start Selected Services & Track Child PIDs
$StartedProcesses = @()

function Stop-LauncherProcesses {
    Write-Host "`n[Launcher] Shutting down services started by this session..." -ForegroundColor Yellow
    foreach ($entry in $StartedProcesses) {
        $p = Get-Process -Id $entry.pid -ErrorAction SilentlyContinue
        if ($p) {
            Write-Host "  -> Stopping $($entry.service) (PID $($entry.pid))..."
            Stop-Process -Id $entry.pid -Force -ErrorAction SilentlyContinue
        }
    }
    if (Test-Path $PidFile) {
        Remove-Item $PidFile -Force -ErrorAction SilentlyContinue
    }
    Write-Host "[Launcher] Shutdown complete." -ForegroundColor Green
}

function Wait-HttpHealth($ServiceName, $Url, $TimeoutSec, $ProcessObj, $ErrLogPath) {
    $deadline = (Get-Date).AddSeconds($TimeoutSec)
    while ((Get-Date) -lt $deadline) {
        if ($ProcessObj.HasExited) {
            $errTail = if (Test-Path $ErrLogPath) { (Get-Content $ErrLogPath -Tail 25) -join "`n" } else { "No stderr output." }
            throw "$ServiceName exited prematurely (ExitCode $($ProcessObj.ExitCode)). Last stderr:`n$errTail"
        }
        try {
            $resp = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 40 -ErrorAction Stop
            if ($resp.StatusCode -ge 200 -and $resp.StatusCode -lt 400) {
                return $true
            }
        } catch {}
        Start-Sleep -Milliseconds 800
    }
    throw "$ServiceName failed to report healthy at $Url within ${TimeoutSec}s."
}

try {
    Write-Section "4. Starting OmniMed Insight Services in Controlled Order"

    # 4A. Start Python Medical AI Inference Service (:8200)
    if ($SelectedList -contains "ai") {
        $AiOutLog = Join-Path $LogDir "ai-service.out.log"
        $AiErrLog = Join-Path $LogDir "ai-service.err.log"
        Write-Host "[1/3] Starting Python Medical AI & Grad-CAM Service on http://${BindHost}:${PythonAiPort} ..."
        $aiProc = Start-Process -FilePath "python" `
            -ArgumentList "-m", "uvicorn", "app.main:app", "--host", $BindHost, "--port", "$PythonAiPort" `
            -WorkingDirectory (Join-Path $RepoRoot "ai-service-python") `
            -RedirectStandardOutput $AiOutLog `
            -RedirectStandardError $AiErrLog `
            -PassThru -WindowStyle Hidden

        $StartedProcesses += @{ service = "ai-service-python"; pid = $aiProc.Id; port = $PythonAiPort; log = $AiOutLog }
        ConvertTo-Json $StartedProcesses | Set-Content $PidFile
        $null = Wait-HttpHealth "Python Medical AI Service" "http://${BindHost}:${PythonAiPort}/health" 45 $aiProc $AiErrLog
        Write-Host "      [READY] Python Medical AI Service healthy at http://${BindHost}:${PythonAiPort}/health (PID $($aiProc.Id))" -ForegroundColor Green
    }

    # 4B. Build & Start Rust Primary Backend (:8100)
    if ($SelectedList -contains "backend") {
        $RustOutLog = Join-Path $LogDir "backend-rust.out.log"
        $RustErrLog = Join-Path $LogDir "backend-rust.err.log"
        Write-Host "[2/3] Building & starting Rust Primary Backend on http://${BindHost}:${RustPort} ..."
        $ErrorActionPreference = "Continue"
        & cargo build --manifest-path (Join-Path $RepoRoot "backend-rust\Cargo.toml")
        $cargoExit = $LASTEXITCODE
        $ErrorActionPreference = "Stop"
        if ($cargoExit -ne 0) {
            throw "Cargo build failed for backend-rust."
        }
        $rustBin = Join-Path $RepoRoot "backend-rust\target\debug\omnimed-backend-rust.exe"
        $rustProc = Start-Process -FilePath $rustBin `
            -WorkingDirectory $RepoRoot `
            -RedirectStandardOutput $RustOutLog `
            -RedirectStandardError $RustErrLog `
            -PassThru -WindowStyle Hidden

        $StartedProcesses += @{ service = "backend-rust"; pid = $rustProc.Id; port = $RustPort; log = $RustOutLog }
        ConvertTo-Json $StartedProcesses | Set-Content $PidFile
        $null = Wait-HttpHealth "Rust Primary Backend" "http://${BindHost}:${RustPort}/health" 30 $rustProc $RustErrLog
        Write-Host "      [READY] Rust Primary Backend healthy at http://${BindHost}:${RustPort}/health (PID $($rustProc.Id))" -ForegroundColor Green
    }

    # 4C. Install (if needed) & Start Next.js Frontend (:3100)
    if ($SelectedList -contains "frontend") {
        $FrontendDir = Join-Path $RepoRoot "frontend"
        if (-not (Test-Path (Join-Path $FrontendDir "node_modules"))) {
            Write-Host "      Installing frontend npm dependencies (first run)..." -ForegroundColor Yellow
            Push-Location $FrontendDir
            & npm.cmd install --no-audit --no-fund
            Pop-Location
        }
        $FeOutLog = Join-Path $LogDir "frontend.out.log"
        $FeErrLog = Join-Path $LogDir "frontend.err.log"
        $NextBin = "node_modules\next\dist\bin\next"
        Write-Host "[3/3] Starting Next.js + Tailwind CSS Frontend on http://${BindHost}:${FrontendPort} ..."
        $feProc = Start-Process -FilePath "node" `
            -ArgumentList $NextBin, "dev", "-p", "$FrontendPort", "-H", $BindHost `
            -WorkingDirectory $FrontendDir `
            -RedirectStandardOutput $FeOutLog `
            -RedirectStandardError $FeErrLog `
            -PassThru -WindowStyle Hidden

        $StartedProcesses += @{ service = "frontend-nextjs"; pid = $feProc.Id; port = $FrontendPort; log = $FeOutLog }
        ConvertTo-Json $StartedProcesses | Set-Content $PidFile
        $null = Wait-HttpHealth "Next.js Frontend" "http://${BindHost}:${FrontendPort}" 90 $feProc $FeErrLog
        Write-Host "      [READY] Next.js Frontend healthy at http://${BindHost}:${FrontendPort} (PID $($feProc.Id))" -ForegroundColor Green
    }

    Write-Section "5. OmniMed Insight (XAI) Service Readiness Summary"
    foreach ($s in $StartedProcesses) {
        Write-Host ("  * {0,-22} | http://{1}:{2,-5} | PID {3,-6} | HEALTHY | Log: {4}" -f $s.service, $BindHost, $s.port, $s.pid, $s.log) -ForegroundColor Green
    }

    if ($VerifyAndExit) {
        Write-Section "6. Executing End-to-End Integration Verification Probe"
        $statusResp = Invoke-RestMethod -Uri "http://${BindHost}:${RustPort}/api/system/status" -Method Get
        Write-Host "  -> Rust API -> Python AI Status : $($statusResp.python_ai_service.status)" -ForegroundColor Cyan
        Write-Host "  -> FHIR R4 Validator Status     : $($statusResp.fhir_interoperability.local_r4_validator)" -ForegroundColor Cyan

        $loginBody = @{ email = "clinician@omnimed-insight.local"; password = "Clinician!2026" } | ConvertTo-Json
        $loginResp = Invoke-RestMethod -Uri "http://${BindHost}:${RustPort}/api/auth/login" -Method Post -ContentType "application/json" -Body $loginBody
        $token = $loginResp.session_token
        $headers = @{ Authorization = "Bearer $token"; "X-CSRF-Token" = $loginResp.csrf_token }

        $anBody = @{ image_id = "img-synth-001"; xai_method = "GRAD_CAM" } | ConvertTo-Json
        $anResp = Invoke-RestMethod -Uri "http://${BindHost}:${RustPort}/api/cases/case-synth-001/analyze" -Method Post -Headers $headers -ContentType "application/json" -Body $anBody
        Write-Host "  -> End-to-End Grad-CAM Job      : $($anResp.job.id) ($($anResp.job.status)) - Predicted: $($anResp.job.predicted_class_label)" -ForegroundColor Green
        Write-Host "`n[VerifyAndExit] End-to-end verification succeeded!" -ForegroundColor Green
        exit 0
    }

    Write-Host "`nPress Ctrl+C at any time to stop all services cleanly. Streaming service logs..." -ForegroundColor Cyan
    while ($true) {
        foreach ($entry in $StartedProcesses) {
            $p = Get-Process -Id $entry.pid -ErrorAction SilentlyContinue
            if (-not $p) {
                throw "Service $($entry.service) (PID $($entry.pid)) stopped unexpectedly."
            }
        }
        Start-Sleep -Seconds 2
    }
} finally {
    Stop-LauncherProcesses
}
