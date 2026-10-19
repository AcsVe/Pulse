@echo off
REM Double-click this to update Pulse-Server.exe to the latest build.
REM Must sit in the SAME folder as Pulse-Server.exe — see update-server.ps1
REM for what it actually does and why.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0update-server.ps1"
echo.
pause
