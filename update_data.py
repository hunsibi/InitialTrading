"""
증분 데이터 업데이트 스크립트 (update_data.py)
==============================================
매주 금요일 장 마감 후 실행.
MongoDB의 최신 날짜 이후 데이터만 다운로드하여 prices 컬렉션에 upsert.
"""

import os, time
import pandas as pd
import FinanceDataReader as fdr
from datetime import datetime, timedelta
from pymongo import MongoClient, ASCENDING, UpdateOne
from pymongo.errors import BulkWriteError
import concurrent.futures
from tqdm import tqdm

# ── 설정 ──────────────────────────────────────────────
MONGO_URI   = 'mongodb://localhost:27017'
DB_NAME     = 'trading'
MAX_WORKERS = 20
CHUNK_SIZE  = 5_000


def get_db():
    client = MongoClient(MONGO_URI)
    return client[DB_NAME]


# ── MongoDB 최신 날짜 조회 ────────────────────────────
def get_latest_date() -> datetime:
    db  = get_db()
    doc = db['prices'].find_one(sort=[('date', -1)], projection={'date':1, '_id':0})
    if not doc:
        raise RuntimeError("DB에 데이터가 없습니다. migrate_to_db.py를 먼저 실행하세요.")
    return datetime.strptime(doc['date'], '%Y-%m-%d')


# ── 단일 종목 다운로드 ────────────────────────────────
def fetch_single(ticker: str, s_date, e_date):
    try:
        df = fdr.DataReader(ticker, s_date, e_date)
        if df is not None and not df.empty:
            df = df.reset_index()
            df['Code'] = ticker
            cols = [c for c in ['Date','Code','Open','High','Low','Close','Volume','Change']
                    if c in df.columns]
            return df[cols]
    except Exception:
        pass
    return None


# ── DB에 upsert ───────────────────────────────────────
def upsert_to_db(df: pd.DataFrame) -> int:
    db      = get_db()
    coll    = db['prices']
    records = df.to_dict('records')
    total_upserted = 0

    for start in range(0, len(records), CHUNK_SIZE):
        chunk = records[start:start + CHUNK_SIZE]
        ops   = [
            UpdateOne(
                {'code': r['code'], 'date': r['date']},
                {'$set': r},
                upsert=True
            ) for r in chunk
        ]
        try:
            res = coll.bulk_write(ops, ordered=False)
            total_upserted += res.upserted_count + res.modified_count
        except BulkWriteError as e:
            total_upserted += e.details.get('nUpserted', 0)

    return total_upserted


# ── stocks 마스터 갱신 ────────────────────────────────
def refresh_stocks():
    """KOSPI/KOSDAQ 종목 마스터를 최신으로 갱신 (필요 시 별도 실행)"""
    print("  종목 마스터 갱신 중...")
    kospi  = fdr.StockListing('KOSPI')
    kosdaq = fdr.StockListing('KOSDAQ')
    master = pd.concat([
        kospi.assign(Market='KOSPI'),
        kosdaq.assign(Market='KOSDAQ')
    ], ignore_index=True)
    master['Code'] = master['Code'].astype(str).str.zfill(6)

    col_map = {'Code':'code','Name':'name','Market':'market',
               'Marcap':'marcap','Stocks':'stocks','ISU_CD':'isu_cd'}
    master  = master.rename(columns={k:v for k,v in col_map.items() if k in master.columns})
    keep    = [v for v in col_map.values() if v in master.columns]
    master  = master[keep].dropna(subset=['code'])

    db   = get_db()
    coll = db['stocks']
    coll.drop()
    ops = [UpdateOne({'code': r['code']}, {'$set': r}, upsert=True)
           for r in master.to_dict('records')]
    coll.bulk_write(ops, ordered=False)
    coll.create_index([('code', ASCENDING)], unique=True)
    print(f"  ✅ stocks 갱신 완료: {len(master):,}개 종목")


# ── 메인 ──────────────────────────────────────────────
def run_update():
    print("=" * 60)
    print("  📥 증분 데이터 업데이터 (MongoDB)")
    print("=" * 60)

    # MongoDB 연결 확인
    try:
        MongoClient(MONGO_URI, serverSelectionTimeoutMS=3000).admin.command('ping')
    except Exception as e:
        print(f"  ❌ MongoDB 연결 실패: {e}")
        return

    # 최신 날짜 확인
    latest_dt  = get_latest_date()
    start_date = latest_dt + timedelta(days=1)
    end_date   = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)

    print(f"  ▸ DB 최신 날짜  : {latest_dt.date()}")
    print(f"  ▸ 다운로드 범위 : {start_date.date()} ~ {end_date.date()}")

    bdays = pd.bdate_range(start=start_date, end=end_date)
    if len(bdays) == 0:
        print("\n  ✅ 이미 최신 상태입니다.")
        return
    print(f"  ▸ 예상 영업일  : {len(bdays)}일\n")

    # 종목 리스트
    db      = get_db()
    tickers = [d['code'] for d in db['stocks'].find({}, {'code':1,'_id':0})]
    print(f"  ▸ 대상 종목 수  : {len(tickers):,}개")

    # 병렬 다운로드
    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futures = {ex.submit(fetch_single, t, start_date, end_date): t for t in tickers}
        for fut in tqdm(concurrent.futures.as_completed(futures),
                        total=len(tickers), desc="  다운로드"):
            res = fut.result()
            if res is not None:
                results.append(res)

    if not results:
        print("\n  ⚠️  새 데이터 없음 (휴장일 또는 데이터 미수신)")
        return

    # 데이터 정제
    new_df = pd.concat(results, ignore_index=True)
    new_df.columns = [c.lower() for c in new_df.columns]
    new_df['date']   = pd.to_datetime(new_df['date']).dt.strftime('%Y-%m-%d')
    new_df['code']   = new_df['code'].astype(str).str.zfill(6)
    new_df['close']  = pd.to_numeric(new_df['close'],  errors='coerce')
    new_df['volume'] = pd.to_numeric(new_df['volume'], errors='coerce')
    new_df = new_df.dropna(subset=['close'])
    new_df = new_df[new_df['close'] > 0]

    print(f"\n  ▸ 다운로드 완료 : {len(new_df):,}행 ({new_df['code'].nunique():,}종목)")

    # DB 저장
    t0 = time.time()
    cnt = upsert_to_db(new_df)
    new_max = db['prices'].find_one(sort=[('date',-1)], projection={'date':1,'_id':0})['date']

    print(f"  ✅ DB 저장 완료 : {len(new_df):,}행 ({time.time()-t0:.1f}s)")
    print(f"  ▸ DB 최신 날짜  : {new_max}")
    print("=" * 60)


if __name__ == '__main__':
    run_update()
