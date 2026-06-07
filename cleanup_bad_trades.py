# -*- coding: utf-8 -*-
"""
DB Cleanup: Remove fake sell records with price=0 and qty=0
These were caused by a bug in BasicLossCutManager returning pending status
that was incorrectly treated as sell orders.
"""
import sys
import os
import sqlite3
from datetime import datetime

sys.path.append(os.path.abspath("d:/ainigravity/work/kabu/antigravity"))

DB_PATH = os.path.join("d:/ainigravity/work/kabu/antigravity", "data", "antigravity.db")

def cleanup():
    # Try to find DB
    if not os.path.exists(DB_PATH):
        # Search for it
        for root, dirs, files in os.walk("d:/ainigravity/work/kabu/antigravity"):
            for f in files:
                if f.endswith(".db"):
                    print(f"Found DB: {os.path.join(root, f)}")
        print(f"DB not found at {DB_PATH}")
        return

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # 1. Count bad records
    cursor.execute("""
        SELECT COUNT(*) as cnt FROM trade_history 
        WHERE side = 'SELL' AND price = 0 AND qty = 0
    """)
    bad_count = cursor.fetchone()["cnt"]
    print(f"Found {bad_count} bad sell records (price=0, qty=0)")

    # 2. Show some samples
    cursor.execute("""
        SELECT id, symbol, symbol_name, side, price, qty, strategy_name, timestamp, realized_pnl
        FROM trade_history 
        WHERE side = 'SELL' AND price = 0 AND qty = 0
        ORDER BY timestamp DESC
        LIMIT 5
    """)
    print("\nSample bad records:")
    for row in cursor.fetchall():
        print(f"  ID={row['id']} | {row['symbol']} | {row['side']} | price={row['price']} | qty={row['qty']} | pnl={row['realized_pnl']} | {row['timestamp']}")

    # 3. Count good records
    cursor.execute("""
        SELECT COUNT(*) as cnt FROM trade_history 
        WHERE NOT (side = 'SELL' AND price = 0 AND qty = 0)
    """)
    good_count = cursor.fetchone()["cnt"]
    print(f"\nGood records that will be kept: {good_count}")

    # 4. Delete bad records
    if bad_count > 0:
        cursor.execute("""
            DELETE FROM trade_history 
            WHERE side = 'SELL' AND price = 0 AND qty = 0
        """)
        conn.commit()
        print(f"\n✅ Deleted {bad_count} bad records.")
    else:
        print("\nNo bad records to delete.")

    # 5. Show remaining summary
    cursor.execute("""
        SELECT side, COUNT(*) as cnt, SUM(realized_pnl) as total_pnl
        FROM trade_history 
        WHERE date(timestamp) = date('now', 'localtime')
        GROUP BY side
    """)
    print("\nToday's remaining records:")
    for row in cursor.fetchall():
        print(f"  {row['side']}: {row['cnt']} trades, Total P&L: ¥{row['total_pnl'] or 0:,.0f}")

    conn.close()

if __name__ == "__main__":
    cleanup()
