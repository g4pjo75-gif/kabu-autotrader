import json
import sqlite3
import sys

sys.stdout.reconfigure(encoding='utf-8')

def report_status():
    db_path = r"d:\ainigravity\work\kabu\antigravity\data\antigravity.db"
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    
    print("=== Active Automation Configs ===")
    c.execute("SELECT * FROM automation_configs WHERE is_active=1")
    active_configs = c.fetchall()
    for row in active_configs:
        config = json.loads(row["config_json"])
        ext = config.get("extraction_strategy")
        uni = config.get("target_universe")
        print(f"ID: {row['id']}, Name: {row['name']}, Strategy: {ext} ({uni})")

    print("\n=== Analysis Candidates for 2026-04-01 ===")
    c.execute("SELECT * FROM analysis_candidates WHERE date='2026-04-01'")
    candidates = c.fetchall()
    if not candidates:
        print("No candidates found.")
    for row in candidates:
        print(f"[{row['status']}] {row['extraction_strategy']} ({row['target_universe']}): {row['symbol']} - {row['skip_reason']}")

if __name__ == "__main__":
    report_status()
