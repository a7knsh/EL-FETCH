; Inno Setup script – builds EL-FETCH-Setup.exe from dist\EL-FETCH.exe
;   iscc /DAppVersion=0.2.0 packaging\windows\elfetch.iss
; Per-user install (no admin rights), Start-menu entry, optional desktop icon,
; and `elfetch` on PATH for cmd/PowerShell.

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif

[Setup]
AppId={{6B0E3C1A-4E1F-4C55-9E64-EF7C0A1D2B31}
AppName=EL-FETCH
AppVersion={#AppVersion}
AppPublisher=a7knsh
AppPublisherURL=https://github.com/a7knsh/EL-FETCH
DefaultDirName={localappdata}\Programs\EL-FETCH
DefaultGroupName=EL-FETCH
DisableProgramGroupPage=yes
DisableDirPage=yes
PrivilegesRequired=lowest
OutputDir=..\..\dist
OutputBaseFilename=EL-FETCH-Setup
SetupIconFile=..\icon.ico
UninstallDisplayIcon={app}\EL-FETCH.exe
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ChangesEnvironment=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "..\..\dist\EL-FETCH.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "elfetch.cmd"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\EL-FETCH"; Filename: "{app}\EL-FETCH.exe"
Name: "{autodesktop}\EL-FETCH"; Filename: "{app}\EL-FETCH.exe"; Tasks: desktopicon

[Registry]
Root: HKCU; Subkey: "Environment"; ValueType: expandsz; ValueName: "Path"; ValueData: "{olddata};{app}"; Check: NeedsAddPath

[Run]
Filename: "{app}\EL-FETCH.exe"; Description: "Start EL-FETCH"; Flags: nowait postinstall skipifsilent

[Code]
function GetUserPath(): string;
begin
  if not RegQueryStringValue(HKCU, 'Environment', 'Path', Result) then
    Result := '';
end;

function NeedsAddPath(): Boolean;
begin
  Result := Pos(';' + Uppercase(ExpandConstant('{app}')) + ';', ';' + Uppercase(GetUserPath()) + ';') = 0;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  P, Dir: string;
  I: Integer;
begin
  if CurUninstallStep <> usPostUninstall then
    exit;
  P := GetUserPath();
  Dir := ExpandConstant('{app}');
  I := Pos(';' + Uppercase(Dir), Uppercase(P));
  if I > 0 then
  begin
    Delete(P, I, Length(Dir) + 1);
    RegWriteExpandStringValue(HKCU, 'Environment', 'Path', P);
  end;
end;
