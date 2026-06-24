@echo off
title AI Interviewer System

REM Force UTF-8 codepage for Chinese character display in console
chcp 65001 >nul 2>&1
REM Tell Python to use UTF-8 for stdout/stderr
set PYTHONIOENCODING=utf-8

echo ========================================
echo   AI Interviewer - Starting All Services
echo ========================================
echo.

REM Check prerequisites
.venv\Scripts\python.exe --version >nul 2>&1
if %errorlevel% neq 0 ( echo [ERROR] Python not found in .venv! Run: python -m venv .venv ^&^& .venv\Scripts\pip install -r requirements.txt & pause & exit /b 1 )
echo [OK] Python found (.venv)

node --version >nul 2>&1
if %errorlevel% neq 0 ( echo [ERROR] Node.js not found! & pause & exit /b 1 )
echo [OK] Node.js found

if not exist ".env" ( echo [ERROR] .env file not found! & pause & exit /b 1 )
echo [OK] .env configured

set ROOT=%cd%
set REDIS_DIR=E:\Redis-8.6.2-Windows-x64-cygwin-with-Service

echo.
echo [1/3] Starting Redis (port 6380)...
if exist "%REDIS_DIR%\RedisService.exe" (
    start "AI-Redis" /D "%REDIS_DIR%" RedisService.exe run --foreground -c redis.conf
    echo       Waiting for Redis...
    timeout /t 3 /nobreak >nul
    echo [OK] Redis started
) else (
    echo [WARN] Redis not found at %REDIS_DIR%, skipping
)

echo.
echo [2/3] Starting Backend (port 8000)...
start "AI-Backend" /D "%ROOT%" .venv\Scripts\python.exe -m uvicorn server.main:app --host 0.0.0.0 --port 8000
echo       Waiting for backend...
timeout /t 5 /nobreak >nul

echo [3/3] Starting Frontend (port 5173)...
start "AI-Frontend" /D "%ROOT%\client" cmd /k "npm run dev"
echo       Waiting for frontend...
timeout /t 6 /nobreak >nul

echo.
echo ========================================
echo   All services started!
echo.
echo   Redis:    localhost:6380
echo   Backend:  http://localhost:8000
echo   API Docs: http://localhost:8000/docs
echo   Frontend: http://localhost:5173
echo ========================================
echo.
echo Close the Redis, Backend and Frontend windows to stop all services.
pause
