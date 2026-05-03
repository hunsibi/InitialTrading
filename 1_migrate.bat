@echo off
title InitialTrading - Migration
color 0A

echo.
echo ============================================================
echo   InitialTrading : CSV to MongoDB Migration
echo ============================================================
echo.

cd /d "%~dp0"

echo [1/3] Checking pymongo...
python -c "import pymongo" 2>nul
if %errorlevel% neq 0 (
    echo   Installing pymongo...
    python -m pip install pymongo -q
    python -c "import pymongo" 2>nul
    if %errorlevel% neq 0 (
        echo.
        echo   ERROR: Could not install pymongo.
        echo   Please run manually:  python -m pip install pymongo
        echo.
        pause
        exit /b 1
    )
)
echo   pymongo OK
echo.

echo [2/3] Checking MongoDB connection...
python -c "from pymongo import MongoClient; MongoClient('localhost',27017,serverSelectionTimeoutMS=3000).admin.command('ping'); print('  MongoDB connected!')"
if %errorlevel% neq 0 (
    echo.
    echo   ERROR: Cannot connect to MongoDB.
    echo   Please start MongoDB service:
    echo     1. Press Win+R, type: services.msc
    echo     2. Find 'MongoDB' and click Start
    echo     3. Run this bat again
    echo.
    pause
    exit /b 1
)
echo.

echo [3/3] Starting migration (10~20 min)...
echo.
python migrate_to_db.py

if %errorlevel% neq 0 (
    echo.
    echo   ERROR: Migration failed.
    pause
    exit /b 1
)

echo.
echo ============================================================
echo   Migration complete!  DB: trading  Collections: prices, stocks
echo ============================================================
echo.
pause
