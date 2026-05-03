# InitialTrading — 프로젝트 마스터 지침서

> **작성자:** Carlos
> **갱신일:** 2026-05-03
> **버전:** v1.0
> **위치:** `D:\WorkSpace\InitialTrading\`

이 문서는 InitialTrading 프로젝트의 **단일 진실 공급원(Single Source of Truth)** 입니다.
새 Cowork 세션이 열리면 Claude가 가장 먼저 읽는 파일이며, 운영 규칙·전략·인프라·일정이 모두 여기에서 출발합니다.

---

## 1. 프로젝트 목적

데이터 기반 퀀트 분석으로 **국내 ETF 중심 1억 포트폴리오** 와 **미국 레버리지 위성 포지션** 을 운영하면서,
한투 OpenAPI를 활용한 자체 단타 시스템도 함께 발전시킨다.

핵심 원칙:

1. **Claude는 분석/근거 제시, Carlos는 최종 결정.** 주문 권한은 항상 Carlos.
2. **모든 의사결정은 데이터 + 룰로 환원 가능해야 한다.** 직관 단독 매매 금지.
3. **세션 메모리는 휘발성, 파일이 영구 메모리.** 모든 결정·근거·복기는 `trading_journal.md` 에 기록.
4. **주간 사이클로 운영.** 일별 트레이딩이 아닌 주간 단위(금→월) 의사결정.

---

## 2. 폴더 구조

```
D:\WorkSpace\InitialTrading\
├── CLAUDE.md                       # 기존 Claude Code 진입점 (커맨드 안내)
├── docs/                           # ★ 지침서 폴더 (이 문서가 여기 있음)
│   ├── PROJECT_GUIDE.md            # ← 마스터 지침서
│   ├── PORTFOLIO.md                # 현재 포트폴리오 + 운용 규칙
│   ├── WEEKLY_CYCLE.md             # 주간 사이클 SOP
│   └── trading_journal.md          # 매매/복기 누적 로그
├── skills/                         # 재사용 스킬 소스
│   ├── friday-review/SKILL.md
│   ├── portfolio-checkup/SKILL.md
│   └── weekly-quant/SKILL.md       # (기존 스킬 fix 버전)
├── outputs/
│   ├── data/
│   │   ├── master_info.csv         # 종목 마스터
│   │   └── prices_YYYY_QN.csv      # 분기별 일봉 (2021 Q2 ~ 현재)
│   └── reports/
│       ├── weekly_full_DATE.html   # 파싱용 key=value 데이터
│       └── report_DATE.html        # 최종 리포트
├── run_pipeline.py                 # 파이프라인 진입점
├── update_data.py                  # FinanceDataReader → MongoDB 증분
├── weekly_analysis.py              # 퀀트 엔진 (4팩터)
├── generate_report.py              # weekly_full_*.html 생성
├── build_html.py                   # 최종 HTML 렌더
├── send_telegram.py                # 텔레그램 봇 전송
├── parse_report.py                 # 리포트 파싱 헬퍼
├── telegram_config.py              # 봇 토큰/chat_id
├── 2_weekly.bat                    # PC 더블클릭 실행
└── .claude/commands/분석.md        # /분석 슬래시 커맨드
```

> **데이터 보존 범위:** 2021 Q2 ~ 2026 Q1 (분기별 CSV). 매주 `update_data.py`가 증분 업데이트.

---

## 3. 데이터 흐름

```
FinanceDataReader (KRX)
        │
        ▼
update_data.py ──→ MongoDB (trading.prices, trading.stocks)
        │
        ▼
weekly_analysis.py (4팩터 스코어링)
        │
        ├──→ generate_report.py ──→ outputs/reports/weekly_full_DATE.html  (key=value, 파싱용)
        │                                       │
        │                                       ▼
        │                              build_html.py ──→ outputs/reports/report_DATE.html (최종)
        │
        └──→ send_telegram.py ──→ 텔레그램 (요약 + HTML 첨부)
```

진입점: `python run_pipeline.py` 또는 `2_weekly.bat` 더블클릭.
MongoDB 미실행 시 기존 CSV로 fallback.

---

## 4. 퀀트 모델 (weekly_analysis.py 기준)

| 팩터 | 비중 | 산식 |
|---|---:|---|
| 모멘텀 | 35% | 1주 수익률(20%) + 4주(30%) + 12주(50%)의 가중 백분위 |
| 거래량 | 20% | 주간 거래량 / 20일 평균 거래량의 백분위 |
| 추세  | 25% | Close / MA60 의 백분위 |
| 기술  | 20% | RSI 최적구간(40~70) + MACD 방향성 |

**스코어 → TOP5 선별 → 매수가/손절가/목표가1·2 산출** 까지 자동.
가중치 변경은 `weekly_analysis.py` 상단에서 수정.

---

## 5. 주간 운영 사이클 (요약 — 상세는 `WEEKLY_CYCLE.md`)

| 요일 | 시간 | 행동 |
|---|---|---|
| **금** | 장 마감(15:30) 후 | `2_weekly.bat` 실행 → 텔레그램 수신 → Claude와 주간 복기 + 차주 TOP5 검토 |
| **토~일** | 자유 | 차주 매매 계획 확정, 포트폴리오 리밸런싱 시그널 점검 |
| **월** | 09:00 전 | 주문 실행 (시장가/지정가) |
| **화~목** | 저녁 | 보유 종목 추적, 손절/익절 신호 모니터링 |

---

## 6. 운영 규칙

### 6.1 자금 규칙
- **국장 코어 포트폴리오:** 약 1억원, ETF 중심.
- **미장 위성 포지션:** TSLL, BITX (레버리지 — 공격적 비중).
- **주간 추가 투입 한도:** 50~100만원 (현금 보유분 제외, 신규 종목/추가매수 모두 포함).
- **단일 종목 최대 비중:** 코어 25%, 위성 단일 15%.

### 6.2 매매 규칙
- 금요일 분석 결과 기준으로 **다음 영업일(월) 시초가** 부근 진입.
- TOP5 신규 종목 진입 시 **분석 리포트의 매수가 ±1%** 내에서 지정가.
- **손절가 이탈 → 무조건 청산.** 감정 개입 금지.
- **목표가1 도달 → 50% 익절, 잔여는 트레일링 스탑(최고가 -8%).**
- **목표가2 도달 → 전량 익절.**

### 6.3 복기 규칙
- 매주 금요일, 다음 항목을 `trading_journal.md` 에 기록:
  - 이번 주 KOSPI/KOSDAQ 수익률, 보유 종목 등락, 매매 체결 결과
  - 모델 추천 vs 실제 행동의 괴리 (왜 안 따랐는지)
  - 다음 주 액션 플랜
- **최소 주 1회 기록**, 빠뜨리면 다음 세션 시작 시 회복.

### 6.4 시스템 변경 규칙
- 팩터 가중치, 손절폭, 포지션 사이즈 등 **모든 룰 변경은 `trading_journal.md` 에 변경 일자/근거를 남긴다**.
- 백테스트 없이 룰을 바꾸지 않는다 (최소 과거 1년 시뮬레이션).

---

## 7. Claude 세션 시작 절차 (SOP)

새 Cowork 세션이 열리면 Claude는 다음을 순서대로 수행:

1. `docs/PROJECT_GUIDE.md` 통독 (= 이 파일)
2. `docs/PORTFOLIO.md` 통독 → 현재 포지션 파악
3. `docs/trading_journal.md` 의 **최근 2개 엔트리** 통독
4. `outputs/reports/weekly_full_*.html` 중 **최신 파일 1개** 파싱 → 최근 분석 결과 메모리에 적재
5. Carlos에게 짧은 인사 + “지난 세션 이후 변경/체결 있었나요?” 한 줄 질문

---

## 8. 재사용 스킬 (Cowork)

| 스킬 | 트리거 | 역할 |
|---|---|---|
| `weekly-quant` | "주간분석", "이번주 top5" | 최신 weekly_full 리포트 파싱 → TOP5 즉시 출력 |
| `friday-review` | "금요복기", "이번주 정리" | 시장 + 포트폴리오 + TOP5 통합 분석 + 차주 전략 제안 |
| `portfolio-checkup` | "포트폴리오 점검", "리밸런싱" | 보유 종목 손익 점검 + 리밸런싱 시그널 |

설치 위치: 사용자 plugin/skill 디렉터리 (Cowork 설치 시 자동 등록).

---

## 9. 외부 자산

- **증권사:** 미래에셋 (M-Stock 앱)
- **데이터 API:** FinanceDataReader, 한투 OpenAPI (개발 중)
- **메시징:** 텔레그램 봇 (`telegram_config.py`)
- **DB:** MongoDB 로컬 (Docker), `trading.prices` / `trading.stocks`

---

## 10. 변경 이력

| 일자 | 내용 |
|---|---|
| 2026-05-03 | v1.0 초안 작성, 미장 포지션 추가, docs/skills 구조 정의 |
