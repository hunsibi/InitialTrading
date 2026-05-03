@echo off
title InitialTrading - Weekly Analysis
color 0B

echo.
echo ============================================================
echo   InitialTrading : Weekly Quant Analysis
echo ============================================================
echo.

cd /d "%~dp0"

python -c "from pymongo import MongoClient; MongoClient('localhost',27017,serverSelectionTimeoutMS=3000).admin.command('ping')" 2>nul
if %errorlevel% neq 0 (
    echo   ERROR: MongoDB not connected. Start MongoDB service first.
    pause
    exit /b 1
)

echo [1/4] Updating new data...
python update_data.py
if %errorlevel% neq 0 ( echo ERROR & pause & exit /b 1 )
echo.

echo [2/4] Running quant analysis...
python weekly_analysis.py
if %errorlevel% neq 0 ( echo ERROR & pause & exit /b 1 )
echo.

echo [3/4] Generating HTML report...
python generate_report.py
if %errorlevel% neq 0 ( echo ERROR & pause & exit /b 1 )
python build_html.py
if %errorlevel% neq 0 ( echo ERROR & pause & exit /b 1 )
echo.

echo [4/4] Sending Telegram report...
python send_telegram.py
echo.

echo ============================================================
echo   Done! Opening report in browser...
echo ============================================================
echo.

for /f "delims=" %%f in ('dir /b /o-n "outputs\reports\report_*.html" 2^>nul') do (
    start "" "%~dp0outputs\reports\%%f"
    goto :opened
)
:opened
pause
