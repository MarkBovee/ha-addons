# Local debug script for Windows PowerShell
# This script helps set up environment variables and run the addon locally

# Check if .env file exists
if (Test-Path .env) {
    Write-Host "Loading environment variables from .env file..."
    Get-Content .env | ForEach-Object {
        if ($_ -match '^\s*([^#][^=]+)=(.*)$') {
            $key = $matches[1].Trim()
            $value = $matches[2].Trim().Trim('"').Trim("'")
            [Environment]::SetEnvironmentVariable($key, $value, "Process")
        }
    }
} else {
    Write-Host "No .env file found. Using system environment variables."
    Write-Host "You can create a .env file based on .env.example"
}

# Set default values if not already set
if (-not $env:CHARGER_HOST_NAME) { $env:CHARGER_HOST_NAME = "my.charge.space" }
if (-not $env:CHARGER_BASE_URL) { $env:CHARGER_BASE_URL = "https://my.charge.space" }
if (-not $env:CHARGER_UPDATE_INTERVAL) { $env:CHARGER_UPDATE_INTERVAL = "1" }
if (-not $env:HA_API_URL) { $env:HA_API_URL = "http://localhost:8123/api" }

# Check if Python 3 is available
try {
    $pythonVersion = python --version 2>&1
    if ($LASTEXITCODE -ne 0) {
        throw "Python not found"
    }
    Write-Host "Found: $pythonVersion"
} catch {
    Write-Host "ERROR: Python is not installed or not in PATH" -ForegroundColor Red
    exit 1
}

# Run the local debug script
python run_local.py

