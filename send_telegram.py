"""
send_telegram.py  -  weekly quant report -> telegram (안정 대장주 TOP5 + 모멘텀 TOP5)
"""
import os, glob, re, requests
from datetime import datetime, timedelta

BASE_DIR   = os.path.dirname(os.path.abspath(__file__))
REPORT_DIR = os.path.join(BASE_DIR, 'outputs', 'reports')

try:
    import telegram_config as cfg
    BOT_TOKEN = cfg.BOT_TOKEN
    CHAT_ID   = str(cfg.CHAT_ID)
except ImportError:
    print("  [오류] telegram_config.py 없음")
    exit(1)

TELEGRAM_API = f"https://api.telegram.org/bot{BOT_TOKEN}"

RANK_ICO = ["1️⃣","2️⃣","3️⃣","4️⃣","5️⃣"]


def load_data() -> dict:
    patterns = sorted(glob.glob(os.path.join(REPORT_DIR, 'weekly_full_*.html')), reverse=True)
    if not patterns:
        raise FileNotFoundError("weekly_full_*.html 없음. generate_report.py 먼저 실행하세요.")
    data_file = patterns[0]
    print(f"  데이터 파일: {data_file}")
    d = {}
    with open(data_file, encoding='utf-8') as f:
        for line in f:
            line = line.rstrip('\n')
            if '=' in line:
                k, _, v = line.partition('=')
                d[k] = v
    d['__file__'] = data_file
    return d


def g(d, k):
    return d.get(k, '')


def fi(v):
    try:    return f"{int(v):,}"
    except: return str(v)


def sp(v):
    try:
        return ('+' if float(v) >= 0 else '') + str(v) + '%'
    except:
        return str(v) + '%'


def held_mark(d, pfx, i):
    """보유 중인 종목 표시 (MY_PORTFOLIO_KR 중복)."""
    return ' 📌보유중' if g(d, f'{pfx}{i}_HELD') == '1' else ''


def qty_txt(d, pfx, i):
    """1,000만원 계좌 1% 리스크 기준 권장 수량."""
    q = g(d, f'{pfx}{i}_QTY')
    return f"  수량 `{q}주`" if q else ''


def next_mon(date_str):
    try:
        dt  = datetime.strptime(date_str, '%Y-%m-%d')
        gap = (7 - dt.weekday()) % 7
        return (dt + timedelta(days=(gap or 7))).strftime('%Y-%m-%d')
    except:
        return ''


def build_summary(d):
    date  = g(d,'DATE')
    nm    = next_mon(date)
    kr    = float(g(d,'KOSPI_RET')  or 0)
    qr    = float(g(d,'KOSDAQ_RET') or 0)
    ki    = "\U0001f4c8" if kr>=0 else "\U0001f4c9"
    qi    = "\U0001f4c8" if qr>=0 else "\U0001f4c9"
    lines = [
        "\U0001f4ca *주간 퀀트 리포트*",
        f"기준일: {date}  |  투자일: {nm}",
        "",
        "━━━ 🇰🇷 한국 시장 ━━━",
        f"{ki} KOSPI  `{kr:+.2f}%`  상승 {g(d,'KOSPI_UP')} / 하락 {g(d,'KOSPI_DN')}",
        f"{qi} KOSDAQ `{qr:+.2f}%`  상승 {g(d,'KOSDAQ_UP')} / 하락 {g(d,'KOSDAQ_DN')}",
    ]
    sp_r = float(g(d, 'US_SP_RET') or 0)
    nq_r = float(g(d, 'US_NQ_RET') or 0)
    dj_r = float(g(d, 'US_DJ_RET') or 0)
    if sp_r or nq_r or dj_r:
        spi = "\U0001f4c8" if sp_r >= 0 else "\U0001f4c9"
        nqi = "\U0001f4c8" if nq_r >= 0 else "\U0001f4c9"
        dji_ico = "\U0001f4c8" if dj_r >= 0 else "\U0001f4c9"
        sp_ad = f"  상승 {g(d,'US_SP_UP')} / 하락 {g(d,'US_SP_DN')}" if g(d,'US_SP_UP') else ''
        dj_ad = f"  상승 {g(d,'US_DJ_UP')} / 하락 {g(d,'US_DJ_DN')}" if g(d,'US_DJ_UP') else ''
        lines += [
            "",
            "━━━ 미국 시장 ━━━",
            f"{spi} S\\&P 500  `{sp_r:+.2f}%`{sp_ad}",
            f"{nqi} NASDAQ   `{nq_r:+.2f}%`",
            f"{dji_ico} Dow Jones `{dj_r:+.2f}%`{dj_ad}",
        ]
    reg = g(d, 'REGIME')
    if reg:
        reg_ico = {'상승': '🟢', '중립': '🟡', '하락': '🔴'}.get(reg, '🟡')
        lines += ["", f"━━━ {reg_ico} 시장 레짐: *{reg}* ━━━",
                  f"_{g(d, 'REGIME_ADVICE')}_"]
        if g(d, 'REGIME_VOLWARN') == '1':
            lines.append(f"⚠️ _단기 변동성 높음 \\(연환산 {g(d, 'REGIME_VOL')}%\\) — 분할 매수 권장_")
        if reg == '하락':
            lines.append("⚠️ *약세장 — 추천 종목 수 3개로 축소, 신규 매수 신중*")
    lines += [
        "",
        "━━━ 🟢 안정 대장주 TOP 5 ━━━",
        "_시총 상위 대장주 · 추세건전성+리스크조정 · 섹터 분산 적용_",
        "_수량 = 1,000만원 계좌 · 1% 리스크 기준_",
    ]
    for i in range(5):
        if not g(d, f'S{i}_NAME'):
            break
        lines += [
            "",
            f"{RANK_ICO[i]} *{g(d,f'S{i}_NAME')}* `{g(d,f'S{i}_CODE')}` {g(d,f'S{i}_MKT')} · {g(d,f'S{i}_SECTOR')}{held_mark(d,'S',i)}",
            f"   현재가 `{fi(g(d,f'S{i}_CLOSE'))}원`  주간 `{sp(g(d,f'S{i}_R1W'))}`  12주 `{sp(g(d,f'S{i}_R12W'))}`",
            f"   RSI `{g(d,f'S{i}_RSI')}`  거래량 `{g(d,f'S{i}_VOLR')}배`",
            f"   매수 `{fi(g(d,f'S{i}_ENTRY'))}`  손절 `{fi(g(d,f'S{i}_STOP'))}`({g(d,f'S{i}_STOP_PCT')}%){qty_txt(d,'S',i)}",
            f"   목표1 `{fi(g(d,f'S{i}_T1'))}`(+{g(d,f'S{i}_T1_PCT')}%)  목표2 `{fi(g(d,f'S{i}_T2'))}`(+{g(d,f'S{i}_T2_PCT')}%)",
        ]
    lines += [
        "",
        "━━━ 🔴 단기 모멘텀 TOP 5 ━━━",
        "_전 종목 · 1주·4주·12주 모멘텀 기준 (고변동성 주의)_",
    ]
    for i in range(5):
        if not g(d, f'M{i}_NAME'):
            break
        lines += [
            "",
            f"{RANK_ICO[i]} *{g(d,f'M{i}_NAME')}* `{g(d,f'M{i}_CODE')}` {g(d,f'M{i}_MKT')}{held_mark(d,'M',i)}",
            f"   현재가 `{fi(g(d,f'M{i}_CLOSE'))}원`  주간 `{sp(g(d,f'M{i}_R1W'))}`  12주 `{sp(g(d,f'M{i}_R12W'))}`",
            f"   RSI `{g(d,f'M{i}_RSI')}`  거래량 `{g(d,f'M{i}_VOLR')}배`",
            f"   매수 `{fi(g(d,f'M{i}_ENTRY'))}`  손절 `{fi(g(d,f'M{i}_STOP'))}`({g(d,f'M{i}_STOP_PCT')}%){qty_txt(d,'M',i)}",
            f"   목표1 `{fi(g(d,f'M{i}_T1'))}`(+{g(d,f'M{i}_T1_PCT')}%)  목표2 `{fi(g(d,f'M{i}_T2'))}`(+{g(d,f'M{i}_T2_PCT')}%)",
        ]
    if g(d, 'E0_NAME'):
        lines += [
            "",
            "━━━ 🔵 ETF 추천 TOP 5 ━━━",
            "_퀀트 선정 유망 ETF · 레버리지·인버스 제외_",
        ]
        for i in range(5):
            if not g(d, f'E{i}_NAME'):
                break
            lines += [
                "",
                f"{RANK_ICO[i]} *{g(d,f'E{i}_NAME')}* `{g(d,f'E{i}_CODE')}` {g(d,f'E{i}_MKT')}{held_mark(d,'E',i)}",
                f"   테마 `{g(d,f'E{i}_SECTOR')}`",
                f"   현재가 `{fi(g(d,f'E{i}_CLOSE'))}원`  주간 `{sp(g(d,f'E{i}_R1W'))}`  12주 `{sp(g(d,f'E{i}_R12W'))}`",
                f"   RSI `{g(d,f'E{i}_RSI')}`  거래량 `{g(d,f'E{i}_VOLR')}배`",
                f"   매수 `{fi(g(d,f'E{i}_ENTRY'))}`  손절 `{fi(g(d,f'E{i}_STOP'))}`({g(d,f'E{i}_STOP_PCT')}%){qty_txt(d,'E',i)}",
                f"   목표1 `{fi(g(d,f'E{i}_T1'))}`(+{g(d,f'E{i}_T1_PCT')}%)  목표2 `{fi(g(d,f'E{i}_T2'))}`(+{g(d,f'E{i}_T2_PCT')}%)",
            ]
    lines += ["", "⚠️ _퀀트 모델 자동 산출 — 투자 손익 책임은 본인에게 있습니다_"]
    return '\n'.join(lines)


def build_performance_section(d):
    """과거 추천 성과 리포트 섹션 (track_performance.py 집계 기반)."""
    weeks = g(d, 'PERF_WEEKS')
    if not weeks:
        return ''
    MODELS = [('S', '🟢 안정 대장주'), ('M', '🔴 단기 모멘텀'),
              ('E', '🔵 ETF 추천'), ('I', '🟣 기관연동')]
    HIT_ICO = {'target2': '🏆', 'target1': '🎯', 'stop': '⛔', '': '▶'}

    kospi = g(d, 'PERF_KOSPI_RET1W')
    lines = [
        "🎯 *지난 추천 성과 리포트*",
        f"_추천 시점 종가 대비 실제 수익률 · 최근 {weeks}회 추천 누적_",
    ]
    if kospi:
        lines.append(f"_같은 기간 KOSPI 1주 평균 `{sp(kospi)}`_")

    for m, label in MODELS:
        if not g(d, f'PERF_{m}_N'):
            continue
        lines += ["", f"━━━ {label} ━━━"]
        row1 = f"1주 평균 `{sp(g(d, f'PERF_{m}_RET1W'))}`  승률 `{g(d, f'PERF_{m}_WIN1W')}%`"
        if g(d, f'PERF_{m}_EXCESS1W'):
            row1 += f"  KOSPI 대비 `{sp(g(d, f'PERF_{m}_EXCESS1W'))}p`"
        lines.append(row1)
        row2_parts = []
        if g(d, f'PERF_{m}_RET4W'):
            row2_parts.append(f"4주 평균 `{sp(g(d, f'PERF_{m}_RET4W'))}`")
        if g(d, f'PERF_{m}_T1HIT'):
            row2_parts.append(f"목표 달성 `{g(d, f'PERF_{m}_T1HIT')}%`")
        if g(d, f'PERF_{m}_STOPHIT'):
            row2_parts.append(f"손절 `{g(d, f'PERF_{m}_STOPHIT')}%`")
        if row2_parts:
            lines.append('  '.join(row2_parts))
        best  = g(d, f'PERF_{m}_BEST').split('|')
        worst = g(d, f'PERF_{m}_WORST').split('|')
        if len(best) == 2 and len(worst) == 2:
            lines.append(f"최고 {best[0]} `{sp(best[1])}` / 최저 {worst[0]} `{sp(worst[1])}`")

    last_date = g(d, 'PERF_LAST_DATE')
    has_last  = any(g(d, f'PERF_LAST_{m}_COUNT') for m, _ in MODELS)
    if last_date and has_last:
        lines += ["", f"━━━ 📅 직전 추천({last_date}) 결과 ━━━"]
        for m, label in MODELS:
            cnt = int(g(d, f'PERF_LAST_{m}_COUNT') or 0)
            if cnt == 0:
                continue
            rows = []
            for i in range(cnt):
                v = g(d, f'PERF_LAST_{m}_{i}')
                if not v:
                    continue
                p    = v.split('|')
                name = p[0]
                ret  = p[2] if len(p) > 2 else ''
                hit  = p[3] if len(p) > 3 else ''
                rows.append(f"{HIT_ICO.get(hit, '▶')} {name} `{sp(ret)}`")
            if rows:
                lines += ["", f"{label}"] + rows
        lines += ["", "_🏆 목표② 🎯 목표① ⛔ 손절 ▶ 평가중 (추천 후 20거래일 기준)_"]

    lines += ["", "⚠️ _퀀트 모델 자동 산출 — 투자 손익 책임은 본인에게 있습니다_"]
    return '\n'.join(lines)


def build_institutional_section(d):
    """글로벌 기관 포트폴리오 동향 섹션 (텔레그램 메시지)."""
    inst_count = int(g(d, 'INST_COUNT') or 0)
    if inst_count == 0:
        return ''
    lines = [
        "🌍 *글로벌 기관 포트폴리오 동향*",
        "_SEC 13F 공시 기반 · 분기별 업데이트_",
    ]
    for j in range(min(inst_count, 11)):
        name   = g(d, f'INST{j}_NAME')
        if not name:
            break
        period  = g(d, f'INST{j}_PERIOD')
        sectors = g(d, f'INST{j}_TOP3_SECTORS').replace('|', '  ')
        holds   = g(d, f'INST{j}_TOP3_HOLD').replace('|', ' / ')
        lines += [
            "",
            f"*{name}* _{period} 기준_",
            f"   섹터: `{sectors}`",
            f"   TOP3: `{holds}`",
        ]
    lines += ["", "⚠️ _퀀트 모델 자동 산출 — 투자 손익 책임은 본인에게 있습니다_"]
    return '\n'.join(lines)


def build_inst_korean_section(d):
    """기관 연동 한국 종목 TOP5 섹션."""
    if not g(d, 'I0_NAME'):
        return ''
    lines = [
        "📍 *기관 연동 한국 종목 TOP 5*",
        "_글로벌 기관 섹터 집중도 연동 퀀트 선정_",
    ]
    for i in range(5):
        if not g(d, f'I{i}_NAME'):
            break
        lines += [
            "",
            f"{RANK_ICO[i]} *{g(d,f'I{i}_NAME')}* `{g(d,f'I{i}_CODE')}` {g(d,f'I{i}_MKT')} · {g(d,f'I{i}_SECTOR')}{held_mark(d,'I',i)}",
            f"   현재가 `{fi(g(d,f'I{i}_CLOSE'))}원`  주간 `{sp(g(d,f'I{i}_R1W'))}`  12주 `{sp(g(d,f'I{i}_R12W'))}`",
            f"   RSI `{g(d,f'I{i}_RSI')}`  거래량 `{g(d,f'I{i}_VOLR')}배`",
            f"   매수 `{fi(g(d,f'I{i}_ENTRY'))}`  손절 `{fi(g(d,f'I{i}_STOP'))}`({g(d,f'I{i}_STOP_PCT')}%){qty_txt(d,'I',i)}",
            f"   목표1 `{fi(g(d,f'I{i}_T1'))}`(+{g(d,f'I{i}_T1_PCT')}%)  목표2 `{fi(g(d,f'I{i}_T2'))}`(+{g(d,f'I{i}_T2_PCT')}%)",
        ]
    lines += ["", "⚠️ _퀀트 모델 자동 산출 — 투자 손익 책임은 본인에게 있습니다_"]
    return '\n'.join(lines)


def build_kr_investor_section(d):
    """한국 외국인/기관/개인 종목별 순매수/매도 TOP5 메시지."""
    fb  = int(g(d, 'KR_FOREIGN_BUY_COUNT')  or 0)
    fs  = int(g(d, 'KR_FOREIGN_SELL_COUNT') or 0)
    ib  = int(g(d, 'KR_INST_BUY_COUNT')     or 0)
    is_ = int(g(d, 'KR_INST_SELL_COUNT')    or 0)
    pb  = int(g(d, 'KR_INDIV_BUY_COUNT')    or 0)
    ps  = int(g(d, 'KR_INDIV_SELL_COUNT')   or 0)
    if fb == 0 and fs == 0 and ib == 0 and is_ == 0 and pb == 0 and ps == 0:
        return ''

    lines = ["🇰🇷 *한국 시장 외국인/기관/개인 매매 동향*",
             "_당일 순매수/매도 거래대금 기준 \\(KRX 공식 데이터\\)_"]

    def _stock_rows(prefix, count):
        rows = []
        for i in range(min(count, 5)):
            v = g(d, f'{prefix}{i}')
            if not v: continue
            p = v.split('|')
            name  = p[0]; code = p[1] if len(p) > 1 else ''
            net_b = int(p[2]) if len(p) > 2 else 0
            rows.append(f"{RANK_ICO[i]} *{name}* `{code}`  `{net_b:,}억원`")
        return rows

    if fb > 0:
        lines += ["", "━━━ 🌏 외국인 순매수 TOP5 📈 ━━━"]
        lines += _stock_rows('KR_FOREIGN_BUY_', fb)
    if fs > 0:
        lines += ["", "━━━ 🌏 외국인 순매도 TOP5 📉 ━━━"]
        lines += _stock_rows('KR_FOREIGN_SELL_', fs)
    if ib > 0:
        lines += ["", "━━━ 🏦 기관 순매수 TOP5 📈 ━━━"]
        lines += _stock_rows('KR_INST_BUY_', ib)
    if is_ > 0:
        lines += ["", "━━━ 🏦 기관 순매도 TOP5 📉 ━━━"]
        lines += _stock_rows('KR_INST_SELL_', is_)
    if pb > 0:
        lines += ["", "━━━ 👤 개인 순매수 TOP5 📈 ━━━"]
        lines += _stock_rows('KR_INDIV_BUY_', pb)
    if ps > 0:
        lines += ["", "━━━ 👤 개인 순매도 TOP5 📉 ━━━"]
        lines += _stock_rows('KR_INDIV_SELL_', ps)

    lines += ["", "⚠️ _퀀트 모델 자동 산출 — 투자 손익 책임은 본인에게 있습니다_"]
    return '\n'.join(lines)


def build_inst_changes_section(d):
    """글로벌 기관 전분기 대비 섹터 투자 변화 메시지."""
    count = int(g(d, 'INST_CHNG_COUNT') or 0)
    if count == 0:
        return ''
    lines = [
        "📊 *글로벌 기관 투자 변화 분석*",
        "_전분기 대비 섹터 비중 변화 \\(SEC 13F 비교\\)_",
    ]
    for i in range(min(count, 11)):
        fund   = g(d, f'INST_CHNG_{i}_FUND')
        if not fund:
            break
        period = g(d, f'INST_CHNG_{i}_PERIOD')
        lines += ["", f"*{fund}* _{period} 기준_"]
        for j in range(3):
            sec  = g(d, f'INST_CHNG_{i}_S{j}')
            dval = g(d, f'INST_CHNG_{i}_S{j}_D')
            dir_ = g(d, f'INST_CHNG_{i}_S{j}_DIR')
            if not sec:
                break
            ico = "▲" if '증가' in dir_ else "▼"
            lines.append(f"   {ico} `{sec}` {dval}")
    lines += ["", "⚠️ _퀀트 모델 자동 산출 — 투자 손익 책임은 본인에게 있습니다_"]
    return '\n'.join(lines)


def build_detail(d, pfx, i):
    clean = lambda s: re.sub(r'<[^>]+>', '', s)
    reasons_raw = g(d, f'{pfx}{i}_REASONS')
    reasons = [clean(r) for r in reasons_raw.split('|')] if reasons_raw else []
    caution = clean(g(d, f'{pfx}{i}_CAUTION'))
    model_label = "🟢 안정 대장주" if pfx == 'S' else ("🔵 ETF 추천" if pfx == 'E' else "🔴 모멘텀")
    lines = [
        f"{model_label} {RANK_ICO[i]} *{g(d,f'{pfx}{i}_NAME')}* `{g(d,f'{pfx}{i}_CODE')}` {g(d,f'{pfx}{i}_MKT')}",
        "",
        "*[지표]*",
        f"현재가 `{fi(g(d,f'{pfx}{i}_CLOSE'))}원`  점수 `{g(d,f'{pfx}{i}_SCORE')}`",
        f"주간 `{sp(g(d,f'{pfx}{i}_R1W'))}`  4주 `{sp(g(d,f'{pfx}{i}_R4W'))}`  12주 `{sp(g(d,f'{pfx}{i}_R12W'))}`",
        f"RSI `{g(d,f'{pfx}{i}_RSI')}`  거래량 `{g(d,f'{pfx}{i}_VOLR')}배`",
        f"MA20 `{fi(g(d,f'{pfx}{i}_MA20'))}`  MA60 `{fi(g(d,f'{pfx}{i}_MA60'))}`",
        "",
        "*[매매 레벨]*",
        f"매수  `{fi(g(d,f'{pfx}{i}_ENTRY'))}원`",
        f"손절  `{fi(g(d,f'{pfx}{i}_STOP'))}원` ({g(d,f'{pfx}{i}_STOP_PCT')}%)",
        f"목표1 `{fi(g(d,f'{pfx}{i}_T1'))}원` (+{g(d,f'{pfx}{i}_T1_PCT')}%)",
        f"목표2 `{fi(g(d,f'{pfx}{i}_T2'))}원` (+{g(d,f'{pfx}{i}_T2_PCT')}%)",
    ]
    if reasons:
        lines += ["", "*[선정 이유]*"] + [f"- {r}" for r in reasons[:4]]
    if caution:
        lines += ["", f"⚠️ {caution}"]
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


def send_file(data_file, date):
    report = os.path.join(REPORT_DIR, f'report_{date}.html')
    if not os.path.exists(report):
        report = data_file
    try:
        with open(report, 'rb') as fp:
            r = requests.post(f"{TELEGRAM_API}/sendDocument",
                data={'chat_id': CHAT_ID, 'caption': f"{date} 전체 리포트"},
                files={'document': (os.path.basename(report), fp, 'text/html')},
                timeout=60)
        ok = r.status_code == 200 and r.json().get('ok')
        if not ok:
            print(f"  [파일 실패] {r.text[:150]}")
        return ok
    except requests.exceptions.Timeout:
        print("  파일 업로드 타임아웃")
        return False
    except Exception as e:
        print(f"  파일 오류: {type(e).__name__}")
        return False


def run():
    print("\n" + "="*50)
    print("  텔레그램 리포트 전송")
    print("="*50)

    try:
        r = requests.get(f"{TELEGRAM_API}/getMe", timeout=10)
        bot = r.json().get('result', {}).get('username', '?')
        print(f"  봇 연결 OK: @{bot}")
    except Exception as e:
        print(f"  봇 연결 실패: {e}")
        return

    d    = load_data()
    date = g(d, 'DATE')

    print("  [1] TOP5 요약 전송...")
    ok1 = send_msg(build_summary(d))
    print(f"  -> {'완료' if ok1 else '실패'}")

    perf_msg = build_performance_section(d)
    if perf_msg:
        print("  [1-b] 지난 추천 성과 전송...")
        ok1b = send_msg(perf_msg)
        print(f"  -> {'완료' if ok1b else '실패'}")

    print("  [2] HTML 파일 전송...")
    ok2 = send_file(d['__file__'], date)
    if ok2:
        print("  -> 완료")
    else:
        print("  -> 파일 불가, 종목 상세 텍스트로 대체 전송")
        for pfx, label in [('S','안정'), ('M','모멘텀'), ('E','ETF')]:
            for i in range(5):
                if not g(d, f'{pfx}{i}_NAME'):
                    break
                ok = send_msg(build_detail(d, pfx, i))
                name = g(d, f'{pfx}{i}_NAME')
                print(f"     [{label}] {i+1}. {name}: {'OK' if ok else 'FAIL'}")

    inst_msg = build_institutional_section(d)
    if inst_msg:
        print("  [3] 글로벌 기관 포트폴리오 동향 전송...")
        ok3 = send_msg(inst_msg)
        print(f"  -> {'완료' if ok3 else '실패'}")

    inst_kr_msg = build_inst_korean_section(d)
    if inst_kr_msg:
        print("  [4] 기관연동 한국 종목 TOP5 전송...")
        ok4 = send_msg(inst_kr_msg)
        print(f"  -> {'완료' if ok4 else '실패'}")

    kr_inv_msg = build_kr_investor_section(d)
    if kr_inv_msg:
        print("  [5] 한국 외국인/기관 섹터 매매 동향 전송...")
        ok5 = send_msg(kr_inv_msg)
        print(f"  -> {'완료' if ok5 else '실패'}")

    inst_chng_msg = build_inst_changes_section(d)
    if inst_chng_msg:
        print("  [6] 글로벌 기관 투자 변화 전송...")
        ok6 = send_msg(inst_chng_msg)
        print(f"  -> {'완료' if ok6 else '실패'}")

    print("\n  전송 완료! 텔레그램을 확인하세요.")
    print("="*50)


if __name__ == '__main__':
    run()
