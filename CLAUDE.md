# InitialTrading — 주간 퀀트 분석 시스템

Carlos의 한국 주식 퀀트 분析 자동화 프로젝트.
매주 금요일 장 마감 후 파이프라인을 돌려 차주 TOP5 유망 종목을 뽑고 텔레그램으로 전송한다.

## 핵심 커맨드

| 커맨드 | 동작 |
|---|---|
| `/분析` | 전체 파이프라인 실행 + 텔레그램 전송 + TOP5 출력 |
| `2_weekly.bat` 더블클릭 | PC에서 직접 파이프라인 실행 (MongoDB 필요) |

## 파이프라인 구조

```
run_pipeline.py         ← /분析 커맨드가 실행하는 진입점
  ├── update_data.py    ← FinanceDataReader → MongoDB 증분 업데이트
  ├── weekly_analysis.py← 퀀트 엔진 (팩터 분析 → 종목 스코어링)
  ├── generate_report.py← weekly_full_DATE.html 데이터 파일 생성
  ├── build_html.py     ← 최종 HTML 리포트 렌더링
  └── send_telegram.py  ← 텔레그램 봇으로 요약 + HTML 전송
```

### 퀀트 팩터 (weekly_analysis.py)
- 모멘텀 35% : 1주(20%) + 4주(30%) + 12주(50%) 수익률 백분위
- 거래량 20% : 주간거래량 / 20일 평균 백분위
- 추세   25% : Close / MA60 백분위
- 기술   20% : RSI 최적구간 + MACD 방향성

## 인프라

- **DB**: MongoDB `trading` DB, `prices` / `stocks` 컬렉션
- **MongoDB 접속**: `run_pipeline.py`가 localhost → host.docker.internal → 172.x.x.x 순으로 자동 탐색
- **MongoDB 미실행 시**: `/분析` 커맨드가 기존 데이터로 fallback 후 안내 메시지 출력

## 주요 파일 경로

```
.claude/commands/분析.md          ← /분析 슬래시 커맨드 정의
outputs/reports/weekly_full_*.html← 파싱 원본 데이터 (key=value 형식)
outputs/reports/report_*.html     ← 최종 HTML 리포트
parse_report.py                   ← 리포트 파싱 헬퍼 (/분析 커맨드가 호출)
telegram_config.py                ← 봇 토큰 + chat_id
```

## 텔레그램 봇
- `telegram_config.py`에 BOT_TOKEN / CHAT_ID 설정
- `send_telegram.py`가 시장 요약 + TOP5 + HTML 파일을 전송
- 전송 실패 시 종목별 텍스트 메시지로 fallback

## 포트폴리오 (현재 보유 ETF)
`weekly_analysis.py` 상단 `MY_PORTFOLIO_KR` 딕셔너리에서 관리.
현재 종목: KODEX AI전력핵심설비, TIGER 200, TIGER 미국S&P500, TIGER KRX금현물,
           KODEX 삼성전자채권혼합, KODEX 종합채권(AA-이상)액티브, KODEX 차이나휴머노이드로봇

## 자주 하는 작업

- **포트폴리오 종목 변경**: `weekly_analysis.py`의 `MY_PORTFOLIO_KR` 수정
- **팩터 가중치 변경**: `weekly_analysis.py` 상단 팩터 비율 수정
- **텔레그램 계정 변경**: `telegram_config.py` 수정
- **파이프라인 수동 실행**: `python run_pipeline.py` 또는 `2_weekly.bat`
