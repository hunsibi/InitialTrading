"""
fetch_institutional.py  -  SEC EDGAR 13F-HR 공시에서 글로벌 주요 기관투자자 포트폴리오 수집
                            → MongoDB institutional_holdings 컬렉션 upsert
                            (90일 캐시: 13F는 분기 공시, 과도한 API 호출 방지)
"""
import os, sys, time, re, json, requests
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from pymongo import MongoClient

BASE_DIR   = os.path.dirname(os.path.abspath(__file__))
MONGO_URI  = 'mongodb://localhost:27017'
DB_NAME    = 'trading'
CACHE_DAYS = 90

EDGAR_BASE = "https://data.sec.gov"
EDGAR_ARCH = "https://www.sec.gov/Archives/edgar"
HEADERS    = {"User-Agent": "InitialTrading hs77.jung@gmail.com"}
RATE_DELAY = 0.15   # 10 req/sec 이하 유지

FUND_UNIVERSE = [
    ("블랙록",            "0001364742"),
    ("뱅가드",            "0000102909"),
    ("피델리티",          "0000315066"),
    ("스테이트스트리트",  "0000093751"),
    ("JP모건자산운용",    "0000019617"),
    ("캐피탈그룹",        "0001422848"),
    ("버크셔해서웨이",    "0001067983"),
    ("T.로우프라이스",    "0000080255"),
    ("웰링턴매니지먼트",  "0000902219"),
    ("골드만삭스",        "0000886982"),
    ("한국투자공사(KIC)", "0001441689"),
]

# 종목명 키워드 → US 섹터 분류
_SECTOR_KW = [
    ('Technology',    ['APPLE','MICROSOFT','NVIDIA','META','ALPHABET','GOOGLE','AMAZON',
                       'INTEL','AMD','QUALCOMM','BROADCOM','SALESFORCE','ORACLE',
                       'TECH','SEMICONDUCTOR','SOFTWARE','SYSTEMS','DIGITAL','CYBER',
                       'TAIWAN SEMICONDUCTOR','TSMC','ASML','MICRON','APPLIED MATERIALS']),
    ('Healthcare',    ['JOHNSON','PFIZER','UNITEDHEALTH','ABBVIE','MERCK','LILLY',
                       'AMGEN','BIOGEN','GILEAD','REGENERON','MODERNA','PHARMA',
                       'BIOTECH','MEDICAL','HEALTH','THERAPEUTICS','GENOMICS','BRISTOL']),
    ('Financials',    ['BERKSHIRE','JPMORGAN','BANK','WELLS FARGO','GOLDMAN','MORGAN',
                       'CITIGROUP','BLACKSTONE','VISA','MASTERCARD','PAYPAL',
                       'AMERICAN EXPRESS','INSURANCE','CAPITAL','FINANCIAL','CHUBB']),
    ('Energy',        ['EXXON','CHEVRON','CONOCOPHILLIPS','PIONEER','SCHLUMBERGER',
                       'HALLIBURTON','OIL','GAS','ENERGY','PETROLEUM','REFIN']),
    ('Consumer',      ['TESLA','HOME DEPOT','WALMART','COSTCO','TARGET',
                       'MCDONALDS','STARBUCKS','NIKE','COCA','PEPSI','PROCTER',
                       'CONSUMER','RETAIL','LUXURY','BRANDS','LVMH','NESTLE']),
    ('Industrials',   ['BOEING','CATERPILLAR','HONEYWELL','UNION PACIFIC','LOCKHEED',
                       'RAYTHEON','GENERAL ELECTRIC','3M','DEFENSE','AEROSPACE',
                       'INDUSTRIAL','TRANSPORT','LOGISTICS','MACHINERY','DEERE']),
    ('Real Estate',   ['PROLOGIS','AMERICAN TOWER','CROWN CASTLE','REALTY','REIT',
                       'REAL ESTATE','PROPERTY','EQUINIX','WELLTOWER']),
    ('Materials',     ['LINDE','AIR PRODUCTS','SHERWIN','NEWMONT','FREEPORT',
                       'MATERIALS','CHEMICALS','MINING','STEEL','METAL','CORTEVA']),
    ('Communication', ['NETFLIX','DISNEY','COMCAST','VERIZON','AT&T',
                       'TWITTER','SNAP','COMMUNICATION','MEDIA','TELECOM','CHARTER']),
    ('Utilities',     ['NEXTERA','DUKE','SOUTHERN','DOMINION','AMERICAN ELECTRIC',
                       'UTILITY','UTILITIES','ELECTRIC','WATER','GAS UTILITY']),
]


def get_db():
    return MongoClient(MONGO_URI)[DB_NAME]


def infer_sector(name: str) -> str:
    n = name.upper()
    for sector, keywords in _SECTOR_KW:
        if any(k in n for k in keywords):
            return sector
    return 'Other'


def is_cache_valid(cik: str) -> bool:
    try:
        doc = get_db()['institutional_holdings'].find_one({'cik': cik}, {'fetched_at': 1})
        if not doc or not doc.get('fetched_at'):
            return False
        return (datetime.utcnow() - doc['fetched_at']).days < CACHE_DAYS
    except Exception:
        return False


def get_cached(cik: str):
    try:
        return get_db()['institutional_holdings'].find_one({'cik': cik})
    except Exception:
        return None


def fetch_latest_13f_accession(cik: str):
    url = f"{EDGAR_BASE}/submissions/CIK{cik}.json"
    try:
        r = requests.get(url, headers=HEADERS, timeout=20)
        time.sleep(RATE_DELAY)
        if r.status_code != 200:
            return None
        data = r.json()
        filings = data.get('filings', {}).get('recent', {})
        forms   = filings.get('form', [])
        accnos  = filings.get('accessionNumber', [])
        dates   = filings.get('filingDate', [])
        periods = filings.get('reportDate', [])
        for i, form in enumerate(forms):
            if form == '13F-HR':
                return {
                    'accession':     accnos[i],
                    'acc_nodash':    accnos[i].replace('-', ''),
                    'filing_date':   dates[i],
                    'period':        periods[i],
                }
    except Exception as e:
        print(f"    submissions 오류: {e}")
    return None


def find_infotable_url(cik_int: int, acc_dashed: str, acc_nodash: str) -> str:
    """filing -index.htm 파싱으로 infotable XML URL 탐색."""
    idx_url = (f"{EDGAR_ARCH}/data/{cik_int}/"
               f"{acc_nodash}/{acc_dashed}-index.htm")
    try:
        r = requests.get(idx_url, headers=HEADERS, timeout=15)
        time.sleep(RATE_DELAY)
        if r.status_code != 200:
            return ''
        # href 파싱 — acc_nodash 이후에 슬래시가 없는 .xml 파일 (서브디렉토리 제외)
        hrefs = re.findall(r'href="(/Archives/edgar/data/[^"]+\.xml)"', r.text)
        base_path = f"/Archives/edgar/data/{cik_int}/{acc_nodash}/"
        for h in hrefs:
            if not h.startswith(base_path):
                continue
            remainder = h[len(base_path):]
            # 서브디렉토리 없고 primary_doc 아닌 파일
            if '/' not in remainder and 'primary_doc' not in remainder:
                return 'https://www.sec.gov' + h
    except Exception as e:
        print(f"    index.htm 탐색 오류: {e}")
    return ''


def parse_infotable_xml(xml_text: str) -> list:
    # 네임스페이스 제거 후 파싱 (xmlns 선언, ns:attr 속성, 태그 prefix 순서대로 제거)
    clean = re.sub(r'\s+xmlns(?::\w+)?="[^"]*"', '', xml_text)
    clean = re.sub(r'\s+\w+:\w+="[^"]*"', '', clean)
    clean = re.sub(r'<(\w+):', '<', clean)
    clean = re.sub(r'</(\w+):', '</', clean)
    holdings = []
    try:
        root = ET.fromstring(clean)
        for info in root.findall('.//infoTable'):
            name  = (info.findtext('nameOfIssuer') or '').strip()
            cusip = (info.findtext('cusip') or '').strip()
            val_el = info.find('.//value')
            value  = 0
            try:
                value = int((val_el.text or '0').replace(',', ''))
            except Exception:
                pass
            shr_el = info.find('.//sshPrnamt')
            shares = 0
            try:
                shares = int((shr_el.text or '0').replace(',', ''))
            except Exception:
                pass
            if name and value > 0:
                holdings.append({'name': name, 'cusip': cusip,
                                 'value': value, 'shares': shares})
    except ET.ParseError as e:
        print(f"    XML 파싱 오류: {e}")
    return holdings


def fetch_holdings(cik: str, acc_info: dict) -> list:
    cik_int    = int(cik)
    acc_nodash = acc_info['acc_nodash']
    acc_dashed = acc_info['accession']
    xml_url    = find_infotable_url(cik_int, acc_dashed, acc_nodash)
    if not xml_url:
        print(f"    infotable URL 탐색 실패")
        return []
    try:
        r = requests.get(xml_url, headers=HEADERS, timeout=40)
        time.sleep(RATE_DELAY)
        if r.status_code != 200:
            print(f"    XML 다운로드 실패: {r.status_code}")
            return []
        return parse_infotable_xml(r.text)
    except Exception as e:
        print(f"    XML 다운로드 오류: {e}")
        return []


def aggregate_sectors(holdings: list) -> dict:
    sv, total = {}, 0
    for h in holdings:
        sec = infer_sector(h['name'])
        h['sector'] = sec
        sv[sec] = sv.get(sec, 0) + h['value']
        total   += h['value']
    if total == 0:
        return {}
    return {k: round(v / total, 4)
            for k, v in sorted(sv.items(), key=lambda x: -x[1])}


def fetch_one_fund(name: str, cik: str):
    print(f"  [{name}] 수집 중...")
    acc_info = fetch_latest_13f_accession(cik)
    if not acc_info:
        print(f"  [{name}] 13F 파일링 없음")
        return None
    print(f"  [{name}] {acc_info['filing_date']} (기준: {acc_info['period']})")
    holdings = fetch_holdings(cik, acc_info)
    if not holdings:
        print(f"  [{name}] 보유 내역 없음")
        return None
    sector_weights = aggregate_sectors(holdings)
    top20 = sorted(holdings, key=lambda x: -x['value'])[:20]
    return {
        'cik':                cik,
        'name':               name,
        'fetched_at':         datetime.utcnow(),
        'filing_date':        acc_info['filing_date'],
        'period_of_report':   acc_info['period'],
        'accession_no':       acc_info['accession'],
        'top_holdings':       top20,
        'sector_weights':     sector_weights,
        'total_holdings_count': len(holdings),
        'total_value_k':      sum(h['value'] for h in holdings),
    }


def upsert(doc: dict):
    coll = get_db()['institutional_holdings']
    coll.create_index('cik', unique=True)

    # 이전 섹터 가중치 보존 → 변화 계산 (전분기 대비)
    existing = coll.find_one({'cik': doc['cik']}, {'sector_weights': 1, '_id': 0})
    if existing and existing.get('sector_weights'):
        doc['prev_sector_weights'] = existing['sector_weights']
        curr     = doc.get('sector_weights', {})
        prev     = existing['sector_weights']
        all_secs = set(curr) | set(prev)
        changes  = {s: round(curr.get(s, 0.0) - prev.get(s, 0.0), 4) for s in all_secs}
        doc['sector_changes'] = {k: v for k, v in changes.items() if abs(v) >= 0.01}
    else:
        doc['sector_changes'] = {}

    coll.update_one({'cik': doc['cik']}, {'$set': doc}, upsert=True)


def run():
    print("\n" + "="*50)
    print("  [1-b/4] 글로벌 기관 포트폴리오 수집 (SEC EDGAR 13F)")
    print("="*50)
    results, skipped = [], 0
    for name, cik in FUND_UNIVERSE:
        if is_cache_valid(cik):
            cached = get_cached(cik)
            if cached:
                print(f"  [{name}] 캐시 유효 ({cached.get('filing_date','?')}) — 스킵")
                results.append(cached)
            skipped += 1
            continue
        doc = fetch_one_fund(name, cik)
        if doc:
            upsert(doc)
            results.append(doc)
            print(f"  [{name}] 저장 완료 ({doc['total_holdings_count']}개 보유)")
        else:
            cached = get_cached(cik)
            if cached:
                print(f"  [{name}] 수집 실패 → 캐시 사용 ({cached.get('filing_date','?')})")
                results.append(cached)
            else:
                print(f"  [{name}] 수집 실패 + 캐시 없음 → 건너뜀")
    print(f"\n  완료: {len(results)}개 기관 데이터 / {skipped}개 캐시")
    return results


if __name__ == '__main__':
    run()
