"""
CSV → MongoDB 마이그레이션 스크립트 (migrate_to_db.py)
======================================================
최초 1회만 실행. 기존 분기별 CSV 파일과 master_info.csv를
MongoDB 로컬 DB로 통합합니다.

DB 구조:
  database   : trading
  collection : prices   → 전 종목 일별 가격 (약 290만 도큐먼트)
  collection : stocks   → 종목 마스터 (코드, 종목명, 시장, 시가총액)

인덱스:
  prices : { code:1, date:1 } unique  → 종목별 기간 조회
  prices : { date:1 }                 → 날짜 기준 시장 전체 조회
  stocks : { code:1 } unique
"""

import os, time
import pandas as pd
from pymongo import MongoClient, ASCENDING, UpdateOne
from pymongo.errors import BulkWriteError

# ── 설정 ──────────────────────────────────────────────
BASE_DIR   = os.path.dirname(os.path.abspath(__file__))
DATA_DIR   = os.path.join(BASE_DIR, 'outputs', 'data')
MONGO_URI  = 'mongodb://localhost:27017'
DB_NAME    = 'trading'
CHUNK_SIZE = 10_000   # 한 번에 insert할 도큐먼트 수


def get_db():
    client = MongoClient(MONGO_URI)
    return client[DB_NAME]


# ── stocks(마스터) 임포트 ─────────────────────────────
def import_stocks(db):
    path = os.path.join(DATA_DIR, 'master_info.csv')
    df   = pd.read_csv(path, low_memory=False)
    df['Code'] = df['Code'].astype(str).str.zfill(6)

    col_map = {'Code':'code', 'Name':'name', 'Market':'market',
               'Marcap':'marcap', 'Stocks':'stocks', 'ISU_CD':'isu_cd'}
    df = df.rename(columns={k:v for k,v in col_map.items() if k in df.columns})
    keep = [v for v in col_map.values() if v in df.columns]
    df = df[keep].dropna(subset=['code'])

    coll = db['stocks']
    coll.drop()

    ops = [
        UpdateOne({'code': row['code']}, {'$set': row}, upsert=True)
        for row in df.to_dict('records')
    ]
    if ops:
        coll.bulk_write(ops, ordered=False)

    coll.create_index([('code', ASCENDING)], unique=True)
    print(f"  ✅ stocks: {len(df):,}개 종목 임포트 완료")


# ── prices(가격) 임포트 ───────────────────────────────
def import_prices(db):
    files = sorted([f for f in os.listdir(DATA_DIR)
                    if f.startswith('prices_') and f.endswith('.csv')])
    coll  = db['prices']
    coll.drop()

    # 인덱스 먼저 생성 (중복 방지용 unique 인덱스)
    coll.create_index([('code', ASCENDING), ('date', ASCENDING)], unique=True)
    coll.create_index([('date', ASCENDING)])

    total = 0
    t0    = time.time()

    for i, fname in enumerate(files, 1):
        path = os.path.join(DATA_DIR, fname)
        df   = pd.read_csv(path, low_memory=False,
                           dtype={'Code': str, 'Open': float, 'High': float,
                                  'Low': float, 'Close': float,
                                  'Volume': float, 'Change': float})
        df['Code'] = df['Code'].astype(str).str.zfill(6)
        df['Date'] = pd.to_datetime(df['Date']).dt.strftime('%Y-%m-%d')
        df = df[['Date','Code','Open','High','Low','Close','Volume','Change']]
        df = df.dropna(subset=['Close'])
        df = df[df['Close'] > 0]

        # 컬럼명 소문자로 통일
        df.columns = [c.lower() for c in df.columns]
        records = df.to_dict('records')

        # 청크 단위로 ordered=False insert (중복 무시)
        inserted = 0
        for start in range(0, len(records), CHUNK_SIZE):
            chunk = records[start:start + CHUNK_SIZE]
            ops   = [UpdateOne({'code': r['code'], 'date': r['date']},
                               {'$setOnInsert': r}, upsert=True)
                     for r in chunk]
            try:
                result = coll.bulk_write(ops, ordered=False)
                inserted += result.upserted_count
            except BulkWriteError as e:
                inserted += e.details.get('nUpserted', 0)

        total += len(records)
        elapsed = time.time() - t0
        print(f"  [{i:02d}/{len(files)}] {fname}: {len(records):,}행  "
              f"(누적 {total:,}행, 경과 {elapsed:.0f}s)")

    print(f"\n  ✅ prices: 총 {total:,}행 임포트 완료")


# ── 검증 ─────────────────────────────────────────────
def verify(db):
    print("\n  ── 검증 ──")
    prices = db['prices']
    stocks = db['stocks']

    p_cnt   = prices.estimated_document_count()
    s_cnt   = stocks.estimated_document_count()
    min_dt  = prices.find_one(sort=[('date', ASCENDING)], projection={'date':1, '_id':0})
    max_dt  = prices.find_one(sort=[('date', -1)],        projection={'date':1, '_id':0})
    c_cnt   = len(prices.distinct('code'))

    print(f"  prices 도큐먼트 : {p_cnt:,}")
    print(f"  stocks 도큐먼트 : {s_cnt:,}")
    print(f"  기간            : {min_dt['date']} ~ {max_dt['date']}")
    print(f"  종목 수         : {c_cnt:,}")

    # 삼성전자 샘플 조회 속도 테스트
    t = time.time()
    rows = list(prices.find(
        {'code': '005930'},
        {'_id':0, 'date':1, 'close':1}
    ).sort('date', -1).limit(5))
    ms = (time.time() - t) * 1000
    print(f"\n  삼성전자 최근 5일 (조회 {ms:.1f}ms):")
    for r in rows:
        print(f"    {r['date']}  {int(r['close']):,}원")


# ── 메인 ──────────────────────────────────────────────
def run():
    print("\n" + "="*60)
    print("  🗄️  CSV → MongoDB 마이그레이션 시작")
    print("="*60)

    try:
        client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=3000)
        client.admin.command('ping')
        print("  ✅ MongoDB 연결 성공 (localhost:27017)")
    except Exception as e:
        print(f"  ❌ MongoDB 연결 실패: {e}")
        print("  → MongoDB 서비스가 실행 중인지 확인하세요.")
        print("  → 서비스 시작: Windows 서비스에서 'MongoDB' 시작")
        return

    db = get_db()

    # 기존 데이터 확인
    existing = db['prices'].estimated_document_count()
    if existing > 0:
        print(f"\n  ⚠️  이미 {existing:,}개 도큐먼트가 있습니다.")
        ans = input("   기존 데이터를 모두 삭제하고 재임포트할까요? (y/N): ").strip().lower()
        if ans != 'y':
            print("   취소됨.")
            return

    t_total = time.time()

    print("\n[1/3] 종목 마스터(stocks) 임포트...")
    import_stocks(db)

    print("\n[2/3] 가격 데이터(prices) 임포트...")
    import_prices(db)

    print("\n[3/3] 검증...")
    verify(db)

    print(f"\n  🎉 마이그레이션 완료! (총 {time.time()-t_total:.0f}초)")
    print(f"  DB: {MONGO_URI}/{DB_NAME}")
    print("="*60)


if __name__ == '__main__':
    run()
