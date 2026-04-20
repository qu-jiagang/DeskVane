#ifndef SourceDir
  #define SourceDir "..\.."
#endif

#ifndef AppName
  #define AppName "DeskVane"
#endif

#ifndef AppVersion
  #error AppVersion must be provided by the build script
#endif

#ifndef DistDir
  #define DistDir SourceDir + "\dist\pyinstaller\" + AppName
#endif

[Setup]
AppId={{8A84A1A3-6A6B-4AF7-9A18-DFD947A9D6A0}
AppName={#AppName}
AppVersion={#AppVersion}
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
OutputDir={#SourceDir}\dist\installer
OutputBaseFilename={#AppName}-setup-{#AppVersion}
Compression=lzma
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayIcon={app}\{#AppName}.exe

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; Flags: unchecked

[Files]
Source: "{#DistDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppName}.exe"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppName}.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppName}.exe"; Description: "Launch {#AppName}"; Flags: nowait postinstall skipifsilent
