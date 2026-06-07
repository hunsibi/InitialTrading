---
name: InitialTrading 파이프라인 주요 기능
description: 추가된 기능 — KRX 투자자 데이터, 기관 변화 추적, GitHub Actions 자동화, GitHub Issue 히스토리
type: project
---
## 추가된 파일

- `fetch_kr_investor.py` — 한국 외국인/기관 섹터 매매 동향 수집 (pykrx 우선, MongoDB 볼륨 폴백)
- `krx_config.py` — KRX 로그인 정보 (KRX_ID=hunsibi, .gitignore 등록)
- `create_github_issue.py` — 분析 결과를 날짜별 GitHub Issue로 자동 등록 (`weekly-analysis` 라벨)
- `requirements.txt` — GitHub Actions용 Python 의존성
- `.github/workflows/weekly-analysis.yml` — 평일 매일 17:00 KST 자동 실행

## GitHub Actions 구조

- 스케줄: `0 8 * * 1-5` (평일 17:00 KST)
- 수동 트리거: workflow_dispatch
- MongoDB 캐시 전략: mongodump → actions/cache → mongorestore (7일 캐시, 매일 갱신으로 사실상 영구)
- 초회 1회만 전체 데이터 수집, 이후 증분 업데이트
- Secrets 등록 완료: TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, KRX_ID, KRX_PW

## 수정된 파일

- `fetch_institutional.py` — upsert 시 prev_sector_weights + sector_changes 자동 계산
- `fetch_kr_investor.py` — 섹터 집계 방식 → 종목별 순매수/매도 TOP5로 전면 재작성 (외국인_매수/매도, 기관_매수/매도)
- `weekly_analysis.py` — load_kr_investor_flows(), load_institutional_changes() 추가; 새 KR investor 포맷 대응
- `generate_report.py` — KR_FLOW, KR_FOREIGN_BUY/SELL, KR_INST_BUY/SELL 키 추가
- `build_html.py` — kr_investor_flow_table() 2×2 그리드 (종목명+코드+억원), inst_changes_table() 추가
- `send_telegram.py` — 메시지 4→6개 (한국 매매 동향 + 기관 변화 분析 추가)
- `run_pipeline.py` — [1-c/4] fetch_kr_investor, [4-b/4] GitHub Issue 생성 (GITHUB_ACTIONS 환경에서는 건너뜀)
- `create_github_issue.py` — get_repo(), get_report_url() 추가; Issue 본문에 HTML 리포트 URL 첨부; 한국 수급동향 섹션 추가
- `.github/workflows/weekly-analysis.yml` — contents: write 권한, HTML 리포트 커밋(reports/ 폴더) → Issue 생성 순서 확정
- `parse_report.py` — KR_FOREIGN_BUY/SELL, KR_INST_BUY/SELL 출력 추가

## GitHub Issue HTML 첨부 구조

- 파이프라인 실행 → HTML을 `reports/report_YYYY-MM-DD.html`로 커밋 → Issue 생성 (URL 포함)
- Issue 본문 끝에: `📎 [HTML 리포트 열기](https://github.com/{repo}/blob/master/reports/report_{date}.html)`
- 순서 중요: HTML 커밋 후 Issue 생성해야 URL이 유효함
- 파일명 날짜: 시스템 날짜 아닌 리포트 데이터 날짜(prices 최신 날짜) 사용 — 불일치 시 404 발생
- `reports/.gitkeep` 추가로 폴더 git 추적

## GitHub Issue 포함 섹션

- 이번주 시장요약: KOSPI/KOSDAQ/S&P500/NASDAQ/Dow Jones 수익률+상승·하락 종목수
- 안정 대장주/모멘텀/ETF/기관연동 TOP5 추천
- 한국 시총 TOP5 / 미국 시총 TOP5
- 한국 시장 수급동향: 외국인·기관 순매수·순매도 TOP5 (억원)
- 글로벌 기관 포트폴리오 동향
- HTML 리포트 링크

## 한자 교체

- 모든 파일에서 `析`(한자) → `석`(한글) 전면 교체 완료

**Why:** 한자가 깨져 보이는 문제
**How to apply:** 앞으로 코드/문서에 분析 대신 반드시 분析(한글) 사용
