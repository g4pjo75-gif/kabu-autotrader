import sqlite3
import json
import sys
import os

# Force utf-8 for stdout
sys.stdout.reconfigure(encoding='utf-8')

db_path = 'd:/ainigravity/work/kabu/antigravity/data/antigravity.db'

if not os.path.exists(db_path):
    print(f"Database not found at {db_path}")
    sys.exit(1)

try:
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    print("Checking automation configs...")
    cursor.execute('SELECT id, name, is_active, config_json FROM automation_configs')
    configs = cursor.fetchall()
    
    for row in configs:
        id, name, is_active, config_json_str = row
        try:
            config = json.loads(config_json_str)
            start_time = config.get("start_time", "Not Set")
            print(f"ID: {id}, Name: {name}, Active: {is_active}, Start Time: {start_time}")
        except Exception as e:
            print(f"Error parsing config for ID {id}: {e}")
            
    conn.close()
except Exception as e:
    print(f"Error: {e}")
