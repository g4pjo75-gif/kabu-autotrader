import asyncio
import sys
import os
from datetime import datetime

# Add project root to path
sys.path.append(os.path.abspath("d:/ainigravity/work/kabu/antigravity"))

from backend.database import Database

def test_dashboard_logic():
    print("Testing Dashboard Data Retrieval Logic...")
    db = Database()
    
    # 1. Test get_today_trades
    print("\n[1] Testing get_today_trades()...")
    try:
        trades = db.get_today_trades()
        print(f"Found {len(trades)} trades for today.")
        if trades:
            t = trades[0]
            print(f"Sample Trade: {t.symbol} {t.side} @ {t.price} (PnL: {t.realized_pnl})")
    except Exception as e:
        print(f"FAILED: {e}")

    # 2. Test get_trades (History)
    print("\n[2] Testing get_trades(limit=50)...")
    try:
        history = db.get_trades(limit=50)
        print(f"Found {len(history)} historical trades.")
    except Exception as e:
        print(f"FAILED: {e}")

    # 3. Test Daily Summary Aggregation Logic
    print("\n[3] Testing Daily Summary Aggregation...")
    try:
        all_trades = db.get_trades(limit=500)
        from collections import defaultdict
        daily_stats = defaultdict(lambda: {"pnl": 0})
        
        for t in all_trades:
            if hasattr(t, 'realized_pnl') and t.realized_pnl:
                date_str = t.timestamp.strftime("%Y-%m-%d")
                daily_stats[date_str]["pnl"] += t.realized_pnl
        
        print("Daily P&L Calculation Result:")
        for d, stats in daily_stats.items():
            print(f" - {d}: {stats['pnl']}")
            
    except Exception as e:
        print(f"FAILED: {e}")

if __name__ == "__main__":
    test_dashboard_logic()
