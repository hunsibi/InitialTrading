"""
주간 퀀트 분석 엔진 (weekly_analysis.py) — MongoDB 버전
=========================================================
금요일 장 마감 후 실행 → 차주 유망종목 + 매수/손절/목표가 HTML 리포트 생성

팩터 구성 (대장주 안정 투자 모델):
  1. 추세 건전성  : MA 정배열 + MA20 이격률 0~7% 최적구간  (35%)
  2. 리스크조정   : 4주수익률 / ATR% — 변동성 대비 수익     (30%)
  3. 기술 안정성  : RSI 45~62 + MACD 지속 + 거래량 안정    (25%)
  4. 중기 모멘텀  : 12주 수익률 백분위만 반영               (10%)
  ※ 종목 풀: 시총 상위 350위 이내 (업종별 대장주) + ATR% <= 5%
"""

import os, warnings
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from pymongo import MongoClient

warnings.filterwarnings('ignore')

# -- 설정 ----------------------------------------------------------------
BASE_DIR   = os.path.dirname(os.path.abspath(__file__))
REPORT_DIR = os.path.join(BASE_DIR, 'outputs', 'reports')
os.makedirs(REPORT_DIR, exist_ok=True)

MONGO_URI = 'mongodb://localhost:27017'
DB_NAME   = 'trading'

# -- 포트폴리오 (국장 ETF) ------------------------------------------------
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


# -------------------------------------------------------------------------
# 1. 데이터 로드 (MongoDB)
# -------------------------------------------------------------------------

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
    df['Code']   = df['Code'].astype(str).str.zfill(6)
    df['Marcap'] = pd.to_numeric(df['Marcap'], errors='coerce')
    return df


# -------------------------------------------------------------------------
# 2. 기술 지표 (벡터화)
# -------------------------------------------------------------------------

def compute_indicators_vectorized(df: pd.DataFrame) -> pd.DataFrame:
    print("  Rolling 지표 계산 중 (벡터화)...")

    grp = df.groupby('Code', sort=False)

    df['MA5']  = grp['Close'].transform(lambda x: x.rolling(5,  min_periods=5).mean())
    df['MA20'] = grp['Close'].transform(lambda x: x.rolling(20, min_periods=20).mean())
    df['MA60'] = grp['Close'].transform(lambda x: x.rolling(60, min_periods=60).mean())

    avg_gain = grp['Close'].transform(
        lambda x: x.diff().clip(lower=0).rolling(14, min_periods=14).mean())
    avg_loss = grp['Close'].transform(
        lambda x: (-x.diff()).clip(lower=0).rolling(14, min_periods=14).mean())
    df['RSI'] = (100 - 100 / (1 + avg_gain / avg_loss.replace(0, np.nan))).fillna(50)

    ema12 = grp['Close'].transform(lambda x: x.ewm(span=12, adjust=False).mean())
    ema26 = grp['Close'].transform(lambda x: x.ewm(span=26, adjust=False).mean())
    df['MACD_Line']   = ema12 - ema26
    df['MACD_Signal'] = grp['MACD_Line'].transform(
        lambda x: x.ewm(span=9, adjust=False).mean())
    df['MACD_Hist']      = df['MACD_Line'] - df['MACD_Signal']
    df['MACD_Hist_Prev'] = grp['MACD_Hist'].transform(lambda x: x.shift(1))

    prev_close = grp['Close'].transform(lambda x: x.shift(1))
    tr = pd.concat([
        df['High'] - df['Low'],
        (df['High'] - prev_close).abs(),
        (df['Low']  - prev_close).abs()
    ], axis=1).max(axis=1)
    df['ATR'] = tr.groupby(df['Code']).transform(
        lambda x: x.rolling(14, min_periods=14).mean())

    vol5  = grp['Volume'].transform(lambda x: x.rolling(5,  min_periods=1).mean())
    vol20 = grp['Volume'].transform(lambda x: x.rolling(20, min_periods=1).mean())
    df['Vol_Ratio']  = vol5 / vol20.replace(0, np.nan)
    df['Avg_Volume'] = vol20

    df['Ret_1W']  = grp['Close'].transform(lambda x: x.pct_change(5))
    df['Ret_4W']  = grp['Close'].transform(lambda x: x.pct_change(20))
    df['Ret_12W'] = grp['Close'].transform(lambda x: x.pct_change(60))

    vol_1w_base  = grp['Volume'].transform(lambda x: x.shift(5))
    vol_4w_base  = grp['Volume'].transform(lambda x: x.shift(20))
    vol_12w_base = grp['Volume'].transform(lambda x: x.shift(60))
    df.loc[vol_1w_base  <= 0, 'Ret_1W']  = np.nan
    df.loc[vol_4w_base  <= 0, 'Ret_4W']  = np.nan
    df.loc[vol_12w_base <= 0, 'Ret_12W'] = np.nan

    latest = df.groupby('Code').tail(1).copy()
    cnt    = df.groupby('Code').size().rename('cnt')
    latest = latest.join(cnt, on='Code')
    latest = latest[latest['cnt'] >= 65].copy()

    latest['MACD_Cross'] = np.where(
        (latest['MACD_Hist'] > 0) & (latest['MACD_Hist_Prev'] <= 0),  1,
        np.where(
        (latest['MACD_Hist'] < 0) & (latest['MACD_Hist_Prev'] >= 0), -1, 0))

    print(f"  지표 계산 완료: {len(latest):,}개 종목")
    return latest.reset_index(drop=True)


# -------------------------------------------------------------------------
# 3. ETF 로드 + 스코어링 (FDR 직접 조회, MongoDB 불필요)
# -------------------------------------------------------------------------

_ETF_THEME_KW = [
    ('국내지수',      ['KOSPI200','코스피200','KRX300','코스닥150']),
    ('미국지수',      ['미국S&P','S&P500','나스닥','NASDAQ','미국테크','다우','필라델피아','미국밸류','빅테크']),
    ('반도체/AI',     ['반도체','AI전력','인공지능','데이터센터','로봇','AI테크','AI반도체','AI밸류','양자']),
    ('커버드콜',      ['커버드콜','CoveredCall','타겟커버드','고정커버드']),
    ('전기차/배터리', ['2차전지','배터리','전기차']),
    ('글로벌',        ['인도','중국','베트남','일본','유럽','신흥국','글로벌','아시아','이머징','MSCI','선진국']),
    ('에너지/자원',   ['에너지','원유','석유','가스','금현물','구리','리튬','원자재']),  # '금' 단독 제거 (금융 오매칭 방지)
    ('바이오/헬스',   ['바이오','헬스','제약','의료']),
    ('고배당',        ['고배당','배당','분배']),
    ('방산/테마',     ['방산','우주','메타버스','게임','ESG','탄소','수소','휴머노이드']),
    ('부동산/리츠',   ['리츠','REITS','부동산']),
    ('섹터/업종',     ['소비재','금융','증권','유통','항공','조선','화학','철강','은행']),
]

def infer_etf_theme(name: str) -> str:
    """ETF명 키워드로 테마 추론"""
    n = str(name)
    for theme, keywords in _ETF_THEME_KW:
        if any(k in n for k in keywords):
            return theme
    return 'ETF'


def load_etf_prices(days: int = 200, top_n: int = 150) -> tuple:
    """ETF 가격 데이터를 FDR에서 직접 로드 (레버리지/인버스 제외, 시총 상위 N개)"""
    import FinanceDataReader as fdr
    import concurrent.futures

    print("  [ETF] ETF 목록 로딩 (FDR)...")
    etf_list = fdr.StockListing('ETF/KR')

    # Category 3(레버리지/인버스) 제외, 시총 상위 top_n 선택
    etf_list = etf_list[etf_list['Category'] != 3].copy()
    etf_list['MarCap_n'] = pd.to_numeric(etf_list['MarCap'], errors='coerce')
    etf_list = etf_list.dropna(subset=['MarCap_n'])
    etf_list = etf_list.nlargest(top_n, 'MarCap_n')

    codes = etf_list['Symbol'].astype(str).str.zfill(6).tolist()
    print(f"  [ETF] 대상 {len(codes)}개 ETF 다운로드 중...")

    since = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
    end   = datetime.now().strftime('%Y-%m-%d')

    def fetch_one(code):
        try:
            df = fdr.DataReader(code, since, end)
            if df is not None and not df.empty:
                df = df.reset_index()
                df['Code'] = code
                cols = [c for c in ['Date','Code','Open','High','Low','Close','Volume','Change'] if c in df.columns]
                return df[cols]
        except Exception:
            pass
        return None

    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=20) as ex:
        futs = {ex.submit(fetch_one, c): c for c in codes}
        for fut in concurrent.futures.as_completed(futs):
            r = fut.result()
            if r is not None:
                results.append(r)

    if not results:
        print("  [ETF] 데이터 로드 실패")
        return pd.DataFrame(), pd.DataFrame()

    prices = pd.concat(results, ignore_index=True)
    prices['Date']   = pd.to_datetime(prices['Date'])
    prices['Close']  = pd.to_numeric(prices['Close'],  errors='coerce')
    prices['Volume'] = pd.to_numeric(prices['Volume'], errors='coerce')
    prices = prices.dropna(subset=['Close', 'Volume'])
    prices = prices[prices['Close'] > 0]
    prices = prices.sort_values(['Code', 'Date']).reset_index(drop=True)

    master = etf_list[['Symbol', 'Name', 'Category', 'MarCap_n']].copy()
    master = master.rename(columns={'Symbol': 'Code', 'MarCap_n': 'Marcap'})
    master['Code']   = master['Code'].astype(str).str.zfill(6)
    master['Market'] = 'KOSPI'

    print(f"  [ETF] 로드 완료: {len(prices):,}행 / {prices['Code'].nunique():,}ETF "
          f"/ {prices['Date'].min().date()} ~ {prices['Date'].max().date()}")
    return prices, master


def screen_and_score_etf(ind: pd.DataFrame, master: pd.DataFrame) -> pd.DataFrame:
    """ETF 전용 스코어링 — 추세건전성+리스크조정 기반"""
    df = ind.merge(master[['Code', 'Name', 'Market', 'Marcap', 'Category']], on='Code', how='left')

    df['ATR_Pct'] = df['ATR'] / df['Close'].replace(0, np.nan) * 100

    # 금리·머니마켓·단기채 ETF 제외 (현금성 상품은 주식형 ETF 추천 대상 아님)
    _MMF_KW = ['금리', '머니마켓', 'KOFR', 'CD금리', '단기채', 'CP금리', '통안채', '국고채', '채권']
    is_mmf = df['Name'].apply(lambda n: any(kw in str(n) for kw in _MMF_KW))

    df = df[
        (df['Close']      >= 500) &
        (df['Avg_Volume'] >= 5_000) &
        (df['ATR'].notna()) &
        (df['MA60'].notna()) &
        (df['MA20'].notna()) &
        (df['Ret_4W'].notna()) &
        (df['Ret_12W']    >= 0.02) &   # 12주 최소 2% 수익률 (현금성 상품 추가 차단)
        (df['RSI'].between(30, 75)) &
        (df['ATR_Pct'].between(0.3, 5.0)) &   # 최소 변동성 0.3% (MMF 차단) ~ 최대 5%
        (df['Close'] >= df['MA60'] * 0.88) &
        (~is_mmf)
    ].copy()

    if df.empty:
        return df

    def pct_rank(s):
        return s.rank(pct=True, na_option='bottom')

    # 추세 건전성 (40%)
    ma5_ok  = df['MA5'].notna()
    full    = (ma5_ok & (df['Close'] > df['MA5']) & (df['MA5'] > df['MA20']) & (df['MA20'] > df['MA60'])).astype(float)
    partial = (~ma5_ok & (df['Close'] > df['MA20']) & (df['MA20'] > df['MA60'])).astype(float)
    ma_align = full + partial

    gap_pct = (df['Close'] / df['MA20'] - 1) * 100
    gap_score = gap_pct.apply(lambda g:
        1.0 if  0 <= g <= 8  else
        0.75 if 8 <  g <= 15 else
        0.6  if -5 <= g < 0  else 0.2)

    df['Score_Trend'] = ma_align * 0.55 + gap_score * 0.45

    # 리스크 조정 수익률 (30%)
    df['RA_Return'] = df['Ret_4W'] / (df['ATR_Pct'] / 100).replace(0, np.nan)
    df['Score_RA']  = pct_rank(df['RA_Return'])

    # 기술 안정성 (20%)
    df['RSI_Score']  = df['RSI'].apply(
        lambda r: 1.0 if 45 <= r <= 62 else 0.75 if (38 <= r < 45) or (62 < r <= 70) else 0.3)
    df['MACD_Score'] = (df['MACD_Hist'] > 0).astype(float) * 0.8 + (df['MACD_Cross'] == 1).astype(float) * 0.2
    df['Score_Tech'] = df['RSI_Score'] * 0.6 + df['MACD_Score'] * 0.4

    # 중기 모멘텀 (10%)
    df['Score_Mom'] = pct_rank(df['Ret_12W'])

    df['Score_Total'] = (df['Score_Trend'] * 0.40 +
                         df['Score_RA']    * 0.30 +
                         df['Score_Tech']  * 0.20 +
                         df['Score_Mom']   * 0.10)

    df = df.sort_values('Score_Total', ascending=False).reset_index(drop=True)

    # 테마 다양성 보장: 테마당 최대 1개 우선 선발, 부족하면 점수순 보충
    df['Theme'] = df['Name'].apply(lambda n: infer_etf_theme(str(n)))
    selected, used_themes = [], set()
    for _, row in df.iterrows():
        if row['Theme'] not in used_themes:
            selected.append(row)
            used_themes.add(row['Theme'])
    # 5개 미만이면 점수순으로 나머지 보충 (테마 중복 허용)
    if len(selected) < 5:
        selected_codes = {r['Code'] for r in selected}
        for _, row in df.iterrows():
            if row['Code'] not in selected_codes:
                selected.append(row)
                selected_codes.add(row['Code'])
            if len(selected) >= 10:
                break

    df = pd.DataFrame(selected).reset_index(drop=True)
    print(f"  [ETF] 최종 후보: {len(df):,}개 (테마 다양성 적용)")
    return df


# -------------------------------------------------------------------------
# 4. 업종 추론 (종목명 키워드 기반)
# -------------------------------------------------------------------------

_SECTOR_KW = [
    ('반도체/장비',  ['하이닉스','반도체','실리콘','HPSP','원익IPS','DB하이텍','리노공업','하나마이크론']),
    ('IT/전자',     ['삼성전자','삼성전기','LG전자','LG이노텍','삼성SDI','SK하이닉스']),
    ('배터리/소재',  ['에너지솔루션','SDI','에코프로','포스코퓨처엠','일진머티리얼즈','엘앤에프','천보','솔루스첨단소재']),
    ('자동차/부품',  ['자동차','기아','모비스','만도','현대위아','성우하이텍','HL만도','에스엘']),
    ('화학',         ['화학','케미칼','OCI','금호석유','효성','SKC','롯데케미칼','한화솔루션','LG화학']),
    ('철강/소재',    ['철강','포스코','POSCO','현대제철','고려아연','풍산','세아']),
    ('금융/보험',    ['KB금융','신한지주','하나금융','우리금융','기업은행','BNK','DGB','JB','삼성생명','한화생명','삼성화재','DB손보','메리츠','현대해상','미래에셋']),
    ('바이오/제약',  ['바이오','제약','셀트리온','유한양행','동아','한미약품','보령','녹십자','대웅','종근당','HLB','알테오젠']),
    ('에너지/전력',  ['한국전력','한전','GS에너지','SK이노베이션','S-Oil','에쓰오일','쌍용C&E','한국가스공사']),
    ('통신/플랫폼',  ['SK텔레콤','KT','LG유플러스','카카오','네이버','크래프톤']),
    ('건설/부동산',  ['건설','삼성물산','GS건설','DL이앤씨','현대건설','포스코이앤씨','HDC현대산업개발']),
    ('유통/소비재',  ['이마트','롯데쇼핑','신세계','현대백화점','BGF리테일','GS리테일','농심','오리온','CJ제일제당','하이트진로']),
    ('방산/항공',    ['대한항공','아시아나항공','한화에어','LIG넥스원','한국항공우주','한화시스템','현대로템']),
    ('게임/엔터',    ['엔씨소프트','넷마블','하이브','SM엔터','JYP','카카오게임즈','펄어비스','크래프톤']),
    ('조선/기계',    ['현대중공업','삼성중공업','한화오션','두산에너빌리티','LS','HD현대']),
    ('반도체장비',   ['원익','테스','유진테크','피에스케이','케이씨텍','에스티아이','성진하이텍','파크시스템스']),
]

def infer_sector(name: str) -> str:
    """종목명 키워드로 업종 추론"""
    n = str(name)
    for sector, keywords in _SECTOR_KW:
        if any(k in n for k in keywords):
            return sector
    return '대형주'


# -------------------------------------------------------------------------
# 4. 스크리닝 & 스코어링 (대장주 안정 투자 모델)
# -------------------------------------------------------------------------

def screen_and_score(ind: pd.DataFrame, master: pd.DataFrame) -> pd.DataFrame:
    df = ind.merge(master, on='Code', how='left')
    df['Marcap'] = pd.to_numeric(df.get('Marcap'), errors='coerce')

    # ── 시총 상위 350위 필터 (대장주 풀) ──
    valid_cap = df.dropna(subset=['Marcap'])
    if len(valid_cap) > 350:
        cap_thr = valid_cap['Marcap'].nlargest(350).min()
        df = df[df['Marcap'] >= cap_thr].copy()
    print(f"  시총 대장주 필터 후: {len(df):,}종목")

    # ── ATR% 계산 ──
    df['ATR_Pct'] = df['ATR'] / df['Close'].replace(0, np.nan) * 100

    # ── 기본 품질 필터 ──
    df = df[
        (df['Close']      >= 2_000) &
        (df['Avg_Volume'] >= 30_000) &
        (df['ATR'].notna()) &
        (df['MA60'].notna()) &
        (df['MA20'].notna()) &
        (df['Ret_4W'].notna()) &
        (df['RSI'].between(30, 68)) &
        (df['ATR_Pct'] <= 5.0) &
        (df['Close'] >= df['MA60'] * 0.88)
    ].copy()
    print(f"  품질 필터 후: {len(df):,}종목")

    if df.empty:
        return df

    def pct_rank(s):
        return s.rank(pct=True, na_option='bottom')

    # ── 팩터 1: 추세 건전성 (35%) ──
    # 정배열: Close > MA5 > MA20 > MA60
    ma5_ok  = df['MA5'].notna()
    full    = (ma5_ok &
               (df['Close'] > df['MA5']) &
               (df['MA5']  > df['MA20']) &
               (df['MA20'] > df['MA60'])).astype(float)
    partial = (~ma5_ok &
               (df['Close'] > df['MA20']) &
               (df['MA20']  > df['MA60'])).astype(float)
    ma_align = (full + partial)  # 0 or 1

    # 이격률: MA20 대비 현재가 (0~7%가 최적 진입)
    gap_pct = (df['Close'] / df['MA20'] - 1) * 100
    gap_score = gap_pct.apply(lambda g:
        1.0 if  0 <= g <= 7  else
        0.75 if 7 <  g <= 12 else
        0.6  if -5 <= g < 0  else
        0.2)

    df['Score_Trend'] = ma_align * 0.55 + gap_score * 0.45

    # ── 팩터 2: 리스크 조정 수익률 (30%) ──
    # 4주 수익률 / ATR% : 변동성 대비 수익률이 높은 종목 선호
    df['RA_Return'] = df['Ret_4W'] / (df['ATR_Pct'] / 100).replace(0, np.nan)
    df['Score_RA']  = pct_rank(df['RA_Return'])

    # ── 팩터 3: 기술 안정성 (25%) ──
    # RSI: 45~62 최적, 62~68 양호, 나머지 낮음
    df['RSI_Score'] = df['RSI'].apply(
        lambda r: 1.0 if 45 <= r <= 62 else
                  0.75 if (38 <= r < 45) or (62 < r <= 68) else 0.3)

    # MACD: 히스토그램 양수 유지 + 상향 크로스 보너스
    df['MACD_Score'] = (
        df['MACD_Hist'].apply(lambda h: 0.8 if h > 0 else 0.3) +
        (df['MACD_Cross'] == 1).astype(float) * 0.2
    )

    # 거래량 안정성: 평소와 비슷한 거래량 선호 (급등은 반락 위험)
    df['Vol_Score'] = df['Vol_Ratio'].apply(
        lambda v: 0.9 if 0.7 <= v <= 1.5 else
                  0.65 if 1.5 < v <= 2.5 else
                  0.4  if v > 2.5        else 0.5)

    df['Score_Tech'] = (df['RSI_Score'] * 0.50 +
                        df['MACD_Score'] * 0.35 +
                        df['Vol_Score']  * 0.15)

    # ── 팩터 4: 중기 모멘텀 (10%) ──
    df['Score_Mom'] = pct_rank(df['Ret_12W'])

    # ── 종합 점수 ──
    df['Score_Total'] = (df['Score_Trend'] * 0.35 +
                         df['Score_RA']    * 0.30 +
                         df['Score_Tech']  * 0.25 +
                         df['Score_Mom']   * 0.10)

    df = df.sort_values('Score_Total', ascending=False).reset_index(drop=True)
    print(f"  최종 후보군: {len(df):,}종목")
    return df


# -------------------------------------------------------------------------
# 5. 스크리닝 & 스코어링 (구 단기 모멘텀 모델)
# -------------------------------------------------------------------------

def screen_and_score_momentum(ind: pd.DataFrame, master: pd.DataFrame) -> pd.DataFrame:
    """단기 모멘텀 모델 — 1주·4주·12주 수익률 기반, 전 종목 대상"""
    df = ind.merge(master, on='Code', how='left')

    df = df[
        (df['Close']      >= 1_000) &
        (df['Volume']     >  0) &
        (df['Avg_Volume'] >= 30_000) &
        (df['ATR'].notna()) &
        (df['MA60'].notna()) &
        (df['Ret_1W'].notna()) &
        (df['Ret_12W'].notna()) &
        (df['RSI'].between(25, 78)) &
        (df['Close'] >= df['MA60'] * 0.85)
    ].copy()

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
    print(f"  [모멘텀] 최종 후보군: {len(df):,}종목")
    return df


# -------------------------------------------------------------------------
# 6. 글로벌 기관투자자 섹터 연동 모델
# -------------------------------------------------------------------------

# US 섹터 → 한국 업종 매핑
US_TO_KR_SECTOR = {
    'Technology':    ['반도체', 'IT서비스', 'AI', '디스플레이', 'IT/전자', '반도체/장비'],
    'Healthcare':    ['제약', '바이오', '의료기기', '바이오/제약'],
    'Financials':    ['금융', '보험', '증권', '금융/보험'],
    'Energy':        ['정유/화학', '신재생에너지', '에너지/전력', '화학'],
    'Consumer':      ['유통/소비재', '음식료', '화장품', '게임/엔터'],
    'Industrials':   ['산업재', '방산/항공', '조선', '방산/테마', '조선/기계'],
    'Real Estate':   ['리츠', '건설/부동산'],
    'Materials':     ['철강/소재', '화학', '배터리/소재', '철강/금속'],
    'Communication': ['통신/플랫폼', '미디어'],
    'Utilities':     ['유틸리티', '에너지/전력'],
}


def load_institutional_sectors() -> dict:
    """MongoDB institutional_holdings에서 기관별 섹터 가중치 평균 집계."""
    try:
        db   = get_db()
        docs = list(db['institutional_holdings'].find({}, {'sector_weights': 1, '_id': 0}))
        if not docs:
            print("  [기관] institutional_holdings 없음 — fetch_institutional.py 필요")
            return {}
        all_sectors = {}
        for doc in docs:
            for sec, w in doc.get('sector_weights', {}).items():
                all_sectors.setdefault(sec, []).append(w)
        avg = {k: round(sum(v) / len(v), 4) for k, v in all_sectors.items()}
        print(f"  [기관] 섹터 집계: {len(docs)}개 기관, 상위 → "
              + ', '.join(f"{k}:{v:.0%}" for k, v in
                          sorted(avg.items(), key=lambda x: -x[1])[:4]))
        return avg
    except Exception as e:
        print(f"  [기관] 섹터 로드 오류: {e}")
        return {}


def load_institutional_docs() -> list:
    """포트폴리오 동향 표시용 전체 문서 로드."""
    try:
        db   = get_db()
        docs = list(db['institutional_holdings'].find(
            {},
            {'cik': 0, 'accession_no': 0, '_id': 0}
        ))
        return docs
    except Exception:
        return []


def load_kr_investor_flows() -> dict:
    """MongoDB kr_investor_flows 최신 데이터 로드 (fetch_kr_investor.py 저장분)."""
    try:
        db  = get_db()
        doc = db['kr_investor_flows'].find_one(sort=[('date', -1)])
        if not doc:
            return {}
        return {
            'date':    doc.get('date', ''),
            '_source': doc.get('source', 'mongodb_volume'),
            '외국인':  doc.get('외국인', []),
            '기관':    doc.get('기관',   []),
        }
    except Exception as e:
        print(f"  [경고] kr_investor_flows 로드 실패: {e}")
        return {}


def load_institutional_changes() -> list:
    """기관별 전분기 대비 섹터 가중치 변화 로드 (fetch_institutional.py 저장분)."""
    try:
        db   = get_db()
        docs = list(db['institutional_holdings'].find(
            {'sector_changes': {'$exists': True, '$ne': {}}},
            {'_id': 0, 'name': 1, 'period_of_report': 1, 'sector_changes': 1}
        ))
        result = []
        for doc in docs:
            changes = doc.get('sector_changes', {})
            if not changes:
                continue
            sorted_chg = sorted(changes.items(), key=lambda x: abs(x[1]), reverse=True)
            result.append({
                'name':        doc.get('name', ''),
                'period':      doc.get('period_of_report', ''),
                'top_changes': sorted_chg[:3],
            })
        return result
    except Exception as e:
        print(f"  [경고] institutional_changes 로드 실패: {e}")
        return []


def calc_sector_boost(kr_sector: str, inst_weights: dict) -> float:
    """한국 업종 → US 섹터 매핑 → 기관 가중치 기반 부스트 (최대 0.15)."""
    for us_sec, kr_list in US_TO_KR_SECTOR.items():
        if any(k in kr_sector for k in kr_list):
            return min(inst_weights.get(us_sec, 0.0) * 0.35, 0.15)
    return 0.0


def screen_institutional_aligned(ind: pd.DataFrame, master: pd.DataFrame) -> pd.DataFrame:
    """
    기존 screen_and_score() 기반으로 기관 섹터 집중도 부스트를 추가한 TOP5.
    institutional_holdings 없으면 빈 DataFrame 반환.
    """
    inst_weights = load_institutional_sectors()
    if not inst_weights:
        return pd.DataFrame()

    df = screen_and_score(ind, master)
    if df.empty:
        return df

    # 업종 컬럼이 없으면 추론
    if 'Sector' not in df.columns:
        df['Sector'] = df['Name'].apply(infer_sector)

    df['Inst_Boost']  = df['Sector'].apply(lambda s: calc_sector_boost(s, inst_weights))
    df['Score_Inst']  = (df['Score_Total'] + df['Inst_Boost']).clip(upper=1.0)
    df = df.sort_values('Score_Inst', ascending=False).reset_index(drop=True)

    # 글로벌 기관 집중 TOP3 US 섹터 → 대응 한국 업종 우선 선발 (최대 3개)
    top_us = [k for k, v in sorted(inst_weights.items(), key=lambda x: -x[1])[:3]]
    top_kr = set()
    for us in top_us:
        top_kr.update(US_TO_KR_SECTOR.get(us, []))

    selected, used_sectors, selected_codes = [], set(), set()
    for _, row in df.iterrows():
        sec = row.get('Sector', '')
        if any(k in sec for k in top_kr) and sec not in used_sectors:
            selected.append(row)
            used_sectors.add(sec)
            selected_codes.add(row['Code'])
        if len(selected) >= 3:
            break

    for _, row in df.iterrows():
        if row['Code'] not in selected_codes:
            selected.append(row)
            selected_codes.add(row['Code'])
        if len(selected) >= 5:
            break

    result = pd.DataFrame(selected).reset_index(drop=True)
    # Score_Total을 Score_Inst로 덮어쓰기 (collect_levels가 Score_Total 읽음)
    result['Score_Total'] = result['Score_Inst']
    print(f"  [기관연동] TOP{len(result)} 선정 완료")
    return result


# -------------------------------------------------------------------------
# 7. 매매 레벨 계산
# -------------------------------------------------------------------------

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


# -------------------------------------------------------------------------
# 6. 시장 요약
# -------------------------------------------------------------------------

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


# Dow Jones 30 components (2025 기준)
DOW30_TICKERS = [
    'AAPL', 'AMGN', 'AXP', 'BA',  'CAT', 'CRM', 'CSCO', 'CVX', 'DIS', 'DOW',
    'GS',   'HD',   'HON', 'IBM', 'JNJ', 'JPM', 'KO',   'MCD', 'MMM', 'MRK',
    'MSFT', 'NKE',  'NVDA','PG',  'SHW', 'TRV', 'UNH',  'V',   'VZ',  'WMT',
]


def us_market_summary() -> dict:
    """S&P 500 · NASDAQ Composite · Dow Jones 30 주간 시장 요약 (yfinance)"""
    import re
    try:
        import yfinance as yf
    except ImportError:
        print("  [경고] yfinance 미설치 — US 시장 데이터 건너뜀 (pip install yfinance)")
        return {}

    end_dt   = datetime.now()
    start_dt = end_dt - timedelta(days=14)

    def _bulk_stats(tickers):
        try:
            raw = yf.download(tickers, start=start_dt, end=end_dt,
                              interval='1d', progress=False, auto_adjust=True)
            if raw.empty:
                return None
            if isinstance(raw.columns, pd.MultiIndex):
                closes = raw['Close']
            else:
                closes = pd.DataFrame({'_': raw['Close']})
            rets = ((closes.iloc[-1] - closes.iloc[0]) / closes.iloc[0] * 100).dropna()
            return {
                'ret': round(float(rets.mean()), 2),
                'up':  int((rets > 0).sum()),
                'dn':  int((rets < 0).sum()),
            }
        except Exception as e:
            print(f"  [경고] yfinance 오류: {e}")
            return None

    def _index_ret(symbol):
        try:
            raw = yf.download(symbol, start=start_dt, end=end_dt,
                              interval='1d', progress=False, auto_adjust=True)
            if raw.empty or len(raw) < 2:
                return None
            c = raw['Close'].dropna() if not isinstance(raw.columns, pd.MultiIndex) \
                else raw['Close'].iloc[:, 0].dropna()
            return round(float((c.iloc[-1] - c.iloc[0]) / c.iloc[0] * 100), 2)
        except:
            return None

    result = {}

    # S&P 500 컴포넌트 → 상승/하락 집계
    print("  [US 시장] S&P 500 수집 중...")
    sp_tickers = []
    try:
        sp_df  = fdr.StockListing('S&P500')
        col    = 'Symbol' if 'Symbol' in sp_df.columns else sp_df.columns[0]
        sp_tickers = [t for t in sp_df[col].dropna().tolist()
                      if re.match(r'^[A-Z]{1,5}$', str(t))][:500]
    except Exception:
        pass
    sp_stats = _bulk_stats(sp_tickers) if sp_tickers else None
    if sp_stats is None:
        ret = _index_ret('SPY') or 0
        sp_stats = {'ret': ret, 'up': 0, 'dn': 0}
    result['SP500'] = sp_stats

    # NASDAQ Composite (지수만, 전 종목 집계 생략)
    print("  [US 시장] NASDAQ 수집 중...")
    nq_ret = _index_ret('^IXIC') or _index_ret('QQQ') or 0
    result['NASDAQ'] = {'ret': nq_ret, 'up': None, 'dn': None}

    # Dow Jones 30
    print("  [US 시장] Dow Jones 30 수집 중...")
    dj_stats = _bulk_stats(DOW30_TICKERS)
    if dj_stats is None:
        dj_ret = _index_ret('^DJI') or _index_ret('DIA') or 0
        dj_stats = {'ret': dj_ret, 'up': 0, 'dn': 0}
    result['DOW30'] = dj_stats

    return result


# -------------------------------------------------------------------------
# 7. 포트폴리오 주간 성과
# -------------------------------------------------------------------------

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


# -------------------------------------------------------------------------
# 8. 메인
# -------------------------------------------------------------------------

def run():
    print("\n" + "="*60)
    print("  검색 주간 퀀트 분석 시작 (MongoDB - 대장주 안정 모델)")
    print("="*60)

    try:
        MongoClient(MONGO_URI, serverSelectionTimeoutMS=3000).admin.command('ping')
        print("  MongoDB 연결 성공")
    except Exception as e:
        print(f"  MongoDB 연결 실패: {e}")
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

    print("\n  -- TOP 10 미리보기 --")
    cols = [c for c in ['Code','Name','Market','Close','Ret_4W','Ret_12W','RSI',
                         'ATR_Pct','Score_Trend','Score_RA','Score_Total']
            if c in scored.columns]
    preview = scored[cols].head(10).copy()
    for c in ['Ret_4W','Ret_12W']:
        if c in preview: preview[c] = (preview[c]*100).round(1)
    for c in ['RSI','ATR_Pct','Score_Trend','Score_RA','Score_Total']:
        if c in preview: preview[c] = preview[c].round(2)
    print(preview.to_string(index=False))

    print("\n[5/5] HTML 리포트 생성...")
    report_path = os.path.join(REPORT_DIR, f'weekly_{analysis_date}.html')
    print(f"  완료: {report_path}")

    print("\n" + "="*60)
    return report_path, scored


if __name__ == '__main__':
    run()
