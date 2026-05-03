---
name: portfolio-checkup
description: >
  Carlos의 InitialTrading 포트폴리오 점검 전용 커맨드.
  사용자가 "포트폴리오 점검", "내 종목 어때", "리밸런싱", "보유 종목 상태",
  "checkup", "내 포지션", "손절 칠까", "수익률 확인" 등을 말하면 반드시 이 스킬을 사용한다.
  D:\WorkSpace\InitialTrading\docs\PORTFOLIO.md 의 보유 종목과
  outputs/data/prices_*_Q*.csv 최신 가격을 결합해 종목별 손익·시그널·리밸런싱 제안을 출력한다.
---

# Portfolio Checkup — 보유 종목 상태 점검

## 데이터 소스

| 파일 | 용도 |
|---|---|
| `D:\WorkSpace\InitialTrading\docs\PORTFOLIO.md` | 보유 종목 + 평단 + 비중 |
| `D:\WorkSpace\InitialTrading\outputs\data\prices_YYYY_QN.csv` | 한국 종목 최신 종가 |
| `D:\WorkSpace\InitialTrading\outputs\data\master_info.csv` | 종목명 → 코드 매핑 |

미국 종목(TSLL, BITX) 가격은 로컬 데이터에 없으므로 Carlos에게 입력 요청.

## 실행 순서

### 1단계: 경로 및 마스터 적재

```bash
WS=$(find /sessions/*/mnt/WorkSpace/InitialTrading -maxdepth 0 -type d 2>/dev/null | head -1)
[ -z "$WS" ] && { echo "MOUNT_MISSING"; exit; }
cat "$WS/docs/PORTFOLIO.md"
```

### 2단계: 한국 보유 종목 최신가 조회

```bash
WS=$(find /sessions/*/mnt/WorkSpace/InitialTrading -maxdepth 0 -type d 2>/dev/null | head -1)
python3 << PYEOF
import os, glob, csv
DATA = os.path.join('$WS','outputs','data')
# 최신 prices 파일
pf = sorted(glob.glob(os.path.join(DATA, 'prices_*_Q*.csv')))[-1]
# 종목 마스터
master = {}
with open(os.path.join(DATA,'master_info.csv'), encoding='utf-8') as f:
    rd = csv.DictReader(f)
    for r in rd:
        master[r['Name']] = r['Code']
# Carlos 보유 한국 ETF (PORTFOLIO.md와 동기화)
holdings = [
    'KODEX AI전력핵심설비',
    'TIGER 200',
    'TIGER 미국S&P500',
    'TIGER KRX금현물',
    'KODEX 삼성전자채권혼합',
    'KODEX 종합채권(AA-이상)액티브',
    'KODEX 차이나휴머노이드로봇',
]
codes = {n: master.get(n) for n in holdings}
# 최신가
last = {}
with open(pf, encoding='utf-8') as f:
    rd = csv.DictReader(f)
    for r in rd:
        c = r.get('Code') or r.get('﻿Code')
        last[c] = (r['Date'], r['Close'])
print(f"PRICE_FILE={os.path.basename(pf)}")
for n, c in codes.items():
    if c and c in last:
        d, p = last[c]
        print(f"{n}|{c}|{d}|{p}")
    else:
        print(f"{n}|{c or 'CODE_MISSING'}|N/A|N/A")
PYEOF
```

### 3단계: 출력

표 없이 줄바꿈 형식으로 출력:

---

**📋 [DATE] 포트폴리오 점검 — Carlos**

**🇺🇸 미장 (위성)**
TSLL 1,037주 — 평단 $172.95 · 현재가 [Carlos 입력 대기] · 손익 [—]
BITX 415주 — 평단 $322.79 · 현재가 [Carlos 입력 대기] · 손익 [—]

> 💬 미장 종가는 마지막에 알려주시면 손익까지 계산해드립니다.

---

**🇰🇷 국장 코어 (1억)**
가격 기준일: [최신 영업일]

KODEX AI전력핵심설비 · 종가 [가격]원 · [전주대비 등락률] · 시그널 [HOLD/REBAL/CUT]
TIGER 200 · ...
(보유 7종 모두)

> 비중·수량은 PORTFOLIO.md 에 아직 입력되지 않음 → 알려주시면 비중 갭 분석 가능.

---

**🚨 알림**
손절 임박: [없음 / 종목·사유]
목표가 근접: [없음 / 종목·사유]
리밸런싱 시그널: [자산군별 ±5%p 이탈 여부]

---

**💡 제안**
- 추가매수 후보: [채권/금/AI 등 비중 부족 자산군]
- 감축 후보: [과열·손절 임박 종목]
- 다음 액션: [특이사항 없으면 "유지"]

---

## 시그널 룰

- **HOLD**: 평단대비 -5% ~ +15% 구간, 추세 양호
- **REBAL**: 자산군 비중 ±5%p 이탈
- **CUT**: 평단대비 -10% 이하 또는 손절가 이탈

## 사용자가 "비중 알려줄게"라고 하면

각 종목 수량/평단 입력받아 PORTFOLIO.md 업데이트, 자산군별 비중 갭 분석 + 리밸런싱 표 출력.
