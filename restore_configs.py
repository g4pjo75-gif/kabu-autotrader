# -*- coding: utf-8 -*-
"""
Restore original configurations.
Deletes all newly registered 24 strategies and restores the single '단타 TICK 상승률' config.
"""
import sys
import os
import json

sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.dirname(__file__))

from backend.database import Database, AutomationConfig

db = Database()

# 1. Get and delete all current configs
print("=== Deleting current configurations ===")
existing = db.get_automation_configs()
for c in existing:
    print(f"  Deleting ID={c.id} Name={c.name}")
    db.delete_automation_config(c.id)
print(f"  Deleted {len(existing)} configs")

# 2. Re-create the single original '단타 TICK 상승률' config
print("\n=== Restoring '단타 TICK 상승률' config ===")

original_config_json = {
    "max_stocks": 3,
    "max_concurrent_positions": 3,
    "max_daily_trades": 5,
    "buy_strategy": "StockSplitFunds",
    "sell_strategy": "BasicLossCutManager",
    "start_time": "09:05",
    "end_time": "15:00",
    "us_market_filter": False,
    "us_market_threshold": 1.0,
    "target_universe": "ranking_leaders",
    "extraction_strategy": "VWAPPullback",
    "gap_filter_min": 1.0,
    "gap_filter_max": 5.0,
    "ranking_type": "5",
    "secondary_ranking_type": "4"
}

restored_config = AutomationConfig(
    id=None,
    name="단타 TICK 상승률",
    config_json=original_config_json,
    is_active=True
)

saved_id = db.save_automation_config(restored_config)
print(f"Successfully restored '단타 TICK 상승률' with ID={saved_id}")

# 3. Verification
print("\n=== Current DB Configs ===")
configs = db.get_automation_configs()
for c in configs:
    print(f"ID={c.id} Active={c.is_active} Name='{c.name}'")
    print(f"  Config: {json.dumps(c.config_json, ensure_ascii=False)}")
