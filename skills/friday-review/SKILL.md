---
name: friday-review
description: >
  Carlos의 InitialTrading 주간 금요복기 전용 커맨드.
  사용자가 "금요복기", "이번주 정리", "주간 복기", "차주 전략", "friday review",
  "이번주 시장 어땠어", "다음주 어떻게 할까" 등을 말하면 반드시 이 스킬을 사용한다.
  D:\WorkSpace\InitialTrading 의 최신 분석 데이터 + 포트폴리오 + 트레이딩 일지를 통합해
  ① 시장 요약 ② 포트폴리오 점검 ③ TOP5 분석 ④ 차주 액션 플랜 4단계로 출력한다.
---

# Friday Review — 주간 복기 + 차주 전략 통합 스킬

매주 금요일 장 마감 후 한 번에 실행하는 통합 분석 스킬.

## 데이터 소스

| 파일 | 용도 |
|---|---|
| `D:\WorkSpace\InitialTrading\outputs\reports\weekly_full_*.html` | TOP5 + 시장 요약 (key=value 형식) |
| `D:\WorkSpace\InitialTrading\docs\PORTFOLIO.md` | 현재 보유 종목 |
| `D:\WorkSpace\InitialTrading\docs\trading_journal.md` | 지난 주 결정/체결 |
| `D:\WorkSpace\InitialTrading\outputs\data\prices_*_Q*.csv` | 보유 종목 가격 추적 |

## bash 경로 결정

세션마다 mount hash가 바뀌므로 동적으로 탐지:

```bash
WS=$(find /sessions/*/mnt/WorkSpace/InitialTrading -maxdepth 0 -type d 2>/dev/null | head -1)
echo "$WS"
```

`$WS` 가 비어있으면: "InitialTrading 폴더가 마운트되지 않았습니다. Cowork에서 D:\WorkSpace 폴더를 연결해주세요." 안내 후 종료.

## 실행 순서

### 1단계: 컨텍스트 적재 (조용히)

```bash
WS=$(find /sessions/*/mnt/WorkSpace/InitialTrading -maxdepth 0 -type d 2>/dev/null | head -1)
cat "$WS/docs/PORTFOLIO.md" 2>/dev/null
echo "---JOURNAL_TAIL---"
tail -80 "$WS/docs/trading_journal.md" 2>/dev/null
echo "---LATEST_REPORT---"
ls -t "$WS/outputs/reports/weekly_full_"*.html 2>/dev/null | head -1
```

### 2단계: 최신 weekly_full 파싱

```bash
WS=$(find /sessions/*/mnt/WorkSpace/InitialTrading -maxdepth 0 -type d 2>/dev/null | head -1)
python3 << PYEOF
import glob, os, re
files = sorted(glob.glob(os.path.join('$WS','outputs','reports','weekly_full_*.html')), reverse=True)
if not files:
    print('NO_DATA'); raise SystemExit
d={}
with open(files[0], encoding='utf-8') as f:
    for line in f:
        line=line.rstrip('\n')
        if '=' in line and not line.startswith('PORT|'):
            k,_,v=line.partition('='); d[k]=v
def g(k): return d.get(k,'')
def fi(v):
    try: return f"{int(v):,}"
    except: return str(v)
def sp(v):
    try: return ('+' if float(v)>=0 else '')+str(v)+'%'
    except: return str(v)+'%'
print(f"DATE={g('DATE')}")
print(f"KS={g('KOSPI_RET')}%|{g('KOSPI_UP')}|{g('KOSPI_DN')}")
print(f"KD={g('KOSDAQ_RET')}%|{g('KOSDAQ_UP')}|{g('KOSDAQ_DN')}")
for i in range(5):
    rr=g(f'S{i}_REASONS')
    rs=[re.sub(r'<[^>]+>','',x) for x in rr.split('|')][:3] if rr else []
    print(f"S{i}={g(f'S{i}_NAME')}|{g(f'S{i}_CODE')}|{g(f'S{i}_MKT')}|{fi(g(f'S{i}_CLOSE'))}|{sp(g(f'S{i}_R1W'))}|{sp(g(f'S{i}_R12W'))}|{g(f'S{i}_RSI')}|{g(f'S{i}_VOLR')}|{fi(g(f'S{i}_ENTRY'))}|{fi(g(f'S{i}_STOP'))}|{g(f'S{i}_STOP_PCT')}|{fi(g(f'S{i}_T1'))}|{g(f'S{i}_T1_PCT')}|{fi(g(f'S{i}_T2'))}|{g(f'S{i}_T2_PCT')}|{';;'.join(rs)}")
PYEOF
```

### 3단계: 출력

다음 4섹션 형식으로 출력. 표/코드블록 사용하지 않는다.

---

**🗓 [DATE] 금요 복기 — Carlos × InitialTrading**

---

**1️⃣ 이번 주 시장**

KOSPI [수익률] · 상승 [N] / 하락 [N]
KOSDAQ [수익률] · 상승 [N] / 하락 [N]
한 줄 코멘트: (예: "코스피 하방 지지, 코스닥 약세 — 위험회피 분위기")

---

**2️⃣ 포트폴리오 점검**

미장: TSLL [상태], BITX [상태]
국장 코어: TIGER 200, KODEX AI전력핵심설비, ... 7종 — 전반 [상태]
손절/목표가 근접 종목: [없음 / 종목명·사유]
한 줄 진단: (예: "AI 인프라 강세 → KODEX AI전력핵심설비 비중 우위, 채권 약세 지속")

> 보유 종목 가격은 prices_*_Q*.csv 에서 직접 조회하지 않고, "다음 세션에서 Carlos가 제공" 또는 "확인 필요"로 표기. (자동 가격 조회는 별도 스킬에서 처리)

---

**3️⃣ 차주 TOP5 (퀀트 모델 산출)**

1️⃣ **[종목명]** [코드] · [시장]
현재가 **[가격]원** | 주간 [수익률] | 12주 [수익률] | RSI [값] | 거래량 [배수]배
💰 매수 [가격]원 → 🛑 손절 [가격]원([%]) → 🎯 목표① [가격]원(+[%]) → 🏆 목표② [가격]원(+[%])
선정: [이유1] / [이유2]

(2~5위 동일)

---

**4️⃣ 차주 액션 플랜 (제안)**

신규 진입 후보: [TOP5 중 1~2종 추천 + 사유]
보유 유지: [코어 ETF 유지 권고]
청산/감축 후보: [있다면 종목+사유, 없으면 "없음"]
이번 주 자금 투입: 약 [50~100]만원 — [어떤 자산군에 우선]
주의 신호: [거시 이벤트, 변동성, 손절 임박 종목]

---

⚠️ 퀀트 모델 자동 산출 + 룰 기반 제안 — 최종 결정은 Carlos.

다음 행동: 위 플랜이 OK면 `trading_journal.md` 에 기록할까요? "기록해" 라고 답하면 자동 추가.

---

## 데이터가 오래됐을 때

파일명 날짜가 7일 이상 지났으면 결과를 보여주되 상단에 다음 안내 추가:

> ⚠️ [N]일 전 데이터입니다. 최신 분석은 PC에서 `2_weekly.bat` 더블클릭 → 약 5분 후 텔레그램 수신.

## 사용자가 "기록해"라고 하면

`trading_journal.md` 상단(역순)에 새 엔트리 추가:

```
## YYYY-MM-DD (요일) — Friday Review

**시장 요약**
- KOSPI [수익률], KOSDAQ [수익률]

**포트폴리오 점검**
- (위 2단계 진단 복붙)

**차주 액션 플랜**
- 신규: ...
- 청산: ...
- 자금: ...

**다음 세션**
- 다음 월요일 09:00 전 — 주문 실행 후 체결 보고
```
