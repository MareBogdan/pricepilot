<#
.SYNOPSIS
  Builds the slim folder that gets pushed to a Hugging Face Docker Space.

.DESCRIPTION
  Copies ONLY what the lean serving image needs (Dockerfile, .dockerignore, README.md with the
  Space metadata, pyproject.toml, src/, services/, config/ and the three result JSONs the dashboard
  reads), then makes it a fresh git repository with one commit. No model, no data, no tests, no
  project history: the Space repo stays about a megabyte. Nothing is pushed from here.

  Usage:  .\scripts\make_space_bundle.ps1 [-OutDir <path>]
  Then:   cd <OutDir>; git remote add space https://huggingface.co/spaces/<user>/<space>
          git push space main --force
#>
param(
    [string]$OutDir = (Join-Path $env:TEMP 'pricepilot-space')
)
$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $PSScriptRoot

$results = @(
    'mmarco-mMiniLMv2-finetuned-ep6-metrics.json',
    'mmarco-mMiniLMv2-zeroshot-metrics.json',
    'phase5-policy-retrieval-eval.json'
)

if (Test-Path $OutDir) { Remove-Item -Recurse -Force $OutDir }
New-Item -ItemType Directory -Force $OutDir | Out-Null

foreach ($f in 'Dockerfile', '.dockerignore', 'README.md', 'pyproject.toml') {
    Copy-Item (Join-Path $repo $f) (Join-Path $OutDir $f)
}
foreach ($d in 'src', 'services', 'config') {
    # /XD skips bytecode caches; robocopy exit codes below 8 mean success.
    robocopy (Join-Path $repo $d) (Join-Path $OutDir $d) /E /XD __pycache__ /XF *.pyc /NFL /NDL /NJH /NJS /NP | Out-Null
    if ($LASTEXITCODE -ge 8) { throw "robocopy failed for $d (exit $LASTEXITCODE)" }
}
$resultsDir = Join-Path $OutDir 'docs\learned\results'
New-Item -ItemType Directory -Force $resultsDir | Out-Null
foreach ($f in $results) {
    Copy-Item (Join-Path $repo "docs\learned\results\$f") (Join-Path $resultsDir $f)
}

# Safety net: fail loudly if anything heavy slipped in.
$heavy = Get-ChildItem -Recurse -File $OutDir | Where-Object { $_.Length -gt 5MB -or $_.Extension -in '.zip', '.onnx', '.pt', '.safetensors', '.gguf' }
if ($heavy) { throw "bundle contains heavy files: $($heavy.FullName -join ', ')" }

Push-Location $OutDir
try {
    $ErrorActionPreference = 'Continue'
    git init -q -b main
    git config core.autocrlf false
    git add -A
    git -c user.name='PricePilot deploy' -c user.email='deploy@localhost' commit -q -m 'Deploy bundle'
    $size = [math]::Round(((Get-ChildItem -Recurse -File $OutDir -Exclude .git | Measure-Object Length -Sum).Sum) / 1MB, 2)
    Write-Host "Bundle ready: $OutDir  ($size MB, $((git ls-files | Measure-Object).Count) files)" -ForegroundColor Green
} finally { Pop-Location }
