
import sqlite3

try:
    conn = sqlite3.connect('d:/ainigravity/work/kabu/antigravity/data/antigravity.db')
    cursor = conn.cursor()
    
    print("Tables:")
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = cursor.fetchall()
    for t in tables:
        print(f"- {t[0]}")
        
    print("\nSchema of automation_configs:")
    cursor.execute("PRAGMA table_info(automation_configs)")
    columns = cursor.fetchall()
    for c in columns:
        print(c)

    print("\nRecent 5 trades:")
    cursor.execute("SELECT * FROM trade_history ORDER BY id DESC LIMIT 5")
    rows = cursor.fetchall()
    for r in rows:
        print(r)
        
    conn.close()
except Exception as e:
    print(f"Error: {e}")
