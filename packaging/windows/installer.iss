; TrackNetV1 Dataset Prepper - Windows installer (Inno Setup 6.3+)
;
; Built by packaging/windows/build_windows.ps1, which passes:
;   /DAppVersion=2.1.0  /DSourceDir=<dist\TrackNetPrepper>
;   /DFFmpegDir=<folder with ffmpeg.exe, ffprobe.exe, LICENSE*>  /DOutputDir=<release>
;
; Behaviour
; * Installs per-user (no admin) by default; "Install for all users" is offered.
; * Detects an existing FFmpeg on PATH, checks its version and CUDA support,
;   and pre-selects the bundled FFmpeg component only if no compatible one
;   exists (the user can override either way).
; * Detects an NVIDIA GPU/driver and reports it. Drivers are never installed.
; * Verifies the installation by running "tracknet-prepper-cli doctor".
; * Re-running the installer repairs/upgrades in place (same AppId).
; * Uninstall never touches extracted frames or datasets; logs/job history
;   are kept unless the user explicitly asks to remove them.

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif
#ifndef SourceDir
  #error SourceDir must be defined
#endif
#ifndef FFmpegDir
  #error FFmpegDir must be defined
#endif
#ifndef OutputDir
  #define OutputDir "..\..\release"
#endif

#define AppName "TrackNetV1 Dataset Prepper"
#define AppExe "TrackNetPrepper.exe"
#define CliExe "tracknet-prepper-cli.exe"

[Setup]
AppId={{6F4C1D0E-3B7A-4E52-9C8D-2A1B7E5F9D31}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher=Sanjay Kumar S
AppPublisherURL=https://github.com/Sanjay1712KSK
AppSupportURL=https://github.com/Sanjay1712KSK
VersionInfoVersion={#AppVersion}
VersionInfoDescription={#AppName} Setup
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0.17763
OutputDir={#OutputDir}
OutputBaseFilename=TrackNetV1_Dataset_Prepper_V2_Setup
SetupIconFile=app.ico
UninstallDisplayIcon={app}\{#AppExe}
UninstallDisplayName={#AppName}
LicenseFile=..\..\LICENSE
; The compiler is a 32-bit process: compress in Inno's separate 64-bit LZMA
; helper, or ~600 MB of input exhausts its address space ("Out of memory").
Compression=lzma2/max
SolidCompression=yes
LZMAUseSeparateProcess=yes
LZMANumBlockThreads=2
WizardStyle=modern
CloseApplications=yes
RestartApplications=no
SetupLogging=yes
ChangesEnvironment=no

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Types]
Name: "full"; Description: "Application + bundled FFmpeg"
Name: "compact"; Description: "Application only (use an FFmpeg already on this PC)"
Name: "custom"; Description: "Custom"; Flags: iscustom

[Components]
Name: "app"; Description: "{#AppName} (required)"; Types: full compact custom; Flags: fixed
Name: "ffmpeg"; Description: "Bundled FFmpeg with NVIDIA NVDEC support (recommended unless a compatible FFmpeg is already installed)"; Types: full

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Excludes: "ffmpeg\*,README-PORTABLE.txt"; Components: app; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "{#FFmpegDir}\ffmpeg.exe"; DestDir: "{app}\ffmpeg"; Components: ffmpeg; Flags: ignoreversion
Source: "{#FFmpegDir}\ffprobe.exe"; DestDir: "{app}\ffmpeg"; Components: ffmpeg; Flags: ignoreversion
Source: "{#FFmpegDir}\LICENSE*"; DestDir: "{app}\ffmpeg"; Components: ffmpeg; Flags: ignoreversion skipifsourcedoesntexist
Source: "{#FFmpegDir}\SOURCE.txt"; DestDir: "{app}\ffmpeg"; Components: ffmpeg; Flags: ignoreversion skipifsourcedoesntexist

[InstallDelete]
; Deselecting the component on a repair/upgrade removes a previously bundled copy.
Type: filesandordirs; Name: "{app}\ffmpeg"; Check: not WizardIsComponentSelected('ffmpeg')
; Stale files from an older build of the same version.
Type: filesandordirs; Name: "{app}\_internal"

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExe}"; Comment: "Video to frames extraction and TrackNet annotation"
Name: "{group}\System Check (command line)"; Filename: "{cmd}"; Parameters: "/K ""{app}\{#CliExe}"" doctor"; WorkingDir: "{app}"
Name: "{group}\Uninstall {#AppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExe}"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall skipifsilent

[Code]
const
  MinLibavcodecMajor = 59;
  MinLibavcodecMinor = 37;

var
  SystemFFmpegPath: String;
  SystemFFmpegVersion: String;
  SystemFFmpegCompatible: Boolean;
  SystemFFmpegCuda: Boolean;
  NvidiaSummary: String;
  ComponentsDefaulted: Boolean;
  SystemPage: TOutputMsgMemoWizardPage;

function RunCapture(const Exe, Params: String; var Output: TArrayOfString): Boolean;
var
  TmpFile: String;
  ResultCode: Integer;
begin
  Result := False;
  TmpFile := ExpandConstant('{tmp}\capture_') + IntToStr(Random(1000000)) + '.txt';
  if Exec(ExpandConstant('{cmd}'), '/C ""' + Exe + '" ' + Params + ' > "' + TmpFile + '" 2>&1"',
          '', SW_HIDE, ewWaitUntilTerminated, ResultCode) then
  begin
    Result := (ResultCode = 0) and LoadStringsFromFile(TmpFile, Output);
  end;
  DeleteFile(TmpFile);
end;

function FindOnPath(const FileName: String): String;
var
  PathValue, Dir: String;
  P: Integer;
begin
  Result := '';
  PathValue := GetEnv('PATH') + ';';
  while Length(PathValue) > 0 do
  begin
    P := Pos(';', PathValue);
    Dir := Trim(Copy(PathValue, 1, P - 1));
    Delete(PathValue, 1, P);
    if (Dir <> '') and FileExists(AddBackslash(Dir) + FileName) then
    begin
      Result := AddBackslash(Dir) + FileName;
      Exit;
    end;
  end;
end;

procedure ParseLibavcodec(const Line: String; var Major, Minor: Integer);
var
  S: String;
  P: Integer;
begin
  { "libavcodec     61.  1.101 / 61.  1.101" }
  Major := 0; Minor := 0;
  S := Trim(Copy(Line, Length('libavcodec') + 1, Length(Line)));
  P := Pos('.', S);
  if P = 0 then Exit;
  Major := StrToIntDef(Trim(Copy(S, 1, P - 1)), 0);
  Delete(S, 1, P);
  S := Trim(S);
  P := Pos('.', S);
  if P = 0 then Exit;
  Minor := StrToIntDef(Trim(Copy(S, 1, P - 1)), 0);
end;

procedure DetectSystemFFmpeg;
var
  Lines: TArrayOfString;
  I, Major, Minor: Integer;
  ProbePath: String;
begin
  SystemFFmpegPath := FindOnPath('ffmpeg.exe');
  SystemFFmpegCompatible := False;
  SystemFFmpegCuda := False;
  SystemFFmpegVersion := '';
  if SystemFFmpegPath = '' then Exit;

  { The app needs ffprobe next to ffmpeg (or on PATH). }
  ProbePath := FindOnPath('ffprobe.exe');
  if ProbePath = '' then
  begin
    SystemFFmpegVersion := '(ffprobe.exe missing)';
    Exit;
  end;

  { An executable that exists is not trusted: run it and check the version. }
  if not RunCapture(SystemFFmpegPath, '-hide_banner -version', Lines) then
  begin
    SystemFFmpegVersion := '(could not be executed)';
    Exit;
  end;
  Major := 0; Minor := 0;
  for I := 0 to GetArrayLength(Lines) - 1 do
  begin
    if Pos('ffmpeg version ', Lines[I]) = 1 then
      SystemFFmpegVersion := Copy(Lines[I], 16, 40);
    if Pos('libavcodec', Trim(Lines[I])) = 1 then
      ParseLibavcodec(Trim(Lines[I]), Major, Minor);
  end;
  SystemFFmpegCompatible := (Major > MinLibavcodecMajor) or
    ((Major = MinLibavcodecMajor) and (Minor >= MinLibavcodecMinor));

  if RunCapture(SystemFFmpegPath, '-hide_banner -hwaccels', Lines) then
    for I := 0 to GetArrayLength(Lines) - 1 do
      if Trim(Lines[I]) = 'cuda' then SystemFFmpegCuda := True;
end;

procedure DetectNvidia;
var
  Smi: String;
  Lines: TArrayOfString;
  I: Integer;
begin
  NvidiaSummary := 'No NVIDIA driver detected (nvidia-smi not found). Extraction will use the CPU.';
  Smi := ExpandConstant('{sys}\nvidia-smi.exe');
  if not FileExists(Smi) then
    Smi := FindOnPath('nvidia-smi.exe');
  if Smi = '' then Exit;
  if RunCapture(Smi, '--query-gpu=name,driver_version --format=csv,noheader', Lines) and
     (GetArrayLength(Lines) > 0) then
  begin
    NvidiaSummary := '';
    for I := 0 to GetArrayLength(Lines) - 1 do
      if Trim(Lines[I]) <> '' then
        NvidiaSummary := NvidiaSummary + 'NVIDIA GPU, driver: ' + Trim(Lines[I]) + #13#10;
    NvidiaSummary := NvidiaSummary +
      'GPU decoding (NVDEC) is verified by an actual test decode after installation and on every start.';
  end
  else
    NvidiaSummary := 'nvidia-smi is present but reported no usable GPU. Extraction will use the CPU.';
end;

function BuildSummary: String;
var
  S: String;
begin
  S := 'Windows: ' + GetWindowsVersionString + #13#10#13#10;
  S := S + 'NVIDIA' + #13#10 + NvidiaSummary + #13#10#13#10;
  S := S + 'FFmpeg' + #13#10;
  if SystemFFmpegPath = '' then
    S := S + 'No FFmpeg found on PATH. The bundled FFmpeg will be installed.'
  else
  begin
    S := S + 'Found: ' + SystemFFmpegPath + #13#10 + 'Version: ' + SystemFFmpegVersion + #13#10;
    if not SystemFFmpegCompatible then
      S := S + 'Too old or unusable (FFmpeg 5.1+ required). The bundled FFmpeg will be installed.'
    else if not SystemFFmpegCuda then
      S := S + 'Compatible, but built without CUDA support. The bundled FFmpeg is recommended for GPU decoding.'
    else
      S := S + 'Compatible, with CUDA support. It will be reused; the bundled copy is not needed '
             + '(you can still select it on the next page).';
  end;
  Result := S;
end;

function SystemFFmpegIsGoodEnough: Boolean;
begin
  Result := (SystemFFmpegPath <> '') and SystemFFmpegCompatible and SystemFFmpegCuda;
end;

procedure InitializeWizard;
begin
  DetectSystemFFmpeg;
  DetectNvidia;
  SystemPage := CreateOutputMsgMemoPage(wpLicense,
    'System check',
    'Detected components. Only what is missing will be installed.',
    'Setup inspected this computer:',
    BuildSummary);
end;

procedure CurPageChanged(CurPageID: Integer);
begin
  { Pre-select the bundled FFmpeg only when no compatible one exists; do it
    once so a user's own choice is never overwritten. Not on upgrades: the
    previous selection is kept by Inno Setup. }
  if (CurPageID = wpSelectComponents) and (not ComponentsDefaulted) then
  begin
    ComponentsDefaulted := True;
    if WizardForm.PrevAppDir = '' then
    begin
      if SystemFFmpegIsGoodEnough then
        WizardSelectComponents('!ffmpeg')
      else
        WizardSelectComponents('ffmpeg');
    end;
  end;
end;

function NextButtonClick(CurPageID: Integer): Boolean;
begin
  Result := True;
  if (CurPageID = wpSelectComponents) and (not WizardIsComponentSelected('ffmpeg')) and
     (not SystemFFmpegCompatible) then
  begin
    Result := MsgBox('No compatible FFmpeg was found on this computer.' + #13#10#13#10 +
      'Without the bundled FFmpeg, video extraction will not work until you install ' +
      'FFmpeg 5.1+ and add it to PATH. The annotation tool works regardless.' + #13#10#13#10 +
      'Continue without the bundled FFmpeg?', mbConfirmation, MB_YESNO) = IDYES;
  end;
end;

procedure ReportVerification;
var
  ResultCode: Integer;
begin
  { "doctor" exit codes: 0 OK, 3 FFmpeg unusable. The JSON report is kept
    in %LOCALAPPDATA%\TrackNetPrepper for troubleshooting. }
  WizardForm.StatusLabel.Caption := 'Verifying installation (FFmpeg and GPU acceleration)...';
  ForceDirectories(ExpandConstant('{localappdata}\TrackNetPrepper'));
  if not Exec(ExpandConstant('{app}\{#CliExe}'),
              'doctor --json "' + ExpandConstant('{localappdata}\TrackNetPrepper\install-check.json') + '"',
              '', SW_HIDE, ewWaitUntilTerminated, ResultCode) then
  begin
    MsgBox('The installed application could not be started for verification.' + #13#10 +
           'Please run "System Check" from the Start menu and report the output.',
           mbError, MB_OK);
    Exit;
  end;
  if (ResultCode = 3) and not WizardSilent then
    MsgBox('Installation finished, but no usable FFmpeg was found.' + #13#10#13#10 +
           'Video extraction is disabled until FFmpeg is available: re-run this setup and ' +
           'select "Bundled FFmpeg", or install FFmpeg 5.1+ on PATH.',
           mbInformation, MB_OK);
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then
    ReportVerification;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  DataDir: String;
begin
  if CurUninstallStep = usPostUninstall then
  begin
    DataDir := ExpandConstant('{localappdata}\TrackNetPrepper');
    if DirExists(DataDir) and not UninstallSilent then
      if MsgBox('Also remove logs, diagnostics and job history?' + #13#10#13#10 +
                DataDir + #13#10 + ExpandConstant('{%USERPROFILE}') + '\.frame-generator' + #13#10#13#10 +
                'Extracted frames, annotations and datasets are never removed.',
                mbConfirmation, MB_YESNO or MB_DEFBUTTON2) = IDYES then
      begin
        DelTree(DataDir, True, True, True);
        DelTree(ExpandConstant('{%USERPROFILE}') + '\.frame-generator', True, True, True);
      end;
  end;
end;
