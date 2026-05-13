"""Parse the latest weekly_full_*.html report and print structured data for the skill."""
import glob, os, re
from datetime import datetime

REPORT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'outputs', 'reports')
files = sorted(glob.glob(os.path.join(REPORT_DIR, 'weekly_full_*.html')), reverse=True)
if not files:
    print("NO_DATA")
    exit(0)

d = {}
with open(files[0], encoding='utf-8') as f:
    for line in f:
        line = line.rstrip()
        if '=' in line:
            k, _, v = line.partition('=')
            d[k] = v

def g(k): return d.get(k, '')

def fi(v):
    try: return f"{int(float(v)):,}"
    except: return str(v)

def sp(v):
    try:
        fv = float(v)
        return ('+' if fv >= 0 else '') + f"{fv:.2f}%"
    except: return str(v) + '%'

try:
    days_old = (datetime.today() - datetime.strptime(g('DATE'), '%Y-%m-%d')).days
except Exception:
    days_old = 0

print(f"DAYS_OLD={days_old}")
print(f"DATE={g('DATE')}")
print(f"KS={g('KOSPI_RET')}%|{g('KOSPI_UP')}|{g('KOSPI_DN')}")
print(f"KD={g('KOSDAQ_RET')}%|{g('KOSDAQ_UP')}|{g('KOSDAQ_DN')}")

def parse_stock(pfx, i):
    reasons_raw = g(f'{pfx}{i}_REASONS')
    reasons = [re.sub(r'<[^>]+>', '', r) for r in reasons_raw.split('|')][:3] if reasons_raw else []
    sector  = g(f'{pfx}{i}_SECTOR') or '대형주'
    return (
        f"{pfx}{i}={g(f'{pfx}{i}_NAME')}|{g(f'{pfx}{i}_CODE')}|{g(f'{pfx}{i}_MKT')}|{sector}|"
        f"{fi(g(f'{pfx}{i}_CLOSE'))}|{sp(g(f'{pfx}{i}_R1W'))}|{sp(g(f'{pfx}{i}_R12W'))}|"
        f"{g(f'{pfx}{i}_RSI')}|{g(f'{pfx}{i}_VOLR')}|"
        f"{fi(g(f'{pfx}{i}_ENTRY'))}|{fi(g(f'{pfx}{i}_STOP'))}|{g(f'{pfx}{i}_STOP_PCT')}|"
        f"{fi(g(f'{pfx}{i}_T1'))}|{g(f'{pfx}{i}_T1_PCT')}|"
        f"{fi(g(f'{pfx}{i}_T2'))}|{g(f'{pfx}{i}_T2_PCT')}|{';;'.join(reasons)}"
    )

# 안정 대장주 모델 TOP5
for i in range(5):
    print(parse_stock('S', i))

# 단기 모멘텀 모델 TOP5
for i in range(5):
    print(parse_stock('M', i))

# ETF 추천 모델 TOP5
for i in range(5):
    print(parse_stock('E', i))
