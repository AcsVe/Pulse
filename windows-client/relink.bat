@echo off
REM Pulse — re-link this device to a server, without typing the full
REM "Pulse-Setup.exe enroll <url> <code>" command by hand every time.
REM Just asks for the server URL and the linking code (get a fresh one from
REM the dashboard's Devices tab, the small "New code" button next to this
REM device), then runs the enroll command itself.
REM
REM Must be run from an elevated (Administrator) Command Prompt / by
REM right-click -> "Run as administrator", same as Pulse-Setup.exe itself.
setlocal
echo Pulse - Re-link this device to a server
echo ==========================================
echo.
set /p SERVERURL="Server URL (e.g. http://10.196.145.147:5000): "
set /p CODE="Linking code (from the dashboard's Devices tab): "
echo.
echo Linking to %SERVERURL% ...
echo.
"%~dp0Pulse-Setup.exe" enroll "%SERVERURL%" "%CODE%"
echo.
if %ERRORLEVEL% EQU 0 (
    echo Done - this device is now linked to %SERVERURL%
) else (
    echo Something went wrong ^(exit code %ERRORLEVEL%^) - double-check the
    echo server URL and that the code hasn't expired, then try again.
)
echo.
pause
