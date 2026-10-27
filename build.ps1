[CmdletBinding()]
param([switch]$SkipTests, [string]$Python = '')
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
if ([string]::IsNullOrWhiteSpace($Python)) { $Python = Join-Path $PSScriptRoot '.venv\Scripts\python.exe' }
function Assert-ExitCode([string]$Step) {
    if ($LASTEXITCODE -ne 0) { throw "$Step failed with exit code $LASTEXITCODE" }
}
Push-Location -LiteralPath $PSScriptRoot
try {
    if (-not (Test-Path -LiteralPath $Python)) { throw 'Install requirements-dev.txt into .venv first.' }
    if ([Environment]::OSVersion.Platform -ne [PlatformID]::Win32NT) { throw 'Build on Windows.' }
    if (-not $SkipTests) { & $Python -m pytest -q; Assert-ExitCode 'Tests' }
    $workPath = Join-Path $PSScriptRoot 'build\v1.1-local'
    $distPath = Join-Path $PSScriptRoot 'dist\v1.1-local'
    $bundlePath = Join-Path $distPath 'NailongQuanxue'
    New-Item -ItemType Directory -Path $workPath -Force | Out-Null
    $arguments = @('-m','PyInstaller','--noconfirm','--onedir','--windowed','--noupx',
        '--name','NailongQuanxue','--distpath',$distPath,'--workpath',$workPath,'--specpath',$workPath)
    foreach ($name in @('default_break.mp4','fallback_overlay.jpg')) {
        $assetPath = Join-Path $PSScriptRoot "assets\$name"
        if (-not (Test-Path -LiteralPath $assetPath)) { throw "Missing fixed asset: $name" }
        $arguments += @('--add-data',"${assetPath}:assets")
    }
    $arguments += 'main.py'
    & $Python @arguments
    Assert-ExitCode 'PyInstaller'
    & $Python tools/prune_bundle.py $bundlePath
    Assert-ExitCode 'Unused image plugin removal'
    foreach ($name in @('README.md','LICENSE','PRIVACY.md','THIRD_PARTY_NOTICES.md','MANUAL_TESTS.md')) {
        Copy-Item -LiteralPath (Join-Path $PSScriptRoot $name) -Destination $bundlePath -Force
    }
    Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'licenses') -Destination $bundlePath -Recurse -Force
    Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'assets\ASSET_MANIFEST.md') -Destination $bundlePath -Force
    Set-Content -LiteralPath (Join-Path $bundlePath 'LOCAL-ONLY-NOT-PUBLISHED.txt') -Encoding ASCII -Value 'Local V1.1 candidate. Contains user-provided video/image. Redistribution and GitHub publication require separate approval.'
    & $Python tools/scan_public.py $bundlePath --allow-fixed-assets --report (Join-Path $workPath 'bundle-audit.json')
    Assert-ExitCode 'Local bundle data audit'
    $zipPath = Join-Path $distPath 'NailongQuanxue-v1.1.0-Windows-local.zip'
    Compress-Archive -LiteralPath $bundlePath -DestinationPath $zipPath -Force
    & $Python tools/scan_public.py $zipPath --allow-fixed-assets --report (Join-Path $workPath 'zip-audit.json')
    Assert-ExitCode 'Local ZIP data audit'
    $hash = (Get-FileHash -LiteralPath $zipPath -Algorithm SHA256).Hash.ToLowerInvariant()
    Set-Content -LiteralPath "$zipPath.sha256" -Encoding ASCII -Value "$hash  $([IO.Path]::GetFileName($zipPath))"
    & $Python -m pip freeze | Set-Content -LiteralPath (Join-Path $workPath 'environment.txt') -Encoding UTF8
    Write-Host "LOCAL ONLY; nothing published: $bundlePath\NailongQuanxue.exe"
    Write-Host "ZIP: $zipPath"
} finally { Pop-Location }
