#define ProjectDir "C:\Users\Admin\Music\watata-main\thesis-main"
#define WorkspaceDir "C:\Users\Admin\Music\watata-main"
#define AppName "CompHub"
#define AppVersion "1.0.0"

[Setup]
AppId={{95DAB36E-2D0E-4A82-8E72-764116A0F785}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher=CompHub
DefaultDirName={autopf}\CompHub
DefaultGroupName=CompHub
OutputDir={#ProjectDir}\installer-output
OutputBaseFilename=CompHub-Setup
SetupIconFile={#WorkspaceDir}\comphub_logo.ico
UninstallDisplayIcon={app}\Server\CompHub-Server\CompHub-Server.exe
PrivilegesRequired=admin
ArchitecturesInstallIn64BitMode=x64compatible
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
DisableProgramGroupPage=yes
CloseApplications=yes
RestartApplications=no

[Dirs]
Name: "{commonappdata}\CompHub"; Permissions: users-modify

[Files]
; ==========================================================
; ADMIN / TEACHER - shared server application
; ==========================================================
Source: "{#ProjectDir}\dist\CompHub-Server\CompHub-Server.exe"; DestDir: "{app}\Server\CompHub-Server"; Flags: ignoreversion; Check: IsServerRole
Source: "{#ProjectDir}\dist\CompHub-Server\_internal\*"; DestDir: "{app}\Server\CompHub-Server\_internal"; Flags: ignoreversion recursesubdirs createallsubdirs; Check: IsServerRole
Source: "{#ProjectDir}\network_config.json"; DestDir: "{app}\Server\CompHub-Server"; Flags: ignoreversion; Check: IsServerRole

; ==========================================================
; STUDENT CLIENT
; ==========================================================
Source: "{#ProjectDir}\dist\CompHub-Student\CompHub-Student.exe"; DestDir: "{app}\Student\CompHub-Student"; Flags: ignoreversion; Check: IsStudentRole
Source: "{#ProjectDir}\dist\CompHub-Student\_internal\*"; DestDir: "{app}\Student\CompHub-Student\_internal"; Flags: ignoreversion recursesubdirs createallsubdirs; Check: IsStudentRole
Source: "{#WorkspaceDir}\Student\network_config.json"; DestDir: "{app}\Student\CompHub-Student"; Flags: ignoreversion; Check: IsStudentRole

[Icons]
; Admin / Teacher share the same application. The signed-in account determines the role.
Name: "{autoprograms}\CompHub\CompHub Admin-Teacher"; Filename: "{app}\Server\CompHub-Server\CompHub-Server.exe"; WorkingDir: "{app}\Server\CompHub-Server"; Check: IsServerRole
Name: "{autodesktop}\CompHub Admin-Teacher"; Filename: "{app}\Server\CompHub-Server\CompHub-Server.exe"; WorkingDir: "{app}\Server\CompHub-Server"; Check: IsServerRole

Name: "{autoprograms}\CompHub\CompHub Student"; Filename: "{app}\Student\CompHub-Student\CompHub-Student.exe"; WorkingDir: "{app}\Student\CompHub-Student"; Check: IsStudentRole
Name: "{autodesktop}\CompHub Student"; Filename: "{app}\Student\CompHub-Student\CompHub-Student.exe"; WorkingDir: "{app}\Student\CompHub-Student"; Check: IsStudentRole
Name: "{commonstartup}\CompHub Student"; Filename: "{app}\Student\CompHub-Student\CompHub-Student.exe"; WorkingDir: "{app}\Student\CompHub-Student"; Check: IsStudentRole

[Run]
; Server firewall: LAN discovery + application ports.
Filename: "{sys}\netsh.exe"; Parameters: "advfirewall firewall add rule name=""CompHub LAN discovery"" dir=in action=allow protocol=UDP localport=37020 remoteip=localsubnet profile=private,public"; Flags: runhidden; Check: IsServerRole
Filename: "{sys}\netsh.exe"; Parameters: "advfirewall firewall add rule name=""CompHub LAN application"" dir=in action=allow protocol=TCP localport=5001,5050,9996-9999 remoteip=localsubnet profile=private,public"; Flags: runhidden; Check: IsServerRole

; Student firewall: ports used for Teacher/Admin connections to the Student client.
Filename: "{sys}\netsh.exe"; Parameters: "advfirewall firewall add rule name=""CompHub Student LAN application"" dir=in action=allow protocol=TCP localport=5050,9996-9999 remoteip=localsubnet profile=private,public"; Flags: runhidden; Check: IsStudentRole

Filename: "{app}\Server\CompHub-Server\CompHub-Server.exe"; Description: "Launch CompHub Admin/Teacher"; Flags: postinstall nowait skipifsilent unchecked; Check: IsServerRole
Filename: "{app}\Student\CompHub-Student\CompHub-Student.exe"; Description: "Launch CompHub Student"; Flags: postinstall nowait skipifsilent unchecked; Check: IsStudentRole

[UninstallRun]
Filename: "{sys}\netsh.exe"; Parameters: "advfirewall firewall delete rule name=""CompHub LAN discovery"""; Flags: runhidden; RunOnceId: "RemoveCompHubDiscoveryFirewallRule"
Filename: "{sys}\netsh.exe"; Parameters: "advfirewall firewall delete rule name=""CompHub LAN application"""; Flags: runhidden; RunOnceId: "RemoveCompHubApplicationFirewallRule"
Filename: "{sys}\netsh.exe"; Parameters: "advfirewall firewall delete rule name=""CompHub Student LAN application"""; Flags: runhidden; RunOnceId: "RemoveCompHubStudentFirewallRule"

[Code]
var
  RolePage: TInputOptionWizardPage;

function IsServerRole: Boolean;
begin
  Result := (RolePage <> nil) and (RolePage.SelectedValueIndex in [0, 1]);
end;

function IsStudentRole: Boolean;
begin
  Result := (RolePage <> nil) and (RolePage.SelectedValueIndex = 2);
end;

procedure InitializeWizard;
begin
  RolePage := CreateInputOptionPage(
    wpWelcome,
    'Choose Installation Role',
    'Where will CompHub be installed?',
    'Select the role for this computer. Admin and Teacher use the same server application; the signed-in account determines the access role.',
    True,
    True
  );
  RolePage.Add('Admin / Main Server');
  RolePage.Add('Teacher Client');
  RolePage.Add('Student Client');
  RolePage.SelectedValueIndex := 0;
end;

function NextButtonClick(CurPageID: Integer): Boolean;
begin
  Result := True;

  if CurPageID = RolePage.ID then
  begin
    if RolePage.SelectedValueIndex < 0 then
    begin
      MsgBox('Please select an installation role before continuing.', mbError, MB_OK);
      Result := False;
      Exit;
    end;
  end;
end;
