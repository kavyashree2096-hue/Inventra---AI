@echo off
title Inventra AI - Frontend
echo ========================================================
echo          Starting Inventra AI Vite Frontend
echo ========================================================
cd /d "%~dp0"

if not exist "node_modules" (
    echo node_modules not detected. Installing dependencies...
    call npm install
)

echo Starting Vite dev server on http://localhost:5173 ...
call npm run dev
pause
