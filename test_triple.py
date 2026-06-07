import asyncio
import pandas as pd
import yfinance as yf
from strategies.extraction import TripleConfirmScorer

async def evaluate_symbols():
    symbols = ['2670.T', '2503.T', '1419.T']
    
    # Download data up to 2026-04-06 (or just last available info assuming recent market close)
    df = yf.download(symbols, start="2025-10-01", end="2026-04-07", group_by="ticker", progress=False)
    
    scorer = TripleConfirmScorer()
    
    results = []
    
    for symbol in symbols:
        ticker = symbol.replace('.T', '')
        if len(symbols) == 1:
            data = df
        else:
            data = df[symbol]
        
        data = data.dropna()
        # Rename columns to lowercase to match strategy logic
        data = data.rename(columns={"Open": "open", "High": "high", "Low": "low", "Close": "close", "Volume": "volume"})
        
        result = await scorer.evaluate(ticker, data)
        results.append({
            "Symbol": ticker,
            "Score": result.score / 10.0, # Map back to 0-10 base score
            "Details": result.details
        })
        
    for r in results:
        print(f"[{r['Symbol']}] Score: {r['Score']}")
        for k, v in r['Details'].items():
            print(f"  - {k}: {v}")

asyncio.run(evaluate_symbols())
