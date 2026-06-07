import asyncio
import logging
from backend.kabu_client import KabuClient
from backend.universe import Universe
from backend.database import Database

logging.basicConfig(level=logging.INFO, format='%(message)s')

async def test_fetch_leaders():
    print("Connecting to Kabu Station API...")
    
    # Get password from DB
    db = Database("data/antigravity.db")
    api_password = db.get_setting("api_password_production")
    
    if not api_password:
        print("❌ API password not found in database settings.")
        return
        
    client = KabuClient()
    
    try:
        # Get token
        token = await client.get_token(api_password)
        if not token:
            print("[FAIL] Failed to get API token. Check if Kabu Station is running and password is correct.")
            return
        
        print("[OK] Successfully connected and authenticated.")
        
        universe = Universe(client=client)
        
        print("\n--- Testing fetch_intraday_leaders (Market-Separated) ---")
        # Use loose filters to ensure we see some output
        leaders = await universe.fetch_intraday_leaders(
            ranking_type="1",           # 가격 상승률
            secondary_ranking_type="5", # TICK 횟수
            exchange_division="ALL",
            count=150,
            gap_min=-20.0,              # 갭락 허용 (조건 완화)
            gap_max=50.0,               # (조건 완화)
            max_rise_from_open_pct=50.0 # (조건 완화)
        )
        
        print(f"\n[OK] Total filtered leaders found: {len(leaders)}")
        for idx, item in enumerate(leaders[:10], 1):
            print(f"{idx}. {item['symbol']} ({item['name']}) - Price: {item['current_price']}, Gap: {item['gap_pct']}%")
            
        if len(leaders) > 10:
            print(f"... and {len(leaders) - 10} more.")
            
    except Exception as e:
        print(f"[FAIL] Error during test: {e}")
    finally:
        await client.close()

if __name__ == "__main__":
    asyncio.run(test_fetch_leaders())
