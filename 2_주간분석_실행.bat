@echo off
chcp 65001 >nul
title 주간 퀀트 분석 - InitialTrading
color 0B

echo.
echo ============================================================
echo   [InitialTrading] 주간 퀀트 분석 (매주 금요일 실행)
echo ============================================================
echo.

cd /d %~dp0

:: MongoDB 연결 확인
python -c "from pymongo import MongoClient; MongoClient('localhost',27017,serverSelectionTimeoutMS=3000).admin.command('ping')" 2>nul
if %errorlevel% neq 0 (
    echo   [오류] MongoDB 연결 실패. MongoDB 서비스를 먼저 시작하세요.
    pause
    exit /b 1
)

:: Step 1. 신규 데이터 업데이트
echo [1/3] 이번 주 신규 데이터 업데이트 중...
python update_data.py
if %errorlevel% neq 0 (
    echo   [오류] 데이터 업데이트 실패
    pause
    exit /b 1
)
echo.

:: Step 2. 퀀트 분석
echo [2/3] 퀀트 분석 실행 중 (약 1~2분)...
python weekly_analysis.py
if %errorlevel% neq 0 (
    echo   [오류] 분석 실패
    pause
    exit /b 1
).
echo.

:: Step 3. HTML 리포트 생성
echo [3/3] HTML 리포트 생성 중...
python generate_report.py
python build_html.py
echo.

:: 리포트 자동 열기
echo ============================================================
echo   분석 완료! 리포트를 브라우저로 열겠습니다.
echo ============================================================
echo.

:: 가장 최신 리포트 열기
for /f "delims=" %%f in ('dir /b /o-n "outputs\reports\report_*.html" 2^>nul') do (
    start "" "outputs\reports\%%f"
    goto :done
)
:done

pause
