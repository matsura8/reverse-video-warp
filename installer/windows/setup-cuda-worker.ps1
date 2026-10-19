[CmdletBinding()]
param(
    [string]$EnvironmentPath = (Join-Path $env:LOCALAPPDATA 'ReverseWarp\venv'),
    [string]$PythonLauncher = 'py',
    [string]$PythonVersion = '3.12'
)

$ErrorActionPreference = 'Stop'
$repoRoot = Resolve-Path (Join-Path $PSScriptRoot '..\..')
$requirements = Join-Path $repoRoot 'inference-worker\requirements-cuda.txt'

if (-not (Get-Command nvidia-smi.exe -ErrorAction SilentlyContinue)) {
    throw 'nvidia-smi.exe was not found. Install a supported NVIDIA driver first.'
}

$gpuNames = & nvidia-smi.exe --query-gpu=name --format=csv,noheader
if ($LASTEXITCODE -ne 0 -or -not $gpuNames) {
    throw 'No NVIDIA GPU was reported by nvidia-smi.'
}

if (-not (Test-Path -LiteralPath $EnvironmentPath)) {
    & $PythonLauncher "-$PythonVersion" -m venv $EnvironmentPath
    if ($LASTEXITCODE -ne 0) { throw 'Failed to create the Python environment.' }
}

$python = Join-Path $EnvironmentPath 'Scripts\python.exe'
& $python -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) { throw 'Failed to upgrade pip.' }
& $python -m pip install --requirement $requirements
if ($LASTEXITCODE -ne 0) { throw 'Failed to install CUDA worker requirements.' }

$worker = Join-Path $repoRoot 'inference-worker\worker.py'
& $python $worker --device cuda:0 --probe
if ($LASTEXITCODE -ne 0) { throw 'CUDA worker probe failed.' }

Write-Host "CUDA worker environment ready at $EnvironmentPath"
