"""
backtest.py — 워크포워드 백테스트 (팩터 가중치 검증 도구)
=========================================================
과거 매주 금요일 시점에 "그날까지의 데이터만으로" TOP5를 뽑고
다음 5거래일(1주) 수익률을 측정한다. look-ahead 없음.

검증 대상:
  - 안정 대장주 모델: 팩터 가중치 4개 변형 비교
  - 단기 모멘텀 모델: 현재 설정
  - 벤치마크: KOSPI 지수 동일 기간 수익률

한계 (해석 시 주의):
  - 시총(Marcap)은 현재 stocks 마스터 값 사용 → 생존 편향이 일부 존재
  - 추천일 종가 매수/5거래일 후 종가 매도 가정 (거래비용·슬리피지 미반영)

사용법:
  python backtest.py                # 최근 52주
  python backtest.py --weeks 104    # 최근 104주(2년)
결과: 콘솔 표 + outputs/backtest_results.csv
"""
import argparse
import os
import numpy as np
import pandas as pd
import weekly_analysis as wa

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUT_CSV  = os.path.join(BASE_DIR, 'outputs', 'backtest_results.csv')

WEIGHT_VARIANTS = {
    '현재(35/30/25/10)':     (0.35, 0.30, 0.25, 0.10),
    '추세중심(45/30/15/10)':  (0.45, 0.30, 0.15, 0.10),
    '모멘텀강화(25/25/20/30)': (0.25, 0.25, 0.20, 0.30),
    '균등(25/25/25/25)':     (0.25, 0.25, 0.25, 0.25),
}

WARMUP_DAYS = 65   # 지표 계산에 필요한 최소 관측일 (weekly_analysis cnt>=65와 동일)
HORIZON     = 5    # 보유 기간 (거래일)


def prepare_indicators(prices: pd.DataFrame) -> pd.DataFrame:
    """전체 시계열 지표 + 코드별 누적 관측일(cnt) 컬럼."""
    print("  전체 시계열 지표 계산 중 (수 분 소요 가능)...")
    ind = wa.compute_rolling_indicators(prices)
    ind['cnt'] = ind.groupby('Code').cumcount() + 1
    return ind


def snapshot_at(ind: pd.DataFrame, date) -> pd.DataFrame:
    """특정 날짜 기준 스냅샷 (그날까지의 데이터만 반영된 지표 행)."""
    snap = ind[ind['Date'] == date].copy()
    snap = snap[snap['cnt'] >= WARMUP_DAYS]
    snap['MACD_Cross'] = np.where(
        (snap['MACD_Hist'] > 0) & (snap['MACD_Hist_Prev'] <= 0), 1,
        np.where((snap['MACD_Hist'] < 0) & (snap['MACD_Hist_Prev'] >= 0), -1, 0))
    return snap.reset_index(drop=True)


def forward_return_table(prices: pd.DataFrame, horizon: int = HORIZON) -> pd.DataFrame:
    """날짜×코드 피벗에서 +horizon 거래일 수익률."""
    pivot = prices.pivot_table(index='Date', columns='Code', values='Close')
    return pivot.shift(-horizon) / pivot - 1


def kospi_forward_returns(dates: list, horizon: int = HORIZON) -> dict:
    """리밸런스 날짜별 KOSPI +horizon 거래일 수익률."""
    try:
        import FinanceDataReader as fdr
        since = (min(dates) - pd.Timedelta(days=10)).strftime('%Y-%m-%d')
        ks    = fdr.DataReader('KS11', since)['Close'].dropna()
        idx   = list(ks.index.normalize())
        out   = {}
        for d in dates:
            d = pd.Timestamp(d).normalize()
            pos = [i for i, dd in enumerate(idx) if dd <= d]
            if not pos or pos[-1] + horizon >= len(ks):
                continue
            i = pos[-1]
            out[d] = float(ks.iloc[i + horizon] / ks.iloc[i] - 1)
        return out
    except Exception as e:
        print(f"  [경고] KOSPI 벤치마크 수집 실패: {e}")
        return {}


def calc_metrics(rets: pd.Series) -> dict:
    rets = rets.dropna()
    if rets.empty:
        return {}
    eq  = (1 + rets).cumprod()
    mdd = float((eq / eq.cummax() - 1).min())
    return {
        '주수':     len(rets),
        '주평균%':  round(rets.mean() * 100, 2),
        '승률%':    round((rets > 0).mean() * 100, 1),
        '누적%':    round((eq.iloc[-1] - 1) * 100, 1),
        'MDD%':    round(mdd * 100, 1),
    }


def run_backtest(weeks: int = 52, top_n: int = 5):
    # 1. 데이터 로드 (리밸런스 주수 + 지표 워밍업 ~300일 여유)
    days = weeks * 7 + 320
    print(f"\n[1/4] 가격 데이터 로드 (최근 {days}일)...")
    prices = wa.load_recent_prices(days=days)
    master = wa.load_master()

    print("\n[2/4] 지표 계산...")
    ind = prepare_indicators(prices)
    fwd = forward_return_table(prices)

    # 2. 리밸런스 날짜: 금요일 + 워밍업 확보 + 5거래일 미래 존재
    all_dates  = sorted(prices['Date'].unique())
    fridays    = [d for d in all_dates if pd.Timestamp(d).weekday() == 4]
    fridays    = [d for d in fridays if d >= all_dates[min(WARMUP_DAYS + 130, len(all_dates) - 1)]]
    fridays    = [d for d in fridays if d <= all_dates[-HORIZON - 1]]
    rebal_dates = fridays[-weeks:]
    if not rebal_dates:
        print("  리밸런스 가능한 날짜가 없습니다. 데이터 기간을 확인하세요.")
        return
    print(f"\n[3/4] 워크포워드 시뮬레이션: {len(rebal_dates)}주 "
          f"({pd.Timestamp(rebal_dates[0]).date()} ~ {pd.Timestamp(rebal_dates[-1]).date()})")

    kospi = kospi_forward_returns(rebal_dates)

    # 3. 주차별 시뮬레이션
    results = {name: [] for name in WEIGHT_VARIANTS}
    results['단기 모멘텀'] = []
    detail_rows = []

    for n, d in enumerate(rebal_dates, 1):
        snap = snapshot_at(ind, d)
        if snap.empty:
            continue
        fwd_row = fwd.loc[d] if d in fwd.index else None
        if fwd_row is None:
            continue

        for name, w in WEIGHT_VARIANTS.items():
            scored = wa.screen_and_score(snap, master, weights=w, verbose=False)
            if scored.empty:
                results[name].append((d, np.nan))
                continue
            codes = scored.head(top_n)['Code'].tolist()
            rets  = fwd_row.reindex(codes).dropna()
            ret   = float(rets.mean()) if not rets.empty else np.nan
            results[name].append((d, ret))
            if name.startswith('현재'):
                detail_rows.append({'date': pd.Timestamp(d).date(), 'model': 'stable',
                                    'codes': ','.join(codes), 'ret_1w': ret})

        scored_m = wa.screen_and_score_momentum(snap, master, verbose=False)
        if scored_m.empty:
            results['단기 모멘텀'].append((d, np.nan))
        else:
            codes = scored_m.head(top_n)['Code'].tolist()
            rets  = fwd_row.reindex(codes).dropna()
            ret   = float(rets.mean()) if not rets.empty else np.nan
            results['단기 모멘텀'].append((d, ret))
            detail_rows.append({'date': pd.Timestamp(d).date(), 'model': 'momentum',
                                'codes': ','.join(codes), 'ret_1w': ret})

        if n % 10 == 0:
            print(f"  ... {n}/{len(rebal_dates)}주 완료")

    # 4. 결과 집계
    print("\n[4/4] 결과 집계\n")
    print("=" * 78)
    print(f"  {'전략':<28s} {'주수':>4s} {'주평균':>7s} {'승률':>6s} {'누적':>8s} {'MDD':>7s}")
    print("-" * 78)

    summary_rows = []
    for name, series in results.items():
        s = pd.Series({d: r for d, r in series})
        m = calc_metrics(s)
        if not m:
            continue
        print(f"  {name:<28s} {m['주수']:>4d} {m['주평균%']:>6.2f}% {m['승률%']:>5.1f}% "
              f"{m['누적%']:>7.1f}% {m['MDD%']:>6.1f}%")
        summary_rows.append({'전략': name, **m})

    if kospi:
        ks = pd.Series(kospi)
        ks = ks[ks.index.isin([pd.Timestamp(d).normalize() for d in rebal_dates])]
        m = calc_metrics(ks)
        if m:
            print("-" * 78)
            print(f"  {'KOSPI (벤치마크)':<28s} {m['주수']:>4d} {m['주평균%']:>6.2f}% "
                  f"{m['승률%']:>5.1f}% {m['누적%']:>7.1f}% {m['MDD%']:>6.1f}%")
            summary_rows.append({'전략': 'KOSPI', **m})
    print("=" * 78)

    # CSV 저장
    os.makedirs(os.path.dirname(OUT_CSV), exist_ok=True)
    pd.DataFrame(summary_rows).to_csv(OUT_CSV, index=False, encoding='utf-8-sig')
    detail_csv = OUT_CSV.replace('.csv', '_detail.csv')
    pd.DataFrame(detail_rows).to_csv(detail_csv, index=False, encoding='utf-8-sig')
    print(f"\n  저장: {OUT_CSV}")
    print(f"  저장: {detail_csv}")
    print("\n  ※ 시총은 현재 마스터 기준(생존 편향 일부), 거래비용 미반영 — 상대 비교용으로 해석할 것")


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description='워크포워드 백테스트')
    ap.add_argument('--weeks', type=int, default=52, help='백테스트 주수 (기본 52)')
    ap.add_argument('--top',   type=int, default=5,  help='주당 선정 종목 수 (기본 5)')
    args = ap.parse_args()
    run_backtest(weeks=args.weeks, top_n=args.top)
