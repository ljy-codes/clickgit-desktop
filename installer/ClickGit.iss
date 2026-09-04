#ifndef AppVersion
  #define AppVersion "0.1.0"
#endif

#ifndef SourceDir
  #define SourceDir "..\artifacts\publish\windows-x64\ClickGit"
#endif

#ifndef OutputDir
  #define OutputDir "..\artifacts\installer"
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
WizardStyle=modern
UninstallDisplayName=ClickGit
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "chinesesimplified"; MessagesFile: "compiler:Default.isl"

[Messages]
SetupAppTitle=安装
SetupWindowTitle=安装 - %1
UninstallAppTitle=卸载
UninstallAppFullTitle=%1 卸载
InformationTitle=信息
ConfirmTitle=确认
ErrorTitle=错误
ExitSetupTitle=退出安装程序
ExitSetupMessage=安装程序尚未完成。如果现在退出，将不会安装该程序。%n%n您之后可以再次运行安装程序完成安装。%n%n现在退出安装程序吗？
ButtonBack=< 上一步(&B)
ButtonNext=下一步(&N) >
ButtonInstall=安装(&I)
ButtonCancel=取消
ButtonFinish=完成(&F)
ClickNext=点击“下一步”继续，或点击“取消”退出安装程序。
WelcomeLabel1=欢迎使用 [name] 安装向导
WelcomeLabel2=即将在您的计算机上安装 [name/ver]。%n%n建议您在继续安装前关闭所有其他应用程序。
WizardSelectDir=选择目标位置
SelectDirDesc=您想将 [name] 安装在哪里？
SelectDirLabel3=安装程序将安装 [name] 到下面的文件夹中。
SelectDirBrowseLabel=点击“下一步”继续。如果您想选择其他文件夹，点击“浏览”。
WizardSelectTasks=选择附加任务
SelectTasksDesc=您想要安装程序执行哪些附加任务？
SelectTasksLabel2=选择您想要安装程序在安装 [name] 时执行的附加任务，然后点击“下一步”。
WizardReady=准备安装
ReadyLabel1=安装程序准备就绪，现在可以开始安装 [name] 到您的计算机。
ReadyLabel2a=点击“安装”继续。如果您想重新查看或修改设置，点击“上一步”。
ReadyLabel2b=点击“安装”继续。
ReadyMemoDir=目标位置：
ReadyMemoGroup=开始菜单文件夹：
ReadyMemoTasks=附加任务：
WizardPreparing=正在准备安装
PreparingDesc=安装程序正在准备安装 [name] 到您的计算机。
WizardInstalling=正在安装
InstallingLabel=安装程序正在安装 [name]，请稍候。
FinishedHeadingLabel=完成 [name] 安装向导
FinishedLabelNoIcons=安装程序已在您的计算机中安装了 [name]。
FinishedLabel=安装程序已在您的计算机中安装了 [name]。您可以通过快捷方式运行此应用程序。
ClickFinish=点击“完成”退出安装程序。
StatusClosingApplications=正在关闭应用程序...
StatusCreateDirs=正在创建目录...
StatusExtractFiles=正在提取文件...
StatusCreateIcons=正在创建快捷方式...
StatusCreateRegistryEntries=正在创建注册表条目...
StatusSavingUninstall=正在保存卸载信息...
StatusRunProgram=正在完成安装...
StatusRestartingApplications=正在重启应用程序...
StatusRollback=正在撤销更改...
ConfirmUninstall=您确认要完全移除 %1 及其所有组件吗？
UninstallStatusLabel=正在从您的计算机中移除 %1，请稍候。
UninstalledAll=已顺利从您的计算机中移除 %1。
UninstalledMost=%1 卸载完成。%n%n有部分内容未能删除，您可以手动删除。
UninstalledAndNeedsRestart=为完成 %1 的卸载，需要重启计算机。%n%n要立即重启吗？

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; GroupDescription: "附加快捷方式："; Flags: unchecked

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\ClickGit"; Filename: "{app}\ClickGit.exe"; WorkingDir: "{app}"
Name: "{group}\卸载 ClickGit"; Filename: "{uninstallexe}"
Name: "{autodesktop}\ClickGit"; Filename: "{app}\ClickGit.exe"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{app}\ClickGit.exe"; Description: "启动 ClickGit"; Flags: nowait postinstall skipifsilent
