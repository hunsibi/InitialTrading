"""
market_regime.py — 시장 레짐(상승/중립/하락) 판정
=========================================================
KOSPI 지수의 MA200/MA60 위치와 최근 변동성으로 시장 국면을 판정한다.

판정 규칙:
  상승 : 종가 > MA200 이고 종가 > MA60
  하락 : 종가 < MA200 이고 종가 < MA60
  중립 : 그 외 (MA200/MA60 사이 혼조)
  + 최근 20일 연환산 변동성 >= 30% 이면 '변동성 주의' 플래그

데이터: FinanceDataReader KS11 (실패 시 MongoDB prices 시장 평균으로 폴백 불가
        → regime='중립', available=False 반환하고 파이프라인은 평소대로 진행)

하락장 대응 (generate_report.py에서 적용):
  - 안정/모멘텀/기관연동 추천 수 5 → 3 축소
  - 텔레그램/HTML에 경고 배너 + 현금·채권 비중 확대 권고
"""
import numpy as np
import pandas as pd

VOL_WARN_THRESHOLD = 30.0   # 연환산 변동성 경고 기준 (%)

REGIME_ADVICE = {
    '상승': '추세 우호적 — 추천 종목 정상 비중 접근',
    '중립': '혼조 구간 — 분할 매수, 신규 진입은 절반 비중 권장',
    '하락': '약세 구간 — 신규 매수 최소화, 현금·채권 ETF 비중 확대 권장',
}


def get_regime() -> dict:
    """KOSPI 레짐 판정. 데이터 수집 실패 시 available=False."""
    try:
        import FinanceDataReader as fdr
        from datetime import datetime, timedelta
        since = (datetime.now() - timedelta(days=420)).strftime('%Y-%m-%d')
        ks = fdr.DataReader('KS11', since)
        if ks is None or len(ks) < 200:
            raise RuntimeError(f"KOSPI 데이터 부족 ({0 if ks is None else len(ks)}일)")

        close = ks['Close'].dropna()
        cur   = float(close.iloc[-1])
        ma60  = float(close.rolling(60).mean().iloc[-1])
        ma200 = float(close.rolling(200).mean().iloc[-1])

        daily_ret = close.pct_change().dropna().tail(20)
        vol20 = float(daily_ret.std() * np.sqrt(252) * 100)

        if cur > ma200 and cur > ma60:
            regime = '상승'
        elif cur < ma200 and cur < ma60:
            regime = '하락'
        else:
            regime = '중립'

        return {
            'available':  True,
            'regime':     regime,
            'kospi':      round(cur, 2),
            'ma60':       round(ma60, 2),
            'ma200':      round(ma200, 2),
            'ma200_gap':  round((cur / ma200 - 1) * 100, 2),
            'vol20':      round(vol20, 1),
            'vol_warn':   vol20 >= VOL_WARN_THRESHOLD,
            'advice':     REGIME_ADVICE[regime],
            'date':       close.index[-1].strftime('%Y-%m-%d'),
        }
    except Exception as e:
        print(f"  [레짐] KOSPI 데이터 수집 실패: {e} — 중립으로 간주하고 계속 진행")
        return {'available': False, 'regime': '중립', 'vol_warn': False,
                'advice': REGIME_ADVICE['중립']}


if __name__ == '__main__':
    r = get_regime()
    print("\n  시장 레짐 판정")
    print("  " + "-" * 40)
    if r['available']:
        print(f"  기준일   : {r['date']}")
        print(f"  KOSPI    : {r['kospi']:,.2f}")
        print(f"  MA60     : {r['ma60']:,.2f}")
        print(f"  MA200    : {r['ma200']:,.2f} (이격 {r['ma200_gap']:+.2f}%)")
        print(f"  변동성   : 연환산 {r['vol20']}%{' ⚠️ 경고' if r['vol_warn'] else ''}")
    print(f"  레짐     : {r['regime']}")
    print(f"  권고     : {r['advice']}")
