# OpenClaw Auto-Deployment Script for Windows Server
# Usage: .\openclaw_deploy.ps1 -GrokKey "YOUR_API_KEY"

param (
    [string]$GrokKey = ""
)

$InstallDir = "C:\OpenClaw_Agent"
$RepoUrl = "https://github.com/openclaw/openclaw.git" # Official 2026 Repo

Write-Host ">>> STARTING OPENCLAW DEPLOYMENT..." -ForegroundColor Hex "#00FF41"

# 1. Check Prerequisites (Node.js & Python)
$nodeVersion = node -v
if (!$nodeVersion) {
    Write-Host "X Node.js not found. Please install Node.js (LTS)." -ForegroundColor Red
    Exit
} else {
    Write-Host "v Node.js detected: $nodeVersion" -ForegroundColor Green
}

# 2. Setup Directory
if (!(Test-Path $InstallDir)) {
    New-Item -ItemType Directory -Force -Path $InstallDir | Out-Null
    Write-Host "+ Created Directory: $InstallDir" -ForegroundColor Green
}
Set-Location $InstallDir

# 3. Clone Repository
if (Test-Path ".git") {
    Write-Host "v Repository already exists. Pulling latest..." -ForegroundColor Yellow
    git pull
} else {
    Write-Host "> Cloning OpenClaw..." -ForegroundColor Cyan
    git clone $RepoUrl .
}

# 4. Install Dependencies
Write-Host "> Installing Dependencies (npm)..." -ForegroundColor Cyan
npm install --silent

# 5. Configure Grok API
$EnvFile = "$InstallDir\.env"
if ($GrokKey) {
    $ConfigContent = @"
PORT=3000
AGENT_NAME=Grok_Farmer
# AI Configuration
AI_PROVIDER=grok
GROK_API_KEY=$GrokKey
GROK_MODEL=grok-3
# System Access
ALLOW_SHELL=true
ALLOW_FILE_SYSTEM=true
"@
    Set-Content -Path $EnvFile -Value $ConfigContent
    Write-Host "+ Generated .env configuration with provided Grok Key." -ForegroundColor Green
} elseif (!(Test-Path $EnvFile)) {
    Write-Host "! No Grok Key provided. Creating empty .env template." -ForegroundColor Yellow
    New-Item -Path $EnvFile -ItemType File -Value "GROK_API_KEY=YOUR_KEY_HERE"
}

# 6. Create Startup Script
$StartScript = "@echo off
cd $InstallDir
npm start"
Set-Content -Path "$InstallDir\start_agent.bat" -Value $StartScript

Write-Host ">>> DEPLOYMENT COMPLETE." -ForegroundColor Hex "#00FF41"
Write-Host "Run 'C:\OpenClaw_Agent\start_agent.bat' to activate." -ForegroundColor White
