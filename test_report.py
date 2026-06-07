import sys
import asyncio
sys.path.insert(0, r'd:\ainigravity\work\kabu\antigravity')
from backend.database import Database
from backend.report_service import ReportService

async def main():
    db = Database()
    rep = ReportService({'database': db})
    r = await rep.generate_daily_report()
    print("FINISHED")

asyncio.run(main())
