; Installateur de QTE-Bot (Inno Setup 6). Fabriqué par build.bat, qui passe /DAppVersion=x.y.z.
;
; Deux dossiers, deux rôles (voir qte_bot/paths.py) :
; - PROGRAMME : %LOCALAPPDATA%\Programs\QTE-Bot  -> géré par ce setup, jamais écrit par le programme ;
; - DONNÉES   : %LOCALAPPDATA%\QTE-Bot           -> config.json, journaux, captures ; créé par le programme au
;   1er lancement (depuis config.default.json), jamais touché par une mise à jour.
; Installation par utilisateur : aucun droit administrateur demandé.
; Désinstallation : le programme part toujours ; les données seulement si le joueur le confirme.

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
Source: "{#DistDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[InstallDelete]
; Mise à jour depuis 1.0.x : journaux et captures vivaient à côté de l'exe. On les retire ; config.json reste
; le temps que le programme le reprenne dans le dossier des données au prochain lancement.
Type: files; Name: "{app}\qte_bot.log"
Type: files; Name: "{app}\qte_bot.old.log"
Type: files; Name: "{app}\config.tmp"
Type: filesandordirs; Name: "{app}\captures"

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{group}\Guide (README)"; Filename: "{app}\README.md"
Name: "{group}\Désinstaller {#AppName}"; Filename: "{uninstallexe}"
Name: "{userdesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExe}"; Description: "Lancer {#AppName}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; Restes éventuels d'une 1.0.x (réglages à côté de l'exe), sinon le dossier du programme resterait.
Type: files; Name: "{app}\config.json"
Type: dirifempty; Name: "{app}"

[Code]
const
  DataDirName = '{localappdata}\QTE-Bot';

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  DataDir: String;
begin
  if CurUninstallStep <> usPostUninstall then
    Exit;
  DataDir := ExpandConstant(DataDirName);
  { Silencieux (script, mise à jour forcée) : on garde les données, c'est l'option qui ne détruit rien. }
  if UninstallSilent or not DirExists(DataDir) then
    Exit;
  if MsgBox('Supprimer aussi tes réglages, journaux et captures ?' + #13#10 + DataDir + #13#10#13#10 +
            'Non = ils seront repris si tu réinstalles QTE-Bot.', mbConfirmation, MB_YESNO or MB_DEFBUTTON2) = IDYES then
    DelTree(DataDir, True, True, True);
end;
