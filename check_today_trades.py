import sqlite3
import pandas as pd
import sys
sys.stdout.reconfigure(encoding='utf-8')

conn = sqlite3.connect('d:/ainigravity/work/kabu/antigravity/data/antigravity.db')
print("=== 2026-04-22 Trades ===")
query = """
SELECT symbol, symbol_name, side, price, qty, strategy_name, timestamp 
FROM trade_history 
WHERE date(timestamp) = '2026-04-22' 
ORDER BY timestamp
"""
trades = pd.read_sql_query(query, conn)
print(trades.to_string())

print("\n=== Candidates for traded symbols ===")
traded_symbols = tuple(trades['symbol'].tolist())
if traded_symbols:
    if len(traded_symbols) == 1:
        symbols_str = f"('{traded_symbols[0]}')"
    else:
        symbols_str = str(traded_symbols)
        
    query2 = f"""
    SELECT symbol, price, score, rank, status, skip_reason 
    FROM analysis_candidates 
    WHERE symbol IN {symbols_str} AND date = '2026-04-22'
    """
    candidates = pd.read_sql_query(query2, conn)
    print(candidates.to_string())
        
conn.close()
