---
name: 텔레그램 데일리 브리핑 구현 상세
description: send_telegram.py 재작성 내역, KODEX 삼성전자채권혼합 티커 오류 수정(282040→448330), 스페이스X 보류
type: project
---
2026-08-29, [[feedback_telegram_daily_digest]] 요청에 따라 `send_telegram.py`를 완전히 새로 작성함.

**구조 변경:**
- 기존: `generate_report.py`가 만든 `weekly_full_*.html`(key=value)을 읽어 7개 메시지 전송
- 변경 후: 파이프라인 산출물과 무관하게 실행 시점에 직접 라이브 조회 → 메시지 1건만 전송
  - 지수: 코스피/코스닥은 FinanceDataReader(`KS11`/`KQ11`), 나스닥/S&P500/필라델피아반도체는 yfinance(`^IXIC`/`^GSPC`/`^SOX`)
  - 보유종목: 한국 종목은 FDR 개별 코드, 미국 종목은 yfinance 티커 — 각각 최근 2거래일 종가로 전일대비 등락률 계산
  - 삼성전자·SK하이닉스 수급: `pykrx.stock.get_market_trading_value_by_date(fromdate, todate, ticker)` 당일 행에서
    외국인합계/기관합계/개인 컬럼(원 단위, 억원으로 변환) 사용. KRX_ID/KRX_PW 없으면 섹션 자체를 건너뜀(파이프라인 중단 없음)

**버그 발견 및 수정:** `weekly_analysis.py`의 `MY_PORTFOLIO_KR`에 있던 'KODEX 삼성전자채권혼합' 코드가 `282040`으로
되어 있었는데, FDR/pykrx 둘 다 이 코드를 인식하지 못함(상장폐지 또는 코드 변경 추정). pykrx ETF 티커 목록에서
이름으로 재검색해 현재 정상 코드가 `448330`임을 확인 — `send_telegram.py`와 `weekly_analysis.py` 양쪽 다 수정함.
이 버그로 인해 기존 `portfolio_weekly()` 함수의 이 종목 행도 계속 '-'로 표시되고 있었을 가능성이 높음(직접 확인은 안 함).

**보류 항목:** 사용자가 보유 종목으로 언급한 '스페이스X'는 비상장 → 상장했다고는 하나 정확한 티커를 모른다고 답해
현재 digest에서 제외됨. 나중에 정확한 티커(NASDAQ/NYSE 심볼)를 알게 되면 `send_telegram.py`의
`PORTFOLIO_US` 리스트에 추가할 것.

**정확도 이슈 2건 (2026-08-29 추가 수정):**
1. *시간외 가격 병기* — 사용자가 "삼성전자 256,500원 -3.5%인데 데이터가 틀렸다"고 지적. 검증 결과 FDR·pykrx(공식 KRX)가
   9종목 전부 일치했고 계산 오류는 없었음. 원인은 **정규장 종가 vs 시간외(NXT 애프터마켓 ~20:00) 최종가** 차이.
   네이버 API `m.stock.naver.com/api/stock/{code}/basic`의 `overMarketPriceInfo.overPrice`가 정확히 사용자가 본 값이었음.
   결론: 정규장 종가를 기본으로 쓰되 시간외가 다르면 아래 줄에 병기(사용자 선택). ETF는 시간외 거래가 없어 병기되지 않음.
2. *yfinance NaN 함정* — `Ticker.history()`가 최신 거래일 Close를 간헐적으로 NaN으로 반환함(재시도해도 캐시되어 계속 NaN).
   단순 `dropna()`만 하면 **하루 전 종가가 당일 값처럼 조용히 표시**되는 게 진짜 위험(실제로 SOX가 -3.47% 대신 +2.33%로 나왔음).
   해결: 최신가는 `fast_info.last_price`, 직전 종가는 history의 마지막 유효 종가로 조합(`us_quote()`).
   주의 — `fast_info.previous_close`는 지수는 맞지만 **개별 종목에서 어긋남**(MU 919.70 vs 실제 08-27 종가 935.39)이라 쓰면 안 됨.
   추가로 지수 행에 데이터 날짜를 병기해 소스가 최신일을 못 주면 즉시 드러나게 함.

**HTML 리포트 추가 (2026-08-29):** 사용자가 "기존처럼 HTML로 정리하고, 특히 삼성전자·SK하이닉스 외국인 매수매도는
일주일치 그래프로" 요청 → `build_daily_html.py` 신규 생성. 요약 메시지 + HTML 파일 2건 전송 구조로 변경.
`collect()`가 데이터를 한 번만 모아 메시지와 HTML이 공유(pykrx/yfinance 중복 호출 방지).
그래프는 최근 5거래일 외국인/기관/개인 일별 순매수 그룹 막대(인라인 SVG, 0선 기준 위=순매수).
색상은 dataviz 스킬 팔레트 검증 통과(라이트/다크 각각). 주간 파이프라인의 `build_html.py`와는 다른 파일이니 혼동 주의.

**검증 방법(재사용 가능):** 한국은 네이버 `m.stock.naver.com/api/stock/{code}/basic`,
미국 지수는 `api.stock.naver.com/index/{.IXIC|.INX|.SOX}/basic`, 미국 종목은 `api.stock.naver.com/stock/{TICKER}.O/basic`.
stooq CSV는 HTTP 차단됨. 이 경로들로 전 종목 대조해 일치 확인함.

**Why:** [[feedback_telegram_daily_digest]] 참고 — 매일 오는 메시지가 스팸처럼 느껴진다는 사용자 피드백.

**How to apply:** 포트폴리오 종목이 바뀌면 `send_telegram.py`의 `PORTFOLIO_KR`/`PORTFOLIO_US`와
`weekly_analysis.py`의 `MY_PORTFOLIO_KR`를 함께 수정해야 함(두 곳에 종목 리스트가 중복 관리됨).
