@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
call "%~dp0scripts\python.cmd" "%~dp0review_lab\run_school.py" check %*
set "BOM_SCHOOL_EXIT=%ERRORLEVEL%"
echo.
if not "%BOM_SCHOOL_EXIT%"=="0" echo 실패한 단계와 진단 기록을 확인해주세요.
pause
exit /b %BOM_SCHOOL_EXIT%
