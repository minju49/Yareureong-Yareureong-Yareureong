@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
echo 먼저 새20문장_정답먼저보기.html에서 문장과 기대 결과를 확인해주세요.
echo 기존 학교 결과를 보고 설계한 추가 개발 점검이며 최종 시험셋이 아닙니다.
call "%~dp0scripts\python.cmd" "%~dp0review_lab\run_school.py" batch --cases "%~dp0review_lab\additional20_cases.json" --seed 20261124 --output-root "%~dp0records\additional20" %*
set "BOM_NEW_EXIT=%ERRORLEVEL%"
echo.
pause
exit /b %BOM_NEW_EXIT%
