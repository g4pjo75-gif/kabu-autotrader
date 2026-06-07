import asyncio
from backend.kabu_client import KabuClient
from backend.database import Database

async def test():
    db = Database("data/antigravity.db")
    pw = db.get_setting("api_password_production")
    
    client = KabuClient()
    await client.get_token(pw)
    for ex in ["ALL", "TSE", "TSE_P", "TSE_S", "TSE_G", "3", "4", "5"]:
        res = await client.get_ranking("1", ex)
        print(f"{ex} -> {len(res)} items")
    await client.close()

if __name__ == "__main__":
    asyncio.run(test())
