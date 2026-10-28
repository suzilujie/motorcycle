; Inno Setup script for the KY bracket desktop app.
; Build with:  .\build.ps1 -Setup   (or ISCC installer.iss)

#define AppName "后视镜支架查询"
#define AppVersion "1.0.0"
#define AppExe "KYBracket.exe"
#define AppId "8F3B1C24-6D77-4E3A-9A15-2C7D9E4B1F02"

[Setup]
AppId={{8F3B1C24-6D77-4E3A-9A15-2C7D9E4B1F02}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher=KY
DefaultDirName={localappdata}\Programs\KYBracket
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=dist
OutputBaseFilename=KYBracket-Setup
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayIcon={app}\{#AppExe}
MinVersion=10.0

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; GroupDescription: "附加任务:"; Flags: unchecked

[Files]
Source: "dist\KYBracket\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{group}\卸载 {#AppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExe}"; Description: "立即启动 {#AppName}"; Flags: nowait postinstall skipifsilent
