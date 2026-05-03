"""
generate_report.py  -  주간 분석 실행 → weekly_full_DATE.html 데이터 파일 생성
"""
import weekly_analysis as wa
import pandas as pd
import os
from datetime import datetime

prices = wa.load_recent_prices(days=200)
master = wa.load_master()
ind    = wa.compute_indicators_vectorized(prices)
scored = wa.screen_and_score(ind, master)
mkt    = wa.market_summary(prices, master)
port   = wa.portfolio_weekly(prices)
top5   = scored.head(5)
date   = prices['Date'].max().strftime('%Y-%m-%d')

# ── 매매 레벨 + 지표값 수집 ────────────────────────────
levels = []
for _, row in top5.iterrows():
    tl = wa.calc_trade_levels(row)
    tl['Name']    = str(row.get('Name', row['Code']))
    tl['Code']    = row['Code']
    tl['Market']  = str(row.get('Market', ''))
    tl['Close']   = int(row['Close'])
    tl['RSI']     = round(row['RSI'], 1)
    tl['MACD']    = round(row['MACD_Hist'], 1)
    tl['VolR']    = round(row['Vol_Ratio'], 2)
    tl['R1W']     = round(row['Ret_1W']*100,  1)
    tl['R4W']     = round(row['Ret_4W']*100,  1)
    tl['R12W']    = round(row['Ret_12W']*100, 1)
    tl['MA20']    = int(row['MA20']) if pd.notna(row['MA20']) else 0
    tl['MA60']    = int(row['MA60']) if pd.notna(row['MA60']) else 0
    tl['ATR']     = round(row['ATR'], 0)
    tl['Score']   = round(row['Score_Total'], 3)
    levels.append(tl)


# ── 동적 선정 이유 생성 함수 ───────────────────────────
def gen_reasons(lv: dict) -> list:
    """지표값을 기반으로 선정 이유를 동적으로 생성"""
    reasons = []

    # 1. 주간 수익률
    if abs(lv['R1W']) >= 10:
        reasons.append(f'주간 수익률 <b>{"+" if lv["R1W"]>=0 else ""}{lv["R1W"]}%</b> 급등 — 강한 단기 모멘텀 확인')
    elif lv['R1W'] > 0:
        reasons.append(f'주간 수익률 <b>+{lv["R1W"]}%</b> — 꾸준한 상승세 유지')

    # 2. 12주 수익률
    if lv['R12W'] >= 50:
        reasons.append(f'12주(3개월) 수익률 <b>+{lv["R12W"]}%</b> — 중장기 추세 매우 강력')
    elif lv['R12W'] >= 20:
        reasons.append(f'12주(3개월) 수익률 <b>+{lv["R12W"]}%</b> — 안정적인 중장기 상승 추세')

    # 3. 4주 수익률
    if lv['R4W'] >= 30:
        reasons.append(f'4주 수익률 <b>+{lv["R4W"]}%</b> — 최근 한 달 급등, 모멘텀 최고조')
    elif lv['R4W'] >= 10:
        reasons.append(f'4주 수익률 <b>+{lv["R4W"]}%</b> — 최근 한 달도 지속 상승 중')

    # 4. 거래량
    if lv['VolR'] >= 3.0:
        reasons.append(f'거래량 평소 대비 <b>{lv["VolR"]}배</b> 폭증 — 기관·세력 강한 유입 신호')
    elif lv['VolR'] >= 1.5:
        reasons.append(f'거래량 평소 대비 <b>{lv["VolR"]}배</b> — 꾸준한 매수세 유입')

    # 5. RSI
    if 45 <= lv['RSI'] <= 65:
        reasons.append(f'RSI <b>{lv["RSI"]}</b> — 이상적인 매수 구간, 과열 아님')
    elif 65 < lv['RSI'] <= 72:
        reasons.append(f'RSI <b>{lv["RSI"]}</b> — 상승 강도 높음 (단계적 매수 권장)')

    # 6. 이동평균선
    if lv['MA20'] > 0 and lv['MA60'] > 0:
        reasons.append(f'현재가({lv["Close"]:,})가 MA20({lv["MA20"]:,})·MA60({lv["MA60"]:,}) 모두 상회 — 완벽한 정배열')
    elif lv['MA60'] > 0:
        reasons.append(f'현재가({lv["Close"]:,})가 MA60({lv["MA60"]:,})을 상회 — 중기 추세 유효')

    # 7. MACD
    if lv['MACD'] > 0:
        reasons.append(f'MACD 히스토그램 <b>+{lv["MACD"]}</b> — 상승 모멘텀 유지')

    # 최소 3개 확보
    if len(reasons) < 3:
        reasons.append(f'퀀트 종합점수 <b>{lv["Score"]}</b> — 2,700+ 종목 중 상위권')

    return reasons[:6]  # 최대 6개


def gen_caution(lv: dict) -> str:
    cautions = []
    if lv['RSI'] > 68:
        cautions.append(f'RSI {lv["RSI"]} — 과열 경계, 절반 먼저 매수 후 조정 시 추가 매수 권장')
    stop_pct = abs(lv.get('Stop_Pct', 0))
    if stop_pct >= 25:
        cautions.append(f'손절폭 {lv["Stop_Pct"]}% — 변동성 큼, 투자금의 3~5% 이하 소량 접근 권장')
    elif stop_pct >= 15:
        cautions.append(f'ATR {int(lv["ATR"]):,}원 — 일변동 큼, 투자금의 5~8% 이하 소량 분할 접근 권장')
    return ' / '.join(cautions) if cautions else ''


# ── 회사 정보 생성 ─────────────────────────────────────
def build_company_info(lv: dict) -> dict:
    return {
        'sector': '',   # stocks DB에 업종 없음 — 이후 확장 가능
        'desc':   '',   # 향후 종목 설명 DB 추가 가능
        'reasons': gen_reasons(lv),
        'caution': gen_caution(lv),
    }


# ── 출력 파일 ──────────────────────────────────────────
REPORT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'outputs', 'reports')
os.makedirs(REPORT_DIR, exist_ok=True)
out_path = os.path.join(REPORT_DIR, f'weekly_full_{date}.html')

with open(out_path, 'w', encoding='utf-8') as f:
    f.write(f'DATE={date}\n')
    f.write(f'KOSPI_RET={mkt["KOSPI"]["mean_ret"]}\n')
    f.write(f'KOSPI_UP={mkt["KOSPI"]["up"]}\n')
    f.write(f'KOSPI_DN={mkt["KOSPI"]["down"]}\n')
    f.write(f'KOSDAQ_RET={mkt["KOSDAQ"]["mean_ret"]}\n')
    f.write(f'KOSDAQ_UP={mkt["KOSDAQ"]["up"]}\n')
    f.write(f'KOSDAQ_DN={mkt["KOSDAQ"]["down"]}\n')

    for i, lv in enumerate(levels):
        ci = build_company_info(lv)
        f.write(f'S{i}_NAME={lv["Name"]}\n')
        f.write(f'S{i}_CODE={lv["Code"]}\n')
        f.write(f'S{i}_MKT={lv["Market"]}\n')
        f.write(f'S{i}_SECTOR={ci["sector"]}\n')
        f.write(f'S{i}_DESC={ci["desc"]}\n')
        f.write(f'S{i}_SCORE={lv["Score"]}\n')
        f.write(f'S{i}_CLOSE={lv["Close"]}\n')
        f.write(f'S{i}_RSI={lv["RSI"]}\n')
        f.write(f'S{i}_MACD={lv["MACD"]}\n')
        f.write(f'S{i}_VOLR={lv["VolR"]}\n')
        f.write(f'S{i}_R1W={lv["R1W"]}\n')
        f.write(f'S{i}_R4W={lv["R4W"]}\n')
        f.write(f'S{i}_R12W={lv["R12W"]}\n')
        f.write(f'S{i}_MA20={lv["MA20"]}\n')
        f.write(f'S{i}_MA60={lv["MA60"]}\n')
        f.write(f'S{i}_ATR={int(lv["ATR"])}\n')
        f.write(f'S{i}_ENTRY={lv["Entry"]}\n')
        f.write(f'S{i}_STOP={lv["StopLoss"]}\n')
        f.write(f'S{i}_STOP_PCT={lv["Stop_Pct"]}\n')
        f.write(f'S{i}_T1={lv["Target1"]}\n')
        f.write(f'S{i}_T1_PCT={lv["T1_Pct"]}\n')
        f.write(f'S{i}_T2={lv["Target2"]}\n')
        f.write(f'S{i}_T2_PCT={lv["T2_Pct"]}\n')
        reasons = ci['reasons']
        f.write(f'S{i}_REASONS={"|".join(reasons)}\n')
        f.write(f'S{i}_CAUTION={ci["caution"]}\n')

    for _, row in port.iterrows():
        r = row['주간수익률']
        f.write(f'PORT|{row["종목명"]}|{row["코드"]}|{row["현재가"]}|{r}\n')

print(f'DATA_FILE={out_path}')
