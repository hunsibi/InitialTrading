---
name: weekly-quant
description: >
  Carlos의 InitialTrading 주간 퀀트 분석 결과 즉시 출력 스킬.
  사용자가 "주간분석", "이번주 top5", "퀀트 결과", "주식 분석해줘",
  "top5 뽑아줘", "weekly", "분석 결과 보여줘" 등을 말하면 반드시 이 스킬을 사용한다.
  D:\WorkSpace\InitialTrading 의 최신 weekly_full_*.html 을 파싱해 TOP5 종목과
  매수/손절/목표가를 바로 보여준다. (포트폴리오 점검·차주 전략까지 통합하려면 friday-review 사용)
---

# Weekly Quant — TOP5 즉시 출력

## 데이터 경로

| 위치 | 용도 |
|---|---|
| `D:\WorkSpace\InitialTrading\outputs\reports\weekly_full_*.html` | 파싱용 데이터 |
| `D:\WorkSpace\InitialTrading\2_weekly.bat` | PC에서 직접 실행하는 분석 배치 |

## bash 경로 (세션 hash 동적 탐지)

```bash
WS=$(find /sessions/*/mnt/WorkSpace/InitialTrading -maxdepth 0 -type d 2>/dev/null | head -1)
```

마운트되지 않았으면 안내 후 종료:
> "InitialTrading 폴더가 마운트되지 않았습니다. Cowork 사이드바에서 D:\WorkSpace 폴더를 연결해주세요."

## 실행 순서

### 1단계: 최신 데이터 파일 확인

```bash
WS=$(find /sessions/*/mnt/WorkSpace/InitialTrading -maxdepth 0 -type d 2>/dev/null | head -1)
[ -z "$WS" ] && { echo "MOUNT_MISSING"; exit; }
ls -t "$WS/outputs/reports/weekly_full_"*.html 2>/dev/null | head -1
```

파일이 없으면: "아직 분석 데이터가 없습니다. PC에서 `2_weekly.bat`를 먼저 실행해주세요."

### 2단계: 데이터 파싱

```bash
WS=$(find /sessions/*/mnt/WorkSpace/InitialTrading -maxdepth 0 -type d 2>/dev/null | head -1)
python3 << PYEOF
import glob, os, re
files = sorted(glob.glob(os.path.join('$WS','outputs','reports','weekly_full_*.html')), reverse=True)
if not files:
    print('NO_DATA'); raise SystemExit
d = {}
with open(files[0], encoding='utf-8') as f:
    for line in f:
        line = line.rstrip('\n')
        if '=' in line and not line.startswith('PORT|'):
            k, _, v = line.partition('=')
            d[k] = v
def g(k): return d.get(k, '')
def fi(v):
    try: return f"{int(v):,}"
    except: return str(v)
def sp(v):
    try: return ('+' if float(v) >= 0 else '') + str(v) + '%'
    except: return str(v) + '%'
print(f"DATE={g('DATE')}")
print(f"KS={g('KOSPI_RET')}%|{g('KOSPI_UP')}|{g('KOSPI_DN')}")
print(f"KD={g('KOSDAQ_RET')}%|{g('KOSDAQ_UP')}|{g('KOSDAQ_DN')}")
for i in range(5):
    rr = g(f'S{i}_REASONS')
    rs = [re.sub(r'<[^>]+>', '', x) for x in rr.split('|')][:3] if rr else []
    print(f"S{i}={g(f'S{i}_NAME')}|{g(f'S{i}_CODE')}|{g(f'S{i}_MKT')}|{fi(g(f'S{i}_CLOSE'))}|{sp(g(f'S{i}_R1W'))}|{sp(g(f'S{i}_R12W'))}|{g(f'S{i}_RSI')}|{g(f'S{i}_VOLR')}|{fi(g(f'S{i}_ENTRY'))}|{fi(g(f'S{i}_STOP'))}|{g(f'S{i}_STOP_PCT')}|{fi(g(f'S{i}_T1'))}|{g(f'S{i}_T1_PCT')}|{fi(g(f'S{i}_T2'))}|{g(f'S{i}_T2_PCT')}|{';;'.join(rs)}")
PYEOF
```

### 3단계: 결과 출력

표/코드블록 없이 다음 형식으로 출력:

---

**📊 [DATE] 주간 퀀트 분석 — 차주 TOP 5**

**이번 주 시장**
KOSPI [수익률] · 상승 [N] / 하락 [N]
KOSDAQ [수익률] · 상승 [N] / 하락 [N]

---

1️⃣ **[종목명]** [코드] · [시장]
현재가 **[가격]원** | 주간 [수익률] | 12주 [수익률] | RSI [값] | 거래량 [배수]배
💰 매수 [가격]원 → 🛑 손절 [가격]원([%]) → 🎯 목표① [가격]원(+[%]) → 🏆 목표② [가격]원(+[%])
선정: [이유1] / [이유2]

(2~5위 동일 형식)

---
⚠️ 퀀트 모델 자동 산출 결과 — 투자 손익 책임은 본인에게 있습니다

## 데이터가 오래됐을 때

파일명 날짜가 7일 이상 지났으면 결과 위에 안내 추가:
> ⚠️ [N]일 전 데이터입니다. 최신 분석을 원하시면 PC에서 `2_weekly.bat`를 실행해주세요.

## 배치파일 실행 요청 시

"분석 실행해줘", "배치 실행해줘" 등의 요청이 오면:
> `2_weekly.bat`는 PC에서 직접 실행해야 합니다.
> `D:\WorkSpace\InitialTrading` 폴더에서 **2_weekly.bat 더블클릭** → 약 5분 후 브라우저 자동 오픈 + 텔레그램 전송까지 자동으로 완료됩니다.
