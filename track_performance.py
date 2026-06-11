"""
track_performance.py — 추천 성과 추적
=========================================================
매주 추천된 TOP5(4개 모델)를 MongoDB `recommendations` 컬렉션에 저장하고,
과거 추천의 실제 성과(1주/2주/4주 수익률, 목표가·손절가 도달)를 평가한다.

컬렉션 스키마 (key: date + model + code):
  date        : 추천 기준일 (prices 최신일, YYYY-MM-DD)
  model       : 'S'(안정) / 'M'(모멘텀) / 'E'(ETF) / 'I'(기관연동)
  rank        : 0~4
  base_close  : 추천 시점 종가 (수익률 계산 기준)
  entry/stop/target1/target2 : 매매 레벨
  eval        : {ret_1w, ret_2w, ret_4w, hit, hit_day, days_elapsed, final}
                hit: 'target2'|'target1'|'stop'|None (20거래일 내 첫 도달)

직접 실행: python track_performance.py  → 평가 갱신 + 요약 출력
"""
import pandas as pd
from datetime import datetime
from pymongo import MongoClient

MONGO_URI = 'mongodb://localhost:27017'
DB_NAME   = 'trading'

MODEL_LABELS = {'S': '안정 대장주', 'M': '단기 모멘텀', 'E': 'ETF 추천', 'I': '기관연동'}
HORIZONS     = {'ret_1w': 5, 'ret_2w': 10, 'ret_4w': 20}
EVAL_WINDOW  = 20          # 목표/손절 판정 최대 거래일
SUMMARY_WEEKS = 12         # 요약 통계에 포함할 최근 추천 회차 수 (매일 실행 시 약 2.5주)


def get_db():
    client = MongoClient(MONGO_URI)
    return client[DB_NAME]


# -------------------------------------------------------------------------
# 1. 추천 저장
# -------------------------------------------------------------------------

def save_recommendations(date: str, model: str, levels: list):
    """generate_report.py의 collect_levels() 결과를 저장.
    같은 (date, model) 재실행 시 해당 주 추천을 새 결과로 교체한다."""
    if not levels:
        return 0
    db  = get_db()
    col = db['recommendations']
    col.create_index([('date', 1), ('model', 1), ('code', 1)], unique=True)

    docs = []
    for rank, lv in enumerate(levels):
        docs.append({
            'date':       date,
            'model':      model,
            'code':       str(lv['Code']).zfill(6),
            'rank':       rank,
            'name':       str(lv.get('Name', lv['Code'])),
            'sector':     str(lv.get('Sector', '')),
            'base_close': int(lv['Close']),
            'entry':      int(lv['Entry']),
            'stop':       int(lv['StopLoss']),
            'target1':    int(lv['Target1']),
            'target2':    int(lv['Target2']),
            'score':      float(lv['Score']),
            'created_at': datetime.now().strftime('%Y-%m-%d %H:%M'),
        })
    col.delete_many({'date': date, 'model': model})
    col.insert_many(docs)
    print(f"  [추천저장] {model}({MODEL_LABELS.get(model, model)}) {len(docs)}종목 — {date}")
    return len(docs)


# -------------------------------------------------------------------------
# 2. 평가용 가격 로드 (MongoDB → 없으면 FDR 폴백, ETF 대응)
# -------------------------------------------------------------------------

def _load_eval_prices(codes: list, since: str) -> pd.DataFrame:
    db     = get_db()
    cursor = db['prices'].find(
        {'code': {'$in': list(codes)}, 'date': {'$gte': since}},
        {'_id': 0, 'date': 1, 'code': 1, 'high': 1, 'low': 1, 'close': 1}
    )
    df = pd.DataFrame(list(cursor))
    have = set(df['code'].astype(str).str.zfill(6)) if not df.empty else set()
    missing = [c for c in codes if c not in have]

    if missing:
        # ETF 등 prices 컬렉션에 없는 종목은 FDR로 직접 조회
        try:
            import FinanceDataReader as fdr
            import concurrent.futures

            def fetch_one(code):
                try:
                    raw = fdr.DataReader(code, since)
                    if raw is None or raw.empty:
                        return None
                    raw = raw.reset_index()
                    return pd.DataFrame({
                        'date':  raw['Date'].dt.strftime('%Y-%m-%d'),
                        'code':  code,
                        'high':  raw['High'],
                        'low':   raw['Low'],
                        'close': raw['Close'],
                    })
                except Exception:
                    return None

            fetched = []
            with concurrent.futures.ThreadPoolExecutor(max_workers=10) as ex:
                for fut in concurrent.futures.as_completed(
                        {ex.submit(fetch_one, c): c for c in missing}):
                    r = fut.result()
                    if r is not None:
                        fetched.append(r)
            if fetched:
                df = pd.concat([df] + fetched, ignore_index=True) if not df.empty \
                     else pd.concat(fetched, ignore_index=True)
        except ImportError:
            print("  [평가] FinanceDataReader 미설치 — ETF 평가 건너뜀")

    if df.empty:
        return df
    df['code']  = df['code'].astype(str).str.zfill(6)
    for c in ['high', 'low', 'close']:
        df[c] = pd.to_numeric(df[c], errors='coerce')
    df = df.dropna(subset=['close'])
    return df.sort_values(['code', 'date']).reset_index(drop=True)


def _kospi_horizon_returns(rec_dates: list) -> dict:
    """추천일별 KOSPI 지수의 +5거래일 수익률. {date: ret_pct}"""
    if not rec_dates:
        return {}
    try:
        import FinanceDataReader as fdr
        ks = fdr.DataReader('KS11', min(rec_dates))
        if ks is None or ks.empty:
            return {}
        closes = ks['Close'].dropna()
        idx    = [d.strftime('%Y-%m-%d') for d in closes.index]
        result = {}
        for rd in rec_dates:
            after = [i for i, dd in enumerate(idx) if dd > rd]
            base  = [i for i, dd in enumerate(idx) if dd <= rd]
            if not base or len(after) < 5:
                continue
            b = float(closes.iloc[base[-1]])
            f = float(closes.iloc[after[4]])
            if b > 0:
                result[rd] = round((f - b) / b * 100, 2)
        return result
    except Exception as e:
        print(f"  [평가] KOSPI 벤치마크 조회 실패: {e}")
        return {}


# -------------------------------------------------------------------------
# 3. 성과 평가
# -------------------------------------------------------------------------

def _evaluate_one(rec: dict, px: pd.DataFrame) -> dict:
    """추천 1건 평가. px: 해당 종목의 추천일 이후 가격 (date 오름차순)."""
    after = px[px['date'] > rec['date']].reset_index(drop=True)
    if after.empty:
        return {}

    base = float(rec['base_close'])
    ev   = {'days_elapsed': len(after),
            'last_eval_date': str(after['date'].iloc[-1])}

    for key, n in HORIZONS.items():
        if len(after) >= n:
            ev[key] = round((float(after['close'].iloc[n - 1]) - base) / base * 100, 2)

    # 목표/손절 첫 도달 판정 (같은 날 동시 도달은 보수적으로 손절 처리)
    hit, hit_day = None, None
    for i, row in after.head(EVAL_WINDOW).iterrows():
        lo = row['low']  if pd.notna(row['low'])  else row['close']
        hi = row['high'] if pd.notna(row['high']) else row['close']
        if lo <= rec['stop']:
            hit, hit_day = 'stop', i + 1
            break
        if hi >= rec['target2']:
            hit, hit_day = 'target2', i + 1
            break
        if hi >= rec['target1']:
            hit, hit_day = 'target1', i + 1
            break
    ev['hit']     = hit
    ev['hit_day'] = hit_day
    ev['final']   = bool(hit is not None or len(after) >= EVAL_WINDOW)
    return ev


def evaluate_all():
    """미확정 추천 전체를 재평가해서 eval 필드 갱신."""
    db  = get_db()
    col = db['recommendations']
    pending = list(col.find({'$or': [{'eval': {'$exists': False}},
                                     {'eval.final': {'$ne': True}}]}))
    if not pending:
        print("  [평가] 갱신할 추천 없음")
        return 0

    codes = sorted({r['code'] for r in pending})
    since = min(r['date'] for r in pending)
    px    = _load_eval_prices(codes, since)
    if px.empty:
        print("  [평가] 가격 데이터 없음 — 평가 건너뜀")
        return 0

    updated = 0
    for rec in pending:
        sub = px[px['code'] == rec['code']]
        ev  = _evaluate_one(rec, sub)
        if ev:
            col.update_one({'_id': rec['_id']}, {'$set': {'eval': ev}})
            updated += 1
    print(f"  [평가] {updated}/{len(pending)}건 갱신")
    return updated


# -------------------------------------------------------------------------
# 4. 요약 통계
# -------------------------------------------------------------------------

def build_summary(current_date: str = None) -> dict:
    """최근 SUMMARY_WEEKS주 추천의 모델별 성과 요약.
    current_date(이번 주 추천일)는 아직 성과가 없으므로 제외."""
    db   = get_db()
    col  = db['recommendations']
    cond = {'eval.ret_1w': {'$exists': True}}
    if current_date:
        cond['date'] = {'$lt': current_date}
    docs = list(col.find(cond, {'_id': 0}))
    if not docs:
        return {}

    dates = sorted({r['date'] for r in docs}, reverse=True)[:SUMMARY_WEEKS]
    docs  = [r for r in docs if r['date'] in dates]

    kospi  = _kospi_horizon_returns(sorted(set(r['date'] for r in docs)))
    models = {}
    for m in MODEL_LABELS:
        recs = [r for r in docs if r['model'] == m]
        if not recs:
            continue
        r1   = [r['eval']['ret_1w'] for r in recs]
        r4   = [r['eval']['ret_4w'] for r in recs if 'ret_4w' in r['eval']]
        done = [r for r in recs if r['eval'].get('final')]
        ex1  = [r['eval']['ret_1w'] - kospi[r['date']] for r in recs if r['date'] in kospi]
        best  = max(recs, key=lambda r: r['eval']['ret_1w'])
        worst = min(recs, key=lambda r: r['eval']['ret_1w'])
        models[m] = {
            'n':        len(recs),
            'ret_1w':   round(sum(r1) / len(r1), 2),
            'win_1w':   round(sum(1 for v in r1 if v > 0) / len(r1) * 100, 0),
            'ret_4w':   round(sum(r4) / len(r4), 2) if r4 else None,
            'excess_1w': round(sum(ex1) / len(ex1), 2) if ex1 else None,
            't1_hit':   round(sum(1 for r in done if r['eval'].get('hit') in
                                  ('target1', 'target2')) / len(done) * 100, 0) if done else None,
            'stop_hit': round(sum(1 for r in done if r['eval'].get('hit') == 'stop')
                              / len(done) * 100, 0) if done else None,
            'n_done':   len(done),
            'best':     {'name': best['name'],  'ret': best['eval']['ret_1w']},
            'worst':    {'name': worst['name'], 'ret': worst['eval']['ret_1w']},
        }

    # 가장 최근 평가 완료 주차의 종목별 결과
    last_date = dates[0]
    last = {}
    for m in MODEL_LABELS:
        rows = sorted([r for r in docs if r['date'] == last_date and r['model'] == m],
                      key=lambda r: r['rank'])
        if rows:
            last[m] = [{'name': r['name'], 'code': r['code'],
                        'ret_1w': r['eval']['ret_1w'],
                        'hit': r['eval'].get('hit')} for r in rows]

    return {
        'weeks':       len(dates),
        'last_date':   last_date,
        'kospi_ret1w': round(sum(kospi.values()) / len(kospi), 2) if kospi else None,
        'models':      models,
        'last':        last,
    }


def get_performance_kv(current_date: str = None) -> list:
    """weekly_full 데이터 파일용 PERF_* key=value 라인 생성."""
    s = build_summary(current_date)
    if not s:
        return []
    kv = [f'PERF_WEEKS={s["weeks"]}',
          f'PERF_LAST_DATE={s["last_date"]}']
    if s['kospi_ret1w'] is not None:
        kv.append(f'PERF_KOSPI_RET1W={s["kospi_ret1w"]}')
    for m, st in s['models'].items():
        kv.append(f'PERF_{m}_N={st["n"]}')
        kv.append(f'PERF_{m}_RET1W={st["ret_1w"]}')
        kv.append(f'PERF_{m}_WIN1W={int(st["win_1w"])}')
        if st['ret_4w'] is not None:
            kv.append(f'PERF_{m}_RET4W={st["ret_4w"]}')
        if st['excess_1w'] is not None:
            kv.append(f'PERF_{m}_EXCESS1W={st["excess_1w"]}')
        if st['t1_hit'] is not None:
            kv.append(f'PERF_{m}_T1HIT={int(st["t1_hit"])}')
        if st['stop_hit'] is not None:
            kv.append(f'PERF_{m}_STOPHIT={int(st["stop_hit"])}')
        kv.append(f'PERF_{m}_BEST={st["best"]["name"]}|{st["best"]["ret"]}')
        kv.append(f'PERF_{m}_WORST={st["worst"]["name"]}|{st["worst"]["ret"]}')
    for m, rows in s['last'].items():
        kv.append(f'PERF_LAST_{m}_COUNT={len(rows)}')
        for i, r in enumerate(rows):
            kv.append(f'PERF_LAST_{m}_{i}={r["name"]}|{r["code"]}|{r["ret_1w"]}|{r["hit"] or ""}')
    return kv


# -------------------------------------------------------------------------
# 5. 직접 실행
# -------------------------------------------------------------------------

if __name__ == '__main__':
    print("\n" + "=" * 50)
    print("  추천 성과 평가")
    print("=" * 50)
    evaluate_all()
    s = build_summary()
    if not s:
        print("  평가된 추천 없음 (다음 주 파이프라인 실행부터 누적됩니다)")
    else:
        print(f"\n  최근 {s['weeks']}회 추천 성과 (KOSPI 1주 평균 "
              f"{s['kospi_ret1w'] if s['kospi_ret1w'] is not None else '-'}%)")
        for m, st in s['models'].items():
            line = (f"  [{m}] {MODEL_LABELS[m]:8s} n={st['n']:3d}  "
                    f"1주 {st['ret_1w']:+.2f}% (승률 {st['win_1w']:.0f}%)")
            if st['ret_4w'] is not None:
                line += f"  4주 {st['ret_4w']:+.2f}%"
            if st['t1_hit'] is not None:
                line += f"  목표달성 {st['t1_hit']:.0f}% / 손절 {st['stop_hit']:.0f}%"
            print(line)
