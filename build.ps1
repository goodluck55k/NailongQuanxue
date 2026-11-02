[CmdletBinding()]
param(
    [switch]$SkipTests,
    [switch]$Release,
    [string]$Python = '',
    [string]$Version = ''
)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
if ([string]::IsNullOrWhiteSpace($Python)) { $Python = Join-Path $PSScriptRoot '.venv\Scripts\python.exe' }
function Assert-ExitCode([string]$Step) {
    if ($LASTEXITCODE -ne 0) { throw "$Step failed with exit code $LASTEXITCODE" }
}
Push-Location -LiteralPath $PSScriptRoot
try {
    if (-not (Test-Path -LiteralPath $Python)) { throw 'Install requirements-dev.txt into .venv first (or pass -Python).' }
    if ([Environment]::OSVersion.Platform -ne [PlatformID]::Win32NT) { throw 'Build on Windows.' }

    if ([string]::IsNullOrWhiteSpace($Version)) {
        $Version = (& $Python tools\read_version.py).Trim()
        Assert-ExitCode 'Read APP_VERSION'
    }
    if ($Version -notmatch '^\d+\.\d+\.\d+$') { throw "Bad version: $Version" }
    Write-Host "Version: $Version"

    if (-not $SkipTests) { & $Python -m pytest -q; Assert-ExitCode 'Tests' }
    & $Python -m compileall -q app main.py tools tests; Assert-ExitCode 'Compile check'
    & $Python -m pip check; Assert-ExitCode 'Dependency check'

    $flavor = if ($Release) { 'release' } else { 'local' }
    $workPath = Join-Path $PSScriptRoot "build\v$Version-$flavor"
    $distPath = Join-Path $PSScriptRoot "dist\v$Version-$flavor"
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
    $docsPath = Join-Path $bundlePath 'docs'
    New-Item -ItemType Directory -Force -Path $docsPath | Out-Null
    Get-ChildItem -LiteralPath (Join-Path $PSScriptRoot 'docs') -Filter *.md -File |
        Copy-Item -Destination $docsPath -Force

    $noticePath = Join-Path $bundlePath 'LOCAL-ONLY-NOT-PUBLISHED.txt'
    if ($Release) {
        Remove-Item -LiteralPath $noticePath -Force -ErrorAction SilentlyContinue
    } else {
        Set-Content -LiteralPath $noticePath -Encoding ASCII -Value 'Local candidate build. Not for redistribution; the official Windows package is built with -Release.'
    }

    & $Python tools/scan_public.py $bundlePath --allow-fixed-assets --report (Join-Path $workPath 'bundle-audit.json')
    Assert-ExitCode 'Bundle data audit'

    $exePath = Join-Path $bundlePath 'NailongQuanxue.exe'
    if (-not (Test-Path -LiteralPath $exePath)) { throw 'Bundle has no NailongQuanxue.exe' }
    $internalPath = Join-Path $bundlePath '_internal'
    if (-not (Test-Path -LiteralPath $internalPath)) { throw 'Bundle has no _internal folder' }
    if ($Release -and (Test-Path -LiteralPath $noticePath)) { throw 'Release bundle still contains the local-only notice' }
    foreach ($forbidden in @('settings.json','records.sqlite3','pending-events.json')) {
        if (Test-Path -LiteralPath (Join-Path $bundlePath $forbidden)) { throw "Release bundle contains local data: $forbidden" }
    }
    foreach ($forbiddenDir in @('photos','videos','NailongData')) {
        if (Test-Path -LiteralPath (Join-Path $bundlePath $forbiddenDir)) { throw "Release bundle contains local data folder: $forbiddenDir" }
    }

    $zipName = if ($Release) { "NailongQuanxue-v$Version-Windows-x64.zip" } else { "NailongQuanxue-v$Version-Windows-local.zip" }
    $zipPath = Join-Path $distPath $zipName
    if (Test-Path -LiteralPath $zipPath) { Remove-Item -LiteralPath $zipPath -Force }
    Compress-Archive -LiteralPath $bundlePath -DestinationPath $zipPath
    & $Python tools/scan_public.py $zipPath --allow-fixed-assets --report (Join-Path $workPath 'zip-audit.json')
    Assert-ExitCode 'ZIP data audit'

    $verifyArgs = @($zipPath, '--report', (Join-Path $workPath 'bundle-verify.json'))
    if (-not $Release) { $verifyArgs += '--allow-local-notice' }
    & $Python tools/verify_bundle.py @verifyArgs
    Assert-ExitCode 'ZIP content verification'

    $hash = (Get-FileHash -LiteralPath $zipPath -Algorithm SHA256).Hash.ToLowerInvariant()
    $zipFileName = [IO.Path]::GetFileName($zipPath)
    Set-Content -LiteralPath "$zipPath.sha256" -Encoding ASCII -Value "$hash  $zipFileName"
    & $Python -m pip freeze | Set-Content -LiteralPath (Join-Path $workPath 'environment.txt') -Encoding UTF8

    Write-Host "Bundle: $bundlePath"
    Write-Host "ZIP: $zipPath"
    Write-Host "SHA256: $hash"
    if ($Release) {
        Write-Host 'RELEASE PACKAGE (ready for GitHub Release)'
    } else {
        Write-Host 'LOCAL BUILD ONLY (pass -Release for the publishable package)'
    }
} finally { Pop-Location }
