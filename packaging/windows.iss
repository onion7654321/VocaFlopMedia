#ifndef Version
  #error Version required
#endif
[Setup]
AppId={{B773A652-0F32-4C44-A89F-D0F28A2AFD20}
AppName=VocaFlop Media Downloader
AppVersion={#Version}
AppPublisher=VocaFlopMedia
AppPublisherURL=https://github.com/onion7654321/VocaFlopMedia
DefaultDirName={localappdata}\Programs\VocaFlopMedia
DefaultGroupName=VocaFlopMedia
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=..\release
OutputBaseFilename=Vocaflop-{#Version}-Windows-x64-Setup
SetupIconFile=..\assets\logo.ico
UninstallDisplayIcon={app}\Vocaflop.exe
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes
[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; Flags: unchecked
[Files]
Source: "..\dist\Vocaflop\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
[Icons]
Name: "{group}\VocaFlopMedia"; Filename: "{app}\Vocaflop.exe"
Name: "{autodesktop}\VocaFlopMedia"; Filename: "{app}\Vocaflop.exe"; Tasks: desktopicon
[Run]
Filename: "{app}\Vocaflop.exe"; Description: "Launch VocaFlopMedia"; Flags: nowait postinstall skipifsilent
