"""
run_pipeline.py - /분석 command wrapper
Tries multiple MongoDB hosts, then runs the full weekly analysis pipeline.
"""
import os, sys, subprocess

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

def find_mongo_host():
    """Try multiple hosts to find accessible MongoDB."""
    from pymongo import MongoClient
    hosts = ['localhost', 'host.docker.internal', '172.17.0.1', '172.18.0.1', '192.168.65.2']
    for h in hosts:
        try:
            c = MongoClient(h, 27017, serverSelectionTimeoutMS=2000)
            c.admin.command('ping')
            c.close()
            print(f"  MongoDB OK: {h}:27017")
            return h
        except Exception as e:
            print(f"  MongoDB NG: {h} ({type(e).__name__})")
    return None

def patch_mongo_host(host):
    """Monkey-patch pymongo MongoClient default to use found host."""
    import pymongo
    _orig = pymongo.MongoClient.__init__
    def patched(self, h='localhost', port=27017, **kw):
        if h == 'localhost':
            h = host
        _orig(self, h, port, **kw)
    pymongo.MongoClient.__init__ = patched

def run_step(label, script):
    print(f"\n{'='*50}")
    print(f"  {label}")
    print('='*50)
    r = subprocess.run([sys.executable, os.path.join(BASE_DIR, script)],
                       capture_output=False, text=True)
    if r.returncode != 0:
        print(f"  [ERROR] {script} failed (exit {r.returncode})")
        sys.exit(r.returncode)

def main():
    print("\n" + "="*50)
    print("  /분석 - 주간 퀀트 분석 파이프라인")
    print("="*50)

    # 1. MongoDB 연결 확인
    print("\n  MongoDB 연결 확인 중...")
    mongo_host = find_mongo_host()
    if not mongo_host:
        print("\n  [오류] MongoDB에 연결할 수 없습니다.")
        print("  Windows에서 MongoDB 서비스가 실행 중인지 확인하세요:")
        print("    net start MongoDB")
        print("  또는 2_weekly.bat 을 직접 실행하세요.")
        sys.exit(1)

    # MongoClient 호출을 올바른 호스트로 패치
    patch_mongo_host(mongo_host)

    # 2. 파이프라인 실행
    run_step("[1/4] 데이터 업데이트 중...", "update_data.py")

    # 기관 포트폴리오 수집 (실패해도 파이프라인 계속)
    print(f"\n{'='*50}")
    print("  [1-b/4] 글로벌 기관 포트폴리오 수집 중...")
    print('='*50)
    r_inst = subprocess.run(
        [sys.executable, os.path.join(BASE_DIR, 'fetch_institutional.py')],
        capture_output=False, text=True
    )
    if r_inst.returncode != 0:
        print("  [경고] fetch_institutional.py 실패 — 캐시 데이터로 계속 진행")

    # 한국 외국인/기관 매매 동향 수집 (실패해도 파이프라인 계속)
    print(f"\n{'='*50}")
    print("  [1-c/4] 한국 외국인/기관 매매 동향 수집 중...")
    print('='*50)
    r_kr = subprocess.run(
        [sys.executable, os.path.join(BASE_DIR, 'fetch_kr_investor.py')],
        capture_output=False, text=True
    )
    if r_kr.returncode != 0:
        print("  [경고] fetch_kr_investor.py 실패 — 건너뜀 (pykrx 설치 확인)")

    run_step("[2/4] 퀀트 분석 실행 중...", "weekly_analysis.py")
    run_step("[3/4-a] 리포트 생성 중...", "generate_report.py")
    run_step("[3/4-b] HTML 빌드 중...", "build_html.py")
    run_step("[4/4] 텔레그램 전송 중...", "send_telegram.py")

    # GitHub Issue 생성 (gh CLI 없으면 건너뜀)
    print(f"\n{'='*50}")
    print("  [4-b/4] GitHub Issue 생성 중...")
    print('='*50)
    r_gh = subprocess.run(
        [sys.executable, os.path.join(BASE_DIR, 'create_github_issue.py')],
        capture_output=False, text=True
    )
    if r_gh.returncode != 0:
        print("  [경고] GitHub Issue 생성 실패 — gh CLI 설치/인증 확인 (선택 기능)")

    print("\n" + "="*50)
    print("  완료! 텔레그램을 확인하세요.")
    print("="*50)

if __name__ == '__main__':
    main()
