#ifndef AppVersion
  #define AppVersion "0.2.0"
#endif

#ifndef SourceDir
  #define SourceDir "..\artifacts\publish\windows-x64\ClickGit"
#endif

#ifndef OutputDir
  #define OutputDir "..\artifacts\installer"
#endif

#ifndef SourceRoot
  #define SourceRoot ".."
#endif

; Native dark/polar styles require 6.6; WizardBackColor requires 6.7.
; Verified with Inno Setup 6.7.3. Fail clearly rather than silently going light.
#if Ver < EncodeVer(6, 7, 0)
  #error ClickGit requires Inno Setup 6.7 or newer for the native dark wizard.
#endif

[Setup]
AppId={{4B747C71-74E9-46B7-B869-02072854766C}
AppName=ClickGit
AppVersion={#AppVersion}
AppPublisher=ljy-codes
AppPublisherURL=https://github.com/ljy-codes/clickgit-desktop
AppSupportURL=https://github.com/ljy-codes/clickgit-desktop/issues
DefaultDirName={localappdata}\Programs\ClickGit
DefaultGroupName=ClickGit
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir={#OutputDir}
OutputBaseFilename=ClickGit-Windows-x64-Setup
Compression=lzma2
SolidCompression=yes
; Keep native controls, license text and selection states; no skinning DLLs.
WizardStyle=modern dark polar
WizardBackColor=#080F20
WizardImageFile={#SourceRoot}\src\clickgit\resources\wizard-panel.png
WizardSmallImageFile={#SourceRoot}\src\clickgit\resources\wizard-small.png
WizardImageBackColor=#080F20
WizardSmallImageBackColor=#080F20
SetupIconFile={#SourceRoot}\src\clickgit\resources\clickgit.ico
DisableWelcomePage=no
LicenseFile={#SourceRoot}\LICENSE
UninstallDisplayName=ClickGit
UninstallDisplayIcon={app}\ClickGit.exe
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "chinesesimplified"; MessagesFile: "Languages\ChineseSimplified.isl"

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; GroupDescription: "附加快捷方式："; Flags: unchecked

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "{#SourceRoot}\installer\Languages\LICENSE"; DestDir: "{app}\licenses"; DestName: "Inno-Setup-Chinese-Translation-LICENSE.txt"; Flags: ignoreversion

[Icons]
Name: "{group}\ClickGit"; Filename: "{app}\ClickGit.exe"; WorkingDir: "{app}"; IconFilename: "{app}\ClickGit.exe"; AppUserModelID: "ljy-codes.ClickGit"
Name: "{group}\卸载 ClickGit"; Filename: "{uninstallexe}"; IconFilename: "{app}\ClickGit.exe"
Name: "{autodesktop}\ClickGit"; Filename: "{app}\ClickGit.exe"; WorkingDir: "{app}"; IconFilename: "{app}\ClickGit.exe"; AppUserModelID: "ljy-codes.ClickGit"; Tasks: desktopicon

[Run]
Filename: "{app}\ClickGit.exe"; Description: "启动 ClickGit"; Flags: nowait postinstall skipifsilent
