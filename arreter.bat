@echo off
rem Eteint la machine virtuelle Harden Defense.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup-windows.ps1" -Action Arreter
