$ErrorActionPreference = "Stop"

Write-Host "OptoSigma GSC-02C setup" -ForegroundColor Cyan
Write-Host "Checking for Astral uv..."

if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Write-Host "uv was not found." -ForegroundColor Yellow
    Write-Host "Install it with one of these commands, then reopen PowerShell:" -ForegroundColor Yellow
    Write-Host '  winget install --id=astral-sh.uv -e'
    Write-Host 'or:'
    Write-Host '  powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"'
    exit 1
}

Write-Host "Creating/syncing the project environment..."
uv sync

Write-Host "Running software-only tests..."
uv run python -m unittest discover -s tests -v

Write-Host ""
Write-Host "Setup complete." -ForegroundColor Green
Write-Host "Launch the UI with: uv run gsc02c-ui"
