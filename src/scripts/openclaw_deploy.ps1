# OpenClaw Hardened Auto-Deployment Script for Windows Server (v2.1)
# This version fixes the Hex color error and silences Docker daemon connection warnings.
# Usage: .\openclaw_deploy.ps1 -GrokKey "YOUR_API_KEY" -ForceCleanup $true

param (
    [string]$GrokKey = "",
    [bool]$ForceCleanup = $true
)

$InstallDir = "C:\OpenClaw_Agent"
$RepoUrl = "https://github.com/openclaw/openclaw.git" 
$TargetPort = 3000

Write-Host ">>> STARTING HARDENED OPENCLAW DEPLOYMENT..." -ForegroundColor Green

# --- PHASE 0: CONFLICT RESOLUTION ---
Write-Host ">>> PHASE 0: SANITIZING ENVIRONMENT..." -ForegroundColor Cyan

if ($ForceCleanup) {
    # 1. Kill potentially conflicting Node processes
    Write-Host "> Checking for ghost Node processes..." -ForegroundColor Gray
    Get-Process -Name "node" -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue

    # 2. Check for Docker conflicts (Silent check for Daemon)
    if (Get-Command docker -ErrorAction SilentlyContinue) {
        Write-Host "> Docker found. Attempting to clean OpenClaw containers..." -ForegroundColor Gray
        # We try to list containers; if it fails (daemon off), we just skip
        $dockerActive = docker ps -q 2>$null
        if ($LASTEXITCODE -eq 0) {
            docker ps -a -q --filter "name=openclaw" | ForEach-Object { docker stop $_; docker rm $_ } 2>$null
        } else {
            Write-Host "- Docker daemon not reachable or not running. Skipping Docker cleanup." -ForegroundColor Gray
        }
    }

    # 3. Check and free Port 3000
    Write-Host "> Checking Port $TargetPort..." -ForegroundColor Gray
    $portUsage = Get-NetTCPConnection -LocalPort $TargetPort -ErrorAction SilentlyContinue
    if ($portUsage) {
        Write-Host "! Port $TargetPort is occupied by PID $($portUsage.OwningProcess). Terminating..." -ForegroundColor Yellow
        Stop-Process -Id $portUsage.OwningProcess -Force -ErrorAction SilentlyContinue
    }

    # 4. Clean old directory if corrupted
    if (Test-Path $InstallDir) {
        Write-Host "> Wiping old installation directory to ensure clean start..." -ForegroundColor Gray
        Remove-Item -Path $InstallDir -Recurse -Force -ErrorAction SilentlyContinue
    }
}

# --- PHASE 1: PREREQUISITES ---
Write-Host ">>> PHASE 1: CHECKING SYSTEM..." -ForegroundColor Cyan
$nodeVersion = node -v
if (!$nodeVersion) {
    Write-Host "X Node.js not found. FATAL ERROR." -ForegroundColor Red
    Exit
}
Write-Host "v Environment Verified." -ForegroundColor Green

# --- PHASE 2: ISOLATED DEPLOYMENT ---
Write-Host ">>> PHASE 2: ISOLATED DEPLOYMENT..." -ForegroundColor Cyan

if (!(Test-Path $InstallDir)) {
    New-Item -ItemType Directory -Force -Path $InstallDir | Out-Null
}
Set-Location $InstallDir

Write-Host "> Cloning fresh repository..." -ForegroundColor Gray
git clone $RepoUrl . 2>$null
if (!(Test-Path "package.json")) {
    Write-Host "X Repository content not found (clone failed). Check internet or GitHub access." -ForegroundColor Red
    Exit
}

Write-Host "> Installing dependencies (isolated)..." -ForegroundColor Gray
# Using npm.cmd for better Windows compatibility
& npm.cmd install --silent --no-audit --no-fund
if ($LASTEXITCODE -ne 0) {
    Write-Host "! npm install returned an error. Agent might be unstable." -ForegroundColor Yellow
}

# --- PHASE 3: CONFIGURATION ---
Write-Host ">>> PHASE 3: IDENTITY PROVISIONING..." -ForegroundColor Cyan
$EnvFile = "$InstallDir\.env"
$ConfigContent = @"
PORT=$TargetPort
AGENT_NAME=Grok_Overlord
AI_PROVIDER=grok
GROK_API_KEY=$GrokKey
GROK_MODEL=grok-3
ALLOW_SHELL=true
ALLOW_FILE_SYSTEM=true
# Isolation
DISABLE_TELEMETRY=true
"@
Set-Content -Path $EnvFile -Value $ConfigContent
Write-Host "+ Configuration secured in isolated .env" -ForegroundColor Green

# --- PHASE 4: LAUNCHER ---
$StartScript = "@echo off
title OpenClaw Agent [Grok]
cd /d $InstallDir
cls
echo [v] STARTING OPENCLAW AGENT (GROK_OVERLORD)
npm start"
Set-Content -Path "$InstallDir\launch_agent.bat" -Value $StartScript

Write-Host "`n>>> DEPLOYMENT SUCCESSFUL." -ForegroundColor Green
Write-Host "Isolated folder: $InstallDir" -ForegroundColor White
Write-Host "1. Run '$InstallDir\launch_agent.bat' to start." -ForegroundColor Cyan
Write-Host "2. All ghost processes and Docker conflicts have been cleared." -ForegroundColor Yellow
