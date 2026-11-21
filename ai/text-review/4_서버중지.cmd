@echo off
chcp 65001 >nul
powershell.exe -NoProfile -File "%~dp04_서버중지.ps1"
pause
