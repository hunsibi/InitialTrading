@echo off
chcp 65001 >nul
title MongoDB 마이그레이션 - InitialTrading
color 0A

echo.
echo ============================================================
echo   [InitialTrading] CSV to MongoDB 마이그레이션
echo ============================================================
echo.

:: pymongo 설치 확인 및 자동 설치
echo [1/3] pymongo 설치 확인 중...
python -c "import pymongo" 2>nul
if %errorlevel% neq 0 (
    echo   pymongo 없음. 자동 설치합니다...
    pip install pymongo -q
    if %errorlevel% neq 0 (
        echo   [오류] pymongo 설치 실패. pip가 정상 동작하는지 확인하세요.
        pause
        exit /b 1
    )
    echo   pymongo 설치 완료.
) else (
    echo   pymongo 이미 설치되어 있습니다.
)
echo.

:: MongoDB 연결 확인
echo [2/3] MongoDB 연결 확인 중...
python -c "from pymongo import MongoClient; MongoClient('localhost',27017,serverSelectionTimeoutMS=3000).admin.command('ping'); print('  MongoDB 연결 성공!')" 2>nul
if %errorlevel% neq 0 (
    echo   [오류] MongoDB에 연결할 수 없습니다.
    echo.
    echo   해결 방법:
    echo   1. Windows 검색 → '서비스' 실행
    echo   2. 'MongoDB' 서비스 찾아서 '시작' 클릭
    echo   3. 이 파일을 다시 실행
    echo.
    pause
    exit /b 1
)
echo.

:: 마이그레이션 실행
echo [3/3] 마이그레이션 시작 (약 10~20분 소요)...
echo   진행 상황이 아래에 실시간 표시됩니다.
echo.
cd /d %~dp0
python migrate_to_db.py

if %errorlevel% neq 0 (
    echo.
    echo   [오류] 마이그레이션 중 문제가 발생했습니다.
    pause
    exit /b 1
)

echo.
echo ============================================================
echo   마이그레이션 완료! MongoDB에서 확인하세요.
echo   DB명: trading  /  컬렉션: prices, stocks
echo ============================================================
echo.
pause
