; Pondside installer - Inno Setup 7
;
; Build the EXE first (build_pondside_exe.bat), then compile this with:
;     "C:\Program Files\Inno Setup 7\ISCC.exe" pondside.iss
; or just run build_installer.bat.
;
; Two deliberate choices, both about not making a hard day harder:
;
;   1. This installs per-user, under %LOCALAPPDATA%\Programs. No administrator
;      prompt, and the folder stays writable - which is exactly why Pondside
;      can keep your database, config and exports beside the EXE, where you can
;      see them, copy them and back them up.
;
;   2. The uninstaller does NOT touch your data. Inno only removes what it
;      installed, and your check-ins, notes, worries, config and exports are
;      all created at runtime, so they are left alone. Uninstalling Pondside
;      never destroys the record of how you have been.

#define AppName "Pondside"
#define AppExeName "Pondside.exe"
#define AppVersion "1.2.0"
#define AppPublisher "SunnySkyesS (Amber)"
#define AppURL "https://github.com/sunnyskyess420/pondside"

[Setup]
; A stable identity for this application. Never change this value: Windows
; uses it to recognise upgrades and to find the right uninstaller.
AppId={{7c5cd4ae-f1d9-4f75-b3e4-5bbee3f551cf}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL={#AppURL}
AppSupportURL={#AppURL}/issues
AppUpdatesURL={#AppURL}/releases
VersionInfoVersion={#AppVersion}

; Per-user, so no admin prompt is ever needed.
DefaultDirName={userpf}\{#AppName}
DefaultGroupName={#AppName}
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog

OutputBaseFilename=Pondside-Setup-{#AppVersion}
OutputDir=installer_output
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64compatible
ArchitecturesAllowed=x64compatible

SetupIconFile=assets\pondside.ico
UninstallDisplayIcon={app}\pondside.ico
UninstallDisplayName={#AppName}

UsePreviousAppDir=no
DirExistsWarning=no
AppendDefaultDirName=no
DisableProgramGroupPage=yes

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Shortcuts:"
Name: "startup"; Description: "Start Pondside when Windows starts (he naps quietly in the corner)"; GroupDescription: "Startup:"; Flags: unchecked

[Files]
Source: "dist\{#AppExeName}"; DestDir: "{app}"; Flags: ignoreversion
Source: "assets\pondside.ico"; DestDir: "{app}"; Flags: ignoreversion
; Seed a fresh config on a new install, and never overwrite an existing one.
Source: "config.template.json"; DestDir: "{app}"; DestName: "config.json"; Flags: onlyifdoesntexist uninsneveruninstall

[Dirs]
; Exports land here. Left behind on uninstall along with the database.
Name: "{app}\exports"

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExeName}"; IconFilename: "{app}\pondside.ico"
Name: "{group}\Uninstall {#AppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExeName}"; IconFilename: "{app}\pondside.ico"; Tasks: desktopicon

[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "{#AppName}"; ValueData: """{app}\{#AppExeName}"""; Tasks: startup; Flags: uninsdeletevalue

[Run]
Filename: "{app}\{#AppExeName}"; Description: "Open {#AppName}"; Flags: nowait postinstall skipifsilent
