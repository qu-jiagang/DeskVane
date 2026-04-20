param(
    [string]$Python = "python",
    [string]$AppName = "DeskVane",
    [string]$DistDir = "",
    [string]$WorkDir = "",
    [string]$IconPath = "",
    [switch]$OneFile,
    [switch]$Console,
    [switch]$SkipInstaller,
    [string]$IsccPath = ""
)

$ErrorActionPreference = "Stop"

$RootDir = Split-Path -Parent $PSScriptRoot
Set-Location $RootDir
if (-not $DistDir) {
    $DistDir = Join-Path $RootDir "dist\pyinstaller"
}
if (-not $WorkDir) {
    $WorkDir = Join-Path $RootDir "build\pyinstaller"
}

$AppVersion = & $Python -c "from pathlib import Path; import re; text=Path('pyproject.toml').read_text(encoding='utf-8'); m=re.search(r'^version\s*=\s*\"([^\"]+)\"', text, re.MULTILINE); print(m.group(1) if m else '')"
if (-not $AppVersion) {
    throw "Unable to read version from pyproject.toml"
}

$env:DESKVANE_APP_NAME = $AppName
$env:DESKVANE_APP_VERSION = $AppVersion.Trim()
$env:DESKVANE_TARGET_OS = "windows"
$env:DESKVANE_ONEFILE = if ($OneFile) { "1" } else { "0" }
$env:DESKVANE_WINDOWED = if ($Console) { "0" } else { "1" }

if ($IconPath) {
    $env:DESKVANE_ICON_FILE = (Resolve-Path $IconPath).Path
}

& $Python -m PyInstaller --version *> $null
if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller is required. Try: $Python -m pip install -e .[packaging]"
}

New-Item -ItemType Directory -Force -Path $DistDir, $WorkDir | Out-Null

& $Python -m PyInstaller `
    --noconfirm `
    --clean `
    --distpath $DistDir `
    --workpath $WorkDir `
    (Join-Path $RootDir "packaging\pyinstaller\deskvane.spec")

if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller build failed"
}

$AppOutput = if ($OneFile) {
    Join-Path $DistDir "$AppName.exe"
} else {
    Join-Path $DistDir $AppName
}
Write-Host "Built application output: $AppOutput"

if ($SkipInstaller -or $OneFile) {
    return
}

if (-not $IsccPath) {
    $defaultPaths = @(
        "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
        "${env:ProgramFiles}\Inno Setup 6\ISCC.exe"
    )
    $IsccPath = $defaultPaths | Where-Object { $_ -and (Test-Path $_) } | Select-Object -First 1
}

if (-not $IsccPath) {
    Write-Host "Skipping installer build because ISCC.exe was not found. See packaging/windows/README.md"
    return
}

& $IsccPath `
    "/DSourceDir=$RootDir" `
    "/DAppName=$AppName" `
    "/DAppVersion=$($AppVersion.Trim())" `
    (Join-Path $RootDir "packaging\windows\deskvane.iss")

if ($LASTEXITCODE -ne 0) {
    throw "Inno Setup packaging failed"
}

Write-Host "Built installer under $(Join-Path $RootDir 'dist\installer')"
