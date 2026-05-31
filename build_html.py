"""
build_html.py  -  weekly_full_DATE.html -> 최종 리포트 HTML
레이아웃: 시장요약 → 전체요약표 → 기관포트폴리오 → 모델별 상세카드
"""
import os, re
from datetime import datetime, timedelta
import glob

BASE_DIR   = os.path.dirname(os.path.abspath(__file__))
REPORT_DIR = os.path.join(BASE_DIR, 'outputs', 'reports')

patterns  = sorted(glob.glob(os.path.join(REPORT_DIR, 'weekly_full_*.html')), reverse=True)
if not patterns:
    raise FileNotFoundError(f"weekly_full_*.html 파일이 없습니다: {REPORT_DIR}")
DATA_FILE = patterns[0]
date_match = re.search(r'weekly_full_(\d{4}-\d{2}-\d{2})\.html', DATA_FILE)
report_date = date_match.group(1) if date_match else datetime.now().strftime('%Y-%m-%d')
OUT_FILE  = os.path.join(REPORT_DIR, f'report_{report_date}.html')
print(f"  데이터 파일: {DATA_FILE}")

d = {}
with open(DATA_FILE, encoding='utf-8') as f:
    for line in f:
        line = line.rstrip('\n')
        if '=' in line:
            k, _, v = line.partition('=')
            d[k] = v

def g(k):    return d.get(k, '')
def fi(k):
    v = g(k)
    try:    return f'{int(v):,}'
    except: return '-'

def fp_raw(v):
    try:
        fv   = float(v)
        col  = '#e74c3c' if fv >= 0 else '#2980b9'
        sign = '+' if fv >= 0 else ''
        return f'<span style="color:{col};font-weight:700">{sign}{fv}%</span>'
    except:
        return '<span style="color:#aaa">-</span>'

def fp(k): return fp_raw(g(k))

try:
    base_dt      = datetime.strptime(report_date, '%Y-%m-%d')
    days_to_mon  = (7 - base_dt.weekday()) % 7
    if days_to_mon == 0: days_to_mon = 7
    next_mon     = (base_dt + timedelta(days=days_to_mon)).strftime('%Y-%m-%d')
except Exception:
    next_mon = '(다음 월요일)'

today_str = datetime.now().strftime('%Y-%m-%d')

# 모델 색상 팔레트
STABLE_COLORS = ['#16a085','#1abc9c','#27ae60','#2ecc71','#00b4d8']
STABLE_LABELS = ['S1','S2','S3','S4','S5']
STABLE_STARS  = {0:'⭐⭐⭐⭐⭐', 1:'⭐⭐⭐⭐⭐', 2:'⭐⭐⭐⭐⭐', 3:'⭐⭐⭐⭐', 4:'⭐⭐⭐⭐'}

MOM_COLORS = ['#f6a623','#9aa5ae','#c8954a','#5b6bd5','#e85d9a']
MOM_LABELS = ['M1','M2','M3','M4','M5']
MOM_STARS  = {0:'⭐⭐⭐⭐⭐', 1:'⭐⭐⭐⭐⭐', 2:'⭐⭐⭐⭐⭐',
              3:'⭐⭐⭐<br><small style="color:#e65100">변동성↑</small>',
              4:'⭐⭐⭐<br><small style="color:#e65100">변동성↑</small>'}

ETF_COLORS = ['#2980b9','#3498db','#1a6fa8','#5dade2','#0077be']
ETF_LABELS = ['E1','E2','E3','E4','E5']
ETF_STARS  = {0:'⭐⭐⭐⭐⭐', 1:'⭐⭐⭐⭐⭐', 2:'⭐⭐⭐⭐⭐', 3:'⭐⭐⭐⭐', 4:'⭐⭐⭐⭐'}

INST_COLORS = ['#8e44ad','#9b59b6','#7d3c98','#a569bd','#bb8fce']
INST_LABELS = ['I1','I2','I3','I4','I5']
INST_STARS  = {0:'⭐⭐⭐⭐⭐', 1:'⭐⭐⭐⭐⭐', 2:'⭐⭐⭐⭐⭐', 3:'⭐⭐⭐⭐', 4:'⭐⭐⭐⭐'}


def stock_card(pfx, i, colors, labels):
    code    = g(f'{pfx}{i}_CODE')
    name    = g(f'{pfx}{i}_NAME')
    mkt     = g(f'{pfx}{i}_MKT')
    sec     = g(f'{pfx}{i}_SECTOR')
    close   = g(f'{pfx}{i}_CLOSE')
    rsi_val = g(f'{pfx}{i}_RSI')
    macd    = g(f'{pfx}{i}_MACD')
    volr    = g(f'{pfx}{i}_VOLR')
    r1w     = g(f'{pfx}{i}_R1W')
    r4w     = g(f'{pfx}{i}_R4W')
    r12w    = g(f'{pfx}{i}_R12W')
    ma20    = fi(f'{pfx}{i}_MA20')
    ma60    = fi(f'{pfx}{i}_MA60')
    atr     = g(f'{pfx}{i}_ATR')
    entry   = fi(f'{pfx}{i}_ENTRY')
    stop    = fi(f'{pfx}{i}_STOP')
    stop_p  = g(f'{pfx}{i}_STOP_PCT')
    t1      = fi(f'{pfx}{i}_T1')
    t1p     = g(f'{pfx}{i}_T1_PCT')
    t2      = fi(f'{pfx}{i}_T2')
    t2p     = g(f'{pfx}{i}_T2_PCT')
    caution = g(f'{pfx}{i}_CAUTION')
    reasons = g(f'{pfx}{i}_REASONS').split('|') if g(f'{pfx}{i}_REASONS') else []

    try:    rsi = float(rsi_val)
    except: rsi = 50.0
    rsi_cls = 'rsi-ok' if 45 <= rsi <= 65 else 'rsi-warn'

    try:    close_int = int(close)
    except: close_int = 0
    try:    atr_int = int(float(atr))
    except: atr_int = 0

    rc = colors[i]
    rl = labels[i]

    try:
        r1w_col  = '#e74c3c' if float(r1w) >= 0 else '#2980b9'
        r1w_sign = '+' if float(r1w) >= 0 else ''
        r1w_html = f'<span style="color:{r1w_col};font-weight:700">{r1w_sign}{r1w}%</span>'
    except:
        r1w_html = f'{r1w}%'

    reason_li    = ''.join(f'<li>{r}</li>' for r in reasons)
    caution_html = f'<div class="caution">⚠ {caution}</div>' if caution else ''

    return f'''
<div class="card">
  <div class="card-top">
    <div class="rank-dot" style="background:{rc}">{rl}</div>
    <div class="card-title-wrap">
      <div class="card-name">{name}</div>
      <div class="card-meta">{code} &middot; {mkt} &middot; <span class="sector-tag">{sec}</span></div>
    </div>
    <div class="card-price">
      <div class="price-num">{close_int:,}원</div>
      <div style="font-size:13px;font-weight:700">주간 {r1w_html}</div>
    </div>
  </div>
  <div class="card-body">
    <div class="two-col">
      <div class="info-box reason-box">
        <div class="box-label">✅ 선정 이유</div>
        <ul class="reason-list">{reason_li if reason_li else '<li>퀀트 종합점수 상위 선정</li>'}</ul>
      </div>
      <div class="info-box indicator-box">
        <div class="box-label">📊 주요 지표</div>
        <div class="chips">
          <div class="chip"><span class="cl">RSI</span><span class="{rsi_cls}">{rsi_val}</span></div>
          <div class="chip"><span class="cl">MACD 히스토</span><span style="color:#e74c3c;font-weight:700">{macd}</span></div>
          <div class="chip"><span class="cl">거래량 비율</span><span style="color:#e74c3c;font-weight:700">{volr}배</span></div>
          <div class="chip"><span class="cl">4주 수익률</span>{fp_raw(r4w)}</div>
          <div class="chip"><span class="cl">12주 수익률</span>{fp_raw(r12w)}</div>
          <div class="chip"><span class="cl">MA20</span><span>{ma20}원</span></div>
          <div class="chip"><span class="cl">MA60</span><span>{ma60}원</span></div>
          <div class="chip"><span class="cl">ATR(일변동)</span><span style="color:#e65100">{atr_int:,}원</span></div>
        </div>
      </div>
    </div>
    <div class="trade-grid">
      <div class="tc tc-entry"><div class="tl">💰 매수가</div><div class="tv">{entry}원</div><div class="ts">월요일 시초가</div></div>
      <div class="tc tc-stop"><div class="tl">🛑 손절가</div><div class="tv">{stop}원</div><div class="ts">{stop_p}%</div></div>
      <div class="tc tc-t1"><div class="tl">🎯 목표가①</div><div class="tv">{t1}원</div><div class="ts">+{t1p}%</div></div>
      <div class="tc tc-t2"><div class="tl">🏆 목표가②</div><div class="tv">{t2}원</div><div class="ts">+{t2p}%</div></div>
    </div>
    {caution_html}
  </div>
</div>'''


def summary_row(pfx, i, colors, stars_map):
    code  = g(f'{pfx}{i}_CODE')
    name  = g(f'{pfx}{i}_NAME')
    mkt   = g(f'{pfx}{i}_MKT')
    sec   = g(f'{pfx}{i}_SECTOR')
    r1w   = g(f'{pfx}{i}_R1W')
    r12w  = g(f'{pfx}{i}_R12W')
    rsi_v = g(f'{pfx}{i}_RSI')
    volr  = g(f'{pfx}{i}_VOLR')
    entry = fi(f'{pfx}{i}_ENTRY')
    stop  = fi(f'{pfx}{i}_STOP')
    t1    = fi(f'{pfx}{i}_T1')
    t2    = fi(f'{pfx}{i}_T2')
    close = g(f'{pfx}{i}_CLOSE')

    try:    rsi_f = float(rsi_v)
    except: rsi_f = 50.0
    rsi_cls = 'rsi-ok' if 45 <= rsi_f <= 65 else 'rsi-warn'

    try:    close_disp = f'{int(close):,}'
    except: close_disp = close

    rc   = colors[i]
    star = stars_map.get(i, '⭐⭐⭐')
    label = f'{pfx}{i+1}'

    return f'''<tr>
      <td style="font-weight:900;color:{rc};font-size:15px">{label}</td>
      <td class="sn">{name}<br><small style="color:#aaa;font-weight:400">{code} · {mkt}</small></td>
      <td style="font-size:11px">{sec}</td>
      <td class="mono">{close_disp}</td>
      <td>{fp_raw(r1w)}</td>
      <td>{fp_raw(r12w)}</td>
      <td><span class="{rsi_cls}">{rsi_v}</span></td>
      <td style="color:#e74c3c;font-weight:700">{volr}배</td>
      <td class="mono" style="font-weight:800">{entry}</td>
      <td class="mono" style="color:#2980b9">{stop}</td>
      <td class="mono" style="color:#e74c3c">{t1}</td>
      <td class="mono" style="color:#c0392b;font-weight:700">{t2}</td>
      <td>{star}</td>
    </tr>'''


def inst_portfolio_table():
    """글로벌 기관 포트폴리오 동향 테이블 생성"""
    count = int(g('INST_COUNT') or 0)
    if count == 0:
        return '<p style="color:#aaa;text-align:center;padding:24px">기관 포트폴리오 데이터 없음</p>'

    sector_colors = {
        'Technology': '#1565c0', 'Healthcare': '#2e7d32', 'Financials': '#e65100',
        'Energy': '#6a1b9a', 'Consumer': '#c62828', 'Industrials': '#37474f',
        'Real Estate': '#00695c', 'Materials': '#4e342e', 'Communication': '#0277bd',
        'Utilities': '#558b2f', 'Other': '#78909c',
    }

    def sector_badge(s):
        parts = s.split(':')
        label = parts[0].strip() if parts else s
        pct   = parts[1].strip() if len(parts) > 1 else ''
        col   = sector_colors.get(label, '#78909c')
        return f'<span style="background:{col}18;color:{col};border:1px solid {col}44;padding:2px 7px;border-radius:10px;font-size:11px;font-weight:700;white-space:nowrap">{label}<br><b>{pct}</b></span>'

    rows = ''
    for j in range(min(count, 11)):
        name    = g(f'INST{j}_NAME')
        if not name: break
        date_   = g(f'INST{j}_DATE')
        period  = g(f'INST{j}_PERIOD')
        sectors = g(f'INST{j}_TOP3_SECTORS').split('|')
        holds   = g(f'INST{j}_TOP3_HOLD').split('|')
        total   = g(f'INST{j}_TOTAL')

        s_cells = ''.join(f'<td style="text-align:center">{sector_badge(s)}</td>' for s in sectors[:3])
        h_cells = ''.join(
            f'<td style="font-size:11px;font-weight:600;max-width:100px">{h.strip()}</td>'
            for h in holds[:3]
        )

        try:    total_disp = f'{int(total):,}'
        except: total_disp = total

        rows += f'''<tr>
          <td class="sn" style="font-size:13px;font-weight:800">{name}</td>
          <td style="font-size:11px;color:#777">{date_}</td>
          <td style="font-size:11px;color:#555;font-weight:600">{period}</td>
          {s_cells}
          {h_cells}
          <td style="font-size:11px;color:#999;text-align:right">{total_disp}종목</td>
        </tr>'''

    return f'''<div style="overflow-x:auto">
<table class="sum-table">
  <thead><tr>
    <th style="text-align:left;padding-left:14px">기관명</th>
    <th>공시일</th><th>기준분기</th>
    <th>섹터①</th><th>섹터②</th><th>섹터③</th>
    <th>TOP보유①</th><th>TOP보유②</th><th>TOP보유③</th>
    <th>보유수</th>
  </tr></thead>
  <tbody>{rows}</tbody>
</table>
</div>'''


# HTML 조각 생성
stable_cards_html = ''.join(stock_card('S', i, STABLE_COLORS, STABLE_LABELS) for i in range(5))
mom_cards_html    = ''.join(stock_card('M', i, MOM_COLORS, MOM_LABELS) for i in range(5))
stable_rows_html  = ''.join(summary_row('S', i, STABLE_COLORS, STABLE_STARS) for i in range(5))
mom_rows_html     = ''.join(summary_row('M', i, MOM_COLORS, MOM_STARS) for i in range(5))

etf_data_ok    = bool(g('E0_NAME'))
etf_cards_html = (
    ''.join(stock_card('E', i, ETF_COLORS, ETF_LABELS) for i in range(5))
    if etf_data_ok else
    '<p style="color:#aaa;text-align:center;padding:24px">ETF 데이터 없음 — 인터넷 연결 또는 FDR 상태 확인</p>'
)
etf_rows_html = ''.join(summary_row('E', i, ETF_COLORS, ETF_STARS) for i in range(5)) if etf_data_ok else ''

inst_data_ok    = bool(g('I0_NAME'))
inst_cards_html = (
    ''.join(stock_card('I', i, INST_COLORS, INST_LABELS) for i in range(5))
    if inst_data_ok else
    '<p style="color:#aaa;text-align:center;padding:24px">기관연동 데이터 없음</p>'
)
inst_rows_html = ''.join(summary_row('I', i, INST_COLORS, INST_STARS) for i in range(5)) if inst_data_ok else ''

inst_port_table = inst_portfolio_table()

ks_ret = float(g('KOSPI_RET')  or 0)
ks_up  = g('KOSPI_UP');  ks_dn = g('KOSPI_DN')
kd_ret = float(g('KOSDAQ_RET') or 0)
kd_up  = g('KOSDAQ_UP'); kd_dn = g('KOSDAQ_DN')
ks_col = '#e74c3c' if ks_ret >= 0 else '#2980b9'
kd_col = '#e74c3c' if kd_ret >= 0 else '#2980b9'
ks_arr = '▲' if ks_ret >= 0 else '▼'
kd_arr = '▲' if kd_ret >= 0 else '▼'

HTML = f'''<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>주간 퀀트 리포트 | {report_date}</title>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:"Apple SD Gothic Neo","Malgun Gothic","Noto Sans KR",sans-serif;
     background:#eef1f7;color:#1a1a2e;font-size:14px;line-height:1.6}}
.hdr{{background:linear-gradient(135deg,#1a1a2e 0%,#0f3460 100%);
      color:#fff;padding:30px 36px 26px}}
.hdr h1{{font-size:22px;font-weight:800;letter-spacing:-.5px}}
.hdr p{{margin-top:6px;color:#8ab4d4;font-size:12px}}
.hdr-badges{{display:flex;flex-wrap:wrap;gap:8px;margin-top:14px}}
.hbadge{{background:rgba(255,255,255,.13);border:1px solid rgba(255,255,255,.2);
         padding:4px 12px;border-radius:16px;font-size:11px;color:#cde}}
.wrap{{max-width:1200px;margin:0 auto;padding:0 16px}}
.sec{{margin:22px 0}}
.sec-title{{font-size:15px;font-weight:800;color:#1a1a2e;
            border-left:4px solid #0f3460;padding-left:10px;margin-bottom:14px}}
.sec-title-green{{border-left-color:#16a085}}
.sec-title-orange{{border-left-color:#f6a623}}
.sec-title-blue{{border-left-color:#2980b9}}
.sec-title-purple{{border-left-color:#8e44ad}}
.sec-title-global{{border-left-color:#d4ac0d}}
.model-badge{{display:inline-block;padding:3px 10px;border-radius:12px;
              font-size:11px;font-weight:700;margin-left:10px;vertical-align:middle}}
.badge-stable{{background:#e8f8f3;color:#16a085}}
.badge-mom{{background:#fff3e0;color:#e65100}}
.badge-etf{{background:#e3f2fd;color:#1565c0}}
.badge-inst{{background:#f3e5f5;color:#7b1fa2}}
.badge-global{{background:#fef9e7;color:#b7950b}}
.mkt-row{{display:flex;gap:14px}}
.mkt-card{{flex:1;background:#fff;border-radius:12px;padding:20px 24px;
           box-shadow:0 2px 10px rgba(0,0,0,.07)}}
.mkt-label{{font-size:11px;color:#999;margin-bottom:6px;font-weight:600}}
.mkt-val{{font-size:30px;font-weight:900}}
.mkt-sub{{font-size:12px;color:#777;margin-top:6px}}
.summary-block{{background:#fff;border-radius:14px;padding:20px 22px;
                box-shadow:0 2px 10px rgba(0,0,0,.07);margin-bottom:20px}}
.summary-block-title{{font-size:13px;font-weight:800;margin-bottom:12px;
                       padding-bottom:8px;border-bottom:1px solid #f0f0f0}}
.card{{background:#fff;border-radius:14px;
       box-shadow:0 2px 10px rgba(0,0,0,.07);overflow:hidden;margin-bottom:18px}}
.card-top{{display:flex;align-items:center;gap:14px;padding:18px 22px 16px;
           border-bottom:1px solid #f0f0f0}}
.rank-dot{{width:44px;height:44px;border-radius:50%;display:flex;
           align-items:center;justify-content:center;
           font-size:14px;font-weight:900;color:#fff;flex-shrink:0}}
.card-title-wrap{{flex:1}}
.card-name{{font-size:19px;font-weight:900;letter-spacing:-.3px}}
.card-meta{{font-size:12px;color:#999;margin-top:3px}}
.sector-tag{{background:#e8f0ff;color:#0f3460;padding:2px 9px;
             border-radius:10px;font-weight:700;font-size:11px}}
.card-price{{text-align:right}}
.price-num{{font-size:22px;font-weight:900}}
.card-body{{padding:18px 22px}}
.info-box{{border-radius:10px;padding:14px 16px;margin-bottom:14px}}
.box-label{{font-size:11px;font-weight:700;color:#0f3460;
            text-transform:uppercase;letter-spacing:.5px;margin-bottom:8px}}
.two-col{{display:grid;grid-template-columns:1fr 1fr;gap:14px;margin-bottom:14px}}
@media(max-width:680px){{.two-col{{grid-template-columns:1fr}}}}
.reason-box{{background:#fffbf0;border-left:4px solid #f9a825}}
.reason-list{{list-style:none;margin-top:4px}}
.reason-list li{{font-size:13px;color:#444;padding:4px 0 4px 20px;
                 position:relative;line-height:1.6}}
.reason-list li::before{{content:"✓";position:absolute;left:0;
                         color:#f9a825;font-weight:800}}
.indicator-box{{background:#f4fdff;border-left:4px solid #00b4d8}}
.chips{{display:flex;flex-wrap:wrap;gap:8px;margin-top:4px}}
.chip{{background:#fff;border:1px solid #e0e0e0;border-radius:8px;
       padding:6px 11px;font-size:12px}}
.chip .cl{{display:block;color:#aaa;font-size:10px;margin-bottom:1px}}
.rsi-ok{{color:#2e7d32;font-weight:700;background:#e8f5e9;
         padding:1px 6px;border-radius:4px}}
.rsi-warn{{color:#e65100;font-weight:700;background:#fff3e0;
           padding:1px 6px;border-radius:4px}}
.trade-grid{{display:grid;grid-template-columns:repeat(4,1fr);
             border-radius:10px;overflow:hidden;border:1px solid #eee}}
@media(max-width:540px){{.trade-grid{{grid-template-columns:repeat(2,1fr)}}}}
.tc{{padding:14px 12px;text-align:center;border-right:1px solid #f0f0f0}}
.tc:last-child{{border-right:none}}
.tl{{font-size:11px;font-weight:600;color:#999;margin-bottom:6px}}
.tv{{font-size:18px;font-weight:900;font-family:monospace}}
.ts{{font-size:11px;margin-top:4px;font-weight:600}}
.tc-entry{{background:#f8f9ff}}.tc-entry .tv{{color:#1a1a2e}}
.tc-stop{{background:#eef4ff}}.tc-stop .tv,.tc-stop .ts{{color:#2980b9}}
.tc-t1{{background:#fff5f5}}.tc-t1 .tv,.tc-t1 .ts{{color:#e74c3c}}
.tc-t2{{background:#fff0ee}}.tc-t2 .tv,.tc-t2 .ts{{color:#c0392b}}
.caution{{background:#fff3e0;border-left:3px solid #ff9800;border-radius:6px;
          padding:10px 14px;font-size:12px;color:#e65100;margin-top:12px}}
.sum-table{{width:100%;border-collapse:collapse;background:#fff;
            border-radius:12px;overflow:hidden;box-shadow:0 2px 10px rgba(0,0,0,.07)}}
.sum-table th{{background:#1a1a2e;color:#fff;padding:11px 10px;
               font-size:11px;text-align:center;white-space:nowrap}}
.sum-table td{{padding:11px 10px;border-bottom:1px solid #f2f2f2;
               text-align:center;font-size:13px;vertical-align:middle}}
.sum-table tr:last-child td{{border-bottom:none}}
.sum-table tr:hover td{{background:#f7f9ff}}
.sn{{text-align:left !important;padding-left:14px !important;font-weight:700}}
.mono{{font-family:monospace;font-size:12px}}
.left{{text-align:left !important;font-weight:600}}
.notice{{background:#fff8e1;border-left:4px solid #f9a825;
         border-radius:8px;padding:14px 18px;font-size:12px;
         color:#666;line-height:1.9;margin-top:0}}
.model-intro{{background:#fff;border-radius:12px;padding:14px 18px;
              margin-bottom:16px;box-shadow:0 1px 6px rgba(0,0,0,.06);font-size:13px}}
.divider{{height:2px;background:linear-gradient(90deg,#0f3460,transparent);
          margin:32px 0;border-radius:2px;opacity:.3}}
.footer{{text-align:center;padding:24px;color:#bbb;font-size:11px}}
</style>
</head>
<body>

<div class="hdr">
  <h1>📊 주간 퀀트 리포트 — {report_date}</h1>
  <p>기준일: {report_date} (금요일 마감) &nbsp;|&nbsp; 차주 월요일({next_mon}) 투자 전략</p>
  <div class="hdr-badges">
    <span class="hbadge">🟢 안정 대장주 TOP5</span>
    <span class="hbadge">🔴 단기 모멘텀 TOP5</span>
    <span class="hbadge">🔵 ETF 추천 TOP5</span>
    <span class="hbadge">🟣 기관연동 한국종목 TOP5</span>
    <span class="hbadge">🌍 글로벌 기관 포트폴리오</span>
    <span class="hbadge">🤖 퀀트 모델 자동 산출</span>
  </div>
</div>

<div class="wrap">

<!-- ① 시장 요약 -->
<div class="sec">
  <div class="sec-title">📈 이번 주 시장 요약</div>
  <div class="mkt-row">
    <div class="mkt-card">
      <div class="mkt-label">KOSPI</div>
      <div class="mkt-val" style="color:{ks_col}">{ks_arr} {ks_ret:+.2f}%</div>
      <div class="mkt-sub">상승 <b style="color:#e74c3c">{ks_up}</b>종목 &nbsp; 하락 <b style="color:#2980b9">{ks_dn}</b>종목</div>
    </div>
    <div class="mkt-card">
      <div class="mkt-label">KOSDAQ</div>
      <div class="mkt-val" style="color:{kd_col}">{kd_arr} {kd_ret:+.2f}%</div>
      <div class="mkt-sub">상승 <b style="color:#e74c3c">{kd_up}</b>종목 &nbsp; 하락 <b style="color:#2980b9">{kd_dn}</b>종목</div>
    </div>
  </div>
</div>

<!-- ② 전체 요약표 모음 -->
<div class="sec">
  <div class="sec-title">📋 종목 추천 요약표</div>

  <!-- 안정 대장주 요약 -->
  <div class="summary-block">
    <div class="summary-block-title" style="color:#16a085">🟢 안정 대장주 TOP 5 <span class="model-badge badge-stable">시총 상위 · 추세건전성+리스크조정</span></div>
    <div style="overflow-x:auto">
    <table class="sum-table">
      <thead><tr>
        <th>#</th>
        <th style="text-align:left;padding-left:14px">종목명</th>
        <th>업종</th><th>현재가</th><th>주간</th><th>12주</th>
        <th>RSI</th><th>거래량</th><th>매수가</th><th>손절가</th><th>목표①</th><th>목표②</th><th>접근</th>
      </tr></thead>
      <tbody>{stable_rows_html}</tbody>
    </table>
    </div>
  </div>

  <!-- 단기 모멘텀 요약 -->
  <div class="summary-block">
    <div class="summary-block-title" style="color:#e65100">🔴 단기 모멘텀 TOP 5 <span class="model-badge badge-mom">전 종목 · 고변동성 주의</span></div>
    <div style="overflow-x:auto">
    <table class="sum-table">
      <thead><tr>
        <th>#</th>
        <th style="text-align:left;padding-left:14px">종목명</th>
        <th>업종</th><th>현재가</th><th>주간</th><th>12주</th>
        <th>RSI</th><th>거래량</th><th>매수가</th><th>손절가</th><th>목표①</th><th>목표②</th><th>접근</th>
      </tr></thead>
      <tbody>{mom_rows_html}</tbody>
    </table>
    </div>
  </div>

  <!-- ETF 요약 -->
  <div class="summary-block">
    <div class="summary-block-title" style="color:#1565c0">🔵 ETF 추천 TOP 5 <span class="model-badge badge-etf">퀀트 선정 · 레버리지·인버스 제외</span></div>
    <div style="overflow-x:auto">
    <table class="sum-table">
      <thead><tr>
        <th>#</th>
        <th style="text-align:left;padding-left:14px">ETF명</th>
        <th>테마</th><th>현재가</th><th>주간</th><th>12주</th>
        <th>RSI</th><th>거래량</th><th>매수가</th><th>손절가</th><th>목표①</th><th>목표②</th><th>접근</th>
      </tr></thead>
      <tbody>{etf_rows_html if etf_rows_html else '<tr><td colspan="13" style="color:#aaa;padding:20px">ETF 데이터 없음</td></tr>'}</tbody>
    </table>
    </div>
  </div>

  <!-- 기관연동 한국 종목 요약 -->
  <div class="summary-block">
    <div class="summary-block-title" style="color:#7b1fa2">🟣 기관연동 한국 종목 TOP 5 <span class="model-badge badge-inst">글로벌 기관 섹터 신호 + 기술적 지표</span></div>
    <div style="overflow-x:auto">
    <table class="sum-table">
      <thead><tr>
        <th>#</th>
        <th style="text-align:left;padding-left:14px">종목명</th>
        <th>업종</th><th>현재가</th><th>주간</th><th>12주</th>
        <th>RSI</th><th>거래량</th><th>매수가</th><th>손절가</th><th>목표①</th><th>목표②</th><th>접근</th>
      </tr></thead>
      <tbody>{inst_rows_html if inst_rows_html else '<tr><td colspan="13" style="color:#aaa;padding:20px">기관연동 데이터 없음</td></tr>'}</tbody>
    </table>
    </div>
  </div>
</div>

<!-- ③ 글로벌 기관 포트폴리오 동향 -->
<div class="sec">
  <div class="sec-title sec-title-global">🌍 글로벌 기관투자자 포트폴리오 동향 <span class="model-badge badge-global">SEC EDGAR 13F 공시 · 분기 기준</span></div>
  <div class="model-intro">
    📌 <b>데이터 출처</b>: 미국 SEC EDGAR 13F-HR 분기 공시 (AUM $100M 이상 기관 의무 보고)<br>
    ✅ <b>활용 방법</b>: 글로벌 스마트머니의 섹터 집중도를 확인하고, 동일 방향성의 한국 종목(기관연동 모델)에 가중치 부여
  </div>
  {inst_port_table}
</div>

<div class="divider"></div>

<!-- ④ 모델별 상세 카드 -->

<!-- 안정 대장주 상세 -->
<div class="sec">
  <div class="sec-title sec-title-green">🟢 안정 대장주 TOP 5 — 상세 분석 <span class="model-badge badge-stable">시총 상위 · 추세건전성+리스크조정</span></div>
  <div class="model-intro">
    📌 <b>선정 기준</b>: 시총 상위 350위 이내(업종별 대장주) 중 ①MA 정배열+이격률(35%) ②변동성 대비 수익률(30%) ③RSI·MACD·거래량 안정성(25%) ④12주 모멘텀(10%) 종합 평가<br>
    ✅ <b>특징</b>: 손절폭 8~12%, 일일 변동성 ≤5%, 안정적 중장기 투자에 적합
  </div>
  {stable_cards_html}
</div>

<!-- 단기 모멘텀 상세 -->
<div class="sec">
  <div class="sec-title sec-title-orange">🔴 단기 모멘텀 TOP 5 — 상세 분석 <span class="model-badge badge-mom">전 종목 · 1주·4주·12주 모멘텀</span></div>
  <div class="model-intro">
    📌 <b>선정 기준</b>: 전 종목 대상 ①1주·4주·12주 수익률 모멘텀(35%) ②거래량(20%) ③추세(25%) ④RSI·MACD(20%) 종합 평가<br>
    ⚠️ <b>주의</b>: 단기 급등 종목 포함, 고변동성·높은 손절폭 가능성 — 소량 분할 접근 권장
  </div>
  {mom_cards_html}
</div>

<!-- ETF 추천 상세 -->
<div class="sec">
  <div class="sec-title sec-title-blue">🔵 ETF 추천 TOP 5 — 상세 분석 <span class="model-badge badge-etf">퀀트 선정 · 레버리지·인버스 제외</span></div>
  <div class="model-intro">
    📌 <b>선정 기준</b>: 전체 ETF 대상(레버리지·인버스 제외) ①MA 추세(40%) ②변동성 대비 수익률(30%) ③RSI·MACD(20%) ④12주 모멘텀(10%) 종합 평가<br>
    ✅ <b>특징</b>: 분산 투자 효과, 일일 변동성 ≤4%, 중장기 보유에 적합
  </div>
  {etf_cards_html}
</div>

<!-- 기관연동 한국 종목 상세 -->
<div class="sec">
  <div class="sec-title sec-title-purple">🟣 기관연동 한국 종목 TOP 5 — 상세 분석 <span class="model-badge badge-inst">글로벌 기관 섹터 신호 + 기술적 지표</span></div>
  <div class="model-intro">
    📌 <b>선정 기준</b>: 안정 대장주 모델 베이스 + 글로벌 11개 기관 섹터 집중도 보너스(최대 +0.15) 적용 — 기관 집중 섹터와 일치하는 한국 종목 우선 선발<br>
    ✅ <b>특징</b>: 글로벌 스마트머니 방향성과 한국 기술적 지표를 결합한 복합 모델
  </div>
  {inst_cards_html}
</div>

<!-- 투자 원칙 -->
<div class="notice">
  ⚠️ <b>실전 투자 원칙</b><br>
  • <b>안정 모델 우선</b> : 장기적으로 변동성이 낮은 안정 대장주 모델 위주로 투자<br>
  • <b>모멘텀 모델 소량</b> : 고변동성 종목은 투자금의 3~5% 이하 소량만 접근<br>
  • <b>손절 필수</b> : 손절가 도달 시 감정 개입 없이 즉시 매도<br>
  • <b>분할 매도</b> : 목표① 도달 시 절반 이상 매도해 수익 확정 후 목표② 추구<br>
  • 본 리포트는 퀀트 모델로 자동 생성된 참고 자료이며, <b>투자 손익 책임은 본인에게 있습니다</b>
</div>

</div>
<div class="footer">InitialTrading Weekly Quant Engine &nbsp;|&nbsp; 기준일: {report_date} &nbsp;|&nbsp; {today_str} 생성</div>
</body></html>'''

with open(OUT_FILE, 'w', encoding='utf-8') as f:
    f.write(HTML)
print(f'OK: {OUT_FILE}')
