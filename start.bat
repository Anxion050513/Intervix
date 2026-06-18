@echo off
title AI Interviewer System

echo ========================================
echo   AI Interviewer - Starting All Services
echo ========================================
echo.

REM Check prerequisites
python --version >nul 2>&1
if %errorlevel% neq 0 ( echo [ERROR] Python not found! & pause & exit /b 1 )
echo [OK] Python found

node --version >nul 2>&1
if %errorlevel% neq 0 ( echo [ERROR] Node.js not found! & pause & exit /b 1 )
echo [OK] Node.js found

if not exist ".env" ( echo [ERROR] .env file not found! & pause & exit /b 1 )
echo [OK] .env configured

set ROOT=%cd%

echo.
echo [1/2] Starting Backend (port 8000)...
start "AI-Backend" /D "%ROOT%" python -m uvicorn server.main:app --host 0.0.0.0 --port 8000
echo       Waiting for backend...
timeout /t 5 /nobreak >nul

echo [2/2] Starting Frontend (port 5173)...
start "AI-Frontend" /D "%ROOT%\client" cmd /k "npm run dev"
echo       Waiting for frontend...
timeout /t 6 /nobreak >nul

echo.
echo ========================================
echo   All services started!
echo.
echo   Backend:  http://localhost:8000
echo   API Docs: http://localhost:8000/docs
echo   Frontend: http://localhost:5173
echo ========================================
echo.
echo Close the Backend and Frontend windows to stop all services.
pause
