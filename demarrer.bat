@echo off
rem Allume le laboratoire (la premiere fois : installe tout). Double-clique sur ce fichier.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup-windows.ps1" -Action Demarrer
