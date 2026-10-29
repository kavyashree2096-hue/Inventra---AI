@echo off
title Inventra AI - Backend API
echo ========================================================
echo          Starting Inventra AI Flask Backend
echo ========================================================
cd /d "%~dp0"

if not exist "venv\Scripts\python.exe" (
    echo Virtual environment not found. Setting up Python venv...
    where py >nul 2>nul
    if %ERRORLEVEL% EQU 0 (
        py -3.11 -m venv venv
    ) else (
        python -m venv venv
    )
    if exist "venv\Scripts\python.exe" (
        echo Installing dependencies from requirements.txt...
        call venv\Scripts\activate.bat
        pip install -r requirements.txt
    )
)

if exist "venv\Scripts\python.exe" (
    echo Launching Flask backend on http://127.0.0.1:5000 ...
    venv\Scripts\python.exe app.py
) else (
    echo Attempting to run with system python...
    python app.py
)
pause
