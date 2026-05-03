import os
import pandas as pd
import FinanceDataReader as fdr
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
import concurrent.futures
from tqdm import tqdm
import time

# 1. 환경 설정
DATA_DIR = 'outputs/data'
os.makedirs(DATA_DIR, exist_ok=True)

def get_quarterly_ranges(start_date, end_date):
    ranges = []
    current = start_date
    while current < end_date:
        next_q = current + relativedelta(months=3)
        q_end = next_q - timedelta(days=1)
        if q_end > end_date:
            q_end = end_date
        ranges.append((current, q_end))
        current = next_q
    return ranges

# 2. 마스터 로드
print("\n[1/3] Checking Master Info...")
master_path = os.path.join(DATA_DIR, 'master_info.csv')
if not os.path.exists(master_path):
    print("Master info not found. Downloading...")
    kospi = fdr.StockListing('KOSPI')
    kosdaq = fdr.StockListing('KOSDAQ')
    master = pd.concat([kospi.assign(Market='KOSPI'), kosdaq.assign(Market='KOSDAQ')])
    master.to_csv(master_path, index=False, encoding='utf-8-sig')
else:
    master = pd.read_csv(master_path)

all_tickers = master['Code'].tolist()
print(f"Master Info loaded: {len(all_tickers)} tickers found.")

# 3. 날짜 설정
end_dt = datetime.now()
start_dt = end_dt - relativedelta(years=5)
quarter_ranges = get_quarterly_ranges(start_dt, end_dt)

def fetch_price_single(ticker, s_date, e_date):
    try:
        df = fdr.DataReader(ticker, s_date, e_date)
        if not df.empty:
            df = df.reset_index()
            df['Code'] = ticker
            return df
    except:
        return None

# 4. 메인 루프
print(f"\n[2/3] Resuming Download (Skipping existing CSVs)...")

for s_dt, e_dt in quarter_ranges:
    year_q = f"prices_{s_dt.year}_Q{(s_dt.month-1)//3 + 1}"
    price_file = os.path.join(DATA_DIR, f'{year_q}.csv')
    
    # 이어받기: 파일이 이미 존재하고 크기가 어느 정도(100KB) 이상이면 패스
    if os.path.exists(price_file) and os.path.getsize(price_file) > 100000:
        print(f"Check: {year_q}.csv already exists. [Skipped]")
        continue

    print(f"\n>>> Current Phase: {year_q} ({s_dt.date()} ~ {e_dt.date()})")
    
    # 데이터 확인용 샘플 미리보기 (첫 번째 종목)
    print(f" - Verifying data connection for {all_tickers[0]}...")
    sample_df = fdr.DataReader(all_tickers[0], s_dt, e_dt)
    if not sample_df.empty:
        print("\n" + "="*50)
        print(f" [DATA PREVIEW: {all_tickers[0]}]")
        print(sample_df.head(3)) # 처음 3줄 출력
        print("="*50 + "\n")
    
    all_prices = []
    # 멀티스레딩 및 진행바 표시
    with concurrent.futures.ThreadPoolExecutor(max_workers=30) as executor:
        futures = {executor.submit(fetch_price_single, t, s_dt, e_dt): t for t in all_tickers}
        
        # tqdm 진행바
        for future in tqdm(concurrent.futures.as_completed(futures), 
                          total=len(all_tickers), 
                          desc=f"Download Progress ({year_q})"):
            res = future.result()
            if res is not None:
                all_prices.append(res)
    
    if all_prices:
        final_df = pd.concat(all_prices)
        final_df.to_csv(price_file, index=False, encoding='utf-8-sig')
        print(f"Result: {price_file} saved successfully ({len(final_df)} rows).")

print("\n[3/3] All missing data collection completed!")
