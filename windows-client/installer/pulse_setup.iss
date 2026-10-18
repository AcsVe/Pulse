; Pulse-Setup-Installer.exe — a single Inno Setup installer that replaces
; the previous manual workflow (unzip, open an elevated prompt, run
; Pulse-Setup.exe enroll then install by hand). It exists specifically to
; eliminate the friction hit during real-world testing of that manual
; workflow:
;
;   - A FIXED, permanent install folder ({autopf}\Pulse, DisableDirPage=yes)
;     so the Windows Service Control Manager's registered binary path can
;     never go stale from someone moving/reinstalling into a different
;     folder (see pulse_cli.py's docstring on why that mattered).
;   - Before copying any files, any already-running PulseHelper.exe is
;     killed and PulseService is stopped — this is the exact
;     "folder or a file in it is open in another program" error hit
;     during manual updates, now handled automatically.
;   - Windows Defender's scan exclusion for the install folder is added
;     (and removed again on uninstall) with no separate step or prompt —
;     "تخطي أو إضافة exclude in MSsecurity بدون أي عناء".
;   - One wizard page collects the server URL + one-time linking code
;     (skipped automatically on an upgrade, once pulse.db already exists)
;     and the installer itself runs "enroll" then "install" — no command
;     line, no separate steps to get wrong.
;   - A second wizard page shows this device's fingerprint (read directly
;     from the registry — the exact same value pulse_agent/license.py
;     reads at runtime) in a real, read-only edit box (auto-selected, so
;     Ctrl+C alone copies it — the plain description text a first version
;     of this page used turned out not to be selectable at all), and lets
;     an already-issued activation key be entered right away. See
;     pulse_agent/license.py's module docstring for the full
;     fingerprint-then-key round trip this pairs with. The service installs
;     and enrolls either way — it just won't report any data to the
;     dashboard until a valid key is on file (enforced in service_main.py).
;   - Uninstalling removes everything: the service, the Startup shortcut,
;     every installed file/folder, AND the local data folder under
;     ProgramData (queue db, enrollment, license) — a true clean slate,
;     not just what Pulse-Setup.exe uninstall does on its own (see
;     [UninstallDelete] below for why those are different).
;
; Built by .github/workflows/build-windows-client.yml, which first builds
; Pulse-Setup.exe/PulseService/PulseHelper exactly as before, collects them
; into windows-client\out\, then compiles this script against that folder.

#ifndef SourceDir
  #define SourceDir "..\out"
#endif

[Setup]
AppId={{8B1E1E4E-9F2D-4A3B-8C7A-5E6F7A8B9C0D}
AppName=Pulse
AppVersion=1.0
AppPublisher=RAS/ACS
AppPublisherURL=https://github.com/AcsVe/Pulse
DefaultDirName={autopf}\Pulse
; Fixed install path — never offer a choice, so the service's registered
; binary path can never end up pointing somewhere that got moved or deleted.
DisableDirPage=yes
DefaultGroupName=Pulse
DisableProgramGroupPage=yes
PrivilegesRequired=admin
ArchitecturesInstallIn64BitMode=x64
OutputDir=.
OutputBaseFilename=Pulse-Setup-Installer
SetupIconFile=pulse.ico
UninstallDisplayIcon={app}\pulse.ico
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Files]
Source: "{#SourceDir}\Pulse-Setup.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#SourceDir}\PulseService\*"; DestDir: "{app}\PulseService"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "{#SourceDir}\PulseHelper\*"; DestDir: "{app}\PulseHelper"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "{#SourceDir}\README.md"; DestDir: "{app}"; Flags: ignoreversion skipifsourcedoesntexist
Source: "pulse.ico"; DestDir: "{app}"; Flags: ignoreversion

[Run]
; Best-effort: exclude the install folder from Windows Defender scanning so
; the first run of these unsigned executables isn't quarantined/blocked.
; SilentlyContinue means a managed/locked-down Defender policy just no-ops
; this instead of failing the install.
Filename: "{sys}\WindowsPowerShell\v1.0\powershell.exe"; Parameters: "-NoProfile -ExecutionPolicy Bypass -Command ""Add-MpPreference -ExclusionPath '{app}' -ErrorAction SilentlyContinue"""; Flags: runhidden waituntilterminated; StatusMsg: "Excluding Pulse from Windows Defender scanning..."
Filename: "{app}\Pulse-Setup.exe"; Parameters: "enroll ""{code:GetServerUrl}"" ""{code:GetCode}"""; Flags: runhidden waituntilterminated; StatusMsg: "Connecting to your Pulse server..."; Check: NeedEnroll
Filename: "{app}\Pulse-Setup.exe"; Parameters: "install"; Flags: runhidden waituntilterminated; StatusMsg: "Installing the Pulse service..."
Filename: "{app}\Pulse-Setup.exe"; Parameters: "license ""{code:GetLicenseKey}"""; Flags: runhidden waituntilterminated; StatusMsg: "Activating your license..."; Check: HasLicenseKey

[UninstallRun]
Filename: "{app}\Pulse-Setup.exe"; Parameters: "uninstall"; Flags: runhidden waituntilterminated; RunOnceId: "PulseUninstall"
Filename: "{sys}\WindowsPowerShell\v1.0\powershell.exe"; Parameters: "-NoProfile -ExecutionPolicy Bypass -Command ""Remove-MpPreference -ExclusionPath '{app}' -ErrorAction SilentlyContinue"""; Flags: runhidden waituntilterminated; RunOnceId: "PulseRemoveExclusion"

[UninstallDelete]
; Pulse-Setup.exe uninstall (above) only stops/removes the service and the
; Startup shortcut — it deliberately leaves C:\ProgramData\Pulse (the local
; queue db, enrollment, activated license) in place, since that command is
; also what a plain in-place update effectively runs. A full uninstall from
; here is a clean slate instead: removes that data too, alongside every
; file/folder Inno itself installed under {app} (handled automatically).
Type: filesandordirs; Name: "{commonappdata}\Pulse"

[Code]
var
  EnrollPage: TInputQueryWizardPage;
  LicensePage: TWizardPage;
  FingerprintEdit: TNewEdit;
  LicenseKeyEdit: TNewEdit;

function DBExists: Boolean;
begin
  Result := FileExists(ExpandConstant('{commonappdata}\Pulse\pulse.db'));
end;

// Windows' own per-install identifier (no admin rights needed to read it).
// MUST match pulse_agent/license.py's fingerprint() exactly — same
// registry value, same uppercase-no-dashes formatting — since the
// developer's license_key_generator.py signs over whatever string is sent
// to them, and that has to be byte-for-byte what license.py re-derives at
// verification time.
function GetMachineFingerprint: string;
var
  Guid: string;
begin
  Guid := '';
  if not RegQueryStringValue(HKLM, 'SOFTWARE\Microsoft\Cryptography', 'MachineGuid', Guid) then
    Guid := '';
  StringChangeEx(Guid, '-', '', True);
  Result := Uppercase(Guid);
end;

procedure InitializeWizard;
begin
  EnrollPage := CreateInputQueryPage(wpSelectDir,
    'Connect to your Pulse server', 'Enter the server address and one-time linking code',
    'Open the dashboard on your server, add this device, and copy the server URL and the code it shows you. ' +
    'You can skip this if you already ran "enroll" yourself — this step is skipped automatically on an upgrade.');
  EnrollPage.Add('Server URL (e.g. https://pulse.example.com):', False);
  EnrollPage.Add('Linking code:', False);

  // A plain CreateInputQueryPage description is a static label, not a real
  // control — it can't be click-selected or Ctrl+C'd, which is exactly
  // what made the fingerprint unusable the first time this page shipped
  // (reported as "it's basically a picture, how do I copy it"). Built as a
  // custom page instead, with the fingerprint in a real (read-only) edit
  // box — any ordinary Windows edit box supports select + copy natively,
  // no extra code needed for that part.
  LicensePage := CreateCustomPage(EnrollPage.ID, 'Device license',
    'Copy the code below and send it to the developer to get your activation key');

  FingerprintEdit := TNewEdit.Create(LicensePage);
  FingerprintEdit.Parent := LicensePage.Surface;
  FingerprintEdit.Top := ScaleY(4);
  FingerprintEdit.Left := 0;
  FingerprintEdit.Width := LicensePage.SurfaceWidth;
  FingerprintEdit.ReadOnly := True;
  FingerprintEdit.Text := GetMachineFingerprint;

  with TNewStaticText.Create(LicensePage) do begin
    Parent := LicensePage.Surface;
    Top := FingerprintEdit.Top + FingerprintEdit.Height + ScaleY(20);
    Left := 0;
    Caption := 'Already have a key from the developer? Paste it below — otherwise leave it blank ' +
      'and activate later (the service still installs and enrolls either way):';
    AutoSize := True;
    WordWrap := True;
    Width := LicensePage.SurfaceWidth;
  end;

  LicenseKeyEdit := TNewEdit.Create(LicensePage);
  LicenseKeyEdit.Parent := LicensePage.Surface;
  LicenseKeyEdit.Top := FingerprintEdit.Top + FingerprintEdit.Height + ScaleY(56);
  LicenseKeyEdit.Left := 0;
  LicenseKeyEdit.Width := LicensePage.SurfaceWidth;
end;

// Selecting the fingerprint the instant this page is shown means Ctrl+C
// alone copies it — no click-drag needed at all.
procedure CurPageChanged(CurPageID: Integer);
begin
  if (LicensePage <> nil) and (CurPageID = LicensePage.ID) then begin
    FingerprintEdit.SetFocus;
    FingerprintEdit.SelectAll;
  end;
end;

function ShouldSkipPage(PageID: Integer): Boolean;
begin
  Result := False;
  if (EnrollPage <> nil) and (PageID = EnrollPage.ID) and DBExists then
    Result := True;
end;

function NextButtonClick(CurPageID: Integer): Boolean;
begin
  Result := True;
  if (EnrollPage <> nil) and (CurPageID = EnrollPage.ID) then begin
    if (Trim(EnrollPage.Values[0]) = '') or (Trim(EnrollPage.Values[1]) = '') then begin
      MsgBox('Please enter both the server URL and the linking code.', mbError, MB_OK);
      Result := False;
    end;
  end;
end;

function GetServerUrl(Param: string): string;
begin
  Result := EnrollPage.Values[0];
end;

function GetCode(Param: string): string;
begin
  Result := EnrollPage.Values[1];
end;

function NeedEnroll: Boolean;
begin
  Result := not DBExists;
end;

function GetLicenseKey(Param: string): string;
begin
  Result := Trim(LicenseKeyEdit.Text);
end;

function HasLicenseKey: Boolean;
begin
  Result := Trim(LicenseKeyEdit.Text) <> '';
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  ResultCode: Integer;
begin
  if CurStep = ssInstall then begin
    // Stop anything already running BEFORE we overwrite its files — this is
    // exactly the "folder or a file in it is open in another program" error
    // hit during manual updates.
    Exec(ExpandConstant('{sys}\taskkill.exe'), '/IM PulseHelper.exe /F', '',
      SW_HIDE, ewWaitUntilTerminated, ResultCode);
    if FileExists(ExpandConstant('{app}\PulseService\PulseService.exe')) then
      Exec(ExpandConstant('{app}\PulseService\PulseService.exe'), 'stop', '',
        SW_HIDE, ewWaitUntilTerminated, ResultCode);
  end;
end;
