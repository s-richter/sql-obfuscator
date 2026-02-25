# run-tests-safe.ps1
# Usage examples:
#   .\run-tests-safe.ps1
#   .\run-tests-safe.ps1 -PytestArgs "tests/test_cli.py -q"
#   .\run-tests-safe.ps1 -SkipPipInstall

param(
  [string]$PytestArgs = "-q",
  [switch]$SkipPipInstall
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $repoRoot

$venvPy = Join-Path $repoRoot ".venv\Scripts\python.exe"
$venvPytest = Join-Path $repoRoot ".venv\Scripts\pytest.exe"

if (-not (Test-Path $venvPy)) {
  throw "Missing virtual env Python: $venvPy"
}
if (-not (Test-Path $venvPytest)) {
  throw "Missing pytest executable: $venvPytest"
}

$runStamp = Get-Date -Format "yyyyMMdd_HHmmss"
$tempRoot = Join-Path $repoRoot ".run_tmp\$runStamp"
$baseTemp = Join-Path $repoRoot ".run_tmp\pytest\$runStamp"

New-Item -ItemType Directory -Force -Path $tempRoot | Out-Null
New-Item -ItemType Directory -Force -Path $baseTemp | Out-Null

# Save old env vars so we can restore them
$oldTEMP = $env:TEMP
$oldTMP = $env:TMP
$oldPIP_CACHE_DIR = $env:PIP_CACHE_DIR
$oldPIP_DISABLE_PIP_VERSION_CHECK = $env:PIP_DISABLE_PIP_VERSION_CHECK
$oldPIP_BUILD_TRACKER = $env:PIP_BUILD_TRACKER
$oldPYTHONDONTWRITEBYTECODE = $env:PYTHONDONTWRITEBYTECODE

try {
  # Keep all temp artifacts local to repo
  $env:TEMP = $tempRoot
  $env:TMP = $tempRoot
  $env:PIP_CACHE_DIR = Join-Path $repoRoot ".pip_cache"
  $env:PIP_DISABLE_PIP_VERSION_CHECK = "1"
  $env:PIP_BUILD_TRACKER = Join-Path $tempRoot "pip-build-tracker"
  $env:PYTHONDONTWRITEBYTECODE = "1"
  New-Item -ItemType Directory -Force -Path $env:PIP_BUILD_TRACKER | Out-Null

  if (-not $SkipPipInstall) {
    & $venvPy -m pip install -e . --no-build-isolation --no-deps
  }

  # -p no:cacheprovider avoids .pytest_cache writes (often AV-locked on Windows)
  $pytestArgList = @()
  if ($PytestArgs.Trim().Length -gt 0) {
    $pytestArgList += ($PytestArgs -split '\s+')
  }
  $pytestArgList += "--basetemp"
  $pytestArgList += $baseTemp
  $pytestArgList += "-p"
  $pytestArgList += "no:cacheprovider"
  Write-Host "Running: $venvPytest $($pytestArgList -join ' ')"

  & $venvPytest @pytestArgList
  $exitCode = $LASTEXITCODE
}
finally {
  # Restore env vars
  $env:TEMP = $oldTEMP
  $env:TMP = $oldTMP
  $env:PIP_CACHE_DIR = $oldPIP_CACHE_DIR
  $env:PIP_DISABLE_PIP_VERSION_CHECK = $oldPIP_DISABLE_PIP_VERSION_CHECK
  $env:PIP_BUILD_TRACKER = $oldPIP_BUILD_TRACKER
  $env:PYTHONDONTWRITEBYTECODE = $oldPYTHONDONTWRITEBYTECODE
}

if ($exitCode -ne 0) {
  Write-Error "pytest failed with exit code $exitCode"
  exit $exitCode
}

Write-Host "pytest completed successfully."
