# InitialTrading — 주간 퀀트 분석 시스템

Carlos의 한국 주식 퀀트 분석 자동화 프로젝트.
매주 금요일 장 마감 후 파이프라인을 돌려 차주 TOP5 유망 종목을 뽑아 HTML 리포트 + GitHub Issue로 남긴다.
텔레그램은 평일 매일 장 마감 후 ①주요 지수 ②보유 종목 현재가 ③삼성전자·SK하이닉스 수급 동향, 3가지만 담은 데일리 브리핑 1건만 전송한다 (TOP5 추천은 텔레그램으로 보내지 않음 — 스팸 방지를 위해 2026-08-29 제거).

## 핵심 커맨드

| 커맨드 | 동작 |
|---|---|
| `/분석` | 전체 파이프라인 실행 + 텔레그램 전송 + TOP5 출력 |
| `2_weekly.bat` 더블클릭 | PC에서 직접 파이프라인 실행 (MongoDB 필요) |

## 파이프라인 구조

```
run_pipeline.py              ← 진입점 (/분석 및 2_weekly.bat 모두 이걸 호출)
  ├── update_data.py         ← FinanceDataReader → MongoDB 증분 업데이트
  │                            └─ pykrx 펀더멘털(PER/PBR/DIV) + KRX 업종 → stocks 병합 (실패 시 기존값 유지)
  ├── fetch_institutional.py ← SEC EDGAR 13F → 글로벌 기관 포트폴리오 수집 (90일 캐시)
  │                            └─ upsert 시 prev_sector_weights + sector_changes 자동 계산
  ├── fetch_kr_investor.py  ← 한국 외국인/기관 섹터 매매 동향 수집 (kr_investor_flows)
  │                            └─ pykrx(KRX_ID/KRX_PW 설정 시) 또는 MongoDB 거래량 추정 폴백
  ├── weekly_analysis.py     ← 퀀트 엔진 (4개 모델 스코어링)
  ├── generate_report.py     ← weekly_full_DATE.html 데이터 파일 생성
  │                            ├─ market_regime.py: KOSPI 레짐 판정 → 하락장 시 추천 수 5→3 축소
  │                            ├─ track_performance.py: 추천 저장 + 과거 추천 성과 평가
  │                            ├─ 안정 모델 섹터당 최대 2종목 분산 선발 + TOP5 상관관계 점검
  │                            └─ 보유 종목 중복 표시 + 포지션 사이징(1,000만원 계좌 1% 리스크)
  ├── market_regime.py       ← KOSPI MA200/MA60 + 변동성 기반 상승/중립/하락 판정
  ├── track_performance.py   ← 추천 이력(recommendations 컬렉션) 저장 + 1주/2주/4주 성과 평가
  ├── build_html.py          ← 최종 HTML 리포트 렌더링
  ├── send_telegram.py       ← 텔레그램 데일리 브리핑 1건 전송 (지수·보유종목·수급, 파이프라인 산출물과 독립적)
  └── create_github_issue.py ← 분석 결과를 GitHub Issue로 등록 (gh CLI 필요)
```

## 4개 추천 모델

| 모델 | 접두사 | 설명 |
|---|---|---|
| 안정 대장주 | S0~S4 | 시총 상위 350위, 추세건전성+리스크조정 |
| 단기 모멘텀 | M0~M4 | 전 종목, 1주·4주·12주 모멘텀 복합 |
| ETF 추천 | E0~E4 | 레버리지·인버스 제외, 추세+안정성 |
| 기관연동 한국종목 | I0~I4 | 안정 모델 베이스 + 글로벌 기관 섹터 부스트 |

### 퀀트 팩터 (안정/모멘텀 공통 기반, weekly_analysis.py)
- 모멘텀 35% : 1주(20%) + 4주(30%) + 12주(50%) 수익률 백분위
- 거래량 20% : 주간거래량 / 20일 평균 백분위
- 추세   25% : Close / MA60 백분위
- 기술   20% : RSI 최적구간 + MACD 방향성
- 안정 모델 추가 규칙: 밸류에이션 가드(PER>300 또는 PBR>30 제외, 펀더멘털 있을 때만) + 섹터당 최대 2종목 분산
- `screen_and_score(weights=...)` 파라미터로 팩터 가중치 변형 가능 (backtest.py가 사용)

### 시장 레짐 (market_regime.py)
- KOSPI 종가 vs MA200/MA60 위치로 상승/중립/하락 판정 + 20일 연환산 변동성 30% 이상 시 경고
- 하락장: 추천 종목 수 5→3 축소, 텔레그램/HTML 경고 배너
- 데이터(FDR KS11) 수집 실패 시 중립으로 간주하고 파이프라인 계속

### 백테스트 (backtest.py, 파이프라인과 별개 단독 도구)
- `python backtest.py --weeks 52` — 과거 금요일마다 look-ahead 없이 TOP5 선정 → 차주 수익률 측정
- 안정 모델 팩터 가중치 4개 변형 + 단기 모멘텀 + KOSPI 벤치마크 비교
- 결과: 콘솔 표 + `outputs/backtest_results.csv` (시총은 현재 마스터 기준 — 생존 편향 일부 존재)

## 글로벌 기관 포트폴리오 (fetch_institutional.py)

SEC EDGAR 13F-HR 공시에서 11개 기관 포트폴리오 수집 → MongoDB `institutional_holdings` 컬렉션

| 기관 | CIK |
|---|---|
| 블랙록 | 0001364742 |
| 뱅가드 | 0000102909 |
| 피델리티 | 0000315066 |
| 스테이트스트리트 | 0000093751 |
| JP모건자산운용 | 0000019617 |
| 캐피탈그룹 | 0001422848 |
| 버크셔해서웨이 | 0001067983 |
| T.로우프라이스 | 0000080255 |
| 웰링턴매니지먼트 | 0000902219 |
| 골드만삭스 | 0000886982 |
| 한국투자공사(KIC) | 0001441689 |

- 90일 캐시 (13F 분기 공시 주기 대응)
- 수집 실패 시 파이프라인은 캐시 데이터로 계속 진행

## 인프라

- **DB**: MongoDB `trading` DB
  - `prices` : 전 종목 일별 가격
  - `stocks` : 종목 마스터 (코드·이름·시장·시총 + per/pbr/div/industry 펀더멘털)
  - `institutional_holdings` : 글로벌 기관 포트폴리오 (upsert key: cik)
  - `recommendations` : 추천 이력 + 성과 평가 (key: date+model+code, eval 필드에 1주/2주/4주 수익률·목표/손절 도달)
- **MongoDB 접속**: `run_pipeline.py`가 localhost → host.docker.internal → 172.x.x.x 순으로 자동 탐색
- **MongoDB 미실행 시**: `/분석` 커맨드가 기존 데이터로 fallback 후 안내 메시지 출력

## 주요 파일

```
run_pipeline.py              ← 파이프라인 진입점
update_data.py               ← 가격 데이터 증분 업데이트
fetch_institutional.py       ← 글로벌 기관 포트폴리오 수집
weekly_analysis.py           ← 퀀트 엔진 (4모델)
market_regime.py             ← 시장 레짐 판정 (단독 실행 시 현재 레짐 출력)
track_performance.py         ← 추천 이력 저장 + 성과 평가 (단독 실행 시 평가 갱신+요약 출력)
backtest.py                  ← 워크포워드 백테스트 (단독 도구, 파이프라인 미포함)
generate_report.py           ← 데이터 파일 생성 (key=value)
build_html.py                ← HTML 리포트 렌더링
send_telegram.py             ← 텔레그램 데일리 브리핑 전송 (요약 메시지 + HTML 리포트)
build_daily_html.py          ← 데일리 브리핑 HTML 생성 (수급 SVG 그래프 포함)
parse_report.py              ← 리포트 파싱 헬퍼 (/분석 커맨드가 호출)
telegram_config.py           ← BOT_TOKEN / CHAT_ID 설정
2_weekly.bat                 ← run_pipeline.py 실행 + 리포트 자동 오픈
.claude/commands/분석.md     ← /분석 슬래시 커맨드 정의
outputs/reports/weekly_full_*.html ← 파싱 원본 데이터
outputs/reports/report_*.html      ← 최종 HTML 리포트
```

## 텔레그램 봇
- `telegram_config.py`에 BOT_TOKEN / CHAT_ID 설정
- `send_telegram.py`는 다른 파이프라인 산출물(weekly_full_*.html)과 무관하게 실행 시점에 직접 라이브 데이터를 조회해
  **요약 메시지 1건 + HTML 리포트 파일 1건**을 전송한다. 데이터는 `collect()`가 한 번만 모아 양쪽이 공유:
  1. 📈 주요 지수 — 코스피·코스닥(FDR: KS11/KQ11) + 나스닥·S&P500·필라델피아반도체 SOX(yfinance: ^IXIC/^GSPC/^SOX), 전일대비 등락률
  2. 💼 보유 종목 — `PORTFOLIO_KR`(FDR) + `PORTFOLIO_US`(yfinance) 현재가·등락률. 스페이스X는 상장 티커 미확정으로 보류 중
  3. 🇰🇷 삼성전자·SK하이닉스 매매 동향 — pykrx `get_market_trading_value_by_date` 기반 **최근 5거래일** 외국인/기관/개인
     순매수 거래대금(억원). 텔레그램 본문에는 당일 + 5일 누적, 그래프는 HTML 리포트에. KRX_ID/KRX_PW 필요
- **가격 기준**: 정규장 종가가 기본. 시간외(넥스트레이드 애프터마켓 ~20:00) 체결가가 다르면 아래 줄에 병기한다.
  증권사 앱은 시간외 최종가를 보여주므로 이 병기가 없으면 "데이터가 틀렸다"는 오해가 생긴다 — 제거하지 말 것.
- TOP5 추천·성과리포트·기관동향 등 기존 메시지들은 전부 제거됨(스팸 민원). 해당 정보는 주간 HTML 리포트 + GitHub Issue에는 남는다.

### HTML 리포트 (build_daily_html.py)
- `outputs/reports/daily_YYYY-MM-DD.html` — 외부 CDN 없는 자체 완결형(인라인 CSS/SVG), 라이트·다크 모드 대응
- 구성: 지수 KPI 타일 → 보유 종목 표 → 삼성전자·SK하이닉스 **일별 순매수 그룹 막대그래프**(인라인 SVG) + 수치 표(5일 누적 포함)
- 색상은 dataviz 스킬 검증 팔레트(외국인 파랑 / 기관 주황 / 개인 초록), light·dark 양쪽 validator 통과
- 주간 파이프라인의 `build_html.py`(TOP5 리포트)와는 별개 파일이니 혼동 주의

## 포트폴리오 (현재 보유 ETF)
`weekly_analysis.py` 상단 `MY_PORTFOLIO_KR` 딕셔너리에서 관리.
현재 종목: KODEX AI전력핵심설비, TIGER 200, TIGER 미국S&P500, TIGER KRX금현물,
           KODEX 삼성전자채권혼합, KODEX 종합채권(AA-이상)액티브, KODEX 차이나휴머노이드로봇

## GitHub 히스토리

- **GitHub Issues**: 분석 완료 시 `[YYYY-MM-DD] 주간 퀀트 분석` 이슈 자동 생성 (`weekly-analysis` 라벨)
  - Issue 포함 내용: 시장요약, 한국 시총 TOP5, 한국 수급동향(외국인·기관 순매수·매도), 종목 추천 TOP5, HTML 리포트 링크
- **GitHub Actions**: `.github/workflows/weekly-analysis.yml` — **평일 매일 20:30 KST**(`cron: '30 11 * * 1-5'`) 자동 실행 + 수동 트리거(`workflow_dispatch`) 지원
  - 20:30인 이유: 시간외(넥스트레이드 애프터마켓)가 **20:00에 종료**되므로 그 뒤여야 시간외 *최종* 체결가가 잡힌다.
    이전 17:00 스케줄은 시간외 장중이라 중간값이 찍혔다 — 앞당기지 말 것
  - GitHub 예약 실행은 러너 혼잡 시 10~30분 지연되는 게 정상(공식 동작)
  - 러너는 UTC이므로 `send_telegram.py`는 `now_kst()`로 한국 장 기준 날짜를 명시 계산한다
  - 스텝 순서: 텔레그램 데일리 브리핑 **먼저** → 파이프라인(`SKIP_TELEGRAM=1`) → 리포트 커밋 → Issue
  - 브리핑은 MongoDB·파이프라인 산출물이 필요 없는 라이브 조회라 앞에 둔다. 뒤 단계가 실패해도 브리핑은 도착한다
  - `run_pipeline.py`는 `SKIP_TELEGRAM` 환경변수가 있으면 텔레그램 단계를 건너뛴다(중복 전송 방지). 로컬 실행 시엔 미설정이므로 종전대로 전송
  - 수동 실행: GitHub → Actions 탭 → "퀀트 분석 파이프라인" → Run workflow
- **HTML 리포트**: Actions 실행 시 `reports/report_YYYY-MM-DD.html`로 커밋 후 Issue에 링크 첨부
  - 파일명 날짜 = 데이터 날짜(prices 최신일) 기준 — 시스템 날짜 사용 시 404 발생
- **로컬 Issue 생성**: `gh auth login` 후 파이프라인 실행 시 자동 처리
- **GitHub Actions Secrets 필요**: `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, `KRX_ID`, `KRX_PW`
- **MongoDB 지속성**: mongodump → actions/cache(7일) → mongorestore 방식으로 증분 업데이트; 매일 실행으로 캐시 만료 없음

## 자주 하는 작업

- **포트폴리오 종목 변경**: `weekly_analysis.py`의 `MY_PORTFOLIO_KR` 수정
- **팩터 가중치 변경**: `weekly_analysis.py` 상단 팩터 비율 수정
- **텔레그램 계정 변경**: `telegram_config.py` 수정
- **파이프라인 수동 실행**: `python run_pipeline.py` 또는 `2_weekly.bat` 더블클릭
- **기관 데이터 강제 갱신**: MongoDB `institutional_holdings` 컬렉션에서 해당 문서 삭제 후 재실행
- **외국인/기관 실데이터 활성화**: `KRX_ID`, `KRX_PW` 환경변수 설정 → pykrx 자동 사용 (미설정 시 거래량 추정 폴백)
- **한국 매매 데이터 강제 재수집**: `python fetch_kr_investor.py` 직접 실행
- **추천 성과 수동 평가/확인**: `python track_performance.py` 직접 실행 (평가 갱신 + 모델별 요약 출력)
- **추천 이력 초기화**: MongoDB `recommendations` 컬렉션 삭제 (성과 통계가 처음부터 다시 누적됨)
- **팩터 가중치 백테스트**: `python backtest.py --weeks 52` (가중치 변형 비교 후 weekly_analysis.py 수정)
- **현재 시장 레짐 확인**: `python market_regime.py`
- **펀더멘털 수동 갱신**: `python -c "import update_data; update_data.refresh_fundamentals()"`
- **포지션 사이징 기준 변경**: `generate_report.py`의 `RISK_BUDGET` 수정 (기본 10만원 = 1,000만원 계좌 1%)
