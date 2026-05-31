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
print(f"US_SP={g('US_SP_RET')}%|{g('US_SP_UP')}|{g('US_SP_DN')}")
print(f"US_NQ={g('US_NQ_RET')}%")
print(f"US_DJ={g('US_DJ_RET')}%|{g('US_DJ_UP')}|{g('US_DJ_DN')}")

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

# 글로벌 기관 포트폴리오 동향
inst_count = int(g('INST_COUNT') or 0)
if inst_count > 0:
    print(f"INST_COUNT={inst_count}")
    for j in range(min(inst_count, 11)):
        name    = g(f'INST{j}_NAME')
        if not name:
            break
        date_   = g(f'INST{j}_DATE')
        period  = g(f'INST{j}_PERIOD')
        sectors = g(f'INST{j}_TOP3_SECTORS')
        holds   = g(f'INST{j}_TOP3_HOLD')
        total   = g(f'INST{j}_TOTAL')
        print(f"INST{j}={name}|{date_}|{period}|{sectors}|{holds}|{total}")

# 기관연동 한국 종목 TOP5
for i in range(5):
    if g(f'I{i}_NAME'):
        print(parse_stock('I', i))

# 한국 시총 TOP5
for i in range(5):
    if g(f'KR_CAP{i}_NAME'):
        marcap_t = f"{int(float(g(f'KR_CAP{i}_MARCAP') or 0))/1e12:.1f}"
        print(f"KR_CAP{i}={g(f'KR_CAP{i}_NAME')}|{g(f'KR_CAP{i}_CODE')}|{marcap_t}조원|{fi(g(f'KR_CAP{i}_PRICE'))}|{sp(g(f'KR_CAP{i}_R1W'))}")

# 미국 시총 TOP5
for i in range(5):
    if g(f'US_CAP{i}_TICKER'):
        print(f"US_CAP{i}={g(f'US_CAP{i}_NAME')}|{g(f'US_CAP{i}_TICKER')}|${g(f'US_CAP{i}_MARCAP_B')}B|${g(f'US_CAP{i}_PRICE')}|{sp(g(f'US_CAP{i}_R1W'))}")
