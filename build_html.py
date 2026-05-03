"""
build_html.py  -  weekly_full_DATE.html 데이터 파일을 읽어 최종 리포트 HTML 생성
"""
import os, re
from datetime import datetime, timedelta
import glob

BASE_DIR   = os.path.dirname(os.path.abspath(__file__))
REPORT_DIR = os.path.join(BASE_DIR, 'outputs', 'reports')

# ── 최신 데이터 파일 자동 탐색 ─────────────────────────
patterns  = sorted(glob.glob(os.path.join(REPORT_DIR, 'weekly_full_*.html')), reverse=True)
if not patterns:
    raise FileNotFoundError(f"weekly_full_*.html 파일이 없습니다: {REPORT_DIR}")
DATA_FILE = patterns[0]
date_match = re.search(r'weekly_full_(\d{4}-\d{2}-\d{2})\.html', DATA_FILE)
report_date = date_match.group(1) if date_match else datetime.now().strftime('%Y-%m-%d')

OUT_FILE  = os.path.join(REPORT_DIR, f'report_{report_date}.html')

print(f"  데이터 파일: {DATA_FILE}")

# ── 파일 파싱 ──────────────────────────────────────────
d = {}
port_rows = []
with open(DATA_FILE, encoding='utf-8') as f:
    for line in f:
        line = line.rstrip('\n')
        if line.startswith('PORT|'):
            parts = line.split('|')
            port_rows.append(parts[1:])
        elif '=' in line:
            k, _, v = line.partition('=')
            d[k] = v

def g(k):    return d.get(k, '')
def fi(k):
    v = g(k)
    try:    return f'{int(v):,}'
    except: return '-'

def fp_raw(v):
    try:
        fv  = float(v)
        col  = '#e74c3c' if fv >= 0 else '#2980b9'
        sign = '+' if fv >= 0 else ''
        return f'<span style="color:{col};font-weight:700">{sign}{fv}%</span>'
    except:
        return '<span style="color:#aaa">-</span>'

def fp(k):
    return fp_raw(g(k))

# ── 차주 월요일 계산 ───────────────────────────────────
try:
    base_dt   = datetime.strptime(report_date, '%Y-%m-%d')
    days_to_mon = (7 - base_dt.weekday()) % 7
    if days_to_mon == 0:
        days_to_mon = 7
    next_mon  = (base_dt + timedelta(days=days_to_mon)).strftime('%Y-%m-%d')
except Exception:
    next_mon  = '(다음 월요일)'

today_str = datetime.now().strftime('%Y-%m-%d')

RANK_COLORS = ['#f6a623','#9aa5ae','#c8954a','#5b6bd5','#3aab6e']
RANK_LABEL  = ['1','2','3','4','5']
STAR_RATINGS = {0:'⭐⭐⭐⭐⭐', 1:'⭐⭐⭐⭐⭐', 2:'⭐⭐⭐⭐⭐',
                3:'⭐⭐⭐<br><small style="color:#e65100">변동성↑</small>',
                4:'⭐⭐⭐<br><small style="color:#e65100">RSI주의</small>'}

# ── 종목 카드 ──────────────────────────────────────────
def stock_card(i):
    code    = g(f'S{i}_CODE')
    name    = g(f'S{i}_NAME')
    mkt     = g(f'S{i}_MKT')
    sec     = g(f'S{i}_SECTOR')
    desc    = g(f'S{i}_DESC')
    score   = g(f'S{i}_SCORE')
    close   = g(f'S{i}_CLOSE')
    rsi_val = g(f'S{i}_RSI')
    macd    = g(f'S{i}_MACD')
    volr    = g(f'S{i}_VOLR')
    r1w     = g(f'S{i}_R1W')
    r4w     = g(f'S{i}_R4W')
    r12w    = g(f'S{i}_R12W')
    ma20    = fi(f'S{i}_MA20')
    ma60    = fi(f'S{i}_MA60')
    atr     = g(f'S{i}_ATR')
    entry   = fi(f'S{i}_ENTRY')
    stop    = fi(f'S{i}_STOP')
    stop_p  = g(f'S{i}_STOP_PCT')
    t1      = fi(f'S{i}_T1')
    t1p     = g(f'S{i}_T1_PCT')
    t2      = fi(f'S{i}_T2')
    t2p     = g(f'S{i}_T2_PCT')
    caution = g(f'S{i}_CAUTION')
    reasons_raw = g(f'S{i}_REASONS')
    reasons = reasons_raw.split('|') if reasons_raw else []

    try:    rsi = float(rsi_val)
    except: rsi = 50.0
    rsi_cls  = 'rsi-ok' if 45 <= rsi <= 65 else 'rsi-warn'

    try:    close_int = int(close)
    except: close_int = 0
    try:    atr_int = int(float(atr))
    except: atr_int = 0

    rc = RANK_COLORS[i]

    reason_li    = ''.join(f'<li>{r}</li>' for r in reasons)
    caution_html = f'<div class="caution">⚠ {caution}</div>' if caution else ''

    # r1w color
    try:
        r1w_col = '#e74c3c' if float(r1w) >= 0 else '#2980b9'
        r1w_sign = '+' if float(r1w) >= 0 else ''
        r1w_html = f'<span style="color:{r1w_col};font-weight:700">{r1w_sign}{r1w}%</span>'
    except:
        r1w_html = f'{r1w}%'

    return f'''
<div class="card">
  <div class="card-top">
    <div class="rank-dot" style="background:{rc}">{RANK_LABEL[i]}</div>
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
    <div class="info-box company-box">
      <div class="box-label">🏢 회사 소개</div>
      <p class="company-desc">{desc if desc else f'{name} — 종목 코드 {code}'}</p>
    </div>

    <div class="two-col">
      <div class="info-box reason-box">
        <div class="box-label">✅ 선정 이유</div>
        <ul class="reason-list">{reason_li if reason_li else '<li>퀀트 종합점수 상위 선정</li>'}</ul>
      </div>

      <div class="info-box indicator-box">
        <div class="box-label">📊 주요 지표</div>
        <div class="chips">
          <div class="chip"><span class="cl">RSI</span><span class="{rsi_cls}">{rsi_val}</span></div>
          <div class="chip"><span class="cl">MACD 히스토그램</span><span style="color:#e74c3c;font-weight:700">{macd}</span></div>
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
      <div class="tc tc-t1"><div class="tl">🎯 목표가 ①</div><div class="tv">{t1}원</div><div class="ts">+{t1p}% · RR 1.5</div></div>
      <div class="tc tc-t2"><div class="tl">🏆 목표가 ②</div><div class="tv">{t2}원</div><div class="ts">+{t2p}% · RR 2.5</div></div>
    </div>
    {caution_html}
  </div>
</div>'''

stocks_html = ''.join(stock_card(i) for i in range(5))

# ── 포트폴리오 행 ──────────────────────────────────────
port_html = ''
for row in port_rows:
    if len(row) >= 4:
        nm, code, price, ret = row[0], row[1], row[2], row[3]
        price_disp = f'{int(price):,}원' if price not in ('-','') else '-'
        port_html += (f'<tr><td class="left">{nm}</td>'
                      f'<td class="mono">{code}</td>'
                      f'<td class="mono">{price_disp}</td>'
                      f'<td>{fp_raw(ret)}</td></tr>')

# ── 동적 summary 테이블 ─────────────────────────────────
def summary_row(i):
    code  = g(f'S{i}_CODE')
    name  = g(f'S{i}_NAME')
    mkt   = g(f'S{i}_MKT')
    sec   = g(f'S{i}_SECTOR')
    close = g(f'S{i}_CLOSE')
    r1w   = g(f'S{i}_R1W')
    r12w  = g(f'S{i}_R12W')
    rsi_v = g(f'S{i}_RSI')
    volr  = g(f'S{i}_VOLR')
    entry = fi(f'S{i}_ENTRY')
    stop  = fi(f'S{i}_STOP')
    t1    = fi(f'S{i}_T1')
    t2    = fi(f'S{i}_T2')

    try:    rsi_f = float(rsi_v)
    except: rsi_f = 50.0
    rsi_cls = 'rsi-ok' if 45 <= rsi_f <= 65 else 'rsi-warn'

    try:    close_disp = f'{int(close):,}'
    except: close_disp = close

    star = STAR_RATINGS.get(i, '⭐⭐⭐⭐⭐')
    rc   = RANK_COLORS[i]
    rank_num = i + 1

    return f'''<tr>
        <td style="font-weight:900;color:{rc};font-size:16px">{rank_num}</td>
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

summary_rows_html = ''.join(summary_row(i) for i in range(5))

# ── 시장 요약 ──────────────────────────────────────────
ks_ret = float(g('KOSPI_RET')  or 0)
ks_up  = g('KOSPI_UP')
ks_dn  = g('KOSPI_DN')
kd_ret = float(g('KOSDAQ_RET') or 0)
kd_up  = g('KOSDAQ_UP')
kd_dn  = g('KOSDAQ_DN')

ks_col = '#e74c3c' if ks_ret >= 0 else '#2980b9'
kd_col = '#e74c3c' if kd_ret >= 0 else '#2980b9'
ks_arr = '▲' if ks_ret >= 0 else '▼'
kd_arr = '▲' if kd_ret >= 0 else '▼'

# ── 최종 HTML ──────────────────────────────────────────
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

.wrap{{max-width:1100px;margin:0 auto;padding:0 16px}}
.sec{{margin:22px 0}}
.sec-title{{font-size:15px;font-weight:800;color:#1a1a2e;
            border-left:4px solid #0f3460;padding-left:10px;margin-bottom:14px}}

.mkt-row{{display:flex;gap:14px}}
.mkt-card{{flex:1;background:#fff;border-radius:12px;padding:20px 24px;
           box-shadow:0 2px 10px rgba(0,0,0,.07)}}
.mkt-label{{font-size:11px;color:#999;margin-bottom:6px;font-weight:600;text-transform:uppercase}}
.mkt-val{{font-size:30px;font-weight:900}}
.mkt-sub{{font-size:12px;color:#777;margin-top:6px}}

.terms-wrap{{background:#fff;border-radius:12px;overflow:hidden;
             box-shadow:0 2px 10px rgba(0,0,0,.07)}}
.terms-hdr{{background:#0f3460;color:#fff;padding:13px 20px;
            font-size:13px;font-weight:700;cursor:pointer;
            display:flex;justify-content:space-between;align-items:center}}
.terms-body{{display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));
             gap:12px;padding:18px}}
.term{{background:#f6f8ff;border-left:3px solid #0f3460;
       border-radius:0 8px 8px 0;padding:12px 14px}}
.term-name{{font-weight:800;font-size:12px;color:#0f3460;margin-bottom:4px}}
.term-desc{{font-size:12px;color:#555;line-height:1.65}}

.ptable{{width:100%;border-collapse:collapse;background:#fff;
         border-radius:12px;overflow:hidden;box-shadow:0 2px 10px rgba(0,0,0,.07)}}
.ptable th{{background:#1a1a2e;color:#fff;padding:11px 12px;
            font-size:12px;text-align:center;white-space:nowrap}}
.ptable td{{padding:11px 12px;border-bottom:1px solid #f0f0f0;text-align:center;font-size:13px}}
.ptable tr:last-child td{{border-bottom:none}}
.ptable tr:hover td{{background:#f7f9ff}}
.left{{text-align:left !important;font-weight:600}}
.mono{{font-family:monospace;font-size:12px}}

.card{{background:#fff;border-radius:14px;
       box-shadow:0 2px 10px rgba(0,0,0,.07);overflow:hidden;margin-bottom:18px}}
.card-top{{display:flex;align-items:center;gap:14px;padding:18px 22px 16px;
           border-bottom:1px solid #f0f0f0}}
.rank-dot{{width:44px;height:44px;border-radius:50%;display:flex;
           align-items:center;justify-content:center;
           font-size:18px;font-weight:900;color:#fff;flex-shrink:0}}
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
.company-box{{background:#f6f8ff;border-left:4px solid #0f3460}}
.company-desc{{font-size:13px;color:#444;line-height:1.75}}

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
.tl{{font-size:11px;font-weight:600;color:#999;
     text-transform:uppercase;letter-spacing:.3px;margin-bottom:6px}}
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
.sum-table td{{padding:12px 10px;border-bottom:1px solid #f2f2f2;
               text-align:center;font-size:13px}}
.sum-table tr:last-child td{{border-bottom:none}}
.sum-table tr:hover td{{background:#f7f9ff}}
.sn{{text-align:left !important;padding-left:14px !important;font-weight:700}}

.notice{{background:#fff8e1;border-left:4px solid #f9a825;
         border-radius:8px;padding:14px 18px;font-size:12px;
         color:#666;line-height:1.9;margin-top:0}}
.footer{{text-align:center;padding:24px;color:#bbb;font-size:11px}}
</style>
</head>
<body>

<div class="hdr">
  <h1>📊 주간 퀀트 리포트 — 차주 유망 종목 TOP 5</h1>
  <p>기준일: {report_date} (금요일 마감) &nbsp;|&nbsp; 차주 월요일({next_mon}) 투자 전략</p>
  <div class="hdr-badges">
    <span class="hbadge">📈 분석 대상 2,770종목</span>
    <span class="hbadge">🔍 최종 선정 TOP 5</span>
    <span class="hbadge">🤖 퀀트 모델 자동 산출</span>
  </div>
</div>

<div class="wrap">

<!-- 시장 요약 -->
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

<!-- 투자 용어 설명 -->
<div class="sec">
  <div class="terms-wrap">
    <div class="terms-hdr" onclick="var b=this.nextElementSibling;b.style.display=b.style.display==='none'?'grid':'none'">
      <span>📚 투자 용어 간단 설명 (클릭하면 접힘)</span><span>▲</span>
    </div>
    <div class="terms-body">
      <div class="term">
        <div class="term-name">RSI (상대강도지수)</div>
        <div class="term-desc">0~100 사이의 <b>과열 온도계</b><br>70 이상 → 과열, 조정 가능성 ↑<br>30 이하 → 과냉각, 반등 가능성 ↑<br><b>45~65 → 이상적인 매수 구간</b></div>
      </div>
      <div class="term">
        <div class="term-name">MACD (방향성 지표)</div>
        <div class="term-desc">단기·장기 평균의 차이로 <b>방향성</b>을 표시<br>히스토그램 + (양수) → 상승 모멘텀 살아있음<br>음수→양수 전환 = <b>골든크로스</b> (강한 매수 신호)</div>
      </div>
      <div class="term">
        <div class="term-name">MA20 / MA60 (이동평균선)</div>
        <div class="term-desc">최근 20일·60일 <b>평균 주가</b><br>현재가 > MA60 → <b>중기 상승 추세</b><br>현재가 > MA20 > MA60 → <b>정배열 (가장 이상적)</b></div>
      </div>
      <div class="term">
        <div class="term-name">ATR (평균 변동폭)</div>
        <div class="term-desc"><b>하루 평균 주가 움직임</b> 폭<br>손절가 설정에 사용 (ATR×2 하락 시 손절)<br>ATR이 클수록 → 변동성 큰 종목, 비중 축소 필요</div>
      </div>
      <div class="term">
        <div class="term-name">거래량 비율 (Vol Ratio)</div>
        <div class="term-desc">이번 주 거래량 ÷ 20일 평균 거래량<br>1.5 이상 → 평소보다 1.5배 거래 = <b>세력 유입 신호</b><br>3.0 이상 → 매우 강한 관심, 테마 수급 유입 중</div>
      </div>
      <div class="term">
        <div class="term-name">모멘텀 (Momentum)</div>
        <div class="term-desc">주가 상승 <b>'관성'</b> 측정<br>1주·4주·12주 수익률을 가중 합산<br><b>단기+중기+장기 모두 상승</b> → 최고 점수</div>
      </div>
      <div class="term">
        <div class="term-name">손절가 (Stop-Loss)</div>
        <div class="term-desc">여기서 이탈 시 추세 붕괴 = <b>즉시 매도</b><br>ATR×2 또는 MA20×0.95 중 높은 값<br>감정 개입 없이 반드시 지켜야 할 선</div>
      </div>
      <div class="term">
        <div class="term-name">RR (Risk/Reward)</div>
        <div class="term-desc">손실 대비 수익 <b>배율</b><br>RR 1.5 = 손실 1만원 감수 → 1.5만원 기대<br><b>RR 1.5 이상이어야 투자 가치 있음</b></div>
      </div>
    </div>
  </div>
</div>

<!-- 내 포트폴리오 현황 -->
<div class="sec">
  <div class="sec-title">💼 내 포트폴리오 현황 (국장 ETF)</div>
  <table class="ptable">
    <thead><tr>
      <th style="text-align:left;padding-left:14px">종목명</th>
      <th>코드</th><th>현재가</th><th>주간 수익률</th>
    </tr></thead>
    <tbody>{port_html if port_html else '<tr><td colspan="4" style="padding:16px;color:#aaa">ETF 가격 데이터 미수록 — ETF는 KOSPI/KOSDAQ 주식 DB가 아닌 별도 피드 필요</td></tr>'}</tbody>
  </table>
</div>

<!-- TOP 5 종목 상세 -->
<div class="sec">
  <div class="sec-title">🎯 차주 유망 종목 TOP 5 상세 분석</div>
  {stocks_html}
</div>

<!-- 전체 요약 테이블 -->
<div class="sec">
  <div class="sec-title">📋 한눈에 보는 요약표</div>
  <div style="overflow-x:auto">
  <table class="sum-table">
    <thead><tr>
      <th>#</th>
      <th style="text-align:left;padding-left:14px">종목명</th>
      <th>업종</th>
      <th>현재가</th>
      <th>주간</th>
      <th>12주</th>
      <th>RSI</th>
      <th>거래량↑</th>
      <th>매수가</th>
      <th>손절가</th>
      <th>목표①</th>
      <th>목표②</th>
      <th>접근</th>
    </tr></thead>
    <tbody>
      {summary_rows_html}
    </tbody>
  </table>
  </div>
</div>

<!-- 투자 원칙 -->
<div class="notice">
  ⚠️ <b>실전 투자 원칙</b><br>
  • <b>분산 투자</b> : 한 종목에 전체 투자금의 10% 이하 (변동성 큰 종목은 5% 이하)<br>
  • <b>손절 필수</b> : 손절가 도달 시 감정 개입 없이 즉시 매도 — 손절을 지키지 않으면 퀀트 전략은 의미 없음<br>
  • <b>분할 매도</b> : 목표① 도달 시 절반 이상 매도해 수익 먼저 확정, 나머지로 목표② 추구<br>
  • <b>분할 매수</b> : 월요일 시초가에 전량 매수 금지 — 2~3회 나눠 매수해 평단가 리스크 분산<br>
  • 본 리포트는 퀀트 모델(모멘텀·기술지표·거래량 팩터)로 자동 생성된 참고 자료이며, <b>투자 손익 책임은 본인에게 있습니다</b>
</div>

</div>
<div class="footer">InitialTrading Weekly Quant Engine &nbsp;|&nbsp; 기준일: {report_date} &nbsp;|&nbsp; {today_str} 생성</div>
</body></html>'''

with open(OUT_FILE, 'w', encoding='utf-8') as f:
    f.write(HTML)
print(f'OK: {OUT_FILE}')
