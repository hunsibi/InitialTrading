import weekly_analysis as wa
import pandas as pd
import numpy as np

prices = wa.load_recent_prices(n_quarters=3)
master = wa.load_master()
ind    = wa.compute_indicators_vectorized(prices)
scored = wa.screen_and_score(ind, master)

top5 = scored.head(5)
for _, row in top5.iterrows():
    tl = wa.calc_trade_levels(row)
    print("---")
    print(row['Name'], row['Code'])
    print("Close", row['Close'], "MA20", round(row['MA20'],0), "MA60", round(row['MA60'],0))
    print("RSI", round(row['RSI'],1), "MACD_Hist", round(row['MACD_Hist'],1), "ATR", round(row['ATR'],1))
    print("Vol_Ratio", round(row['Vol_Ratio'],2), "Avg_Volume", round(row['Avg_Volume'],0))
    print("Ret_1W", round(row['Ret_1W']*100,1), "Ret_4W", round(row['Ret_4W']*100,1), "Ret_12W", round(row['Ret_12W']*100,1))
    print("Entry", tl['Entry'], "Stop", tl['StopLoss'], "Stop_Pct", tl['Stop_Pct'])
    print("Target1", tl['Target1'], "T1_Pct", tl['T1_Pct'], "Target2", tl['Target2'], "T2_Pct", tl['T2_Pct'])
    print("RR1", tl['RR1'], "RR2", tl['RR2'])
