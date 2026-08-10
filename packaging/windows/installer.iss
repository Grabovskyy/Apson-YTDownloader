#define AppName "Apson YTDownloader"
#ifndef AppVersion
  #define AppVersion "0.5.2"
#endif
#define AppExeName "ApsonYTDownloader.exe"

#ifndef BuildSource
  #error BuildSource must point to the PyInstaller onedir directory
#endif

[Setup]
AppId={{9D0481C9-E4C8-4F99-B0EA-A57531A0C485}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher=Apson
DefaultDirName={localappdata}\Programs\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputBaseFilename=Apson-YTDownloader-Setup-{#AppVersion}
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
SetupIconFile=..\..\assets\icons\apson-ytdownloader.ico
UninstallDisplayIcon={app}\{#AppExeName}
CloseApplications=force
CloseApplicationsFilter={#AppExeName}
ChangesAssociations=yes
MinVersion=10.0.17763

[Languages]
Name: "polish"; MessagesFile: "compiler:Languages\Polish.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[CustomMessages]
english.UninstallDataPrompt=Do you also want to remove the Apson YTDownloader application data?
english.UninstallDataPath=Data directory:
english.UninstallDataWarning=This removes settings, history, cache, temporary files, logs, thumbnails, and MP3 files stored in the managed data\downloads directory. Downloads saved elsewhere will not be touched.
english.UninstallDataUnsafe=The application data could not be removed safely. The directory is not owned by Apson YTDownloader, its ownership marker is missing or invalid, or the path is unsafe. The data has been preserved.
polish.UninstallDataPrompt=Czy usunąć również dane aplikacji Apson YTDownloader?
polish.UninstallDataPath=Katalog danych:
polish.UninstallDataWarning=Spowoduje to usunięcie ustawień, historii, cache, plików tymczasowych, logów, miniatur oraz plików MP3 zapisanych w zarządzanym katalogu data\downloads. Pliki pobrane w inne miejsce nie zostaną usunięte.
polish.UninstallDataUnsafe=Nie można bezpiecznie usunąć danych aplikacji. Katalog nie należy do Apson YTDownloader, brakuje poprawnego znacznika własności albo ścieżka jest niebezpieczna. Dane zostały zachowane.

[Tasks]
Name: "desktopicon"; Description: "Utwórz skrót na pulpicie"; GroupDescription: "Dodatkowe skróty:"; Flags: unchecked

[Files]
Source: "{#BuildSource}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExeName}"; WorkingDir: "{app}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExeName}"; WorkingDir: "{app}"; Tasks: desktopicon

[Registry]
Root: HKCU; Subkey: "Software\Classes\apson-ytdownloader"; ValueType: string; ValueData: "URL:Apson YTDownloader Protocol"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\Classes\apson-ytdownloader"; ValueType: string; ValueName: "URL Protocol"; ValueData: ""
Root: HKCU; Subkey: "Software\Classes\apson-ytdownloader\DefaultIcon"; ValueType: string; ValueData: "{app}\{#AppExeName},0"
Root: HKCU; Subkey: "Software\Classes\apson-ytdownloader\shell\open\command"; ValueType: string; ValueData: """{app}\{#AppExeName}"" --protocol ""%1"""
Root: HKCU; Subkey: "Software\Apson\Apson YTDownloader"; ValueType: string; ValueName: "DataDir"; ValueData: "{code:GetSelectedDataDir}"; Flags: uninsdeletevalue uninsdeletekeyifempty

[Run]
Filename: "{app}\{#AppExeName}"; Description: "Uruchom {#AppName}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: files; Name: "{app}\app-config.json"

[Code]
var
  DataDirPage: TInputDirWizardPage;
  DataDirWasEdited: Boolean;
  PreviousAppDir: String;
  UninstallDataDir: String;

const
  DataOwnerMarkerName = '.apson-ytdownloader-data';
  DataOwnerMarkerContent = 'Apson YTDownloader|{9D0481C9-E4C8-4F99-B0EA-A57531A0C485}|1';

procedure InitializeWizard;
var
  CommandDataDir: String;
  StoredDataDir: String;
begin
  DataDirPage := CreateInputDirPage(wpSelectDir,
    'Katalog danych aplikacji',
    'Wybierz miejsce na ustawienia, cache, historię, pliki tymczasowe i logi.',
    'Domyślnie dane będą przechowywane w podkatalogu data. Możesz wskazać dowolny zapisywalny katalog, także na innym dysku.',
    False, '');
  DataDirPage.Add('Katalog danych:');
  CommandDataDir := RemoveQuotes(ExpandConstant('{param:DATADIR|}'));
  if Trim(CommandDataDir) <> '' then
  begin
    DataDirPage.Values[0] := CommandDataDir;
    DataDirWasEdited := True;
  end
  else if RegQueryStringValue(HKCU, 'Software\Apson\Apson YTDownloader', 'DataDir', StoredDataDir) and
     (Trim(StoredDataDir) <> '') then
  begin
    DataDirPage.Values[0] := StoredDataDir;
    DataDirWasEdited := True;
  end
  else
  begin
    DataDirPage.Values[0] := AddBackslash(WizardDirValue) + 'data';
    DataDirWasEdited := False;
  end;
  PreviousAppDir := WizardDirValue;
end;

function GetSelectedDataDir(Param: String): String;
begin
  Result := DataDirPage.Values[0];
end;

procedure CurPageChanged(CurPageID: Integer);
begin
  if CurPageID = DataDirPage.ID then
  begin
    if (not DataDirWasEdited) or (DataDirPage.Values[0] = PreviousAppDir + '\data') then
      DataDirPage.Values[0] := WizardDirValue + '\data';
    PreviousAppDir := WizardDirValue;
  end;
end;

function NextButtonClick(CurPageID: Integer): Boolean;
begin
  Result := True;
  if CurPageID = DataDirPage.ID then
  begin
    DataDirWasEdited := True;
    if Trim(DataDirPage.Values[0]) = '' then
    begin
      MsgBox('Wskaż katalog danych aplikacji.', mbError, MB_OK);
      Result := False;
      Exit;
    end;
    if not ForceDirectories(DataDirPage.Values[0]) then
    begin
      MsgBox('Nie można utworzyć wybranego katalogu danych.', mbError, MB_OK);
      Result := False;
    end;
  end;
end;

function JsonEscape(Value: String): String;
begin
  StringChangeEx(Value, '\', '\\', True);
  StringChangeEx(Value, '"', '\"', True);
  Result := Value;
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  Config: String;
  MarkerPath: String;
begin
  if CurStep = ssPostInstall then
  begin
    Config := '{"schema_version":1,"data_dir":"' + JsonEscape(DataDirPage.Values[0]) + '"}';
    SaveStringToFile(ExpandConstant('{app}\app-config.json'), Config, False);
    MarkerPath := AddBackslash(DataDirPage.Values[0]) + DataOwnerMarkerName;
    if not SaveStringToFile(MarkerPath, DataOwnerMarkerContent, False) then
      Log('Warning: could not create the application data ownership marker: ' + MarkerPath);
  end;
end;

function HasPurgeDataParameter: Boolean;
var
  Index: Integer;
begin
  Result := False;
  for Index := 1 to ParamCount do
  begin
    if CompareText(ParamStr(Index), '/PURGEDATA=1') = 0 then
    begin
      Result := True;
      Exit;
    end;
  end;
end;

function IsSafeOwnedDataDirectory(DataDirectory: String): Boolean;
var
  MarkerContent: AnsiString;
  MarkerPath: String;
  NormalizedPath: String;
begin
  Result := False;
  if Trim(DataDirectory) = '' then
    Exit;
  if not PathIsRooted(DataDirectory) then
    Exit;

  NormalizedPath := RemoveBackslashUnlessRoot(ExpandFileName(DataDirectory));
  if CompareText(NormalizedPath,
     RemoveBackslashUnlessRoot(ExtractFileDrive(NormalizedPath) + '\')) = 0 then
    Exit;

  MarkerPath := AddBackslash(NormalizedPath) + DataOwnerMarkerName;
  if not LoadStringFromFile(MarkerPath, MarkerContent) then
    Exit;

  Result := String(MarkerContent) = DataOwnerMarkerContent;
  if Result then
    UninstallDataDir := NormalizedPath;
end;

procedure DeleteManagedDataDirectory(DirectoryName: String);
var
  Target: String;
begin
  Target := AddBackslash(UninstallDataDir) + DirectoryName;
  if DirExists(Target) and (not DelTree(Target, True, True, True)) then
    Log('Warning: could not completely remove managed data directory: ' + Target);
end;

procedure DeleteManagedApplicationData;
var
  MarkerPath: String;
begin
  DeleteManagedDataDirectory('settings');
  DeleteManagedDataDirectory('cache');
  DeleteManagedDataDirectory('history');
  DeleteManagedDataDirectory('thumbnails');
  DeleteManagedDataDirectory('temp');
  DeleteManagedDataDirectory('logs');
  DeleteManagedDataDirectory('downloads');

  MarkerPath := AddBackslash(UninstallDataDir) + DataOwnerMarkerName;
  if FileExists(MarkerPath) and (not DeleteFile(MarkerPath)) then
    Log('Warning: could not remove application data ownership marker: ' + MarkerPath);

  if DirExists(UninstallDataDir) and (not RemoveDir(UninstallDataDir)) then
    Log('Application data root was preserved because it is not empty: ' + UninstallDataDir);
end;

function InitializeUninstall: Boolean;
begin
  Result := True;
  UninstallDataDir := '';
  RegQueryStringValue(HKCU, 'Software\Apson\Apson YTDownloader', 'DataDir', UninstallDataDir);
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  DeleteData: Boolean;
  Prompt: String;
begin
  if CurUninstallStep <> usUninstall then
    Exit;

  DeleteData := HasPurgeDataParameter;
  if (not DeleteData) and (not UninstallSilent) and (Trim(UninstallDataDir) <> '') then
  begin
    Prompt := CustomMessage('UninstallDataPrompt') + #13#10#13#10 +
      CustomMessage('UninstallDataPath') + #13#10 + UninstallDataDir + #13#10#13#10 +
      CustomMessage('UninstallDataWarning');
    DeleteData := MsgBox(Prompt, mbConfirmation, MB_YESNO or MB_DEFBUTTON2) = IDYES;
  end;

  if not DeleteData then
  begin
    Log('Application data was preserved.');
    Exit;
  end;

  if not IsSafeOwnedDataDirectory(UninstallDataDir) then
  begin
    Log('Refused to remove application data: the path or ownership marker is invalid.');
    if not UninstallSilent then
      MsgBox(CustomMessage('UninstallDataUnsafe'), mbError, MB_OK);
    Exit;
  end;

  DeleteManagedApplicationData;
end;
