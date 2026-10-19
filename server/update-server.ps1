# Pulse Server — self-update script.
#
# Pulse-Server.exe is a portable, standalone build (see
# .github/workflows/build-server-exe.yml) with no auto-update mechanism of
# its own — every code change needs the new build downloaded and swapped in
# by hand. This script is that swap, automated: stop the running server,
# download the latest build from the stable release link, replace the old
# .exe with it, and start it back up — one double-click instead of manually
# visiting GitHub, downloading, and re-placing the file every time.
#
# Run this FROM THE SAME FOLDER Pulse-Server.exe already lives in (double-
# click update-server.bat, which just calls this with the right working
# directory). pulse.db and instance/screens/ are never touched — they sit
# next to the .exe and are picked up again automatically by whatever .exe
# is there afterward (see app.py's DATA_DIR comment for why that's safe).

$ErrorActionPreference = 'Stop'
$here    = Split-Path -Parent $MyInvocation.MyCommand.Path
$exePath = Join-Path $here 'Pulse-Server.exe'
$oldPath = Join-Path $here 'Pulse-Server.old.exe'
$tmpPath = Join-Path $here 'Pulse-Server.new.exe'
$url     = 'https://github.com/AcsVe/Pulse/releases/latest/download/Pulse-Server.exe'

Write-Host "Stopping Pulse-Server.exe if it's running..."
Get-Process -Name 'Pulse-Server' -ErrorAction SilentlyContinue | Stop-Process -Force
Start-Sleep -Seconds 1

Write-Host "Downloading the latest build..."
try {
    Invoke-WebRequest -Uri $url -OutFile $tmpPath -UseBasicParsing
} catch {
    Write-Host "Download failed: $_" -ForegroundColor Red
    Write-Host "The old Pulse-Server.exe was left untouched and not restarted — run it yourself if needed." -ForegroundColor Yellow
    exit 1
}

# A failed/partial download (bad network, GitHub hiccup) can still produce a
# small file instead of throwing — guard against swapping in something
# broken. A real build is several MB; anything under ~1 MB is almost
# certainly an error page or a truncated transfer, not a working .exe.
$downloaded = Get-Item $tmpPath -ErrorAction SilentlyContinue
if (-not $downloaded -or $downloaded.Length -lt 1MB) {
    Write-Host "Download looks incomplete (too small) — aborting. Old server left untouched." -ForegroundColor Red
    Remove-Item $tmpPath -ErrorAction SilentlyContinue
    exit 1
}

if (Test-Path $exePath) {
    # Kept as a .bak-style copy, not deleted outright, so a bad build can be
    # rolled back by hand (rename Pulse-Server.old.exe back to
    # Pulse-Server.exe) without needing yesterday's download again.
    Move-Item -Force $exePath $oldPath
}
Move-Item -Force $tmpPath $exePath

Write-Host "Starting the updated server..."
Start-Process -FilePath $exePath -WorkingDirectory $here

Write-Host "Done — Pulse-Server.exe updated and restarted. pulse.db and instance/screens/ were left as they were." -ForegroundColor Green
