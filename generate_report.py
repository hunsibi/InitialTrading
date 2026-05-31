"""
generate_report.py  -  세 모델(안정 대장주 TOP5 + 모멘텀 TOP5 + ETF TOP5) 동시 실행
                        weekly_full_DATE.html 데이터 파일 생성
"""
import weekly_analysis as wa
import pandas as pd
import os
from datetime import datetime

prices = wa.load_recent_prices(days=200)
master = wa.load_master()
ind    = wa.compute_indicators_vectorized(prices)

# -- 세 모델 실행 ----------------------------------------------------------
print("\n=== [안정 대장주 모델] ===")
scored_stable = wa.screen_and_score(ind, master)

print("\n=== [단기 모멘텀 모델] ===")
scored_mom    = wa.screen_and_score_momentum(ind, master)

print("\n=== [ETF 추천 모델] ===")
try:
    etf_prices, etf_master = wa.load_etf_prices(days=200, top_n=200)
    etf_ind    = wa.compute_indicators_vectorized(etf_prices)
    scored_etf = wa.screen_and_score_etf(etf_ind, etf_master)
    top5_etf   = scored_etf.head(5)
    etf_ok     = True
except Exception as e:
    print(f"  [경고] ETF 모델 실패: {e}")
    top5_etf = pd.DataFrame()
    etf_ok   = False

mkt     = wa.market_summary(prices, master)
print("\n=== [미국 시장 요약] ===")
try:
    us_mkt = wa.us_market_summary()
except Exception as e:
    print(f"  [경고] US 시장 수집 실패: {e}")
    us_mkt = {}
top5_stable = scored_stable.head(5)
top5_mom    = scored_mom.head(5)
date = prices['Date'].max().strftime('%Y-%m-%d')


# -- 매매 레벨 수집 함수 ---------------------------------------------------
def collect_levels(top5: pd.DataFrame, sector_fn=None) -> list:
    levels = []
    for _, row in top5.iterrows():
        tl = wa.calc_trade_levels(row)
        tl['Name']   = str(row.get('Name', row['Code']))
        tl['Code']   = row['Code']
        tl['Market'] = str(row.get('Market', ''))
        tl['Sector'] = sector_fn(tl['Name']) if sector_fn else wa.infer_sector(tl['Name'])
        tl['Close']  = int(row['Close'])
        tl['RSI']    = round(row['RSI'], 1)
        tl['MACD']   = round(row['MACD_Hist'], 1)
        tl['VolR']   = round(row['Vol_Ratio'], 2)
        tl['R1W']    = round(row['Ret_1W']*100,  1)
        tl['R4W']    = round(row['Ret_4W']*100,  1)
        tl['R12W']   = round(row['Ret_12W']*100, 1)
        tl['MA20']   = int(row['MA20']) if pd.notna(row['MA20']) else 0
        tl['MA60']   = int(row['MA60']) if pd.notna(row['MA60']) else 0
        tl['ATR']    = round(row['ATR'], 0)
        tl['Score']  = round(row['Score_Total'], 3)
        levels.append(tl)
    return levels

levels_stable = collect_levels(top5_stable)
levels_mom    = collect_levels(top5_mom)
levels_etf    = collect_levels(top5_etf, sector_fn=wa.infer_etf_theme) if etf_ok and not top5_etf.empty else []


# -- 선정 이유: 안정 대장주 모델 -------------------------------------------
def gen_reasons_stable(lv: dict) -> list:
    reasons = []

    if lv['MA20'] > 0 and lv['MA60'] > 0:
        if lv['Close'] > lv['MA20'] > lv['MA60']:
            reasons.append('MA20·MA60 <b>정배열</b> — 중장기 상승추세 확립')
        elif lv['Close'] > lv['MA60']:
            reasons.append(f'현재가가 MA60({lv["MA60"]:,}원) 상회 — 중기 추세 유효')

    if lv['MA20'] > 0:
        gap = (lv['Close'] - lv['MA20']) / lv['MA20'] * 100
        if 0 <= gap <= 7:
            reasons.append(f'MA20 대비 <b>+{gap:.1f}%</b> — 과열 없는 이상적 진입 구간')
        elif 7 < gap <= 12:
            reasons.append(f'MA20 대비 <b>+{gap:.1f}%</b> — 상승세 유효 (단계 매수 권장)')
        elif -5 <= gap < 0:
            reasons.append('MA20 소폭 하회 — 단기 눌림목 반등 진입 구간')

    if 45 <= lv['RSI'] <= 62:
        reasons.append(f'RSI <b>{lv["RSI"]}</b> — 과열·과매도 없는 최적 매수 구간')
    elif 62 < lv['RSI'] <= 68:
        reasons.append(f'RSI <b>{lv["RSI"]}</b> — 상승 강도 높음 (분할 매수 권장)')

    if lv['ATR'] > 0 and lv['Close'] > 0:
        atr_pct = lv['ATR'] / lv['Close'] * 100
        if atr_pct <= 2.0:
            reasons.append(f'일일 변동성 <b>{atr_pct:.1f}%</b> — 낮은 변동성, 안정적 투자 환경')
        elif 2.0 < atr_pct <= 3.5:
            reasons.append(f'일일 변동성 <b>{atr_pct:.1f}%</b> — 적정 수준의 변동성')

    r4 = lv['R4W']
    if 5 <= r4 <= 20:
        reasons.append(f'4주 수익률 <b>+{r4}%</b> — 과열 없는 안정적 상승세')
    elif 20 < r4 <= 40:
        reasons.append(f'4주 수익률 <b>+{r4}%</b> — 강한 상승세 유지')
    elif 0 < r4 < 5:
        reasons.append(f'4주 수익률 <b>+{r4}%</b> — 완만하고 안정적인 회복세')

    if lv['MACD'] > 0:
        reasons.append(f'MACD 히스토그램 <b>+{lv["MACD"]}</b> — 상승 모멘텀 지속')

    vr = lv['VolR']
    if 0.7 <= vr <= 1.5:
        reasons.append(f'거래량 <b>{vr}배</b> — 안정적 수급 (꾸준한 매수세)')
    elif 1.5 < vr <= 2.5:
        reasons.append(f'거래량 <b>{vr}배</b> — 평소보다 활발한 매수세 유입')

    r12 = lv['R12W']
    if 10 <= r12 <= 60:
        reasons.append(f'12주 수익률 <b>+{r12}%</b> — 중장기 안정 상승 추세')

    if len(reasons) < 3:
        reasons.append(f'시총 대장주 퀀트 점수 <b>{lv["Score"]}</b> — 안정성·수익성 종합 우수')

    return reasons[:5]


def gen_caution_stable(lv: dict) -> str:
    cautions = []
    if lv['RSI'] > 65:
        cautions.append(f'RSI {lv["RSI"]} — 과열 경계, 분할 매수 권장')
    if abs(lv.get('Stop_Pct', 0)) >= 20:
        cautions.append(f'손절폭 {abs(lv["Stop_Pct"]):.0f}% — 소량 접근 권장')
    if lv['ATR'] > 0 and lv['Close'] > 0:
        atr_pct = lv['ATR'] / lv['Close'] * 100
        if 3.5 < atr_pct <= 5.0:
            cautions.append(f'일일변동 {atr_pct:.1f}% — 분할 매수 권장')
    return ' / '.join(cautions) if cautions else ''


# -- 선정 이유: 단기 모멘텀 모델 -------------------------------------------
def gen_reasons_momentum(lv: dict) -> list:
    reasons = []

    if abs(lv['R1W']) >= 10:
        sign = '+' if lv['R1W'] >= 0 else ''
        reasons.append(f'주간 수익률 <b>{sign}{lv["R1W"]}%</b> 급등 — 강한 단기 모멘텀 확인')
    elif lv['R1W'] > 0:
        reasons.append(f'주간 수익률 <b>+{lv["R1W"]}%</b> — 꾸준한 상승세 유지')

    if lv['R12W'] >= 50:
        reasons.append(f'12주 수익률 <b>+{lv["R12W"]}%</b> — 중장기 추세 매우 강력')
    elif lv['R12W'] >= 20:
        reasons.append(f'12주 수익률 <b>+{lv["R12W"]}%</b> — 안정적인 중장기 상승 추세')

    if lv['R4W'] >= 30:
        reasons.append(f'4주 수익률 <b>+{lv["R4W"]}%</b> — 최근 한 달 급등, 모멘텀 최고조')
    elif lv['R4W'] >= 10:
        reasons.append(f'4주 수익률 <b>+{lv["R4W"]}%</b> — 최근 한 달 지속 상승 중')

    if lv['VolR'] >= 3.0:
        reasons.append(f'거래량 <b>{lv["VolR"]}배</b> 폭증 — 기관·세력 강한 유입 신호')
    elif lv['VolR'] >= 1.5:
        reasons.append(f'거래량 <b>{lv["VolR"]}배</b> — 꾸준한 매수세 유입')

    if 45 <= lv['RSI'] <= 65:
        reasons.append(f'RSI <b>{lv["RSI"]}</b> — 이상적인 매수 구간, 과열 아님')
    elif 65 < lv['RSI'] <= 72:
        reasons.append(f'RSI <b>{lv["RSI"]}</b> — 상승 강도 높음 (단계적 매수 권장)')

    if lv['MA20'] > 0 and lv['MA60'] > 0:
        reasons.append(f'현재가({lv["Close"]:,})가 MA20·MA60 모두 상회 — 완벽한 정배열')

    if lv['MACD'] > 0:
        reasons.append(f'MACD 히스토그램 <b>+{lv["MACD"]}</b> — 상승 모멘텀 유지')

    if len(reasons) < 3:
        reasons.append(f'퀀트 종합점수 <b>{lv["Score"]}</b> — 2,700+ 종목 중 상위권')

    return reasons[:6]


def gen_caution_momentum(lv: dict) -> str:
    cautions = []
    if lv['RSI'] > 68:
        cautions.append(f'RSI {lv["RSI"]} — 과열 경계, 절반 먼저 매수 후 조정 시 추가 매수')
    stop_pct = abs(lv.get('Stop_Pct', 0))
    if stop_pct >= 25:
        cautions.append(f'손절폭 {lv["Stop_Pct"]}% — 변동성 큼, 투자금의 3~5% 이하 소량 접근')
    elif stop_pct >= 15:
        cautions.append(f'ATR {int(lv["ATR"]):,}원 — 일변동 큼, 분할 접근 권장')
    return ' / '.join(cautions) if cautions else ''


# -- 선정 이유: ETF 추천 모델 -----------------------------------------------
def gen_reasons_etf(lv: dict) -> list:
    reasons = []
    theme = lv['Sector']
    reasons.append(f'테마: <b>{theme}</b> — 구조적 성장 섹터 추종 ETF')

    r12 = lv['R12W']
    if r12 >= 30:
        reasons.append(f'12주 수익률 <b>+{r12}%</b> — 강한 중장기 상승 추세')
    elif r12 >= 10:
        reasons.append(f'12주 수익률 <b>+{r12}%</b> — 안정적 중장기 상승세')
    elif r12 >= 0:
        reasons.append(f'12주 수익률 <b>+{r12}%</b> — 완만한 회복세 진행 중')

    r4 = lv['R4W']
    if r4 >= 15:
        reasons.append(f'4주 수익률 <b>+{r4}%</b> — 최근 한 달 강한 상승세')
    elif r4 >= 5:
        reasons.append(f'4주 수익률 <b>+{r4}%</b> — 안정적 단기 상승세')

    if lv['ATR'] > 0 and lv['Close'] > 0:
        atr_pct = lv['ATR'] / lv['Close'] * 100
        if atr_pct <= 2.0:
            reasons.append(f'일일 변동성 <b>{atr_pct:.1f}%</b> — 낮은 변동성, 안정적 ETF')
        elif 2.0 < atr_pct <= 3.5:
            reasons.append(f'일일 변동성 <b>{atr_pct:.1f}%</b> — 적정 수준의 변동성')

    if 45 <= lv['RSI'] <= 62:
        reasons.append(f'RSI <b>{lv["RSI"]}</b> — 과열 없는 최적 진입 구간')
    elif 62 < lv['RSI'] <= 72:
        reasons.append(f'RSI <b>{lv["RSI"]}</b> — 상승 강도 높음 (분할 매수 권장)')

    if lv['MA20'] > 0 and lv['MA60'] > 0:
        if lv['Close'] > lv['MA20'] > lv['MA60']:
            reasons.append('MA20·MA60 <b>정배열</b> — 중장기 상승추세 확립')

    if lv['MACD'] > 0:
        reasons.append(f'MACD 히스토그램 <b>+{lv["MACD"]}</b> — 상승 모멘텀 지속')

    if len(reasons) < 3:
        reasons.append(f'ETF 퀀트 점수 <b>{lv["Score"]}</b> — 안정성·성장성 종합 우수')

    return reasons[:5]


def gen_caution_etf(lv: dict) -> str:
    cautions = []
    if lv['RSI'] > 68:
        cautions.append(f'RSI {lv["RSI"]} — 단기 과열, 분할 매수 권장')
    if lv['ATR'] > 0 and lv['Close'] > 0:
        atr_pct = lv['ATR'] / lv['Close'] * 100
        if atr_pct > 3.5:
            cautions.append(f'일일변동 {atr_pct:.1f}% — 레버리지·고위험 ETF 가능성 확인')
    return ' / '.join(cautions) if cautions else ''


# -- 출력 파일 --------------------------------------------------------------
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
    # 미국 시장
    sp  = us_mkt.get('SP500',  {})
    nq  = us_mkt.get('NASDAQ', {})
    dj  = us_mkt.get('DOW30',  {})
    f.write(f'US_SP_RET={sp.get("ret", "")}\n')
    f.write(f'US_SP_UP={sp.get("up", "")}\n')
    f.write(f'US_SP_DN={sp.get("dn", "")}\n')
    f.write(f'US_NQ_RET={nq.get("ret", "")}\n')
    f.write(f'US_DJ_RET={dj.get("ret", "")}\n')
    f.write(f'US_DJ_UP={dj.get("up", "")}\n')
    f.write(f'US_DJ_DN={dj.get("dn", "")}\n')

    # 안정 대장주 모델 (S prefix)
    for i, lv in enumerate(levels_stable):
        reasons = gen_reasons_stable(lv)
        caution = gen_caution_stable(lv)
        f.write(f'S{i}_NAME={lv["Name"]}\n')
        f.write(f'S{i}_CODE={lv["Code"]}\n')
        f.write(f'S{i}_MKT={lv["Market"]}\n')
        f.write(f'S{i}_SECTOR={lv["Sector"]}\n')
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
        f.write(f'S{i}_REASONS={"|".join(reasons)}\n')
        f.write(f'S{i}_CAUTION={caution}\n')

    # 단기 모멘텀 모델 (M prefix)
    for i, lv in enumerate(levels_mom):
        reasons = gen_reasons_momentum(lv)
        caution = gen_caution_momentum(lv)
        f.write(f'M{i}_NAME={lv["Name"]}\n')
        f.write(f'M{i}_CODE={lv["Code"]}\n')
        f.write(f'M{i}_MKT={lv["Market"]}\n')
        f.write(f'M{i}_SECTOR={lv["Sector"]}\n')
        f.write(f'M{i}_SCORE={lv["Score"]}\n')
        f.write(f'M{i}_CLOSE={lv["Close"]}\n')
        f.write(f'M{i}_RSI={lv["RSI"]}\n')
        f.write(f'M{i}_MACD={lv["MACD"]}\n')
        f.write(f'M{i}_VOLR={lv["VolR"]}\n')
        f.write(f'M{i}_R1W={lv["R1W"]}\n')
        f.write(f'M{i}_R4W={lv["R4W"]}\n')
        f.write(f'M{i}_R12W={lv["R12W"]}\n')
        f.write(f'M{i}_MA20={lv["MA20"]}\n')
        f.write(f'M{i}_MA60={lv["MA60"]}\n')
        f.write(f'M{i}_ATR={int(lv["ATR"])}\n')
        f.write(f'M{i}_ENTRY={lv["Entry"]}\n')
        f.write(f'M{i}_STOP={lv["StopLoss"]}\n')
        f.write(f'M{i}_STOP_PCT={lv["Stop_Pct"]}\n')
        f.write(f'M{i}_T1={lv["Target1"]}\n')
        f.write(f'M{i}_T1_PCT={lv["T1_Pct"]}\n')
        f.write(f'M{i}_T2={lv["Target2"]}\n')
        f.write(f'M{i}_T2_PCT={lv["T2_Pct"]}\n')
        f.write(f'M{i}_REASONS={"|".join(reasons)}\n')
        f.write(f'M{i}_CAUTION={caution}\n')

    # ETF 추천 모델 (E prefix)
    for i, lv in enumerate(levels_etf):
        reasons = gen_reasons_etf(lv)
        caution = gen_caution_etf(lv)
        f.write(f'E{i}_NAME={lv["Name"]}\n')
        f.write(f'E{i}_CODE={lv["Code"]}\n')
        f.write(f'E{i}_MKT={lv["Market"]}\n')
        f.write(f'E{i}_SECTOR={lv["Sector"]}\n')
        f.write(f'E{i}_SCORE={lv["Score"]}\n')
        f.write(f'E{i}_CLOSE={lv["Close"]}\n')
        f.write(f'E{i}_RSI={lv["RSI"]}\n')
        f.write(f'E{i}_MACD={lv["MACD"]}\n')
        f.write(f'E{i}_VOLR={lv["VolR"]}\n')
        f.write(f'E{i}_R1W={lv["R1W"]}\n')
        f.write(f'E{i}_R4W={lv["R4W"]}\n')
        f.write(f'E{i}_R12W={lv["R12W"]}\n')
        f.write(f'E{i}_MA20={lv["MA20"]}\n')
        f.write(f'E{i}_MA60={lv["MA60"]}\n')
        f.write(f'E{i}_ATR={int(lv["ATR"])}\n')
        f.write(f'E{i}_ENTRY={lv["Entry"]}\n')
        f.write(f'E{i}_STOP={lv["StopLoss"]}\n')
        f.write(f'E{i}_STOP_PCT={lv["Stop_Pct"]}\n')
        f.write(f'E{i}_T1={lv["Target1"]}\n')
        f.write(f'E{i}_T1_PCT={lv["T1_Pct"]}\n')
        f.write(f'E{i}_T2={lv["Target2"]}\n')
        f.write(f'E{i}_T2_PCT={lv["T2_Pct"]}\n')
        f.write(f'E{i}_REASONS={"|".join(reasons)}\n')
        f.write(f'E{i}_CAUTION={caution}\n')

print(f'DATA_FILE={out_path}')

# -- 기관투자자 연동 모델 (I prefix) ---------------------------------------
print("\n=== [글로벌 기관투자자 연동 모델] ===")
try:
    top5_inst = wa.screen_institutional_aligned(ind, master)
    inst_ok   = not top5_inst.empty
except Exception as e:
    print(f"  [경고] 기관연동 모델 실패: {e}")
    top5_inst = pd.DataFrame()
    inst_ok   = False

inst_docs = wa.load_institutional_docs()
levels_inst = collect_levels(top5_inst) if inst_ok and not top5_inst.empty else []
inst_weights = wa.load_institutional_sectors() if inst_ok else {}


def gen_reasons_institutional(lv: dict, weights: dict) -> list:
    reasons = []
    # 기관 섹터 이유
    for us_sec, kr_list in wa.US_TO_KR_SECTOR.items():
        if any(k in lv['Sector'] for k in kr_list):
            w = weights.get(us_sec, 0)
            if w >= 0.05:
                reasons.append(
                    f'글로벌 기관 <b>{us_sec}</b> 섹터 평균 <b>{w*100:.0f}%</b> 집중 — {lv["Sector"]} 수혜 기대'
                )
            break
    # 기존 안정 이유 재사용
    if lv['MA20'] > 0 and lv['MA60'] > 0:
        if lv['Close'] > lv['MA20'] > lv['MA60']:
            reasons.append('MA20·MA60 <b>정배열</b> — 중장기 상승추세 확립')
        elif lv['Close'] > lv['MA60']:
            reasons.append(f'현재가가 MA60({lv["MA60"]:,}원) 상회 — 중기 추세 유효')
    if lv['MA20'] > 0:
        gap = (lv['Close'] - lv['MA20']) / lv['MA20'] * 100
        if 0 <= gap <= 7:
            reasons.append(f'MA20 대비 <b>+{gap:.1f}%</b> — 과열 없는 이상적 진입 구간')
    if 45 <= lv['RSI'] <= 62:
        reasons.append(f'RSI <b>{lv["RSI"]}</b> — 과열·과매도 없는 최적 매수 구간')
    elif 62 < lv['RSI'] <= 68:
        reasons.append(f'RSI <b>{lv["RSI"]}</b> — 상승 강도 높음 (분할 매수 권장)')
    r4 = lv['R4W']
    if r4 > 0:
        reasons.append(f'4주 수익률 <b>+{r4}%</b> — 안정적 상승세')
    if lv['MACD'] > 0:
        reasons.append(f'MACD 히스토그램 <b>+{lv["MACD"]}</b> — 상승 모멘텀 지속')
    if len(reasons) < 3:
        reasons.append(f'퀀트+기관연동 종합점수 <b>{lv["Score"]}</b> — 스마트머니 섹터 + 기술적 우수')
    return reasons[:5]


with open(out_path, 'a', encoding='utf-8') as f:
    # 글로벌 기관 동향 요약 (INST prefix)
    f.write(f'INST_COUNT={len(inst_docs)}\n')
    for j, idoc in enumerate(inst_docs[:11]):
        sw = idoc.get('sector_weights', {})
        top3_sectors = '|'.join(
            f"{k}:{v*100:.0f}%"
            for k, v in sorted(sw.items(), key=lambda x: -x[1])[:3]
        )
        top3_hold = '|'.join(
            h['name'][:25] for h in idoc.get('top_holdings', [])[:3]
        )
        f.write(f'INST{j}_NAME={idoc.get("name","")}\n')
        f.write(f'INST{j}_DATE={idoc.get("filing_date","")}\n')
        f.write(f'INST{j}_PERIOD={idoc.get("period_of_report","")}\n')
        f.write(f'INST{j}_TOP3_SECTORS={top3_sectors}\n')
        f.write(f'INST{j}_TOP3_HOLD={top3_hold}\n')
        f.write(f'INST{j}_TOTAL={idoc.get("total_holdings_count",0)}\n')

    # 기관연동 한국 종목 (I prefix)
    if inst_ok:
        for i, lv in enumerate(levels_inst):
            reasons = gen_reasons_institutional(lv, inst_weights)
            caution = gen_caution_stable(lv)
            f.write(f'I{i}_NAME={lv["Name"]}\n')
            f.write(f'I{i}_CODE={lv["Code"]}\n')
            f.write(f'I{i}_MKT={lv["Market"]}\n')
            f.write(f'I{i}_SECTOR={lv["Sector"]}\n')
            f.write(f'I{i}_SCORE={lv["Score"]}\n')
            f.write(f'I{i}_CLOSE={lv["Close"]}\n')
            f.write(f'I{i}_RSI={lv["RSI"]}\n')
            f.write(f'I{i}_MACD={lv["MACD"]}\n')
            f.write(f'I{i}_VOLR={lv["VolR"]}\n')
            f.write(f'I{i}_R1W={lv["R1W"]}\n')
            f.write(f'I{i}_R4W={lv["R4W"]}\n')
            f.write(f'I{i}_R12W={lv["R12W"]}\n')
            f.write(f'I{i}_MA20={lv["MA20"]}\n')
            f.write(f'I{i}_MA60={lv["MA60"]}\n')
            f.write(f'I{i}_ATR={int(lv["ATR"])}\n')
            f.write(f'I{i}_ENTRY={lv["Entry"]}\n')
            f.write(f'I{i}_STOP={lv["StopLoss"]}\n')
            f.write(f'I{i}_STOP_PCT={lv["Stop_Pct"]}\n')
            f.write(f'I{i}_T1={lv["Target1"]}\n')
            f.write(f'I{i}_T1_PCT={lv["T1_Pct"]}\n')
            f.write(f'I{i}_T2={lv["Target2"]}\n')
            f.write(f'I{i}_T2_PCT={lv["T2_Pct"]}\n')
            f.write(f'I{i}_REASONS={"|".join(reasons)}\n')
            f.write(f'I{i}_CAUTION={caution}\n')

print(f'\n  [기관연동] 완료 — {len(levels_inst)}개 종목, {len(inst_docs)}개 기관 동향')
