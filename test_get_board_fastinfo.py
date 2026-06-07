import asyncio
import sys
from backend.kabu_client import MockKabuClient

sys.stdout.reconfigure(encoding='utf-8')

async def main():
    client = MockKabuClient()
    print("Testing get_board with fast_info logic...")
    
    symbols = ["1605", "4684", "6383", "9983"]
    for s in symbols:
        try:
            board = await client.get_board(s)
            print(f"\n[{s}] Board Info:")
            print(f"  Price: {board.current_price}")
            print(f"  Bid: {board.bid_price}, Ask: {board.ask_price}")
            print(f"  Prev Close: {board.previous_close}")
        except Exception as e:
            print(f"[{s}] Error: {e}")

if __name__ == "__main__":
    asyncio.run(main())
