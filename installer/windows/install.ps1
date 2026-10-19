[CmdletBinding()]
param(
    [switch]$SkipBuild
)

$ErrorActionPreference = 'Stop'
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$installRoot = Join-Path $env:LOCALAPPDATA 'ReverseWarp'
$binRoot = Join-Path $installRoot 'bin'
$appRoot = Join-Path $installRoot 'app'
$extensionRoot = Join-Path $installRoot 'extensions'
$manifestRoot = Join-Path $installRoot 'native-hosts'
$cargoTarget = Join-Path $env:LOCALAPPDATA 'Temp\reversewarp-target'

if (-not $SkipBuild) {
    $env:CARGO_TARGET_DIR = $cargoTarget
    cargo build --workspace --release --locked --manifest-path (Join-Path $repoRoot 'Cargo.toml')
    if ($LASTEXITCODE -ne 0) { throw 'Rust release build failed' }
    npm ci --ignore-scripts --prefix (Join-Path $repoRoot 'extension')
    if ($LASTEXITCODE -ne 0) { throw 'Extension dependency restore failed' }
    npm test --prefix (Join-Path $repoRoot 'extension')
    if ($LASTEXITCODE -ne 0) { throw 'Extension build or tests failed' }
}

New-Item -ItemType Directory -Force -Path $binRoot, $appRoot, $extensionRoot, $manifestRoot | Out-Null
Copy-Item -LiteralPath (Join-Path $cargoTarget 'release\reversewarp-host.exe') -Destination (Join-Path $binRoot 'reversewarp-host.exe') -Force
Copy-Item -LiteralPath (Join-Path $cargoTarget 'release\reversewarp.exe') -Destination (Join-Path $binRoot 'reversewarp.exe') -Force
Copy-Item -LiteralPath (Join-Path $repoRoot 'inference-worker') -Destination $appRoot -Recurse -Force
Copy-Item -LiteralPath (Join-Path $repoRoot 'extension\dist\chromium') -Destination $extensionRoot -Recurse -Force
Copy-Item -LiteralPath (Join-Path $repoRoot 'extension\dist\firefox') -Destination $extensionRoot -Recurse -Force

$hostPath = (Join-Path $binRoot 'reversewarp-host.exe').Replace('\', '\\')
$manifests = @(
    @{ Source = 'native-host-chrome.json'; Target = 'chrome.json'; Registry = 'HKCU:\Software\Google\Chrome\NativeMessagingHosts\com.maxpowerit.reversewarp' },
    @{ Source = 'native-host-edge.json'; Target = 'edge.json'; Registry = 'HKCU:\Software\Microsoft\Edge\NativeMessagingHosts\com.maxpowerit.reversewarp' },
    @{ Source = 'native-host-firefox.json'; Target = 'firefox.json'; Registry = 'HKCU:\Software\Mozilla\NativeMessagingHosts\com.maxpowerit.reversewarp' }
)
foreach ($item in $manifests) {
    $destination = Join-Path $manifestRoot $item.Target
    (Get-Content -LiteralPath (Join-Path $PSScriptRoot $item.Source) -Raw).Replace('__HOST_PATH__', $hostPath) | Set-Content -LiteralPath $destination -Encoding utf8NoBOM
    New-Item -Path $item.Registry -Force | Out-Null
    Set-Item -Path $item.Registry -Value $destination
}

$record = @{
    installedAt = [DateTimeOffset]::Now.ToString('o')
    repository = $repoRoot
    chromiumExtension = (Join-Path $extensionRoot 'chromium')
    firefoxExtension = (Join-Path $extensionRoot 'firefox')
    host = (Join-Path $binRoot 'reversewarp-host.exe')
} | ConvertTo-Json
$record | Set-Content -LiteralPath (Join-Path $installRoot 'install.json') -Encoding utf8NoBOM

Write-Host "ReverseWarp installed at $installRoot"
Write-Host "Edge/Chrome unpacked extension: $(Join-Path $extensionRoot 'chromium')"
Write-Host "Firefox temporary extension: $(Join-Path $extensionRoot 'firefox\manifest.json')"
