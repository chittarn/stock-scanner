import yfinance as yf
import pandas as pd
import json

def calculate_momentum(tickers):
    data = yf.download(tickers + ['SPY'], period="1y", auto_adjust=True, progress=False)['Close']
    data = data.ffill()
    
    w6, w3 = 0.6, 0.4
    results = []
    
    for t in tickers:
        if t in data.columns:
            curr = data[t].iloc[-1]
            p3m = data[t].iloc[-min(63, len(data)-1)]
            p6m = data[t].iloc[-min(126, len(data)-1)]
            
            ret3m = (curr / p3m - 1) * 100
            ret6m = (curr / p6m - 1) * 100
            score = (ret6m * w6) + (ret3m * w3)
            
            ma200 = data[t].rolling(window=200).mean().iloc[-1]
            above_ma200 = curr > ma200
            conviction = score * 1.2 if above_ma200 else score * 0.5
            
            results.append({
                'Ticker': t,
                'Score': score,
                'Conviction': conviction,
                'Above_MA200': above_ma200,
                'Price': curr
            })
            
    return pd.DataFrame(results).sort_values('Conviction', ascending=False)

current_universe = ["NVDA", "MSFT", "QQQ", "AMZN", "SMH", "CAT", "XLE", "WMT", "GLD"]
candidates = ["AMD", "LLY", "META", "GOOGL", "AAPL", "XLF", "XLV", "TSLA", "AVGO"]

print("--- Current Universe Performance ---")
print(calculate_momentum(current_universe))

print("\n--- Candidates Performance ---")
print(calculate_momentum(candidates))
