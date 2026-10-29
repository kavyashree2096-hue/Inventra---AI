@echo off
title INVENTRA AI Launcher
echo ========================================================
echo Starting INVENTRA AI Full-Stack Platform...
echo ========================================================

echo [1/2] Starting Flask Backend API on http://127.0.0.1:5000 ...
start "Inventra Backend (Flask)" cmd /k "cd /d %~dp0inventra-back && python app.py"

timeout /t 3 /nobreak >nul

echo [2/2] Starting Vite React Frontend on http://localhost:5173 ...
start "Inventra Frontend (Vite React)" cmd /k "cd /d %~dp0inventra-front && npm run dev"

timeout /t 2 /nobreak >nul

echo ========================================================
echo INVENTRA AI is now running!
echo Application Dashboard:  http://localhost:5173
echo Backend API Endpoint:   http://127.0.0.1:5000
echo ========================================================
start http://localhost:5173
