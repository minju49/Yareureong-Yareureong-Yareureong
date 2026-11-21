@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
call "%~dp0scripts\python.cmd" "%~dp0review_lab\run_batch.py" %*
set "BOM_ENTRY_EXIT=%ERRORLEVEL%"
echo.
if not "%BOM_ENTRY_EXIT%"=="0" echo 중단 또는 오류가 있어요. 위 안내를 확인해주세요.
pause
exit /b %BOM_ENTRY_EXIT%
