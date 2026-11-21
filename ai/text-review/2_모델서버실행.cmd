@echo off
chcp 65001 >nul
powershell.exe -NoProfile -File "%~dp02_모델서버실행.ps1"
pause
