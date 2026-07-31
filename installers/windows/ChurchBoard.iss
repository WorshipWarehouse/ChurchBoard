#define AppName "ChurchBoard"
#define AppPublisher "ChurchBoard"
#define AppURL "https://github.com/wtapper89/ChurchBoard"
#define AppExeName "ChurchBoard.exe"
#define AppVersion GetEnv("CHURCHBOARD_VERSION")

[Setup]
AppId={{83F55FB9-5F32-4D1C-9B43-43C3AE231C61}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL={#AppURL}
AppSupportURL={#AppURL}
DefaultDirName={localappdata}\Programs\ChurchBoard
DefaultGroupName=ChurchBoard
DisableProgramGroupPage=yes
OutputDir=..\..\dist
OutputBaseFilename=ChurchBoard-{#AppVersion}-Windows-x64-Setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayName=ChurchBoard
UninstallDisplayIcon={app}\{#AppExeName}
SetupIconFile=..\..\packaging\assets\ChurchBoard.ico
CloseApplications=yes
RestartApplications=no

[Tasks]
Name: "autostart"; Description: "Start ChurchBoard automatically when I sign in"; GroupDescription: "Startup:"; Flags: checkedonce
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Shortcuts:"

[Files]
Source: "..\..\dist\ChurchBoard.exe"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\ChurchBoard"; Filename: "{app}\{#AppExeName}"; Parameters: "--page desktop"; IconFilename: "{app}\{#AppExeName}"
Name: "{group}\Open ChurchBoard Setup"; Filename: "{app}\{#AppExeName}"; Parameters: "--page admin"; IconFilename: "{app}\{#AppExeName}"
Name: "{group}\Open Main Dashboard"; Filename: "{app}\{#AppExeName}"; Parameters: "--page display/main"; IconFilename: "{app}\{#AppExeName}"
Name: "{group}\Start ChurchBoard"; Filename: "{app}\{#AppExeName}"; Parameters: "--background"
Name: "{autodesktop}\ChurchBoard"; Filename: "{app}\{#AppExeName}"; Parameters: "--page desktop"; IconFilename: "{app}\{#AppExeName}"; Tasks: desktopicon

[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "ChurchBoard"; ValueData: """{app}\{#AppExeName}"" --background"; Flags: uninsdeletevalue; Tasks: autostart

[Run]
Filename: "{app}\{#AppExeName}"; Parameters: "--page desktop"; Description: "Start and open ChurchBoard"; Flags: nowait postinstall skipifsilent

[UninstallRun]
Filename: "{cmd}"; Parameters: "/C taskkill /IM ChurchBoard.exe /F"; Flags: runhidden; RunOnceId: "StopChurchBoard"
