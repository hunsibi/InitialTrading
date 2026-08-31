"""
send_telegram.py  -  장마감 후 텔레그램 데일리 브리핑

전송 내용은 아래 3가지만:
  1. 주요 지수: 코스피/코스닥/나스닥/S&P500/필라델피아반도체(SOX)
  2. 보유 종목 현재가·등락률
  3. 삼성전자·SK하이닉스 외국인/기관/개인 매매 동향 (pykrx, KRX_ID/KRX_PW 필요)
"""
import os
from datetime import datetime, timedelta, timezone
import requests

KST = timezone(timedelta(hours=9))


def now_kst():
    """한국 장 기준 현재 시각(naive). GitHub Actions 러너는 UTC라 명시 변환한다."""
    return datetime.now(KST).replace(tzinfo=None)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

try:
    import telegram_config as cfg
    BOT_TOKEN = cfg.BOT_TOKEN
    CHAT_ID   = str(cfg.CHAT_ID)
except ImportError:
    print("  [오류] telegram_config.py 없음")
    raise SystemExit(1)

# pykrx import 전에 KRX 자격증명을 환경변수에 미리 주입 (기관/외국인 수급 조회용)
try:
    import krx_config as _kc
    os.environ.setdefault('KRX_ID', _kc.KRX_ID)
    os.environ.setdefault('KRX_PW', _kc.KRX_PW)
except ImportError:
    pass

TELEGRAM_API = f"https://api.telegram.org/bot{BOT_TOKEN}"

KR_INDEXES = [('코스피', 'KS11'), ('코스닥', 'KQ11')]
US_INDEXES = [('나스닥', '^IXIC'), ('S&P500', '^GSPC'), ('필라델피아 반도체', '^SOX')]

# 보유 종목 (한국: FDR 코드 / 미국: yfinance 티커)
PORTFOLIO_KR = [
    ('삼성전자',                    '005930'),
    ('SK하이닉스',                  '000660'),
    ('KODEX 삼성전자채권혼합',       '448330'),
    ('TIGER 미국S&P500',           '143850'),
    ('KODEX AI전력핵심설비',        '466920'),
    ('TIGER 200',                  '102110'),
    ('TIGER KRX금현물',             '411060'),
    ('KODEX 종합채권(AA-이상)액티브', '273130'),
    ('KODEX 차이나휴머노이드로봇',    '453810'),
]
PORTFOLIO_US = [
    ('마이크론 테크놀로지', 'MU'),
    ('BITX',              'BITX'),
    ('TSLL',              'TSLL'),
]

# 매매 동향 조회 대상 (한국 종목만 pykrx 지원)
FLOW_TARGETS = [('삼성전자', '005930'), ('SK하이닉스', '000660')]


def fnum(v, nd=0):
    try:
        return f"{v:,.{nd}f}"
    except (TypeError, ValueError):
        return str(v)


def fpct(v):
    try:
        return f"{'+' if v >= 0 else ''}{v:.2f}%"
    except (TypeError, ValueError):
        return str(v)


def icon(chg):
    if chg > 0:  return "📈"
    if chg < 0:  return "📉"
    return "➖"


def kr_series(code, days=15):
    import FinanceDataReader as fdr
    end   = now_kst()
    start = end - timedelta(days=days)
    df = fdr.DataReader(code, start, end)
    return df['Close'].dropna() if df is not None and 'Close' in df else None


def us_quote(ticker):
    """미국 지수/종목의 최신 종가 + 직전 종가.

    yfinance의 history()는 최신 거래일 Close를 NaN으로 돌려주는 경우가 잦다.
    그대로 dropna 하면 하루 전 종가가 당일 값처럼 조용히 표시되므로,
    최신가는 fast_info.last_price(안정적)로, 직전 종가는 history의 마지막
    유효 종가로 조합한다. fast_info.previous_close는 개별 종목에서 실제
    직전 거래일 종가와 어긋나므로 쓰지 않는다.
    """
    import yfinance as yf
    tk = yf.Ticker(ticker)

    series = None
    try:
        h = tk.history(period='10d', interval='1d')
        if h is not None and 'Close' in h and not h.empty:
            series = h['Close'].dropna()
    except Exception:
        pass
    if series is None or len(series) < 1:
        return None

    last_price = None
    try:
        lp = tk.fast_info.last_price
        if lp and float(lp) > 0:
            last_price = float(lp)
    except Exception:
        pass

    hist_last = float(series.iloc[-1])
    hist_date = series.index[-1]

    # fast_info가 history보다 최신 시점을 가리키면 그 값을 당일 종가로 채택
    if last_price is not None and abs(last_price - hist_last) > 1e-6:
        import pandas as _pd
        return {'value': last_price, 'prev': hist_last,
                'date': (hist_date + _pd.tseries.offsets.BDay(1)).strftime('%m-%d')}

    if len(series) < 2:
        return None
    return {'value': hist_last, 'prev': float(series.iloc[-2]),
            'date': hist_date.strftime('%m-%d')}


def kr_after_market(code):
    """네이버 API 기반 시간외(NXT 애프터마켓) 최종가.

    FDR·KRX는 정규장(~15:30) 종가만 제공하지만 증권사 앱은 20:00까지 이어지는
    시간외 최종 체결가를 보여준다. 두 값이 다를 때 병기하기 위해 조회한다.
    ETF 등 시간외 거래가 없는 종목은 None.
    """
    try:
        r = requests.get(
            f'https://m.stock.naver.com/api/stock/{code}/basic',
            headers={'User-Agent': 'Mozilla/5.0',
                     'Referer': 'https://m.stock.naver.com/'},
            timeout=10)
        if r.status_code != 200:
            return None
        info = (r.json() or {}).get('overMarketPriceInfo') or {}
        price = str(info.get('overPrice', '')).replace(',', '')
        chg   = str(info.get('fluctuationsRatio', '')).replace(',', '')
        if not price or not chg:
            return None
        return {'value': float(price), 'chg': float(chg)}
    except Exception:
        return None


def kr_row(name, code, after=False):
    """FDR 기반 한국 지수/종목 정규장 종가 + 전일대비 등락률 (+ 시간외 병기)."""
    try:
        c = kr_series(code)
        if c is None or len(c) < 2:
            return None
        cur, prev = float(c.iloc[-1]), float(c.iloc[-2])
        chg = (cur - prev) / prev * 100 if prev else 0.0
        row = {'name': name, 'value': cur, 'chg': chg,
               'date': c.index[-1].strftime('%m-%d'), 'after': None}
        if after:
            am = kr_after_market(code)
            # 정규장과 값이 다를 때만 병기 (동일하면 노이즈)
            if am and abs(am['value'] - cur) >= 0.5:
                row['after'] = am
        return row
    except Exception as e:
        print(f"  [경고] {name} 조회 실패: {type(e).__name__}: {e}")
        return None


def us_row(name, ticker, after=False):
    """yfinance 기반 미국 지수/종목 정규장 종가 + 등락률 (+ 애프터마켓 병기)."""
    try:
        q = us_quote(ticker)
        if not q:
            print(f"  [경고] {name}({ticker}) 유효 데이터 없음 — 생략")
            return None
        cur, prev = q['value'], q['prev']
        chg = (cur - prev) / prev * 100 if prev else 0.0
        row = {'name': name, 'value': cur, 'chg': chg,
               'date': q['date'], 'after': None}
        if after:
            try:
                import yfinance as yf
                info = yf.Ticker(ticker).info or {}
                ap   = info.get('postMarketPrice')
                # 애프터마켓 등락률도 전일 종가 대비로 계산해 기준을 통일
                if ap and abs(float(ap) - cur) >= 0.005:
                    ap = float(ap)
                    row['after'] = {'value': ap,
                                    'chg': (ap - prev) / prev * 100 if prev else 0.0}
            except Exception:
                pass
        return row
    except Exception as e:
        print(f"  [경고] {name}({ticker}) 조회 실패: {type(e).__name__}: {e}")
        return None


def weekly_flows(code, days=5):
    """pykrx 기반 최근 N거래일 외국인/기관/개인 일별 순매수 거래대금(억원)."""
    try:
        kid = os.environ.get('KRX_ID', '')
        kpw = os.environ.get('KRX_PW', '')
        if not (kid and kpw):
            return []
        from pykrx import stock as pykrx_stock
        today = now_kst()
        if today.weekday() >= 5:                       # 주말 → 직전 금요일
            today -= timedelta(days=today.weekday() - 4)
        start = (today - timedelta(days=20)).strftime('%Y%m%d')
        end   = today.strftime('%Y%m%d')
        df = pykrx_stock.get_market_trading_value_by_date(start, end, code)
        if df is None or df.empty:
            return []
        df = df.tail(days)
        return [{
            'date':      idx.strftime('%m-%d'),
            'full_date': idx.strftime('%Y-%m-%d'),
            'foreign':   float(r.get('외국인합계', 0)) / 1e8,
            'inst':      float(r.get('기관합계', 0)) / 1e8,
            'indiv':     float(r.get('개인', 0)) / 1e8,
        } for idx, r in df.iterrows()]
    except Exception as e:
        print(f"  [경고] {code} 수급 조회 실패: {type(e).__name__}: {e}")
        return []


def collect() -> dict:
    """텔레그램 메시지와 HTML 리포트가 함께 쓰는 데이터를 한 번만 수집."""
    data = {'date': now_kst().strftime('%Y-%m-%d'),
            'indexes': [], 'holdings': [], 'flows': []}

    for name, code in KR_INDEXES:
        r = kr_row(name, code)
        if r:
            r['flag'] = '🇰🇷'
            data['indexes'].append(r)
    for name, ticker in US_INDEXES:
        r = us_row(name, ticker)
        if r:
            r['flag'] = '🇺🇸'
            data['indexes'].append(r)

    for name, code in PORTFOLIO_KR:
        r = kr_row(name, code, after=True)
        if r:
            r['cur'] = '원'
            data['holdings'].append(r)
    for name, ticker in PORTFOLIO_US:
        r = us_row(name, ticker, after=True)
        if r:
            r['cur'] = '$'
            data['holdings'].append(r)

    for name, code in FLOW_TARGETS:
        data['flows'].append({'name': name, 'code': code,
                              'flows': weekly_flows(code)})
    return data


def build_message(data) -> str:
    lines = [f"📊 *일일 시황 브리핑* `{data['date']}`"]

    # 1. 삼성전자·SK하이닉스 매매 동향 (당일 + 주간 합계) — 가장 먼저
    lines += ["", "━━━ 🇰🇷 삼성전자·SK하이닉스 매매 동향 ━━━"]
    any_flow = False
    for c in data['flows']:
        f = c['flows']
        if not f:
            continue
        any_flow = True
        last = f[-1]
        wf = sum(x['foreign'] for x in f)
        wi = sum(x['inst'] for x in f)
        wp = sum(x['indiv'] for x in f)
        lines.append(f"*{c['name']}* _{last['full_date']}_")
        lines.append(f"   외국인 `{last['foreign']:+,.0f}억`  기관 `{last['inst']:+,.0f}억`  개인 `{last['indiv']:+,.0f}억`")
        lines.append(f"   _{len(f)}일 누적_  외국인 `{wf:+,.0f}억`  기관 `{wi:+,.0f}억`  개인 `{wp:+,.0f}억`")
    if not any_flow:
        lines.append("_데이터 수집 실패 (KRX_ID/KRX_PW 확인 필요)_")
    lines.append("_일별 그래프는 첨부 HTML 리포트 첫 화면에 있습니다_")

    # 2. 주요 지수 (날짜 병기 — 소스가 최신일을 못 주면 바로 드러나도록)
    lines += ["", "━━━ 📈 주요 지수 ━━━"]
    for r in data['indexes']:
        lines.append(f"{icon(r['chg'])} {r['flag']} {r['name']}  "
                     f"`{fnum(r['value'], 2)}`  `{fpct(r['chg'])}`  _{r['date']}_")

    # 3. 보유 종목 (정규장 종가 기준 · 시간외가 다르면 병기)
    lines += ["", "━━━ 💼 보유 종목 ━━━"]
    for r in data['holdings']:
        usd = r['cur'] == '$'
        val = f"${fnum(r['value'], 2)}" if usd else f"{fnum(r['value'], 0)}원"
        lines.append(f"{icon(r['chg'])} {r['name']}  `{val}`  `{fpct(r['chg'])}`")
        if r['after']:
            a  = r['after']
            av = f"${fnum(a['value'], 2)}" if usd else f"{fnum(a['value'], 0)}원"
            lines.append(f"      _{'애프터' if usd else '시간외'} {av} {fpct(a['chg'])}_")

    return '\n'.join(lines)


def send_msg(text):
    try:
        r = requests.post(f"{TELEGRAM_API}/sendMessage",
            data={'chat_id': CHAT_ID, 'text': text, 'parse_mode': 'Markdown'},
            timeout=15)
        ok = r.status_code == 200 and r.json().get('ok')
        if not ok:
            print(f"  [전송 실패] {r.text[:150]}")
        return ok
    except Exception as e:
        print(f"  [전송 오류] {type(e).__name__}")
        return False


def send_file(path, caption):
    try:
        with open(path, 'rb') as fp:
            r = requests.post(f"{TELEGRAM_API}/sendDocument",
                data={'chat_id': CHAT_ID, 'caption': caption},
                files={'document': (os.path.basename(path), fp, 'text/html')},
                timeout=60)
        ok = r.status_code == 200 and r.json().get('ok')
        if not ok:
            print(f"  [파일 전송 실패] {r.text[:150]}")
        return ok
    except Exception as e:
        print(f"  [파일 전송 오류] {type(e).__name__}: {e}")
        return False


def run():
    print("\n" + "="*50)
    print("  텔레그램 데일리 브리핑 전송")
    print("="*50)

    try:
        r = requests.get(f"{TELEGRAM_API}/getMe", timeout=10)
        bot = r.json().get('result', {}).get('username', '?')
        print(f"  봇 연결 OK: @{bot}")
    except Exception as e:
        print(f"  봇 연결 실패: {e}")
        return

    print("  데이터 수집 중...")
    data = collect()

    print("  [1] 요약 메시지 전송...")
    ok1 = send_msg(build_message(data))
    print(f"  -> {'완료' if ok1 else '실패'}")

    print("  [2] HTML 리포트 생성...")
    try:
        import build_daily_html as bh
        path = bh.build(data['date'], data['indexes'], data['holdings'], data['flows'])
        print(f"  -> {path}")
        print("  [3] HTML 리포트 전송...")
        ok2 = send_file(path, f"{data['date']} 일일 시황 리포트")
        print(f"  -> {'완료' if ok2 else '실패'}")
    except Exception as e:
        print(f"  [경고] HTML 리포트 실패: {type(e).__name__}: {e}")

    print("="*50)


if __name__ == '__main__':
    run()
