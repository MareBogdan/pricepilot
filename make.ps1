<#
.SYNOPSIS
  Windows shim for the Makefile. `make` is not installed on this machine.

.DESCRIPTION
  Mirrors the Makefile targets so the same commands work here and on the VPS.
  The real logic lives in scripts/ and in uv, so neither this file nor the Makefile
  is a source of truth. See DECISIONS.md ADR-0003.

.EXAMPLE
  .\make.ps1 status
  .\make.ps1 check
#>
param(
    [Parameter(Position = 0)][string]$Target = 'help',
    [Parameter(Position = 1, ValueFromRemainingArguments = $true)][string[]]$Rest
)

$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot

function Invoke-Step {
    param([string[]]$Command)
    Write-Host "> $($Command -join ' ')" -ForegroundColor DarkGray
    & $Command[0] @($Command[1..($Command.Length - 1)])
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}

switch ($Target) {
    'install'    { Invoke-Step @('uv', 'sync', '--extra', 'dev') }
    'lint'       { Invoke-Step @('uv', 'run', 'ruff', 'check', '.'); Invoke-Step @('uv', 'run', 'ruff', 'format', '--check', '.') }
    'format'     { Invoke-Step @('uv', 'run', 'ruff', 'format', '.'); Invoke-Step @('uv', 'run', 'ruff', 'check', '--fix', '.') }
    'typecheck'  { Invoke-Step @('uv', 'run', 'mypy') }
    'test'       { Invoke-Step @('uv', 'run', 'pytest') }
    'check'      { & $PSCommandPath lint; & $PSCommandPath typecheck; & $PSCommandPath test }
    'status'     { Invoke-Step @('uv', 'run', 'python', 'scripts/status.py') }
    'cost'       { Invoke-Step @('uv', 'run', 'python', 'scripts/cost.py') }
    'up'         { Invoke-Step @('docker', 'compose', 'up', '-d', '--build') }
    'down'       { Invoke-Step @('docker', 'compose', 'down') }
    'logs'       { Invoke-Step @('docker', 'compose', 'logs', '-f') }
    'migrate'    { Invoke-Step @('uv', 'run', 'alembic', 'upgrade', 'head') }
    'revision'   { Invoke-Step (@('uv', 'run', 'alembic', 'revision', '--autogenerate', '-m') + $Rest) }
    'api'        { Invoke-Step @('uv', 'run', 'uvicorn', 'pricepilot.api.main:app', '--reload', '--port', '8000') }
    'mock-store' { Invoke-Step @('uv', 'run', 'uvicorn', 'services.mock_store.app:app', '--reload', '--port', '8001') }
    'health' {
        foreach ($u in 'http://localhost:8000/health', 'http://localhost:8001/health') {
            try { (Invoke-WebRequest -Uri $u -UseBasicParsing -TimeoutSec 5).Content }
            catch { Write-Host "$u -> unreachable" -ForegroundColor Yellow }
        }
    }
    'clean' {
        foreach ($d in '.pytest_cache', '.ruff_cache', '.mypy_cache', 'htmlcov') {
            if (Test-Path $d) { Remove-Item -Recurse -Force $d }
        }
    }
    default {
        Write-Host "PricePilot targets:" -ForegroundColor Cyan
        @(
            'install     Create the venv and install all dependencies'
            'lint        ruff check + format check'
            'format      Auto-format and auto-fix'
            'typecheck   mypy strict'
            'test        Run the test suite (offline)'
            'check       lint + typecheck + test (what CI runs)'
            'status      Live project status - run this first each session'
            'cost        LLM spend to date by phase and model'
            'up/down     docker compose up -d --build / down'
            'migrate     alembic upgrade head'
            'api         Run the API locally on :8000'
            'mock-store  Run the mock store locally on :8001'
            'health      Curl both health endpoints'
        ) | ForEach-Object { Write-Host "  $_" }
    }
}
