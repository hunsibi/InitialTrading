"""
create_github_issue.py
주간 분석 결과를 GitHub Issue로 자동 등록 (날짜별 히스토리).
로컬: gh auth login 필요 / GitHub Actions: GH_TOKEN 자동 설정
"""
import os, sys, subprocess, glob

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LABEL = 'weekly-analysis'


def get_repo() -> str:
    """현재 GitHub repo (owner/name) 반환. Actions: 환경변수, 로컬: gh CLI."""
    repo = os.environ.get('GITHUB_REPOSITORY', '')
    if repo:
        return repo
    try:
        r = subprocess.run(
            ['gh', 'repo', 'view', '--json', 'nameWithOwner', '--jq', '.nameWithOwner'],
            capture_output=True, text=True, cwd=BASE_DIR
        )
        if r.returncode == 0:
            return r.stdout.strip()
    except Exception:
        pass
    return ''


def get_report_url(date: str) -> str:
    """reports/report_{date}.html 의 GitHub URL 반환."""
    repo = get_repo()
    if repo and date:
        return f"https://github.com/{repo}/blob/master/reports/report_{date}.html"
    return ''


def run_parse() -> dict:
    r = subprocess.run(
        [sys.executable, os.path.join(BASE_DIR, 'parse_report.py')],
        capture_output=True, text=True, encoding='utf-8'
    )
    d = {}
    for line in r.stdout.splitlines():
        if '=' in line:
            k, _, v = line.partition('=')
            d[k.strip()] = v.strip()
    return d


def g(d, k): return d.get(k, '')


def build_body(d: dict) -> str:
    date = g(d, 'DATE')
    parts = [f"## 📊 {date} 주간 퀀트 분석\n"]

    # 한국 시장
    parts.append("### 🇰🇷 한국 시장")
    parts.append("| 지수 | 수익률 | 상승 | 하락 |")
    parts.append("|---|---:|---:|---:|")
    for key, name in [('KS', 'KOSPI'), ('KD', 'KOSDAQ')]:
        v = g(d, key)
        if v:
            p = v.split('|')
            parts.append(f"| {name} | {p[0]} | {p[1] if len(p)>1 else '-'} | {p[2] if len(p)>2 else '-'} |")
    parts.append("")

    # 미국 시장
    parts.append("### 🇺🇸 미국 시장")
    parts.append("| 지수 | 수익률 | 상승 | 하락 |")
    parts.append("|---|---:|---:|---:|")
    for key, name in [('US_SP', 'S&P 500'), ('US_NQ', 'NASDAQ'), ('US_DJ', 'Dow Jones')]:
        v = g(d, key)
        if v:
            p = v.split('|')
            parts.append(f"| {name} | {p[0]} | {p[1] if len(p)>1 else '-'} | {p[2] if len(p)>2 else '-'} |")
    parts.append("")

    def stock_section(pfx, title, icon):
        rows = []
        for i in range(5):
            v = g(d, f'{pfx}{i}')
            if not v:
                continue
            p = v.split('|')
            if len(p) < 16:
                continue
            name_s, code, sector = p[0], p[1], p[3]
            r1w, r12w = p[5], p[6]
            entry, t1, t1p, stop, stop_pct = p[9], p[12], p[13], p[10], p[11]
            rows.append(
                f"| {i+1} | **{name_s}** `{code}` | {sector} | {r1w} | {r12w} |"
                f" {entry}원 | {t1}원({t1p}) | {stop}원({stop_pct}) |"
            )
        if not rows:
            return []
        return [
            f"\n### {icon} {title}",
            "| # | 종목(코드) | 업종 | 주간 | 12주 | 매수가 | 목표① | 손절 |",
            "|---|---|---|---:|---:|---:|---:|---:|",
            *rows,
        ]

    parts.extend(stock_section('S', '안정 대장주 TOP5', '🟢'))
    parts.extend(stock_section('M', '단기 모멘텀 TOP5', '🔴'))
    parts.extend(stock_section('E', 'ETF 추천 TOP5',   '🔵'))
    parts.extend(stock_section('I', '기관연동 한국종목 TOP5', '🟣'))

    # 한국 시총 TOP5
    kr_rows = []
    for i in range(5):
        v = g(d, f'KR_CAP{i}')
        if v:
            p = v.split('|')
            kr_rows.append(f"| {i+1} | {p[0]} | {p[1]} | {p[2]} | {p[3]}원 | {p[4]} |")
    if kr_rows:
        parts += ["\n### 🇰🇷 한국 시총 TOP5",
                  "| # | 종목 | 코드 | 시총 | 주가 | 주간 |",
                  "|---|---|---|---:|---:|---:|", *kr_rows]

    # 미국 시총 TOP5
    us_rows = []
    for i in range(5):
        v = g(d, f'US_CAP{i}')
        if v:
            p = v.split('|')
            us_rows.append(f"| {i+1} | {p[0]} | {p[1]} | {p[2]} | {p[3]} | {p[4]} |")
    if us_rows:
        parts += ["\n### 🇺🇸 미국 시총 TOP5",
                  "| # | 종목 | 티커 | 시총 | 주가 | 주간 |",
                  "|---|---|---|---:|---:|---:|", *us_rows]

    # 한국 시장 수급동향
    def flow_rows(cat_prefix, label, sign):
        cnt = int(g(d, f'{cat_prefix}_COUNT') or 0)
        rows = []
        for i in range(cnt):
            v = g(d, f'{cat_prefix}_{i}')
            if not v:
                continue
            p = v.split('|')
            if len(p) < 3:
                continue
            amt = int(p[2])
            rows.append(f"| {i+1} | {p[0]} | `{p[1]}` | {sign}{abs(amt):,}억원 |")
        return rows

    fb = flow_rows('KR_FOREIGN_BUY',  '외국인 순매수', '+')
    fs = flow_rows('KR_FOREIGN_SELL', '외국인 순매도', '-')
    ib = flow_rows('KR_INST_BUY',     '기관 순매수',   '+')
    is_ = flow_rows('KR_INST_SELL',   '기관 순매도',   '-')

    if any([fb, fs, ib, is_]):
        parts.append("\n### 📊 한국 시장 수급동향")
        hdr = ["| # | 종목 | 코드 | 금액 |", "|---|---|---|---:|"]
        if fb:
            parts += ["\n**🌏 외국인 순매수 TOP5**", *hdr, *fb]
        if fs:
            parts += ["\n**🌏 외국인 순매도 TOP5**", *hdr, *fs]
        if ib:
            parts += ["\n**🏛️ 기관 순매수 TOP5**", *hdr, *ib]
        if is_:
            parts += ["\n**🏛️ 기관 순매도 TOP5**", *hdr, *is_]

    # 글로벌 기관 동향
    inst_count = int(g(d, 'INST_COUNT') or 0)
    if inst_count > 0:
        parts += ["\n### 🌍 글로벌 기관 포트폴리오",
                  "| 기관 | 분기 | TOP3 섹터 | TOP3 종목 |",
                  "|---|---|---|---|"]
        for j in range(min(inst_count, 11)):
            v = g(d, f'INST{j}')
            if not v:
                break
            p = v.split('|')
            parts.append(
                f"| {p[0]} | {p[2] if len(p)>2 else '-'} |"
                f" {p[3] if len(p)>3 else '-'} | {p[4] if len(p)>4 else '-'} |"
            )

    # HTML 리포트 링크 (reports/ 폴더에 커밋된 경우)
    report_url = get_report_url(date)
    if report_url:
        parts.append(f"\n---\n📎 **[HTML 리포트 열기]({report_url})**")

    parts += ["\n---",
              "_⚠️ 퀀트 모델 자동 산출 결과 — 투자 손익 책임은 본인에게 있습니다_"]
    return '\n'.join(parts)


def ensure_label():
    subprocess.run(
        ['gh', 'label', 'create', LABEL,
         '--color', '0075ca',
         '--description', '주간 퀀트 분석 히스토리'],
        capture_output=True, cwd=BASE_DIR
    )


def create_issue(title: str, body: str) -> bool:
    ensure_label()
    r = subprocess.run(
        ['gh', 'issue', 'create', '--title', title, '--body', body, '--label', LABEL],
        capture_output=True, text=True, cwd=BASE_DIR
    )
    if r.returncode == 0:
        print(f"  GitHub Issue 생성 완료: {r.stdout.strip()}")
        return True
    print(f"  [경고] GitHub Issue 생성 실패: {r.stderr.strip()}")
    return False


def main():
    d = run_parse()
    if not d or not g(d, 'DATE'):
        print("  [경고] 리포트 데이터 없음 — GitHub Issue 생성 건너뜀")
        return
    title = f"[{g(d, 'DATE')}] 주간 퀀트 분석"
    body  = build_body(d)
    create_issue(title, body)


if __name__ == '__main__':
    main()
