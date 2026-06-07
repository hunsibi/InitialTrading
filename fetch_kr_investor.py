"""
fetch_kr_investor.py  -  한국 시장 주간 외국인/기관 종목별 순매수/매도 TOP5 수집
                         pykrx (KRX_ID/KRX_PW 필요) → MongoDB kr_investor_flows 컬렉션
"""
import os
from datetime import datetime, timedelta
from pymongo import MongoClient
import pandas as pd

# pykrx import 전에 KRX 자격증명을 환경변수에 미리 주입
try:
    import krx_config as _kc
    os.environ.setdefault('KRX_ID', _kc.KRX_ID)
    os.environ.setdefault('KRX_PW', _kc.KRX_PW)
except ImportError:
    pass

BASE_DIR  = os.path.dirname(os.path.abspath(__file__))
MONGO_URI = 'mongodb://localhost:27017'
DB_NAME   = 'trading'


def get_db():
    return MongoClient(MONGO_URI)[DB_NAME]


def _get_week_range():
    today  = datetime.now()
    monday = today - timedelta(days=today.weekday())
    return monday.strftime('%Y%m%d'), today.strftime('%Y%m%d')


def _load_krx_credentials() -> tuple:
    try:
        import krx_config
        return krx_config.KRX_ID, krx_config.KRX_PW
    except ImportError:
        pass
    return os.environ.get('KRX_ID', ''), os.environ.get('KRX_PW', '')


def _try_pykrx(fromdate: str, todate: str) -> dict:
    """pykrx로 외국인/기관 종목별 순매수 TOP5 + 순매도 TOP5 수집."""
    try:
        from pykrx import stock as pykrx_stock
    except ImportError:
        return {}

    kid, kpw = _load_krx_credentials()
    if not (kid and kpw):
        return {}

    os.environ['KRX_ID'] = kid
    os.environ['KRX_PW'] = kpw

    # code → name 매핑 (MongoDB stocks)
    try:
        db = get_db()
        code_to_name = {s['code']: s.get('name', s['code'])
                        for s in db['stocks'].find({}, {'_id': 0, 'code': 1, 'name': 1})}
    except Exception:
        code_to_name = {}

    result = {}

    for investor_key, label in [('외국인', '외국인'), ('기관합계', '기관')]:
        frames = []
        for market in ['KOSPI', 'KOSDAQ']:
            try:
                df = pykrx_stock.get_market_net_purchases_of_equities_by_ticker(
                    fromdate, todate, market=market, investor=investor_key
                )
                if df is not None and not df.empty:
                    frames.append(df)
            except Exception as e:
                print(f"  [pykrx/{label}/{market}] 오류: {type(e).__name__}: {e}")

        if not frames:
            result[f'{label}_매수'] = []
            result[f'{label}_매도'] = []
            continue

        combined = pd.concat(frames)
        net_col = next((c for c in combined.columns if '순매수거래대금' in c), None)
        if net_col is None:
            net_col = next((c for c in combined.columns if '순매수' in c), combined.columns[-1])

        combined.index = combined.index.astype(str).str.zfill(6)
        combined[net_col] = pd.to_numeric(combined[net_col], errors='coerce').fillna(0)
        combined = combined.sort_values(net_col, ascending=False)

        def make_list(sub_df):
            rows = []
            for code, row in sub_df.iterrows():
                code = str(code).zfill(6)
                net  = int(row[net_col])
                rows.append({
                    'code':  code,
                    'name':  code_to_name.get(code, code),
                    'net_krw': net,
                    'net_b': round(abs(net) / 1e8, 0),  # 억원
                })
            return rows

        buy_df  = combined[combined[net_col] > 0].head(5)
        sell_df = combined[combined[net_col] < 0].tail(5).sort_values(net_col)

        result[f'{label}_매수'] = make_list(buy_df)
        result[f'{label}_매도'] = make_list(sell_df)
        print(f"  [pykrx/{label}] 순매수 {len(buy_df)}종목 / 순매도 {len(sell_df)}종목")

    return result


def fetch_market_flows(fromdate: str, todate: str) -> dict:
    """외국인/기관 종목별 순매수/매도 TOP5 수집. pykrx 필요."""
    result = _try_pykrx(fromdate, todate)
    if not result:
        print("  pykrx 로그인 없음 또는 실패 — 종목별 데이터 수집 건너뜀")
        print("  (실제 데이터: KRX_ID / KRX_PW 설정 필요)")
    return result


def run():
    print("\n" + "="*50)
    print("  [1-c/4] 한국 외국인/기관 종목별 매매 동향 수집")
    print("="*50)

    fromdate, todate = _get_week_range()
    print(f"  기간: {fromdate} ~ {todate}")

    flows = fetch_market_flows(fromdate, todate)
    if not flows:
        print("  데이터 없음 — 건너뜀")
        return {}

    try:
        doc = {
            'date':       todate,
            'fromdate':   fromdate,
            'fetched_at': datetime.utcnow(),
            'source':     'pykrx',
            '외국인_매수': flows.get('외국인_매수', []),
            '외국인_매도': flows.get('외국인_매도', []),
            '기관_매수':   flows.get('기관_매수',   []),
            '기관_매도':   flows.get('기관_매도',   []),
        }
        db = get_db()
        db['kr_investor_flows'].create_index('date')
        db['kr_investor_flows'].update_one({'date': todate}, {'$set': doc}, upsert=True)
        print(f"  저장 완료 — "
              f"외국인 매수 {len(doc['외국인_매수'])}종목 / 매도 {len(doc['외국인_매도'])}종목 / "
              f"기관 매수 {len(doc['기관_매수'])}종목 / 매도 {len(doc['기관_매도'])}종목")
    except Exception as e:
        print(f"  [경고] MongoDB 저장 실패: {e}")

    return flows


if __name__ == '__main__':
    run()
