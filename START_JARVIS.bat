@echo off
rem JARVIS-free launcher for Windows 10/11 (x64).
rem First run: creates a virtual environment, installs dependencies and downloads speech models.
setlocal EnableExtensions
cd /d "%~dp0"
title JARVIS-free

set "VENV=%~dp0.venv"
set "PY=%VENV%\Scripts\python.exe"

if not exist "%PY%" (
    echo [setup] Creating virtual environment...
    where py >nul 2>nul && (py -3 -m venv "%VENV%") || (python -m venv "%VENV%")
    if errorlevel 1 (
        echo [error] Python 3.10+ not found. Install it from https://www.python.org/downloads/ ^(tick "Add to PATH"^).
        pause
        exit /b 1
    )
)

if not exist "%VENV%\.deps_ok" (
    echo [setup] Installing dependencies...
    "%PY%" -m pip install --upgrade pip >nul
    "%PY%" -m pip install -r requirements.txt
    if errorlevel 1 (
        echo [error] Dependency installation failed. See messages above.
        pause
        exit /b 1
    )
    echo ok > "%VENV%\.deps_ok"
)

rem The dashboard window uses the WebView2 runtime (preinstalled on most Windows 10/11 machines).
reg query "HKLM\SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}" >nul 2>nul || reg query "HKCU\SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}" >nul 2>nul || (
    echo [warn] WebView2 Runtime not found. The dashboard will open in your browser instead.
    echo        Optional: install it from https://developer.microsoft.com/microsoft-edge/webview2/
)

set "MODELS_OK=1"
if not exist "resources\models\vosk-model-small-ru-0.22" set "MODELS_OK=0"
if not exist "resources\models\vosk-model-small-en-us-0.15" set "MODELS_OK=0"
if "%MODELS_OK%"=="0" (
    echo [setup] Downloading speech models ^(about 90 MB, one time^)...
    "%PY%" tools\download_models.py
)

echo [run] Starting JARVIS-free. Say "Jarvis" / "Джарвис" to wake it up.
rem pythonw would hide the console; use "python -m jarvis" instead to see the log in this window.
"%PY%" -m jarvis %*
if errorlevel 1 pause
endlocal
