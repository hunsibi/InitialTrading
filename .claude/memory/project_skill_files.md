---
name: InitialTrading skill files
description: weekly-quant.skill and 분析.skill location and purpose for /분析 command
type: project
---
D:\WorkSpace\InitialTrading 에 두 개의 스킬 파일이 있다:
- `weekly-quant.skill` → `/weekly-quant` 커맨드 (name: weekly-quant)
- `분析.skill` → `/분석` 커맨드 (name: 분석)

두 파일 모두 동일한 파이프라인 로직을 가진다:
1. `python run_pipeline.py 2>&1` 실행 (MongoDB 접속 → 데이터 업데이트 → 퀀트 분析 → 리포트 생성 → 텔레그램 전송)
2. 성공: "완료! 텔레그램을 확인하세요" 포함 시 pipeline_ok=True
3. 실패: "MongoDB에 연결할 수 없습니다" 포함 시 기존 데이터로 fallback
4. `python parse_report.py` 실행 → outputs/reports/weekly_full_*.html 파싱
5. TOP5 종목 결과 출력 + 텔레그램 전송 완료 안내

**Why:** 기존 스킬은 /sessions/zen-clever-feynman 경로(Docker) 기반이었고, 파이프라인 미실행 + python3 사용으로 현재 환경(Windows, D:\WorkSpace\InitialTrading)에서 동작 안 했음.

**How to apply:** 경로는 항상 D:/WorkSpace/InitialTrading, Python 명령은 python (not python3).
