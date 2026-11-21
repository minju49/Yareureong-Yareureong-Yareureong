@echo off
setlocal
if defined BOM_PYTHON goto configured
if exist "%~dp0..\runtime\python311\python.exe" goto bundled
where py >nul 2>&1
if not errorlevel 1 goto pylauncher
where python >nul 2>&1
if not errorlevel 1 goto normal
goto missing
:configured
if not exist "%BOM_PYTHON%" goto missing
"%BOM_PYTHON%" %*
exit /b %errorlevel%
:bundled
"%~dp0..\runtime\python311\python.exe" %*
exit /b %errorlevel%
:pylauncher
py -3 %*
exit /b %errorlevel%
:normal
python %*
exit /b %errorlevel%
:missing
echo Python 3.11 이상을 설치하거나 BOM_PYTHON에 python.exe 경로를 지정해주세요.
exit /b 2
