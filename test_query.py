import asyncio
import json
from backend.database import Database

db = Database()
candidates = db.get_analysis_candidates("2026-04-06")

results = []
for c in candidates:
    if c.extraction_strategy == "TripleConfirmScorer" and c.target_universe == "nikkei400":
        results.append({
            "symbol": c.symbol,
            "score": c.score,
            "details": c.details
        })

print(json.dumps(results, indent=2, ensure_ascii=False))
