"""
fetch_kr_investor.py  -  한국 시장 주간 외국인/기관 섹터별 순매수 TOP5 수집
                         1순위: pykrx (KRX_ID/KRX_PW 환경변수 설정 시)
                         폴백 : MongoDB 가격 데이터 기반 섹터 거래량 급증 분석
                         결과  → MongoDB kr_investor_flows 컬렉션
"""
import os
from datetime import datetime, timedelta
from pymongo import MongoClient
import pandas as pd

# pykrx import 전에 KRX 자격증명을 환경변수에 미리 주입
# krx_config.py 우선, 없으면 기존 환경변수 사용
try:
    import krx_config as _kc
    os.environ.setdefault('KRX_ID', _kc.KRX_ID)
    os.environ.setdefault('KRX_PW', _kc.KRX_PW)
except ImportError:
    pass

BASE_DIR  = os.path.dirname(os.path.abspath(__file__))
MONGO_URI = 'mongodb://localhost:27017'
DB_NAME   = 'trading'

# 종목명 키워드 → 한국 업종 (weekly_analysis.infer_sector 와 동일 체계)
_SECTOR_KW = [
    ('반도체/장비',  ['하이닉스', '반도체', '원익', '이오테크', '테스', '피에스케이',
                     '리노공업', '솔브레인', '이엔에프', '동진쎄미켐', '한미반도체',
                     'DB하이텍', '에이피티씨', '실트론', '하나머티리얼즈']),
    ('IT/전자',      ['삼성전자', 'LG전자', '삼성전기', 'LG이노텍', '삼성SDS',
                     '넥스틴', '파크시스템스', '고영', 'LG디스플레이']),
    ('배터리/소재',  ['에코프로', '에너지솔루션', '포스코퓨처엠', '일진머티리얼즈',
                     '코스모화학', '이차전지', '배터리', '양극재', '음극재', '전해질', '분리막']),
    ('자동차/부품',  ['현대차', '기아', '현대모비스', '한온시스템', '현대위아', '만도', '모터스']),
    ('화학',         ['LG화학', '롯데케미칼', '한화솔루션', '금호석유', '효성화학',
                     '케미칼', '화학', '페트로', '플라스틱']),
    ('철강/소재',    ['포스코', '현대제철', '고려아연', '영풍', '동국제강', '철강', '금속']),
    ('금융/보험',    ['삼성생명', '삼성화재', 'KB금융', '신한지주', '하나금융', '우리금융',
                     '메리츠', '한화생명', 'DB손해보험', '현대해상',
                     '금융', '은행', '증권', '보험', '자산운용']),
    ('바이오/제약',  ['셀트리온', '삼성바이오', '한미약품', '유한양행', '종근당', '동아ST',
                     '녹십자', '일동제약', '바이오', '제약', '헬스케어', '의료', '치료', '진단']),
    ('에너지/전력',  ['한국전력', '한국가스공사', 'SK이노베이션', 'GS칼텍스', 'S-Oil',
                     '에너지', '전력', '발전', '원자력', '신재생']),
    ('통신/플랫폼',  ['SK텔레콤', 'KT', 'LG유플러스', '카카오', '네이버', '카카오뱅크',
                     '통신', '플랫폼', '인터넷', '미디어', '콘텐츠']),
    ('건설/부동산',  ['현대건설', '삼성물산', 'GS건설', '대우건설', 'DL이앤씨', '건설', '부동산', '리츠']),
    ('유통/소비재',  ['롯데', '신세계', '이마트', 'CJ', '농심', '오리온', '한국콜마',
                     '유통', '소비재', '식품', '음료', '화장품', '뷰티']),
    ('방산/항공',    ['한화에어로스페이스', 'LIG넥스원', '현대로템', '한국항공우주',
                     '방산', '방위', '항공우주', '드론']),
    ('게임/엔터',    ['크래프톤', '넥슨', '엔씨소프트', '넷마블', '카카오게임즈', '하이브',
                     'SM', 'JYP', 'YG', '게임', '엔터']),
    ('조선/기계',    ['현대중공업', '삼성중공업', '대우조선', '한화오션', '두산',
                     '조선', '기계', '플랜트', '중공업']),
]


def get_db():
    return MongoClient(MONGO_URI)[DB_NAME]


def infer_kr_sector(name: str) -> str:
    n = str(name)
    for sector, kws in _SECTOR_KW:
        if any(k in n for k in kws):
            return sector
    return '기타'


def _get_week_range():
    """이번 주 월요일 ~ 오늘 (YYYYMMDD)"""
    today  = datetime.now()
    monday = today - timedelta(days=today.weekday())
    return monday.strftime('%Y%m%d'), today.strftime('%Y%m%d')


# ---------------------------------------------------------------------------
# 1순위: pykrx (KRX 로그인 있을 때)
# ---------------------------------------------------------------------------

def _load_krx_credentials() -> tuple:
    """KRX 자격증명 로드: krx_config.py 우선, 없으면 환경변수."""
    try:
        import krx_config
        return krx_config.KRX_ID, krx_config.KRX_PW
    except ImportError:
        pass
    kid = os.environ.get('KRX_ID', '')
    kpw = os.environ.get('KRX_PW', '')
    return kid, kpw


def _try_pykrx(fromdate: str, todate: str) -> dict:
    """pykrx로 외국인/기관 실제 순매수 데이터 수집. 실패 시 {} 반환."""
    try:
        from pykrx import stock as pykrx_stock
    except ImportError:
        return {}

    # KRX_ID/KRX_PW 설정 여부 확인
    kid, kpw = _load_krx_credentials()
    if not (kid and kpw):
        return {}

    # 환경변수로 주입 (pykrx가 os.environ에서 읽음)
    os.environ['KRX_ID'] = kid
    os.environ['KRX_PW'] = kpw

    try:
        db           = get_db()
        code_to_name = {s['code']: s['name']
                        for s in db['stocks'].find({}, {'_id': 0, 'code': 1, 'name': 1})}
    except Exception:
        code_to_name = {}

    result = {}
    for investor_key, label in [('외국인', '외국인'), ('기관합계', '기관')]:
        sector_data = {}

        for market in ['KOSPI', 'KOSDAQ']:
            try:
                df = pykrx_stock.get_market_net_purchases_of_equities_by_ticker(
                    fromdate, todate, market=market, investor=investor_key
                )
                if df is None or df.empty:
                    continue
                net_col = next((c for c in df.columns if '순매수거래대금' in c), df.columns[-1])

                for code_raw, row in df.iterrows():
                    code = str(code_raw).zfill(6)
                    name = code_to_name.get(code, code)
                    try:
                        net = float(row[net_col])
                    except (TypeError, ValueError):
                        continue
                    if net == 0:
                        continue
                    sec = infer_kr_sector(name)
                    if sec not in sector_data:
                        sector_data[sec] = {'net': 0.0, 'stocks': []}
                    sector_data[sec]['net'] += net
                    sector_data[sec]['stocks'].append((abs(net), name, net > 0))
            except Exception as e:
                print(f"  [pykrx/{label}/{market}] 오류: {type(e).__name__}: {e}")

        top5 = []
        for sec, data in sorted(sector_data.items(),
                                key=lambda x: abs(x[1]['net']), reverse=True)[:5]:
            net    = data['net']
            is_buy = net >= 0
            filtered   = [(a, n) for a, n, b in data['stocks'] if b == is_buy]
            top_stocks = [n for _, n in sorted(filtered, reverse=True)[:2]]
            top5.append({
                'sector':     sec,
                'net_raw':    net,
                'net_abs_b':  round(abs(net) / 1e8, 0),
                'dir':        'BUY' if is_buy else 'SELL',
                'top_stocks': top_stocks,
                'source':     'pykrx',
            })
        result[label] = top5
        print(f"  [pykrx/{label}] {len(top5)}개 섹터 집계")

    return result


# ---------------------------------------------------------------------------
# 폴백: MongoDB 가격 데이터 기반 섹터 거래량 급증 분석
# ---------------------------------------------------------------------------

def _fallback_volume_surge(days_back: int = 5) -> dict:
    """
    MongoDB prices + stocks 데이터를 이용한 섹터별 주간 거래량 급증 TOP5.
    외국인/기관을 구분하지 않고 전체 시장 기준 수급 동향을 추정.
    """
    try:
        db = get_db()

        # 최근 30일 가격 데이터
        since = (datetime.now() - timedelta(days=35)).strftime('%Y-%m-%d')
        cursor = db['prices'].find(
            {'date': {'$gte': since}},
            {'_id': 0, 'date': 1, 'code': 1, 'close': 1, 'volume': 1}
        )
        prices = pd.DataFrame(list(cursor))
        if prices.empty:
            return {}
        prices['date']   = pd.to_datetime(prices['date'])
        prices['code']   = prices['code'].astype(str).str.zfill(6)
        prices['volume'] = pd.to_numeric(prices['volume'], errors='coerce').fillna(0)

        # 종목 마스터 (이름 + 시장)
        master = pd.DataFrame(list(db['stocks'].find(
            {}, {'_id': 0, 'code': 1, 'name': 1, 'market': 1}
        )))
        if master.empty:
            return {}
        master['code'] = master['code'].astype(str).str.zfill(6)

        latest_date = prices['date'].max()
        week_start  = latest_date - timedelta(days=days_back)
        prev_start  = week_start  - timedelta(days=20)

        # 이번 주 / 이전 4주 거래량
        this_week = prices[prices['date'] > week_start].groupby('code')['volume'].sum()
        prev_4wk  = prices[
            (prices['date'] > prev_start) & (prices['date'] <= week_start)
        ].groupby('code')['volume'].mean().replace(0, float('nan'))

        # 거래량 비율
        vol_ratio = (this_week / prev_4wk).dropna()
        vol_ratio = vol_ratio[vol_ratio > 0]

        # 섹터 분류
        code_to_sector = {}
        for _, row in master.iterrows():
            code_to_sector[row['code']] = infer_kr_sector(row.get('name', ''))

        # 이번 주 가격 변화 (순방향 추정)
        this_close = prices[prices['date'] == latest_date].set_index('code')['close']
        prev_close = prices[prices['date'] <= week_start].groupby('code')['close'].last()
        price_chg  = ((this_close - prev_close) / prev_close.replace(0, float('nan'))).dropna()

        # 섹터별 집계
        sector_vol   = {}
        sector_chg   = {}
        sector_stocks = {}

        for code in vol_ratio.index:
            sec = code_to_sector.get(code, '기타')
            vr  = vol_ratio.get(code, 1.0)
            pc  = price_chg.get(code, 0.0)
            vraw = this_week.get(code, 0)

            if sec not in sector_vol:
                sector_vol[sec]    = []
                sector_chg[sec]    = []
                sector_stocks[sec] = []

            sector_vol[sec].append(vr)
            sector_chg[sec].append(pc)
            sector_stocks[sec].append((vr, code))

        # 섹터별 평균 거래량 비율 + 방향 판단
        top5_buy  = []  # 거래량 급증 + 가격 상승 (매수 추정)
        top5_sell = []  # 거래량 급증 + 가격 하락 (매도 추정)

        agg = []
        for sec, vr_list in sector_vol.items():
            avg_vr = sum(vr_list) / len(vr_list)
            avg_pc = sum(sector_chg[sec]) / len(sector_chg[sec])
            top_stocks_raw = sorted(sector_stocks[sec], reverse=True)[:3]
            agg.append((sec, avg_vr, avg_pc, top_stocks_raw))

        agg.sort(key=lambda x: -x[1])  # 거래량 비율 기준 정렬

        # 상위 섹터 → 매수/매도 방향으로 분리
        foreign_proxy = []
        inst_proxy    = []
        for sec, avg_vr, avg_pc, top_s in agg[:10]:
            is_buy = avg_pc >= 0
            item   = {
                'sector':     sec,
                'net_raw':    avg_pc,
                'net_abs_b':  round(avg_vr, 2),   # 여기서는 거래량 비율로 사용
                'vol_ratio':  round(avg_vr, 2),
                'dir':        'BUY' if is_buy else 'SELL',
                'top_stocks': [],  # 코드만 있음 — 이름 변환 생략
                'source':     'mongodb_volume',
            }
            # 대표 종목 이름 채우기
            code_to_name = {row['code']: row.get('name', '')
                            for _, row in master.iterrows()}
            item['top_stocks'] = [code_to_name.get(c, c) for _, c in top_s[:2] if code_to_name.get(c)]

            if is_buy and len(foreign_proxy) < 5:
                foreign_proxy.append(item)
            elif not is_buy and len(inst_proxy) < 5:
                inst_proxy.append(item)

        # 매수 TOP5 / 매도 TOP5 → 외국인(proxy)/기관(proxy)으로 분리 표시
        # 실제 외국인/기관 구분이 아님을 source 필드로 표시
        result = {
            '외국인': foreign_proxy[:5],
            '기관':   inst_proxy[:5],
        }
        print(f"  [MongoDB폴백] 거래량 급증 섹터 {len(foreign_proxy)+len(inst_proxy)}개 집계")
        return result

    except Exception as e:
        print(f"  [MongoDB폴백] 오류: {type(e).__name__}: {e}")
        return {}


# ---------------------------------------------------------------------------
# 메인
# ---------------------------------------------------------------------------

def fetch_market_flows(fromdate: str, todate: str) -> dict:
    """외국인/기관 섹터 매매 동향 수집. pykrx 우선, 실패 시 MongoDB 폴백."""
    # 1순위: pykrx
    result = _try_pykrx(fromdate, todate)
    if result:
        return result

    # 폴백: MongoDB 거래량 분석
    print("  pykrx 로그인 없음 → MongoDB 거래량 기반 섹터 수급 추정")
    print("  (실제 외국인/기관 데이터: KRX_ID / KRX_PW 환경변수 설정 필요)")
    return _fallback_volume_surge()


def run():
    print("\n" + "="*50)
    print("  [1-c/4] 한국 외국인/기관 섹터 매매 동향 수집")
    print("="*50)

    fromdate, todate = _get_week_range()
    print(f"  기간: {fromdate} ~ {todate}")

    flows = fetch_market_flows(fromdate, todate)
    if not flows:
        print("  데이터 없음 — 건너뜀")
        return {}

    # pykrx 여부 표시
    source = (flows.get('외국인') or flows.get('기관') or [{}])[0].get('source', '')
    is_real = source == 'pykrx'
    flows['_source'] = source

    try:
        doc = {
            'date':       todate,
            'fromdate':   fromdate,
            'fetched_at': datetime.utcnow(),
            'source':     source,
            '외국인':     flows.get('외국인', []),
            '기관':       flows.get('기관',   []),
        }
        db   = get_db()
        coll = db['kr_investor_flows']
        coll.create_index('date')
        coll.update_one({'date': todate}, {'$set': doc}, upsert=True)
        kind = "외국인/기관 실데이터" if is_real else "거래량 기반 추정"
        print(f"  저장 완료 [{kind}] — 외국인 {len(flows.get('외국인',[]))}섹터 / "
              f"기관 {len(flows.get('기관',[]))}섹터")
    except Exception as e:
        print(f"  [경고] MongoDB 저장 실패: {e}")

    return flows


if __name__ == '__main__':
    run()
