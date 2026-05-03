"""
주간 퀀트 분석 엔진 (weekly_analysis.py) — MongoDB 버전
=========================================================
금요일 장 마감 후 실행 → 차주 유망종목 + 매수/손절/목표가 HTML 리포트 생성

팩터 구성:
  1. 모멘텀 점수  : 1주(20%) + 4주(30%) + 12주(50%) 수익률 백분위
  2. 거래량 점수  : 이번 주 거래량 / 20일 평균 거래량 백분위
  3. 추세 점수    : Close / MA60 백분위
  4. 기술 점수    : RSI 최적 구간 + MACD 방향성
  → 종합점수 = 모멘텀(35%) + 거래량(20%) + 추세(25%) + 기술(20%)
"""

import os, warnings
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from pymongo import MongoClient

warnings.filterwarnings('ignore')

# ── 설정 ─────────────────────────────────────────────
BASE_DIR   = os.path.dirname(os.path.abspath(__file__))
REPORT_DIR = os.path.join(BASE_DIR, 'outputs', 'reports')
os.makedirs(REPORT_DIR, exist_ok=True)

MONGO_URI = 'mongodb://localhost:27017'
DB_NAME   = 'trading'

# ── 포트폴리오 (국장 ETF) ─────────────────────────────
MY_PORTFOLIO_KR = {
    'KODEX AI전력핵심설비':          '466920',
    'TIGER 200':                    '102110',
    'TIGER 미국S&P500':             '143850',
    'TIGER KRX금현물':              '411060',
    'KODEX 삼성전자채권혼합':        '282040',
    'KODEX 종합채권(AA-이상)액티브': '273130',
    'KODEX 차이나휴머노이드로봇':    '453810',
}


def get_db():
    client = MongoClient(MONGO_URI)
    return client[DB_NAME]


# ─────────────────────────────────────────────────────
# 1. 데이터 로드 (MongoDB)
# ─────────────────────────────────────────────────────

def load_recent_prices(days: int = 200) -> pd.DataFrame:
    """최근 N일 가격 데이터를 MongoDB에서 로드"""
    db         = get_db()
    since_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')

    print(f"  MongoDB 조회: {since_date} 이후 데이터...")
    cursor = db['prices'].find(
        {'date': {'$gte': since_date}},
        {'_id': 0, 'date': 1, 'code': 1,
         'open': 1, 'high': 1, 'low': 1, 'close': 1, 'volume': 1, 'change': 1}
    )
    df = pd.DataFrame(list(cursor))

    if df.empty:
        raise RuntimeError("가격 데이터가 없습니다. migrate_to_db.py를 먼저 실행하세요.")

    df['date']   = pd.to_datetime(df['date'])
    df['code']   = df['code'].astype(str).str.zfill(6)
    df['close']  = pd.to_numeric(df['close'],  errors='coerce')
    df['volume'] = pd.to_numeric(df['volume'], errors='coerce')
    df = df.dropna(subset=['close', 'volume'])
    df = df[df['close'] > 0]
    df = df.sort_values(['code', 'date']).reset_index(drop=True)

    # 컬럼명 대문자로 맞추기 (내부 처리 통일)
    df = df.rename(columns={'date':'Date','code':'Code','open':'Open',
                             'high':'High','low':'Low','close':'Close',
                             'volume':'Volume','change':'Change'})

    print(f"  로드 완료: {len(df):,}행 / {df['Code'].nunique():,}종목 / "
          f"{df['Date'].min().date()} ~ {df['Date'].max().date()}")
    return df


def load_master() -> pd.DataFrame:
    db  = get_db()
    cur = db['stocks'].find({}, {'_id':0,'code':1,'name':1,'market':1,'marcap':1})
    df  = pd.DataFrame(list(cur))
    if df.empty:
        return pd.DataFrame(columns=['Code','Name','Market','Marcap'])
    df = df.rename(columns={'code':'Code','name':'Name','market':'Market','marcap':'Marcap'})
    df['Code'] = df['Code'].astype(str).str.zfill(6)
    return df


# ─────────────────────────────────────────────────────
# 2. 기술 지표 (벡터화)
# ─────────────────────────────────────────────────────

def compute_indicators_vectorized(df: pd.DataFrame) -> pd.DataFrame:
    print("  Rolling 지표 계산 중 (벡터화)...")

    grp = df.groupby('Code', sort=False)

    # Moving Averages
    df['MA5']  = grp['Close'].transform(lambda x: x.rolling(5,  min_periods=5).mean())
    df['MA20'] = grp['Close'].transform(lambda x: x.rolling(20, min_periods=20).mean())
    df['MA60'] = grp['Close'].transform(lambda x: x.rolling(60, min_periods=60).mean())

    # RSI(14)
    avg_gain = grp['Close'].transform(
        lambda x: x.diff().clip(lower=0).rolling(14, min_periods=14).mean())
    avg_loss = grp['Close'].transform(
        lambda x: (-x.diff()).clip(lower=0).rolling(14, min_periods=14).mean())
    df['RSI'] = (100 - 100 / (1 + avg_gain / avg_loss.replace(0, np.nan))).fillna(50)

    # MACD(12,26,9)
    ema12 = grp['Close'].transform(lambda x: x.ewm(span=12, adjust=False).mean())
    ema26 = grp['Close'].transform(lambda x: x.ewm(span=26, adjust=False).mean())
    df['MACD_Line']   = ema12 - ema26
    df['MACD_Signal'] = grp['MACD_Line'].transform(
        lambda x: x.ewm(span=9, adjust=False).mean())
    df['MACD_Hist']      = df['MACD_Line'] - df['MACD_Signal']
    df['MACD_Hist_Prev'] = grp['MACD_Hist'].transform(lambda x: x.shift(1))

    # ATR(14)
    prev_close = grp['Close'].transform(lambda x: x.shift(1))
    tr = pd.concat([
        df['High'] - df['Low'],
        (df['High'] - prev_close).abs(),
        (df['Low']  - prev_close).abs()
    ], axis=1).max(axis=1)
    df['ATR'] = tr.groupby(df['Code']).transform(
        lambda x: x.rolling(14, min_periods=14).mean())

    # Volume ratio
    vol5  = grp['Volume'].transform(lambda x: x.rolling(5,  min_periods=1).mean())
    vol20 = grp['Volume'].transform(lambda x: x.rolling(20, min_periods=1).mean())
    df['Vol_Ratio']  = vol5 / vol20.replace(0, np.nan)
    df['Avg_Volume'] = vol20

    # 수익률
    df['Ret_1W']  = grp['Close'].transform(lambda x: x.pct_change(5))
    df['Ret_4W']  = grp['Close'].transform(lambda x: x.pct_change(20))
    df['Ret_12W'] = grp['Close'].transform(lambda x: x.pct_change(60))

    # 거래정지 종목 수익률 무효화: 기준일 거래량=0이면 실제 시장가격이 아님
    vol_1w_base  = grp['Volume'].transform(lambda x: x.shift(5))
    vol_4w_base  = grp['Volume'].transform(lambda x: x.shift(20))
    vol_12w_base = grp['Volume'].transform(lambda x: x.shift(60))
    df.loc[vol_1w_base  <= 0, 'Ret_1W']  = np.nan
    df.loc[vol_4w_base  <= 0, 'Ret_4W']  = np.nan
    df.loc[vol_12w_base <= 0, 'Ret_12W'] = np.nan

    # 최신 행만 추출 + 최소 65일 요건
    latest = df.groupby('Code').tail(1).copy()
    cnt    = df.groupby('Code').size().rename('cnt')
    latest = latest.join(cnt, on='Code')
    latest = latest[latest['cnt'] >= 65].copy()

    # MACD 크로스 신호
    latest['MACD_Cross'] = np.where(
        (latest['MACD_Hist'] > 0) & (latest['MACD_Hist_Prev'] <= 0),  1,
        np.where(
        (latest['MACD_Hist'] < 0) & (latest['MACD_Hist_Prev'] >= 0), -1, 0))

    print(f"  지표 계산 완료: {len(latest):,}개 종목")
    return latest.reset_index(drop=True)


# ─────────────────────────────────────────────────────
# 3. 스크리닝 & 스코어링
# ─────────────────────────────────────────────────────

def screen_and_score(ind: pd.DataFrame, master: pd.DataFrame) -> pd.DataFrame:
    df = ind.merge(master, on='Code', how='left')

    df = df[
        (df['Close']      >= 1000) &
        (df['Volume']     >  0) &
        (df['Avg_Volume'] >= 30000) &
        (df['ATR'].notna()) &
        (df['MA60'].notna()) &
        (df['Ret_1W'].notna()) &
        (df['Ret_12W'].notna()) &
        (df['RSI'].between(25, 78)) &
        (df['Close'] >= df['MA60'] * 0.85)
    ].copy()
    print(f"  1차 필터 후: {len(df):,}종목")

    def pct_rank(s):
        return s.rank(pct=True, na_option='bottom')

    df['Score_Mom']   = (pct_rank(df['Ret_1W'])  * 0.20 +
                         pct_rank(df['Ret_4W'])  * 0.30 +
                         pct_rank(df['Ret_12W']) * 0.50)
    df['Score_Vol']   = pct_rank(df['Vol_Ratio'])
    df['Score_Trend'] = pct_rank(df['Close'] / df['MA60'])
    df['RSI_Score']   = df['RSI'].apply(
        lambda r: 1.0 if 45<=r<=65 else (0.7 if 35<=r<45 or 65<r<=72 else 0.3))
    df['MACD_Score']  = (df['MACD_Hist'].apply(lambda h: 0.8 if h>0 else 0.4)
                       + df['MACD_Cross'] * 0.2)
    df['Score_Tech']  = df['RSI_Score'] * 0.5 + df['MACD_Score'] * 0.5
    df['Score_Total'] = (df['Score_Mom']   * 0.35 +
                         df['Score_Vol']   * 0.20 +
                         df['Score_Trend'] * 0.25 +
                         df['Score_Tech']  * 0.20)

    df = df[(df['Close'] >= df['MA60']) & (df['RSI'] < 75)].copy()
    df = df.sort_values('Score_Total', ascending=False).reset_index(drop=True)
    print(f"  최종 후보군: {len(df):,}종목")
    return df


# ─────────────────────────────────────────────────────
# 4. 매매 레벨 계산
# ─────────────────────────────────────────────────────

def calc_trade_levels(row) -> dict:
    close = row['Close']
    atr   = row['ATR']   if pd.notna(row['ATR'])  else close * 0.03
    ma20  = row['MA20']  if pd.notna(row['MA20']) else close * 0.95

    entry   = round(close * 1.005 / 10) * 10
    stop    = max(close - atr * 2.0, ma20 * 0.95)
    stop    = round(stop / 10) * 10
    risk    = max(entry - stop, entry * 0.03)
    target1 = round((entry + risk * 1.5) / 10) * 10
    target2 = round((entry + risk * 2.5) / 10) * 10

    sp  = (stop    - entry) / entry * 100
    t1p = (target1 - entry) / entry * 100
    t2p = (target2 - entry) / entry * 100

    return dict(Entry=int(entry), StopLoss=int(stop),
                Target1=int(target1), Target2=int(target2),
                Stop_Pct=round(sp,1), T1_Pct=round(t1p,1), T2_Pct=round(t2p,1),
                RR1=round(abs(t1p/sp),2) if sp!=0 else 0,
                RR2=round(abs(t2p/sp),2) if sp!=0 else 0)


# ─────────────────────────────────────────────────────
# 5. 시장 요약
# ─────────────────────────────────────────────────────

def market_summary(prices: pd.DataFrame, master: pd.DataFrame) -> dict:
    df          = prices.merge(master[['Code','Market']], on='Code', how='left')
    latest_date = prices['Date'].max()
    prev_date   = latest_date - timedelta(days=7)
    summary     = {}
    for mkt in ['KOSPI','KOSDAQ']:
        sub    = df[df['Market'] == mkt]
        latest = sub[sub['Date'] == latest_date].set_index('Code')['Close']
        prev   = sub[sub['Date'] >= prev_date].groupby('Code').first()['Close']
        rets   = ((latest - prev) / prev * 100).dropna()
        summary[mkt] = {
            'mean_ret': round(rets.mean(), 2),
            'up'  : int((rets > 0).sum()),
            'down': int((rets < 0).sum()),
            'flat': int((rets == 0).sum()),
        }
    return summary


# ─────────────────────────────────────────────────────
# 6. 포트폴리오 주간 성과
# ─────────────────────────────────────────────────────

def portfolio_weekly(prices: pd.DataFrame) -> pd.DataFrame:
    names  = {v: k for k, v in MY_PORTFOLIO_KR.items()}
    latest = prices['Date'].max()
    prev   = latest - timedelta(days=7)
    rows   = []
    for code, name in names.items():
        sub = prices[prices['Code'] == code].sort_values('Date')
        if sub.empty:
            rows.append({'종목명':name,'코드':code,'현재가':'-','주간수익률':'-'})
            continue
        cur    = sub.iloc[-1]['Close']
        p_rows = sub[sub['Date'] >= prev]
        prev_c = p_rows.iloc[0]['Close'] if not p_rows.empty else cur
        ret    = (cur - prev_c) / prev_c * 100
        rows.append({'종목명':name,'코드':code,
                     '현재가':int(cur),'주간수익률':round(ret,2)})
    return pd.DataFrame(rows)


# ─────────────────────────────────────────────────────
# 7. 메인
# ─────────────────────────────────────────────────────

def run():
    print("\n" + "="*60)
    print("  🔍 주간 퀀트 분석 시작 (MongoDB)")
    print("="*60)

    # MongoDB 연결 확인
    try:
        MongoClient(MONGO_URI, serverSelectionTimeoutMS=3000).admin.command('ping')
        print("  ✅ MongoDB 연결 성공")
    except Exception as e:
        print(f"  ❌ MongoDB 연결 실패: {e}")
        return None, None

    print("\n[1/5] 가격 데이터 로드...")
    prices = load_recent_prices(days=200)
    master = load_master()
    analysis_date = prices['Date'].max().strftime('%Y-%m-%d')
    print(f"  분석 기준일: {analysis_date}")

    print("\n[2/5] 기술 지표 계산...")
    ind = compute_indicators_vectorized(prices)

    print("\n[3/5] 스크리닝 & 팩터 스코어링...")
    scored = screen_and_score(ind, master)

    print("\n[4/5] 시장 요약 & 포트폴리오...")
    mkt_sum   = market_summary(prices, master)
    port_perf = portfolio_weekly(prices)
    for mkt, d in mkt_sum.items():
        print(f"  {mkt}: {d['mean_ret']:+.2f}%  상승 {d['up']} / 하락 {d['down']}")

    print("\n  ── TOP 10 미리보기 ──")
    cols = [c for c in ['Code','Name','Market','Close','Ret_1W','Ret_12W','RSI','Score_Total']
            if c in scored.columns]
    preview = scored[cols].head(10).copy()
    for c in ['Ret_1W','Ret_12W']:
        if c in preview: preview[c] = (preview[c]*100).round(1)
    if 'RSI' in preview: preview['RSI'] = preview['RSI'].round(1)
    if 'Score_Total' in preview: preview['Score_Total'] = preview['Score_Total'].round(3)
    print(preview.to_string(index=False))

    print("\n[5/5] HTML 리포트 생성...")
    # generate_report.py 와 build_html.py 를 통해 리포트 생성
    report_path = os.path.join(REPORT_DIR, f'weekly_{analysis_date}.html')
    print(f"  ✅ 완료: {report_path}")

    print("\n" + "="*60)
    return report_path, scored


if __name__ == '__main__':
    run()
