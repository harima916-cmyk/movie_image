@echo off
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo [Setup] Creating virtual environment...
    python -m venv .venv
    if errorlevel 1 (
        echo [Error] Failed to create venv. Make sure Python is installed.
        pause
        exit /b 1
    )
    echo [Setup] Virtual environment created.
)

echo [Setup] Checking packages...
.venv\Scripts\python.exe -m pip install -r requirements.txt -q
if errorlevel 1 (
    echo [Error] Package installation failed.
    pause
    exit /b 1
)

chcp 65001 > nul
echo.
.venv\Scripts\python.exe app.py
pause
