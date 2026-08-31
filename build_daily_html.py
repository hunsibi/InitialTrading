"""
build_daily_html.py  -  장마감 후 데일리 브리핑 HTML 리포트 생성

send_telegram.py가 수집한 데이터를 받아 자체 완결형(외부 CDN 없음) HTML을 만든다.
  1. 주요 지수 (KPI 타일)
  2. 보유 종목 (표 · 정규장/시간외)
  3. 삼성전자·SK하이닉스 일주일치 외국인/기관/개인 순매수 그래프 (인라인 SVG)
"""
import os
from datetime import datetime

REPORT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'outputs', 'reports')

# dataviz 검증 통과 팔레트 (categorical 슬롯 1~3, light/dark 각각 검증)
SERIES = [
    ('외국인', '#2a78d6', '#3987e5'),
    ('기관',   '#eb6834', '#d95926'),
    ('개인',   '#1baf7a', '#199e70'),
]


def _esc(s):
    return (str(s).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;'))


def _fmt(v, nd=0):
    try:
        return f"{v:,.{nd}f}"
    except (TypeError, ValueError):
        return str(v)


def _sign(v, nd=2, suffix='%'):
    try:
        return f"{'+' if v >= 0 else ''}{v:.{nd}f}{suffix}"
    except (TypeError, ValueError):
        return str(v)


def _cls(v):
    """상승=빨강 / 하락=파랑 (국내 관행)."""
    try:
        return 'up' if float(v) > 0 else ('down' if float(v) < 0 else 'flat')
    except (TypeError, ValueError):
        return 'flat'


# ---------------------------------------------------------------- 그래프
def bar_chart(flows, width=560, height=260):
    """일별 외국인/기관/개인 순매수 그룹 막대그래프 (0선 기준 위=순매수).

    flows: [{'date','foreign','inst','indiv'}, ...] · 단위 억원
    """
    if not flows:
        return '<p class="empty">데이터 없음</p>'

    pad_l, pad_r, pad_t, pad_b = 52, 12, 16, 42
    plot_w = width - pad_l - pad_r
    plot_h = height - pad_t - pad_b

    vals = []
    for f in flows:
        vals += [f['foreign'], f['inst'], f['indiv']]
    vmax = max(abs(v) for v in vals) or 1
    # 눈금이 깔끔하게 떨어지도록 상한을 올림 처리
    step = 10 ** max(0, len(str(int(vmax))) - 2)
    top  = (int(vmax / step) + 1) * step if step else vmax
    y0   = pad_t + plot_h / 2                      # 0선

    def yv(v):
        return y0 - (v / top) * (plot_h / 2)

    n_grp   = len(flows)
    grp_w   = plot_w / n_grp
    bar_w   = min(15, (grp_w - 14) / 3)
    gap     = 2                                     # 인접 막대 사이 surface gap

    out = [f'<svg viewBox="0 0 {width} {height}" width="100%" '
           f'role="img" aria-label="일별 투자자별 순매수 그래프" '
           f'preserveAspectRatio="xMidYMid meet">']

    # 눈금선 + y축 라벨
    for frac in (1.0, 0.5, 0.0, -0.5, -1.0):
        v  = top * frac
        yy = yv(v)
        is_zero = (frac == 0.0)
        out.append(f'<line x1="{pad_l}" y1="{yy:.1f}" x2="{width-pad_r}" y2="{yy:.1f}" '
                   f'class="{"axis" if is_zero else "grid"}"/>')
        out.append(f'<text x="{pad_l-8}" y="{yy+4:.1f}" class="ytick">{_fmt(v)}</text>')

    # 막대
    for gi, f in enumerate(flows):
        gx = pad_l + gi * grp_w
        trio = [f['foreign'], f['inst'], f['indiv']]
        # 그룹을 가운데 정렬
        total_w = bar_w * 3 + gap * 2
        bx0 = gx + (grp_w - total_w) / 2
        for si, v in enumerate(trio):
            label = SERIES[si][0]
            x = bx0 + si * (bar_w + gap)
            yy = yv(v)
            h  = abs(yy - y0)
            r  = min(4, h / 2) if h > 0 else 0
            if h < 0.6:                              # 0에 가까우면 얇은 선으로 표시
                out.append(f'<rect x="{x:.1f}" y="{y0-0.6:.1f}" width="{bar_w:.1f}" '
                           f'height="1.2" class="s{si}"><title>{label} '
                           f'{f["date"]}: {_fmt(v)}억원</title></rect>')
                continue
            if v >= 0:      # 위로: 윗변만 라운드
                d = (f'M{x:.1f},{y0:.1f} L{x:.1f},{yy+r:.1f} '
                     f'Q{x:.1f},{yy:.1f} {x+r:.1f},{yy:.1f} '
                     f'L{x+bar_w-r:.1f},{yy:.1f} '
                     f'Q{x+bar_w:.1f},{yy:.1f} {x+bar_w:.1f},{yy+r:.1f} '
                     f'L{x+bar_w:.1f},{y0:.1f} Z')
            else:           # 아래로: 아랫변만 라운드
                d = (f'M{x:.1f},{y0:.1f} L{x:.1f},{yy-r:.1f} '
                     f'Q{x:.1f},{yy:.1f} {x+r:.1f},{yy:.1f} '
                     f'L{x+bar_w-r:.1f},{yy:.1f} '
                     f'Q{x+bar_w:.1f},{yy:.1f} {x+bar_w:.1f},{yy-r:.1f} '
                     f'L{x+bar_w:.1f},{y0:.1f} Z')
            out.append(f'<path d="{d}" class="s{si}"><title>{label} '
                       f'{f["date"]}: {_fmt(v)}억원</title></path>')
        out.append(f'<text x="{gx+grp_w/2:.1f}" y="{height-pad_b+20}" '
                   f'class="xtick">{f["date"]}</text>')

    out.append(f'<text x="{pad_l-8}" y="{pad_t-4}" class="unit">억원</text>')
    out.append('</svg>')
    return ''.join(out)


def legend():
    items = ''.join(
        f'<span class="lg"><i class="sw s{i}"></i>{n}</span>'
        for i, (n, _, _) in enumerate(SERIES))
    return f'<div class="legend">{items}</div>'


def flow_table(flows):
    if not flows:
        return ''
    head = ''.join(f'<th>{f["date"]}</th>' for f in flows)
    head += f'<th class="tot">{len(flows)}일 누적</th>'
    rows = ''
    for si, (name, _, _) in enumerate(SERIES):
        key = ['foreign', 'inst', 'indiv'][si]
        cell = lambda v, extra='': (f'<td class="{_cls(v)} {extra}">'
                                    f'{"+" if v >= 0 else "−"}{abs(v):,.0f}</td>')
        tds = ''.join(cell(f[key]) for f in flows)
        tds += cell(sum(f[key] for f in flows), 'tot')
        rows += (f'<tr><th class="rowh"><i class="sw s{si}"></i>{name}</th>{tds}</tr>')
    return (f'<table class="tbl flow"><caption>순매수 거래대금 (억원) · '
            f'양수=순매수, 음수=순매도</caption>'
            f'<thead><tr><th></th>{head}</tr></thead><tbody>{rows}</tbody></table>')


# ---------------------------------------------------------------- 문서
CSS = """
:root{color-scheme:light;
 --surface:#fcfcfb;--plane:#f9f9f7;--ink:#0b0b0b;--ink2:#52514e;--muted:#898781;
 --grid:#e1e0d9;--axis:#c3c2b7;--ring:rgba(11,11,11,.10);
 --s0:#2a78d6;--s1:#eb6834;--s2:#1baf7a;--up:#d03b3b;--down:#1c5cab;}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){color-scheme:dark;
 --surface:#1a1a19;--plane:#0d0d0d;--ink:#fff;--ink2:#c3c2b7;--muted:#898781;
 --grid:#2c2c2a;--axis:#383835;--ring:rgba(255,255,255,.10);
 --s0:#3987e5;--s1:#d95926;--s2:#199e70;--up:#e66767;--down:#86b6ef;}}
[data-theme="dark"]{color-scheme:dark;
 --surface:#1a1a19;--plane:#0d0d0d;--ink:#fff;--ink2:#c3c2b7;--muted:#898781;
 --grid:#2c2c2a;--axis:#383835;--ring:rgba(255,255,255,.10);
 --s0:#3987e5;--s1:#d95926;--s2:#199e70;--up:#e66767;--down:#86b6ef;}
*{box-sizing:border-box}
body{margin:0;padding:20px 14px 48px;background:var(--plane);color:var(--ink);
 font-family:system-ui,-apple-system,"Segoe UI","Malgun Gothic",sans-serif;
 font-size:15px;line-height:1.5}
.wrap{max-width:720px;margin:0 auto}
h1{font-size:20px;margin:0 0 2px}
.sub{color:var(--muted);font-size:13px;margin:0 0 22px}
h2{font-size:15px;margin:28px 0 12px;padding-bottom:7px;border-bottom:1px solid var(--ring)}
.card{background:var(--surface);border:1px solid var(--ring);border-radius:10px;padding:14px}
.kpi{display:grid;grid-template-columns:repeat(auto-fit,minmax(128px,1fr));gap:8px}
.kpi .t{background:var(--surface);border:1px solid var(--ring);border-radius:10px;padding:11px 12px}
.kpi .n{font-size:12px;color:var(--ink2);margin-bottom:5px;
 min-height:2.5em;display:flex;align-items:flex-start}
.kpi .v{font-size:19px;font-weight:650;letter-spacing:-.02em}
.kpi .d{font-size:13px;font-weight:600;margin-top:2px}
.kpi .dt{font-size:11px;color:var(--muted);margin-top:3px}
.up{color:var(--up)}.down{color:var(--down)}.flat{color:var(--muted)}
.tbl{width:100%;border-collapse:collapse;font-size:14px}
.tbl th,.tbl td{padding:8px 9px;border-bottom:1px solid var(--ring);text-align:right}
.tbl th:first-child,.tbl td:first-child{text-align:left}
.tbl thead th{font-size:12px;color:var(--muted);font-weight:600;white-space:nowrap}
.tbl td{font-variant-numeric:tabular-nums}
.tbl tbody tr:last-child td,.tbl tbody tr:last-child th{border-bottom:0}
.nm{font-weight:600}
.aft{font-size:12px;color:var(--muted);font-variant-numeric:tabular-nums}
.scroll{overflow-x:auto;-webkit-overflow-scrolling:touch}
.chart{margin-top:18px}
.chart h3{font-size:14px;margin:0 0 2px}
.chart .meta{font-size:12px;color:var(--muted);margin:0 0 8px}
svg{display:block;overflow:visible}
.grid{stroke:var(--grid);stroke-width:1}
.axis{stroke:var(--axis);stroke-width:1.5}
.ytick,.xtick,.unit{fill:var(--muted);font-size:11px;font-family:inherit}
.ytick{text-anchor:end;font-variant-numeric:tabular-nums}
.xtick{text-anchor:middle}
.unit{text-anchor:end}
.s0{fill:var(--s0)}.s1{fill:var(--s1)}.s2{fill:var(--s2)}
path.s0,path.s1,path.s2,rect.s0,rect.s1,rect.s2{stroke:var(--surface);stroke-width:2;
 paint-order:stroke fill}
path:hover,rect:hover{opacity:.78;cursor:pointer}
.legend{display:flex;gap:14px;flex-wrap:wrap;margin:10px 0 2px;font-size:13px;color:var(--ink2)}
.lg{display:inline-flex;align-items:center;gap:6px}
.sw{width:11px;height:11px;border-radius:3px;display:inline-block;flex:none}
i.sw.s0{background:var(--s0)}i.sw.s1{background:var(--s1)}i.sw.s2{background:var(--s2)}
.flow{margin-top:14px}
.flow caption{caption-side:top;text-align:left;font-size:12px;color:var(--muted);
 padding-bottom:7px}
.flow th.rowh{text-align:left;font-weight:600;white-space:nowrap;color:var(--ink2)}
.flow th.rowh .sw{margin-right:6px;vertical-align:-1px}
.flow .tot{border-left:1px solid var(--ring);font-weight:700;white-space:nowrap}
.note{margin-top:26px;font-size:12px;color:var(--muted);line-height:1.65}
.empty{color:var(--muted);font-size:13px}
"""


def build(date_str, indexes, holdings, flow_charts, out_path=None):
    """HTML 리포트 생성 후 파일 경로 반환.

    indexes     : [{'name','value','chg','date','flag','nd'}]
    holdings    : [{'name','value','chg','after','cur'}]
    flow_charts : [{'name','code','flows':[...]}]
    """
    # 1. 지수 KPI
    tiles = ''
    for r in indexes:
        tiles += (f'<div class="t"><div class="n">{r["flag"]} {_esc(r["name"])}</div>'
                  f'<div class="v">{_fmt(r["value"], r.get("nd", 2))}</div>'
                  f'<div class="d {_cls(r["chg"])}">{_sign(r["chg"])}</div>'
                  f'<div class="dt">{_esc(r["date"])} 종가</div></div>')

    # 2. 보유 종목
    rows = ''
    for h in holdings:
        cur = h.get('cur', '원')
        nd  = 2 if cur == '$' else 0
        val = (f'${_fmt(h["value"], 2)}' if cur == '$'
               else f'{_fmt(h["value"], 0)}원')
        aft = ''
        if h.get('after'):
            a = h['after']
            av = (f'${_fmt(a["value"], 2)}' if cur == '$' else f'{_fmt(a["value"], 0)}원')
            tag = '애프터' if cur == '$' else '시간외'
            aft = (f'<div class="aft">{tag} {av} '
                   f'<span class="{_cls(a["chg"])}">{_sign(a["chg"])}</span></div>')
        rows += (f'<tr><td class="nm">{_esc(h["name"])}</td>'
                 f'<td>{val}{aft}</td>'
                 f'<td class="{_cls(h["chg"])}">{_sign(h["chg"])}</td></tr>')

    # 3. 수급 그래프
    charts = ''
    for c in flow_charts:
        rng = ''
        if c['flows']:
            rng = f'{c["flows"][0]["date"]} ~ {c["flows"][-1]["date"]}'
        charts += (f'<div class="chart"><h3>{_esc(c["name"])} '
                   f'<span class="aft">{c["code"]}</span></h3>'
                   f'<p class="meta">{rng} · 일별 순매수 거래대금</p>'
                   f'{legend()}'
                   f'<div class="scroll">{bar_chart(c["flows"])}</div>'
                   f'<div class="scroll">{flow_table(c["flows"])}</div></div>')
    if not charts:
        charts = ('<p class="empty">수급 데이터를 가져오지 못했습니다 '
                  '(KRX_ID / KRX_PW 확인 필요).</p>')

    html = f"""<!DOCTYPE html>
<html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>일일 시황 브리핑 {date_str}</title>
<style>{CSS}</style></head><body><div class="wrap">
<h1>📊 일일 시황 브리핑</h1>
<p class="sub">{date_str} · 정규장 종가 기준</p>

<h2>🇰🇷 삼성전자 · SK하이닉스 투자자별 매매 동향</h2>
<div class="card">{charts}</div>

<h2>📈 주요 지수</h2>
<div class="kpi">{tiles}</div>

<h2>💼 보유 종목</h2>
<div class="card"><table class="tbl">
<thead><tr><th>종목</th><th>종가</th><th>전일대비</th></tr></thead>
<tbody>{rows}</tbody></table></div>

<p class="note">
가격은 정규장 종가 기준입니다. 시간외(넥스트레이드 애프터마켓, ~20:00) 체결가가
다르면 종가 아래에 함께 표시했습니다.<br>
순매수 거래대금은 KRX 공식 데이터이며, 0선 위는 순매수 · 아래는 순매도입니다.
막대에 마우스를 올리면 정확한 값이 표시되고, 아래 표에서도 같은 수치를 확인할 수 있습니다.<br>
자동 생성 리포트입니다 — 투자 손익 책임은 본인에게 있습니다.
</p>
</div></body></html>"""

    os.makedirs(REPORT_DIR, exist_ok=True)
    out_path = out_path or os.path.join(REPORT_DIR, f'daily_{date_str}.html')
    with open(out_path, 'w', encoding='utf-8') as f:
        f.write(html)
    return out_path
