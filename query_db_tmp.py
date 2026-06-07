import sqlite3
db = sqlite3.connect('data/antigravity.db')
cur = db.cursor()
cur.execute("SELECT extraction_strategy, status, skip_reason, symbol FROM analysis_candidates WHERE date='2026-04-27'")
for row in cur.fetchall():
    print(row)
