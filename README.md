# InitialTrading — 주간 퀀트 분석 시스템

한국 ETF 중심 포트폴리오를 위한 **주간 퀀트 분석 자동화 파이프라인**.  
매주 금요일 장 마감 후 실행하여 차주 TOP5 유망 종목을 산출하고 텔레그램으로 전송한다.

---

## 주요 기능

- **4팩터 퀀트 스코어링** — 모멘텀·거래량·추세·기술 지표를 결합해 전 종목 랭킹
- **TOP5 자동 선별** — 매수가 / 손절가 / 목표가1·2 자동 산출
- **HTML 리포트 자동 생성** — 종목별 상세 분석 포함 시각화 리포트
- **텔레그램 자동 전송** — 요약 메시지 + HTML 파일 첨부
- **MongoDB 증분 업데이트** — FinanceDataReader → MongoDB 자동 동기화
- **MongoDB 미실행 시 fallback** — 기존 CSV 데이터로 자동 전환

---

## 퀀트 모델

| 팩터 | 비중 | 산식 |
|---|---:|---|
| 모멘텀 | 35% | 1주(20%) + 4주(30%) + 12주(50%) 수익률의 가중 백분위 |
| 거래량 | 20% | 주간 거래량 / 20일 평균 거래량의 백분위 |
| 추세   | 25% | Close / MA60 백분위 |
| 기술   | 20% | RSI 최적구간(40~70) + MACD 방향성 |

---

## 파이프라인 구조

```
run_pipeline.py
  ├── update_data.py     ← FinanceDataReader → MongoDB 증분 업데이트
  ├── weekly_analysis.py ← 4팩터 스코어링 → TOP5 선별
  ├── generate_report.py ← weekly_full_DATE.html (key=value 데이터)
  ├── build_html.py      ← 최종 HTML 리포트 렌더링
  └── send_telegram.py   ← 텔레그램 봇으로 요약 + HTML 전송
```

---

## 데이터 흐름

```
FinanceDataReader (KRX)
        │
        ▼
update_data.py ──→ MongoDB (trading.prices / trading.stocks)
        │
        ▼
weekly_analysis.py (4팩터 스코어링)
        │
        ├──→ generate_report.py ──→ outputs/reports/weekly_full_DATE.html
        │                                    │
        │                                    ▼
        │                           build_html.py ──→ report_DATE.html
        │
        └──→ send_telegram.py ──→ 텔레그램
```

---

## 설치 및 설정

### 요구 사항

- Python 3.10+
- MongoDB (로컬 또는 Docker)
- 텔레그램 봇 토큰 + Chat ID

### Python 패키지 설치

```bash
pip install pymongo FinanceDataReader pandas numpy requests
```

### 텔레그램 봇 설정

`telegram_config.py` 파일을 수정한다.

```python
BOT_TOKEN = "YOUR_BOT_TOKEN"
CHAT_ID   = "YOUR_CHAT_ID"
```

### MongoDB 실행 (Windows)

```bat
net start MongoDB
```

또는 Docker:

```bash
docker run -d -p 27017:27017 --name mongo mongo:latest
```

---

## 실행 방법

### 방법 1 — 더블클릭 (Windows)

```
2_weekly.bat  ← 더블클릭
```

### 방법 2 — 터미널

```bash
python run_pipeline.py
```

### 방법 3 — Claude Code `/분析` 커맨드

Claude Code 세션에서:

```
/분析
```

전체 파이프라인 실행 + 텔레그램 전송 + TOP5 콘솔 출력까지 자동 처리.

---

## 폴더 구조

```
InitialTrading/
├── run_pipeline.py          # 파이프라인 진입점
├── update_data.py           # 데이터 업데이트 (FinanceDataReader → MongoDB)
├── weekly_analysis.py       # 퀀트 엔진 (4팩터 스코어링)
├── generate_report.py       # weekly_full_DATE.html 생성
├── build_html.py            # 최종 HTML 리포트 렌더링
├── send_telegram.py         # 텔레그램 전송
├── parse_report.py          # 리포트 파싱 헬퍼
├── telegram_config.py       # 봇 토큰 / chat_id (git 제외 권장)
├── 2_weekly.bat             # Windows 실행 배치
├── docs/
│   ├── PROJECT_GUIDE.md     # 마스터 지침서
│   ├── PORTFOLIO.md         # 포트폴리오 현황
│   ├── WEEKLY_CYCLE.md      # 주간 운영 SOP
│   └── trading_journal.md   # 매매 복기 로그
├── outputs/
│   ├── data/
│   │   ├── master_info.csv          # 종목 마스터
│   │   └── prices_YYYY_QN.csv       # 분기별 일봉 데이터
│   └── reports/
│       ├── weekly_full_DATE.html    # 파싱용 원본 데이터
│       └── report_DATE.html         # 최종 HTML 리포트
└── .claude/
    └── commands/분析.md             # Claude Code 슬래시 커맨드
```

---

## 주간 운영 사이클

| 요일 | 시간 | 행동 |
|---|---|---|
| **금** | 15:30 이후 | `2_weekly.bat` 실행 → 텔레그램 수신 → TOP5 검토 |
| **토~일** | 자유 | 차주 매매 계획 확정, 리밸런싱 점검 |
| **월** | 09:00 전 | 주문 실행 |
| **화~목** | 저녁 | 보유 종목 추적, 손절/익절 신호 모니터링 |

---

## 매매 규칙

- 금요일 분석 결과 기준으로 **다음 영업일(월) 시초가** 부근 진입
- TOP5 신규 종목 진입 시 **분석 리포트의 매수가 ±1%** 내에서 지정가
- **손절가 이탈 → 무조건 청산**
- **목표가1 도달 → 50% 익절, 잔여는 트레일링 스탑(최고가 -8%)**
- **목표가2 도달 → 전량 익절**

---

## 인프라

| 항목 | 내용 |
|---|---|
| DB | MongoDB `trading` DB — `prices` / `stocks` 컬렉션 |
| 데이터 API | FinanceDataReader (KRX) |
| 메시징 | 텔레그램 봇 |
| 자동화 | Claude Code `/분析` 커맨드 |

MongoDB 접속 순서: `localhost` → `host.docker.internal` → `172.17.0.1` → `172.18.0.1` → `192.168.65.2`  
모두 실패 시 기존 CSV 데이터로 자동 fallback.

---

## 주의사항

- `telegram_config.py` 에는 봇 토큰과 chat_id가 포함되어 있으므로 `.gitignore` 에 추가 권장
- 과거 데이터(`outputs/data/prices_*.csv`)는 용량이 크므로 `.gitignore` 처리 권장
- 팩터 가중치 변경 시 반드시 백테스트 후 적용 (최소 1년 시뮬레이션)

---

## 라이선스

Private repository — 개인 투자 목적 프로젝트.
