@echo off
setlocal
cd /d "%~dp0"
if not defined ZIP_PYTHON set "ZIP_PYTHON=.venv\Scripts\python.exe"
if not exist "%ZIP_PYTHON%" (
    echo Python environment missing. See README.md.
    pause
    exit /b 1
)
echo Kiosk: http://127.0.0.1:8058/kiosk/
echo WAV comparison: http://127.0.0.1:8058/
"%ZIP_PYTHON%" -m uvicorn server:app --host 127.0.0.1 --port 8058 --workers 1
if errorlevel 1 pause
