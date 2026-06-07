import asyncio
import sys
from pathlib import Path

sys.path.append(r"d:\ainigravity\work\kabu\antigravity")

from backend.database import Database

def main():
    db = Database()
    trades = db.get_trades(limit=10)
    print("Recent 10 trades:")
    for t in trades:
        print(f"{t.timestamp} - {t.symbol} - {t.side} - {t.qty} @ {t.price}")

if __name__ == "__main__":
    main()
