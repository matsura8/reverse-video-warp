[CmdletBinding()]
param(
    [string]$InstallRoot = (Join-Path $env:LOCALAPPDATA 'ReverseWarp\third_party\FALdetector')
)

$ErrorActionPreference = 'Stop'
$repoRoot = Resolve-Path (Join-Path $PSScriptRoot '..\..')
$manifestPath = Join-Path $repoRoot 'inference-worker\fal-baseline.json'
$manifest = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
$parent = Split-Path -Parent $InstallRoot
New-Item -ItemType Directory -Force -Path $parent | Out-Null

if (-not (Test-Path -LiteralPath (Join-Path $InstallRoot '.git'))) {
    git clone $manifest.upstream.repository $InstallRoot
    if ($LASTEXITCODE -ne 0) { throw 'Failed to clone the pinned FALdetector source.' }
}

git -C $InstallRoot fetch --all --prune
if ($LASTEXITCODE -ne 0) { throw 'Failed to refresh the FALdetector source.' }
git -C $InstallRoot checkout --detach $manifest.upstream.commit
if ($LASTEXITCODE -ne 0) { throw 'Failed to check out the pinned FALdetector commit.' }
$actualCommit = git -C $InstallRoot rev-parse HEAD
if ($actualCommit -ne $manifest.upstream.commit) {
    throw "FALdetector commit mismatch: expected $($manifest.upstream.commit), got $actualCommit"
}

$weightsRoot = Join-Path $InstallRoot 'weights'
New-Item -ItemType Directory -Force -Path $weightsRoot | Out-Null
foreach ($property in $manifest.weights.PSObject.Properties) {
    $name = $property.Name
    $record = $property.Value
    $destination = Join-Path $weightsRoot $name
    $valid = $false
    if (Test-Path -LiteralPath $destination) {
        $hash = (Get-FileHash -Algorithm SHA256 -LiteralPath $destination).Hash.ToLowerInvariant()
        $length = (Get-Item -LiteralPath $destination).Length
        $valid = $hash -eq $record.sha256 -and $length -eq $record.size
    }
    if (-not $valid) {
        $temporary = "$destination.download"
        Invoke-WebRequest -Uri $record.url -OutFile $temporary
        $hash = (Get-FileHash -Algorithm SHA256 -LiteralPath $temporary).Hash.ToLowerInvariant()
        $length = (Get-Item -LiteralPath $temporary).Length
        if ($hash -ne $record.sha256 -or $length -ne $record.size) {
            Remove-Item -LiteralPath $temporary -Force
            throw "Downloaded weight failed verification: $name"
        }
        Move-Item -LiteralPath $temporary -Destination $destination -Force
    }
}

$python = Join-Path $env:LOCALAPPDATA 'ReverseWarp\venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python)) {
    throw 'CUDA worker environment is missing. Run setup-cuda-worker.ps1 first.'
}
$worker = Join-Path $repoRoot 'inference-worker\worker.py'
& $python $worker --device cuda:0 --fal-root $InstallRoot --fal-self-test
if ($LASTEXITCODE -ne 0) { throw 'Pinned FAL CUDA self-test failed.' }

Write-Host "Pinned FAL baseline ready at $InstallRoot"
