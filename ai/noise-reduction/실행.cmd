@echo off
setlocal
cd /d "%~dp0"
if exist "%~dp0local-runtime.cmd" call "%~dp0local-runtime.cmd"
if not defined ZIP_PYTHON set "ZIP_PYTHON=.venv\Scripts\python.exe"
if not defined ZIP_STT_MODEL_DIR if exist "%~dp0models\sensevoice-small\model.int8.onnx" set "ZIP_STT_MODEL_DIR=%~dp0models\sensevoice-small"
if not defined ZIP_PORT set "ZIP_PORT=8058"
if not exist "%ZIP_PYTHON%" (
    echo Python environment missing. See README.md.
    pause
    exit /b 1
)
echo Kiosk: http://127.0.0.1:%ZIP_PORT%/kiosk/
echo WAV comparison: http://127.0.0.1:%ZIP_PORT%/
"%ZIP_PYTHON%" -m uvicorn server:app --host 127.0.0.1 --port %ZIP_PORT% --workers 1
if errorlevel 1 pause
