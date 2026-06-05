@echo off
title Canteen Food Ordering - Setup
cd /d "%~dp0"

echo ============================================
echo  Canteen Food Ordering System - Setup
echo ============================================
echo.

:: Check Python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python is not installed or not in PATH.
    echo Please install Python 3.14+ from https://www.python.org/downloads/
    pause
    exit /b 1
)
echo [OK] Python found:
python --version
echo.

:: Create virtual environment
if exist venv\Scripts\python.exe (
    echo [SKIP] Virtual environment already exists.
) else (
    echo [1/5] Creating virtual environment...
    python -m venv venv
    if %errorlevel% neq 0 (
        echo [ERROR] Failed to create virtual environment.
        pause
        exit /b 1
    )
    echo [OK] Virtual environment created.
)
echo.

:: Install dependencies
echo [2/5] Installing dependencies...
call venv\Scripts\pip install -r requirements.txt
if %errorlevel% neq 0 (
    echo [ERROR] Failed to install dependencies.
    pause
    exit /b 1
)
echo [OK] Dependencies installed.
echo.

:: Run migrations
echo [3/5] Running database migrations...
call venv\Scripts\python manage.py migrate
if %errorlevel% neq 0 (
    echo [ERROR] Migration failed.
    pause
    exit /b 1
)
echo [OK] Migrations complete.
echo.

:: Seed data
echo [4/5] Seeding sample data...
call venv\Scripts\python manage.py shell -c "from django.test import Client; c=Client(); print('Seeding menu...', c.post('/api/seed/menu/').status_code); print('Seeding IDs...', c.post('/api/seed/ids/').status_code)"
echo [OK] Sample data seeded.
echo.

:: Create superuser
echo [5/5] Creating admin account...
call venv\Scripts\python manage.py createsuperuser
echo.

echo ============================================
echo  Setup complete!
echo ============================================
echo.
echo To start the server, run:
echo   .\venv\Scripts\python manage.py runserver
echo.
echo For WebSocket support, run:
echo   .\venv\Scripts\pip install uvicorn
echo   .\venv\Scripts\uvicorn food_ordering.asgi:application --reload
echo.
echo Visit: http://localhost:8000/
echo Admin: http://localhost:8000/admin/
echo.

pause
