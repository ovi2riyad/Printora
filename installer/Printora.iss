; Compile through python -m scripts.build_release. TestRoot is compiler-only.
#ifndef Payload
  #error Payload must point to the complete validated onedir application.
#endif
#ifndef ProductVersion
  #define ProductVersion "3.3.3"
#endif
#ifndef ReleaseOutput
  #define ReleaseOutput "..\dist\installers"
#endif

[Setup]
AppVersion={#ProductVersion}
AppPublisher=Riyad Ahmed Ovi
AppPublisherURL=https://enthugo.com
AppSupportURL=https://github.com/ovi2riyad/Printora/issues
DefaultGroupName=Printora
DisableProgramGroupPage=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
UninstallDisplayIcon={app}\Printora.exe
SetupIconFile={#Payload}\Printora.ico
Compression=lzma2/normal
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes
RestartApplications=no
AppMutex=Local\Printora.Desktop.Running
OutputDir={#ReleaseOutput}
#ifdef TestRoot
AppId={{4F077504-7244-4BEB-B290-FE8758932B47}-InstallerTest
AppName=Printora Installer Test
DefaultDirName={#TestRoot}\Application
PrivilegesRequired=lowest
OutputBaseFilename=Printora-{#ProductVersion}-InstallerTest
#else
AppId={{4F077504-7244-4BEB-B290-FE8758932B47}
AppName=Printora
DefaultDirName=C:\Printora
PrivilegesRequired=admin
OutputBaseFilename=Printora-{#ProductVersion}-Setup
#endif

[Files]
Source: "{#Payload}\StudioPhotoMaker.exe"; DestDir: "{app}"; DestName: "Printora.exe"; Flags: ignoreversion
Source: "{#Payload}\*"; DestDir: "{app}"; Excludes: "StudioPhotoMaker.exe"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
#ifdef TestRoot
Name: "{#TestRoot}\Desktop\Printora"; Filename: "{app}\Printora.exe"; WorkingDir: "{app}"; AppUserModelID: "Printora.Desktop"
Name: "{#TestRoot}\StartMenu\Printora\Printora"; Filename: "{app}\Printora.exe"; WorkingDir: "{app}"; AppUserModelID: "Printora.Desktop"
#else
Name: "{commondesktop}\Printora"; Filename: "{app}\Printora.exe"; WorkingDir: "{app}"; AppUserModelID: "Printora.Desktop"
Name: "{commonprograms}\Printora\Printora"; Filename: "{app}\Printora.exe"; WorkingDir: "{app}"; AppUserModelID: "Printora.Desktop"
#endif

; Inno's uninstall log removes only installed files/shortcuts. Never delete app data.
