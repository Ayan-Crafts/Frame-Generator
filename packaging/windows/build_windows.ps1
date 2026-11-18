<#
.SYNOPSIS
  Build the Windows release: frozen app, portable zip and installer.

.DESCRIPTION
  1. Creates an isolated build virtualenv (build\venv-win) from pinned
     requirements - the system Python is never modified.
  2. Runs the test suite (skip with -SkipTests).
  3. Freezes the app with PyInstaller (dist\TrackNetPrepper).
  4. Stages FFmpeg: either -FFmpegDir, or the pinned + SHA-256 verified
     download from packaging\ffmpeg_pins.json.
  5. Smoke-tests the frozen executables (CLI doctor + GUI window).
  6. Writes release\TrackNetV1_Dataset_Prepper_V2_Portable.zip.
  7. Compiles release\TrackNetV1_Dataset_Prepper_V2_Setup.exe with Inno Setup.
  8. Writes release\SHA256SUMS.txt.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File packaging\windows\build_windows.ps1
.EXAMPLE
  ... -FFmpegDir "C:\Program Files\ffmpeg\bin" -SkipTests
#>
[CmdletBinding()]
param(
    [string]$Python = "",
    [string]$FFmpegDir = "",
    [string]$InnoSetupCompiler = "",
    [switch]$SkipTests,
    [switch]$SkipInstaller
)

$ErrorActionPreference = "Stop"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
Set-Location $Root

function Step($text) { Write-Host "`n=== $text ===" -ForegroundColor Cyan }
function Fail($text) { Write-Host "BUILD FAILED: $text" -ForegroundColor Red; exit 1 }
function Run($exe, [string[]]$arguments) {
    & $exe @arguments
    if ($LASTEXITCODE -ne 0) { Fail "$exe $($arguments -join ' ') exited with $LASTEXITCODE" }
}

# ---------------------------------------------------------------- version
$Version = (Select-String -Path "app\__init__.py" -Pattern 'APP_VERSION = "([^"]+)"').Matches[0].Groups[1].Value
if (-not $Version) { Fail "Could not read APP_VERSION from app\__init__.py" }
Write-Host "TrackNetV1 Dataset Prepper $Version"

$BuildDir = Join-Path $Root "build"
$DistDir = Join-Path $Root "dist\TrackNetPrepper"
$ReleaseDir = Join-Path $Root "release"
New-Item -ItemType Directory -Force $BuildDir, $ReleaseDir | Out-Null

# ---------------------------------------------------------------- venv
Step "Build environment"
$Venv = Join-Path $BuildDir "venv-win"
$VenvPy = Join-Path $Venv "Scripts\python.exe"
if (-not (Test-Path $VenvPy)) {
    if ($Python) { Run $Python @("-m", "venv", $Venv) }
    else { Run "py" @("-3.12", "-m", "venv", $Venv) }
}
Run $VenvPy @("-m", "pip", "install", "--quiet", "--upgrade", "pip")
Run $VenvPy @("-m", "pip", "install", "--quiet", "-r", "requirements-dev.txt")
& $VenvPy -c "import sys, PySide6, PIL, psutil; print('Python', sys.version.split()[0], '| PySide6', PySide6.__version__, '| Pillow', PIL.__version__, '| psutil', psutil.__version__)"

# ---------------------------------------------------------------- tests
if (-not $SkipTests) {
    Step "Test suite"
    $TestTemp = Join-Path $BuildDir "pytest-tmp"
    Run $VenvPy @("-m", "pytest", "-q", "--basetemp", $TestTemp, "-p", "no:cacheprovider")
}

# ---------------------------------------------------------------- version resource
Step "Version resource"
$parts = ($Version.Split(".") + @("0", "0", "0"))[0..3] | ForEach-Object { [int]($_ -replace '\D', '') }
$tuple = ($parts -join ", ")
@"
VSVersionInfo(
  ffi=FixedFileInfo(filevers=($tuple), prodvers=($tuple), mask=0x3f, flags=0x0, OS=0x40004, fileType=0x1, subtype=0x0, date=(0, 0)),
  kids=[
    StringFileInfo([StringTable('040904B0', [
      StringStruct('CompanyName', 'Sanjay Kumar S'),
      StringStruct('FileDescription', 'TrackNetV1 Dataset Prepper'),
      StringStruct('FileVersion', '$Version'),
      StringStruct('InternalName', 'TrackNetPrepper'),
      StringStruct('LegalCopyright', 'MIT License'),
      StringStruct('OriginalFilename', 'TrackNetPrepper.exe'),
      StringStruct('ProductName', 'TrackNetV1 Dataset Prepper'),
      StringStruct('ProductVersion', '$Version')])]),
    VarFileInfo([VarStruct('Translation', [1033, 1200])])
  ]
)
"@ | Set-Content -Encoding UTF8 (Join-Path $BuildDir "version_info.txt")

# ---------------------------------------------------------------- freeze
Step "PyInstaller"
if (Test-Path $DistDir) { Remove-Item -Recurse -Force $DistDir }
Run $VenvPy @("-m", "PyInstaller", "--noconfirm", "--clean",
    "--distpath", (Join-Path $Root "dist"), "--workpath", (Join-Path $BuildDir "pyinstaller"),
    "packaging\pyinstaller\tracknet_prepper.spec")

# ---------------------------------------------------------------- ffmpeg
Step "FFmpeg"
$FFStage = Join-Path $BuildDir "ffmpeg-win"
if (Test-Path $FFStage) { Remove-Item -Recurse -Force $FFStage }
New-Item -ItemType Directory -Force $FFStage | Out-Null

if ($FFmpegDir) {
    foreach ($tool in "ffmpeg.exe", "ffprobe.exe") {
        if (-not (Test-Path (Join-Path $FFmpegDir $tool))) { Fail "$tool not found in $FFmpegDir" }
        Copy-Item (Join-Path $FFmpegDir $tool) $FFStage
    }
    $licenseCandidates = @((Join-Path $FFmpegDir "LICENSE*"), (Join-Path (Split-Path $FFmpegDir) "LICENSE*"))
    foreach ($candidate in $licenseCandidates) { Copy-Item $candidate $FFStage -ErrorAction SilentlyContinue }
    "FFmpeg copied from: $FFmpegDir`r`nSource code: https://ffmpeg.org/download.html" |
        Set-Content -Encoding UTF8 (Join-Path $FFStage "SOURCE.txt")
} else {
    $pins = Get-Content "packaging\ffmpeg_pins.json" -Raw | ConvertFrom-Json
    $pin = $pins.windows
    $cache = Join-Path $BuildDir "cache"
    New-Item -ItemType Directory -Force $cache | Out-Null
    $zip = Join-Path $cache ([IO.Path]::GetFileName($pin.url))
    if (-not (Test-Path $zip)) {
        Write-Host "Downloading $($pin.url)"
        [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
        Invoke-WebRequest -Uri $pin.url -OutFile $zip -UseBasicParsing
    }
    $hash = (Get-FileHash -Algorithm SHA256 $zip).Hash.ToLower()
    if ($hash -ne $pin.sha256) { Fail "FFmpeg archive hash mismatch: $hash (expected $($pin.sha256))" }
    $extract = Join-Path $cache "ffmpeg-win-extract"
    if (Test-Path $extract) { Remove-Item -Recurse -Force $extract }
    Expand-Archive -Path $zip -DestinationPath $extract
    $bin = Get-ChildItem -Path $extract -Recurse -Filter ffmpeg.exe | Select-Object -First 1
    Copy-Item $bin.FullName, (Join-Path $bin.DirectoryName "ffprobe.exe") $FFStage
    Get-ChildItem -Path $extract -Recurse -Filter "LICENSE*" | Select-Object -First 1 | Copy-Item -Destination $FFStage
    "FFmpeg $($pin.version)`r`nBinary: $($pin.url)`r`nSHA-256: $($pin.sha256)`r`nSource code: https://github.com/FFmpeg/FFmpeg (see LICENSE)" |
        Set-Content -Encoding UTF8 (Join-Path $FFStage "SOURCE.txt")
}

# Portable build: FFmpeg lives next to the executables.
Copy-Item -Recurse $FFStage (Join-Path $DistDir "ffmpeg")

# ---------------------------------------------------------------- smoke tests
Step "Smoke test (frozen build)"
$env:TNP_DATA_DIR = Join-Path $BuildDir "smoke-appdata"
& (Join-Path $DistDir "tracknet-prepper-cli.exe") doctor
if ($LASTEXITCODE -ne 0) { Fail "Frozen CLI 'doctor' exited with $LASTEXITCODE" }
$shot = Join-Path $BuildDir "smoke-window.png"
$gui = Start-Process -FilePath (Join-Path $DistDir "TrackNetPrepper.exe") `
    -ArgumentList @("--smoke-test", "6", "--screenshot", "`"$shot`"") -PassThru -Wait
if ($gui.ExitCode -ne 0) { Fail "Frozen GUI smoke test exited with $($gui.ExitCode)" }
if (-not (Test-Path $shot)) { Fail "GUI smoke test did not produce a window screenshot" }
Remove-Item Env:\TNP_DATA_DIR
Write-Host "GUI window rendered: $shot"

# ---------------------------------------------------------------- portable zip
Step "Portable zip"
$portable = Join-Path $ReleaseDir "TrackNetV1_Dataset_Prepper_V2_Portable.zip"
if (Test-Path $portable) { Remove-Item $portable }
@"
TrackNetV1 Dataset Prepper $Version - portable build

Run TrackNetPrepper.exe. Nothing is installed; delete the folder to remove it.
Logs and job history are written to %LOCALAPPDATA%\TrackNetPrepper and
%USERPROFILE%\.frame-generator (never inside this folder).

Command-line tools: tracknet-prepper-cli.exe doctor | extract | convert-tracknet
Requires 64-bit Windows 10 1809+ . NVIDIA GPU decoding needs an NVIDIA driver
(not included); without one the CPU is used automatically.
"@ | Set-Content -Encoding UTF8 (Join-Path $DistDir "README-PORTABLE.txt")
Compress-Archive -Path $DistDir -DestinationPath $portable -CompressionLevel Optimal

# ---------------------------------------------------------------- installer
if (-not $SkipInstaller) {
    Step "Installer (Inno Setup)"
    $iscc = $InnoSetupCompiler
    if (-not $iscc) {
        $candidates = @(
            (Join-Path $env:LOCALAPPDATA "Programs\Inno Setup 6\ISCC.exe"),
            (Join-Path ${env:ProgramFiles(x86)} "Inno Setup 6\ISCC.exe"),
            (Join-Path $env:ProgramFiles "Inno Setup 6\ISCC.exe")
        )
        $iscc = $candidates | Where-Object { Test-Path $_ } | Select-Object -First 1
    }
    if (-not $iscc) {
        Fail "Inno Setup 6 (ISCC.exe) not found. Install it with: winget install JRSoftware.InnoSetup --scope user  (or pass -InnoSetupCompiler)"
    }
    Run $iscc @("/Qp", "/DAppVersion=$Version", "/DSourceDir=$DistDir", "/DFFmpegDir=$FFStage",
        "/DOutputDir=$ReleaseDir", "packaging\windows\installer.iss")
}

# ---------------------------------------------------------------- checksums
Step "Checksums"
$sums = Get-ChildItem $ReleaseDir -File | Where-Object { $_.Name -like "TrackNetV1_Dataset_Prepper_V2_*" } | ForEach-Object {
    "{0}  {1}" -f (Get-FileHash -Algorithm SHA256 $_.FullName).Hash.ToLower(), $_.Name
}
$sums | Set-Content -Encoding ASCII (Join-Path $ReleaseDir "SHA256SUMS-windows.txt")
$sums | ForEach-Object { Write-Host $_ }
Get-ChildItem $ReleaseDir -File | Format-Table Name, @{n = "MB"; e = { [math]::Round($_.Length / 1MB, 1) } }
Write-Host "`nDone." -ForegroundColor Green
