@echo off
rem Montre ce qui serait telecharge, sans rien installer.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup-windows.ps1" -PlanSeulement
