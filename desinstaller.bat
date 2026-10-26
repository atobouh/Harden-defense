@echo off
rem Supprime la machine virtuelle Harden Defense (demande confirmation).
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup-windows.ps1" -Action Desinstaller
