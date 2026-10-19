[CmdletBinding(SupportsShouldProcess)]
param()

$ErrorActionPreference = 'Stop'
$registrations = @(
    'HKCU:\Software\Google\Chrome\NativeMessagingHosts\com.maxpowerit.reversewarp',
    'HKCU:\Software\Microsoft\Edge\NativeMessagingHosts\com.maxpowerit.reversewarp',
    'HKCU:\Software\Mozilla\NativeMessagingHosts\com.maxpowerit.reversewarp'
)
foreach ($registration in $registrations) {
    if ((Test-Path -LiteralPath $registration) -and $PSCmdlet.ShouldProcess($registration, 'Remove native-host registration')) {
        Remove-Item -LiteralPath $registration -Force
    }
}
$installRoot = Join-Path $env:LOCALAPPDATA 'ReverseWarp'
if ((Test-Path -LiteralPath $installRoot) -and $PSCmdlet.ShouldProcess($installRoot, 'Remove ReverseWarp installation')) {
    $resolved = (Resolve-Path -LiteralPath $installRoot).Path
    $expected = [IO.Path]::GetFullPath((Join-Path $env:LOCALAPPDATA 'ReverseWarp'))
    if ($resolved -ne $expected) { throw "Refusing to remove unexpected path: $resolved" }
    Remove-Item -LiteralPath $resolved -Recurse -Force
}
