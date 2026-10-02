
#define ProjectDir "C:\Users\Admin\Music\watata-main\thesis-main"
#define AppName "CompHub"
#define AppVersion "1.0.0"

[Setup]
AppId={{95DAB36E-2D0E-4A82-8E72-764116A0F785}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher=CompHub
DefaultDirName={autopf}\CompHub
DefaultGroupName=CompHub
OutputDir={#ProjectDir}\..\installer-output
OutputBaseFilename=CompHub-Setup
PrivilegesRequired=admin
ArchitecturesInstallIn64BitMode=x64compatible
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
UninstallDisplayIcon={app}\Server\CompHub-Server\CompHub-Server.exe
CloseApplications=yes
RestartApplications=no

[Types]
Name: "full"; Description: "Admin + Teacher Server and Student Client"
Name: "server"; Description: "Admin + Teacher Server only"
Name: "student"; Description: "Student Client only"

[Components]
Name: "server"; Description: "Admin + Teacher Server (login app)"; Types: full server
Name: "student"; Description: "Student Client"; Types: full student

[Tasks]
Name: "desktopicon"; Description: "Create desktop shortcuts"; GroupDescription: "Additional shortcuts:"; Flags: checkedonce

[Dirs]
Name: "{commonappdata}\CompHub"; Permissions: users-modify

[Files]
; ==========================================
; ADMIN / TEACHER SERVER
; ==========================================

Source: "{#ProjectDir}\dist\CompHub-Server\CompHub-Server.exe"; DestDir: "{app}\Server\CompHub-Server"; Flags: ignoreversion; Components: server

Source: "{#ProjectDir}\dist\CompHub-Server\_internal\*"; DestDir: "{app}\Server\CompHub-Server\_internal"; Flags: ignoreversion recursesubdirs createallsubdirs; Components: server

; SERVER CONFIGURATION
Source: "{#ProjectDir}\network_config.json"; DestDir: "{app}\Server\CompHub-Server"; Flags: ignoreversion; Components: server

; ==========================================
; STUDENT CLIENT
; ==========================================

Source: "{#ProjectDir}\dist\CompHub-Student\CompHub-Student.exe"; DestDir: "{app}\Student\CompHub-Student"; Flags: ignoreversion; Components: student

Source: "{#ProjectDir}\dist\CompHub-Student\_internal\*"; DestDir: "{app}\Student\CompHub-Student\_internal"; Flags: ignoreversion recursesubdirs createallsubdirs; Components: student

; STUDENT CONFIGURATION - PERMANENT FIX
Source: "{#ProjectDir}\..\Student\network_config.json"; DestDir: "{app}\Student\CompHub-Student"; Flags: ignoreversion; Components: student

[Icons]
Name: "{autoprograms}\CompHub\CompHub Admin-Teacher"; Filename: "{app}\Server\CompHub-Server\CompHub-Server.exe"; WorkingDir: "{app}\Server\CompHub-Server"; Components: server

Name: "{autoprograms}\CompHub\CompHub Student"; Filename: "{app}\Student\CompHub-Student\CompHub-Student.exe"; WorkingDir: "{app}\Student\CompHub-Student"; Components: student

Name: "{autodesktop}\CompHub Admin-Teacher"; Filename: "{app}\Server\CompHub-Server\CompHub-Server.exe"; WorkingDir: "{app}\Server\CompHub-Server"; Tasks: desktopicon; Components: server

Name: "{autodesktop}\CompHub Student"; Filename: "{app}\Student\CompHub-Student\CompHub-Student.exe"; WorkingDir: "{app}\Student\CompHub-Student"; Tasks: desktopicon; Components: student

[Run]
Filename: "{sys}\netsh.exe"; Parameters: "advfirewall firewall add rule name=""CompHub LAN discovery"" dir=in action=allow protocol=UDP localport=37020 remoteip=localsubnet profile=private,public"; Flags: runhidden; Components: server

Filename: "{sys}\netsh.exe"; Parameters: "advfirewall firewall add rule name=""CompHub LAN application"" dir=in action=allow protocol=TCP localport=5001,5050,9996-9999 remoteip=localsubnet profile=private,public"; Flags: runhidden; Components: server

Filename: "{app}\Server\CompHub-Server\CompHub-Server.exe"; Description: "Launch CompHub Admin/Teacher"; Flags: postinstall nowait skipifsilent unchecked; Components: server

Filename: "{app}\Student\CompHub-Student\CompHub-Student.exe"; Description: "Launch CompHub Student"; Flags: postinstall nowait skipifsilent unchecked; Components: student

[UninstallRun]
Filename: "{sys}\netsh.exe"; Parameters: "advfirewall firewall delete rule name=""CompHub LAN discovery"""; Flags: runhidden; RunOnceId: "RemoveCompHubDiscoveryFirewallRule"

Filename: "{sys}\netsh.exe"; Parameters: "advfirewall firewall delete rule name=""CompHub LAN application"""; Flags: runhidden; RunOnceId: "RemoveCompHubApplicationFirewallRule"