
import sqlite3
import sys

# Force UTF-8 for output
sys.stdout.reconfigure(encoding='utf-8')

try:
    conn = sqlite3.connect('d:/ainigravity/work/kabu/antigravity/data/antigravity.db')
    cursor = conn.cursor()
    
    print("Checking active configs...")
    cursor.execute('SELECT id, name, is_active, created_at FROM automation_configs')
    configs = cursor.fetchall()
    
    if not configs:
        print("No automation configs found.")
    
    for c in configs:
        print(f"ID: {c[0]}, Name: {c[1]}, Active: {c[2]}, Created: {c[3]}")
        
    conn.close()
except Exception as e:
    print(f"Error: {e}")
