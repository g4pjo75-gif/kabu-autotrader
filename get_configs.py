# -*- coding: utf-8 -*-
import sqlite3, json, sys
sys.stdout.reconfigure(encoding='utf-8')

conn = sqlite3.connect("data/antigravity.db")
conn.row_factory = sqlite3.Row
c = conn.cursor()

c.execute("SELECT * FROM automation_configs")
for r in c.fetchall():
    d = dict(r)
    config = json.loads(d.get('config_json', '{}'))
    print(f"ID: {d.get('id')}")
    print(f"  Name: {d.get('name')}")
    print(f"  Active: {d.get('is_active')}")
    print(f"  Config: {json.dumps(config, indent=4, ensure_ascii=False)}")
    print()

conn.close()
