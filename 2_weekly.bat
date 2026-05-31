@echo off
chcp 65001 >nul
title InitialTrading - Weekly Analysis
color 0B

echo.
echo ============================================================
echo   InitialTrading : Weekly Quant Analysis
echo ============================================================
echo.

cd /d "%~dp0"

python run_pipeline.py

if %errorlevel% neq 0 (
    echo.
    echo   [오류] 파이프라인 실패. 위 로그를 확인하세요.
    pause
    exit /b 1
)

echo.
echo ============================================================
echo   완료! 최신 리포트를 브라우저로 엽니다.
echo ============================================================
echo.

for /f "delims=" %%f in ('dir /b /o-n "outputs\reports\report_*.html" 2^>nul') do (
    start "" "%~dp0outputs\reports\%%f"
    goto :done
)
:done
pause
