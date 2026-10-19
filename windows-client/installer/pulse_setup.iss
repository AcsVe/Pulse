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
;     and the installer itself runs "enroll" then "install" — no command
;     line, no separate steps to get wrong. On an upgrade (pulse.db already
;     exists) the fields start out disabled behind a "re-link this device"
;     checkbox instead of being skipped outright — the first version of
;     this page always skipped itself once a device had ever enrolled,
;     with literally no way back into it short of the raw CLI command,
;     which is exactly what "no option to update the Windows link" meant
;     in practice. Re-linking reuses the dashboard's existing Devices tab
;     "↻ New code" button (server/static/app.js) — that already worked
;     server-side; the installer just never exposed a way to use it again.
;   - Both the enroll and install steps now run through Code (CurStepChanged)
;     instead of a declarative [Run] line, specifically so a failure is a
;     real MsgBox with the exit code instead of silently finishing the
;     wizard as if nothing went wrong — "tried it on another device, it
;     didn't work" with zero detail is exactly what a silently-swallowed
;     Exec() failure here looks like from the outside.
;   - A second wizard page shows this device's fingerprint (read directly
;     from the registry — the exact same value pulse_agent/license.py
;     reads at runtime) in a real, read-only edit box (Ctrl+A then Ctrl+C
;     copies it — the plain description text a first version of this page
;     used turned out not to be selectable at all), and lets an
;     already-issued activation key be entered right away. See
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
; enroll/install/license themselves moved into CurStepChanged (below) so a
; failure shows a real error instead of the wizard just finishing silently
; — see the top-of-file note on "tried it on another device, it didn't work".

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
  RelinkCheck: TNewCheckBox;
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

procedure RelinkCheckClick(Sender: TObject);
begin
  EnrollPage.Edits[0].Enabled := RelinkCheck.Checked;
  EnrollPage.Edits[1].Enabled := RelinkCheck.Checked;
end;

procedure InitializeWizard;
begin
  EnrollPage := CreateInputQueryPage(wpSelectDir,
    'Connect to your Pulse server', 'Enter the server address and one-time linking code',
    'Open the dashboard on your server, add this device (or, for a device that''s already linked, use its ' +
    '"↻ New code" button on the Devices tab), and copy the server URL and the code it shows you.');
  EnrollPage.Add('Server URL (e.g. https://pulse.example.com):', False);
  EnrollPage.Add('Linking code:', False);

  // Earlier versions of this page skipped itself entirely once pulse.db
  // existed, with no way back in short of running "Pulse-Setup.exe enroll"
  // by hand — reported as "no option to update the Windows link". Now the
  // page always shows; on an upgrade the fields just start out disabled
  // behind this checkbox so a normal update doesn't re-prompt for nothing,
  // but re-linking to a different server (or after a lost/expired code) is
  // one click away instead of a CLI command nobody's told about.
  RelinkCheck := TNewCheckBox.Create(EnrollPage);
  RelinkCheck.Parent := EnrollPage.Surface;
  RelinkCheck.Top := EnrollPage.Edits[1].Top + EnrollPage.Edits[1].Height + ScaleY(12);
  RelinkCheck.Width := EnrollPage.SurfaceWidth;
  RelinkCheck.Caption := 'This device is already linked — check this to re-link it (new server and/or new code)';
  RelinkCheck.Checked := not DBExists;
  RelinkCheck.Visible := DBExists;
  RelinkCheck.OnClick := @RelinkCheckClick;
  EnrollPage.Edits[0].Enabled := RelinkCheck.Checked;
  EnrollPage.Edits[1].Enabled := RelinkCheck.Checked;

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
    Top := FingerprintEdit.Top + FingerprintEdit.Height + ScaleY(4);
    Left := 0;
    Caption := 'Click the code above, press Ctrl+A then Ctrl+C to copy it.';
    AutoSize := True;
    Font.Style := [fsItalic];
  end;

  with TNewStaticText.Create(LicensePage) do begin
    Parent := LicensePage.Surface;
    Top := FingerprintEdit.Top + FingerprintEdit.Height + ScaleY(26);
    Left := 0;
    Caption := 'Already have a key from the developer? Paste it below — otherwise leave it blank ' +
      'and activate later (the service still installs and enrolls either way):';
    AutoSize := True;
    WordWrap := True;
    Width := LicensePage.SurfaceWidth;
  end;

  LicenseKeyEdit := TNewEdit.Create(LicensePage);
  LicenseKeyEdit.Parent := LicensePage.Surface;
  LicenseKeyEdit.Top := FingerprintEdit.Top + FingerprintEdit.Height + ScaleY(62);
  LicenseKeyEdit.Left := 0;
  LicenseKeyEdit.Width := LicensePage.SurfaceWidth;
end;

// The page is never skipped any more (see InitializeWizard's comment) — it
// always shows, so there's always a way back into it.
function ShouldSkipPage(PageID: Integer): Boolean;
begin
  Result := False;
end;

function NeedEnroll: Boolean;
begin
  Result := (not DBExists) or RelinkCheck.Checked;
end;

function NextButtonClick(CurPageID: Integer): Boolean;
begin
  Result := True;
  if (EnrollPage <> nil) and (CurPageID = EnrollPage.ID) and NeedEnroll then begin
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
  ExePath, Msg: string;
  Ok: Boolean;
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

  // enroll/install/license run from here rather than a declarative [Run]
  // line specifically so a failure is a real MsgBox with the exit code
  // instead of the wizard just finishing as if nothing went wrong — that
  // silence is exactly what "tried it on another device, it didn't work"
  // (with no further detail to go on) looks like from the outside.
  if CurStep = ssPostInstall then begin
    ExePath := ExpandConstant('{app}\Pulse-Setup.exe');

    if NeedEnroll then begin
      WizardForm.StatusLabel.Caption := 'Connecting to your Pulse server...';
      WizardForm.StatusLabel.Repaint;
      Ok := Exec(ExePath, Format('enroll "%s" "%s"', [GetServerUrl(''), GetCode('')]),
        '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
      if (not Ok) or (ResultCode <> 0) then begin
        Msg := 'Could not link this device to the server (exit code ' + IntToStr(ResultCode) + ').' + #13#10 +
          'Double-check the server URL and the linking code (it''s one-time and expires), then either ' +
          'run this installer again or, from an elevated Command Prompt:' + #13#10#13#10 +
          '"' + ExePath + '" enroll "<server URL>" "<code>"';
        MsgBox(Msg, mbError, MB_OK);
      end;
    end;

    WizardForm.StatusLabel.Caption := 'Installing the Pulse service...';
    WizardForm.StatusLabel.Repaint;
    Ok := Exec(ExePath, 'install', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
    if (not Ok) or (ResultCode <> 0) then begin
      Msg := 'Installing the Pulse service failed (exit code ' + IntToStr(ResultCode) + ').' + #13#10 +
        'Run this from an elevated Command Prompt to see the full error:' + #13#10#13#10 +
        '"' + ExePath + '" install';
      MsgBox(Msg, mbError, MB_OK);
    end;

    if HasLicenseKey then begin
      WizardForm.StatusLabel.Caption := 'Activating your license...';
      WizardForm.StatusLabel.Repaint;
      Exec(ExePath, 'license "' + GetLicenseKey('') + '"', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
      // Not fatal if this one fails — install/enroll already succeeded, and
      // the key can always be entered again later via "Pulse-Setup.exe
      // license <key>" or by re-running this installer.
    end;
  end;
end;
