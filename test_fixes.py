import sys
import io
from pathlib import Path
import asyncio

# Fix printing unicode in Windows command prompt for tests
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf8')

sys.path.insert(0, str(Path(r"d:\ainigravity\work\kabu\antigravity")))

from backend.kabu_client import MockKabuClient
from backend.report_service import _format_price

async def test_mock_client():
    print("=== Testing MockKabuClient.get_stock_history ===")
    client = MockKabuClient()
    df = await client.get_stock_history("9432", days=5) # NTT
    print(f"9432 (NTT) last prices:\n{df['close'].tail()}")
    
    df = await client.get_stock_history("1959", days=5)
    print(f"\n1959 last prices:\n{df['close'].tail()}")

def test_format_price():
    print("\n=== Testing _format_price ===")
    prices = [156.4, 156.0, 999.9, 1000.0, 5000.0, 11285.5]
    for p in prices:
        print(f"{p} -> {_format_price(p)}")

if __name__ == "__main__":
    asyncio.run(test_mock_client())
    test_format_price()
