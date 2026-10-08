; Installateur de QTE-Bot (Inno Setup 6). Fabriqué par build.bat, qui passe /DAppVersion=x.y.z.
;
; Choix :
; - installation PAR UTILISATEUR (%LOCALAPPDATA%\Programs\QTE-Bot) : aucun droit administrateur demandé, et le
;   dossier reste inscriptible (le programme y écrit config.json, qte_bot.log et captures\) ;
; - mise à jour = relancer un setup plus récent : les réglages (config.json) sont conservés ;
; - désinstallation complète (Paramètres Windows > Applications) : programme, réglages et journaux supprimés.

#ifndef AppVersion
  #error "Version manquante : lancer build.bat (ou ISCC /DAppVersion=x.y.z)"
#endif

#define AppName "QTE-Bot"
#define AppExe "QTE-Bot.exe"
#define DistDir "..\dist\QTE-Bot"

[Setup]
; Identifiant fixe : ne jamais le changer, c'est lui qui relie une mise à jour à l'installation existante.
AppId={{0474ADFB-0AA4-48AA-9123-0CBDF0A16286}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher=Adrien
DefaultDirName={localappdata}\Programs\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
DisableDirPage=yes
DisableReadyPage=yes
PrivilegesRequired=lowest
OutputDir=..\dist
OutputBaseFilename={#AppName}-Setup-{#AppVersion}
UninstallDisplayIcon={app}\{#AppExe}
UninstallDisplayName={#AppName}
; Le programme tient un mutex d'instance unique : le setup demande de le fermer avant d'écraser les fichiers.
AppMutex=Local\QteBot_AutoPrompt
CloseApplications=yes
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0

[Languages]
Name: "fr"; MessagesFile: "compiler:Languages\French.isl"

[Tasks]
Name: "desktopicon"; Description: "Créer un raccourci sur le Bureau"; GroupDescription: "Raccourcis :"

[Files]
Source: "{#DistDir}\*"; DestDir: "{app}"; Excludes: "config.json"; Flags: ignoreversion recursesubdirs createallsubdirs
; Réglages du joueur : posés à la 1re installation seulement, jamais écrasés par une mise à jour.
Source: "{#DistDir}\config.json"; DestDir: "{app}"; Flags: onlyifdoesntexist

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{group}\Guide (README)"; Filename: "{app}\README.md"
Name: "{group}\Désinstaller {#AppName}"; Filename: "{uninstallexe}"
Name: "{userdesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExe}"; Description: "Lancer {#AppName}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; Fichiers créés par le programme lui-même (absents du setup) : sinon le dossier resterait après désinstallation.
Type: files; Name: "{app}\config.json"
Type: files; Name: "{app}\config.json.tmp"
Type: files; Name: "{app}\qte_bot.log"
Type: files; Name: "{app}\qte_bot.old.log"
Type: filesandordirs; Name: "{app}\captures"
Type: dirifempty; Name: "{app}"
