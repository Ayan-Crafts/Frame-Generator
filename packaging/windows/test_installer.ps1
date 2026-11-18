<#
.SYNOPSIS
  Automated install / launch / repair / uninstall test for the Windows installer.

.DESCRIPTION
  Installs per-user (no admin) into a temporary folder, so it can run on a
  developer machine without touching an existing installation, then:
    1. silent install with bundled FFmpeg
    2. checks files, Start-menu shortcuts, uninstall registry entry,
       post-install verification report
    3. runs the installed CLI (doctor, extract into a path with spaces and
       non-ASCII characters) and the GUI (smoke test + screenshot)
    4. repair (re-run installer over the existing install)
    5. reinstall WITHOUT bundled FFmpeg -> app must use FFmpeg from PATH
       (skipped if none on PATH)
    6. silent uninstall -> program files, shortcuts and registry entry gone,
       user data (logs, extracted frames) preserved
  Results: build\installer-test\summary.txt
#>
param(
    [string]$Installer = "",
    [string]$WorkDir = ""
)
$ErrorActionPreference = "Stop"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
if (-not $Installer) { $Installer = Join-Path $Root "release\TrackNetV1_Dataset_Prepper_V2_Setup.exe" }
if (-not $WorkDir) { $WorkDir = Join-Path $Root "build\installer-test" }
if (Test-Path $WorkDir) { Remove-Item -Recurse -Force $WorkDir }
New-Item -ItemType Directory -Force $WorkDir | Out-Null

$Summary = Join-Path $WorkDir "summary.txt"
$script:pass = 0; $script:fail = 0
function Log($t) { Write-Host $t; Add-Content -Encoding UTF8 $Summary $t }
function Check($name, [scriptblock]$test) {
    try { $ok = & $test } catch { $ok = $false; Log "      error: $($_.Exception.Message)" }
    if ($ok) { $script:pass++; Log "PASS  $name" } else { $script:fail++; Log "FAIL  $name" }
}

$AppId = "{6F4C1D0E-3B7A-4E52-9C8D-2A1B7E5F9D31}_is1"
$UninstKey = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\$AppId"
$InstallDir = Join-Path $WorkDir "Program Files Ünïcode\TrackNet Prepper"
$StartMenu = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs\TrackNetV1 Dataset Prepper"
$UserData = Join-Path $env:LOCALAPPDATA "TrackNetPrepper"
$hadUserData = Test-Path $UserData
if (Test-Path $UninstKey) { throw "An installation already exists for this user; uninstall it first." }

Log "Installer: $Installer ($([math]::Round((Get-Item $Installer).Length / 1MB, 1)) MB)"
Log "Windows: $((Get-CimInstance Win32_OperatingSystem).Caption) $((Get-CimInstance Win32_OperatingSystem).Version)"

function Install([string]$components, [string]$logName) {
    $log = Join-Path $WorkDir $logName
    $p = Start-Process -FilePath $Installer -Wait -PassThru -ArgumentList @(
        "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/CURRENTUSER",
        "/DIR=`"$InstallDir`"", "/COMPONENTS=`"$components`"", "/TASKS=`"`"", "/LOG=`"$log`"")
    return $p.ExitCode
}

try {
# ------------------------------------------------------------------ 1-3
Log "--- install (app + bundled FFmpeg)"
$t0 = Get-Date
Check "installer exit code 0" { (Install "app,ffmpeg" "install.log") -eq 0 }
Log "      install time: $([math]::Round(((Get-Date) - $t0).TotalSeconds, 1)) s"
Check "GUI exe installed" { Test-Path (Join-Path $InstallDir "TrackNetPrepper.exe") }
Check "CLI exe installed" { Test-Path (Join-Path $InstallDir "tracknet-prepper-cli.exe") }
Check "bundled ffmpeg installed" { Test-Path (Join-Path $InstallDir "ffmpeg\ffmpeg.exe") }
Check "Start menu shortcut" { Test-Path (Join-Path $StartMenu "TrackNetV1 Dataset Prepper.lnk") }
Check "uninstall registry entry (per-user)" { (Get-ItemProperty $UninstKey).DisplayName -eq "TrackNetV1 Dataset Prepper" }
Check "post-install verification report written" {
    $r = Get-Content (Join-Path $UserData "install-check.json") -Raw | ConvertFrom-Json
    Log "      install-check: ffmpeg_ok=$($r.ffmpeg_ok) source=$($r.ffmpeg.source) nvdec=$($r.nvdec_state) gpu_pipeline_ready=$($r.gpu_pipeline_ready)"
    $r.ffmpeg_ok -and $r.ffmpeg.source -eq "bundled"
}

$env:TNP_DATA_DIR = Join-Path $WorkDir "appdata"
$cli = Join-Path $InstallDir "tracknet-prepper-cli.exe"
Check "installed CLI doctor" {
    & $cli doctor *> (Join-Path $WorkDir "doctor.txt"); $LASTEXITCODE -eq 0
}
Get-Content (Join-Path $WorkDir "doctor.txt") | Where-Object { $_ -match "FFmpeg:|NVDEC|NVENC|Auto mode|NVIDIA GPU" } |
    ForEach-Object { Log "      $_" }

$media = Join-Path $WorkDir "média in\clip dir"
$out = Join-Path $WorkDir "frames out ✓"
New-Item -ItemType Directory -Force $media | Out-Null
$ff = Join-Path $InstallDir "ffmpeg\ffmpeg.exe"
if (-not (Test-Path $ff)) { $ff = (Get-Command ffmpeg.exe -ErrorAction Stop).Source }
& $ff -hide_banner -loglevel error -y -f lavfi -i "testsrc2=size=1280x720:rate=50" -t 4 -c:v mpeg4 -q:v 3 (Join-Path $media "vidéo test.avi")
foreach ($mode in "auto", "cpu") {
    Check "installed CLI extract ($mode) to unicode/space path" {
        & $cli extract $media (Join-Path $out $mode) --mode $mode *> (Join-Path $WorkDir "extract-$mode.txt")
        $n = (Get-ChildItem (Join-Path $out "$mode\vidéo test") -Filter *.jpg).Count
        Log "      [$mode] frames: $n (expected 200); $((Get-Content (Join-Path $WorkDir "extract-$mode.txt") | Select-String 'via').Line.Trim())"
        ($LASTEXITCODE -eq 0) -and ($n -eq 200)
    }
}

Check "installed GUI launches and renders" {
    $shot = Join-Path $WorkDir "installed-window.png"
    $p = Start-Process -FilePath (Join-Path $InstallDir "TrackNetPrepper.exe") -Wait -PassThru `
        -ArgumentList @("--smoke-test", "6", "--screenshot", "`"$shot`"")
    ($p.ExitCode -eq 0) -and (Test-Path $shot)
}
Check "GUI log written" { Test-Path (Join-Path $env:TNP_DATA_DIR "logs\tracknet-prepper.log") }
Remove-Item Env:\TNP_DATA_DIR

# ------------------------------------------------------------------ 4
Log "--- repair (re-run installer over existing install)"
Check "repair exit code 0" { (Install "app,ffmpeg" "repair.log") -eq 0 }
Check "app still works after repair" { & $cli --version *> $null; $LASTEXITCODE -eq 0 }

# ------------------------------------------------------------------ 5
$systemFF = Get-Command ffmpeg.exe -ErrorAction SilentlyContinue
if ($systemFF) {
    Log "--- reinstall without bundled FFmpeg (system FFmpeg on PATH: $($systemFF.Source))"
    Check "install app only" { (Install "app" "install-nobundle.log") -eq 0 }
    Check "bundled ffmpeg removed when component deselected" { -not (Test-Path (Join-Path $InstallDir "ffmpeg")) }
    Check "app reuses system FFmpeg" {
        $j = Join-Path $WorkDir "doctor-system.json"
        $env:TNP_DATA_DIR = Join-Path $WorkDir "appdata"
        & $cli doctor --json $j *> $null
        Remove-Item Env:\TNP_DATA_DIR
        $r = Get-Content $j -Raw | ConvertFrom-Json
        Log "      ffmpeg source=$($r.ffmpeg.source) path=$($r.ffmpeg.ffmpeg_path)"
        $r.ffmpeg.source -eq "system"
    }
} else {
    Log "SKIP  no FFmpeg on PATH; 'reuse system FFmpeg' not tested"
}

} catch {
    $script:fail++; Log "FAIL  aborted: $($_.Exception.Message)"
} finally {
# ------------------------------------------------------------------ 6
Log "--- uninstall"
$uninst = Join-Path $InstallDir "unins000.exe"
Check "uninstaller exit code 0" {
    (Start-Process -FilePath $uninst -Wait -PassThru -ArgumentList @("/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART")).ExitCode -eq 0
}
Start-Sleep -Seconds 2   # uninstaller deletes itself via a helper process
Check "program files removed" { -not (Test-Path (Join-Path $InstallDir "TrackNetPrepper.exe")) }
Check "Start menu shortcuts removed" { -not (Test-Path $StartMenu) }
Check "uninstall registry entry removed" { -not (Test-Path $UninstKey) }
Check "extracted frames preserved" { (Get-ChildItem (Join-Path $out "cpu\vidéo test") -Filter *.jpg).Count -eq 200 }
Check "user logs preserved (silent uninstall keeps data)" { Test-Path (Join-Path $UserData "install-check.json") }

# Clean up what this test created in the real profile.
if (-not $hadUserData -and (Test-Path $UserData)) { Remove-Item -Recurse -Force $UserData }
}

Log "--- RESULT: $script:pass passed, $script:fail failed"
if ($script:fail -gt 0) { exit 1 }
