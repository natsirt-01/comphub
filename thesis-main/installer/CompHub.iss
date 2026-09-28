#define AppName "CompHub"
#define AppVersion "1.0.0"

[Setup]
AppId={{95DAB36E-2D0E-4A82-8E72-764116A0F785}
AppName={#AppName}
AppVersion={#AppVersion}
DefaultDirName={autopf}\CompHub
DefaultGroupName=CompHub
OutputDir=..\installer-output
OutputBaseFilename=CompHub-Setup
PrivilegesRequired=admin
ArchitecturesInstallIn64BitMode=x64
Compression=lzma2
SolidCompression=yes
WizardStyle=modern

[Types]
Name: "full"; Description: "Server and Student"
Name: "server"; Description: "Admin and Teacher Server"
Name: "student"; Description: "Student Client"

[Components]
Name: "server"; Description: "Admin and Teacher Server"; Types: full server
Name: "student"; Description: "Student Client"; Types: full student

[Files]
Source: "..\dist\CompHub-Server\*"; DestDir: "{app}\Server"; Flags: ignoreversion recursesubdirs createallsubdirs; Components: server
Source: "..\dist\CompHub-Student\*"; DestDir: "{app}\Student"; Flags: ignoreversion recursesubdirs createallsubdirs; Components: student

[Icons]
Name: "{autoprograms}\CompHub Server"; Filename: "{app}\Server\CompHub-Server.exe"; Components: server
Name: "{autoprograms}\CompHub Student"; Filename: "{app}\Student\CompHub-Student.exe"; Components: student

[Code]
var
  NetworkPage: TInputQueryWizardPage;

procedure InitializeWizard;
begin
  NetworkPage := CreateInputQueryPage(wpSelectDir,
    'Network configuration', 'Enter the IP addresses used by this lab',
    'The Student client uses these addresses to find the Teacher and Admin server.');
  NetworkPage.Add('Teacher server IPv4 address:', False);
  NetworkPage.Add('Admin server IPv4 address:', False);
end;

function NextButtonClick(CurPageID: Integer): Boolean;
begin
  Result := True;
  if CurPageID = NetworkPage.ID then
  begin
    if (Trim(NetworkPage.Values[0]) = '') or (Trim(NetworkPage.Values[1]) = '') then
    begin
      MsgBox('Enter both server IP addresses to continue.', mbError, MB_OK);
      Result := False;
    end;
  end;
end;

procedure SaveNetworkConfig(const Folder: String; const IsStudent: Boolean);
var
  ConfigText: String;
  ConfigPath: String;
begin
  ForceDirectories(Folder);
  if IsStudent then
    ConfigText := '{' + #13#10 +
      '  "teacher_ip": "' + Trim(NetworkPage.Values[0]) + '",' + #13#10 +
      '  "admin_ip": "' + Trim(NetworkPage.Values[1]) + '",' + #13#10 +
      '  "log_port": 5001,' + #13#10 +
      '  "listener_port": 5050,' + #13#10 +
      '  "broadcast_port": 9996,' + #13#10 +
      '  "stream_port": 9998,' + #13#10 +
      '  "remote_view_port": 9997,' + #13#10 +
      '  "control_port": 9999' + #13#10 + '} '
  else
    ConfigText := '{' + #13#10 +
      '  "teacher_ip": "' + Trim(NetworkPage.Values[0]) + '",' + #13#10 +
      '  "admin_ip": "' + Trim(NetworkPage.Values[1]) + '",' + #13#10 +
      '  "log_port": 5001,' + #13#10 +
      '  "command_port": 5050,' + #13#10 +
      '  "control_port": 9999,' + #13#10 +
      '  "broadcast_port": 9996,' + #13#10 +
      '  "stream_port": 9998,' + #13#10 +
      '  "remote_view_port": 9997,' + #13#10 +
      '  "student_pc_ip": []' + #13#10 + '}';
  ConfigPath := AddBackslash(Folder) + 'network_config.json';
  SaveStringToFile(ConfigPath, ConfigText, False);
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then
  begin
    if WizardIsComponentSelected('server') then
      SaveNetworkConfig(ExpandConstant('{app}\Server'), False);
    if WizardIsComponentSelected('student') then
      SaveNetworkConfig(ExpandConstant('{app}\Student'), True);
  end;
end;