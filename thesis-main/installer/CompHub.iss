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

[Run]
Filename: "{sys}\netsh.exe"; Parameters: "advfirewall firewall add rule name=""CompHub LAN discovery"" dir=in action=allow protocol=UDP localport=37020 remoteip=localsubnet profile=private,public"; Flags: runhidden
Filename: "{sys}\netsh.exe"; Parameters: "advfirewall firewall add rule name=""CompHub LAN application"" dir=in action=allow protocol=TCP localport=5001,5050,9996-9999 remoteip=localsubnet profile=private,public"; Flags: runhidden

[UninstallRun]
Filename: "{sys}\netsh.exe"; Parameters: "advfirewall firewall delete rule name=""CompHub LAN discovery"""; Flags: runhidden
Filename: "{sys}\netsh.exe"; Parameters: "advfirewall firewall delete rule name=""CompHub LAN application"""; Flags: runhidden
