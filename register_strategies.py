# -*- coding: utf-8 -*-
"""
Register 18 Automation Strategies
9 extraction strategies × 2 universes (nikkei225, nikkei400)
"""
import sys
import os
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.dirname(__file__))

from backend.database import Database, AutomationConfig
import json

db = Database()

# 1. Delete existing configs
print("=== Deleting existing configs ===")
existing = db.get_automation_configs()
for c in existing:
    print(f"  Deleting ID={c.id} Name={c.name}")
    db.delete_automation_config(c.id)
print(f"  Deleted {len(existing)} configs")

# 2. Define 9 extraction strategies
extraction_strategies = [
    "SMAGoldenDeadCross",
    "StockSMAEMACross",
    "StockMACDShift",
    "StockRSIStochastic",
    "TurtleBreakoutFilter",
    "TurtleLiquidityFilter",
    "TurtleVolatilityFilter",
    "BollingerBands",
    "CandlePatterns",
    "TripleConfirmScorer",
    "MACDPullback",
    "HighBreakoutStrategy",
]

# Display names for readable config names
display_names = {
    "SMAGoldenDeadCross": "SMA골든크로스",
    "StockSMAEMACross": "SMA/EMA크로스",
    "StockMACDShift": "MACD모멘텀",
    "StockRSIStochastic": "RSI스토캐스틱",
    "TurtleBreakoutFilter": "터틀브레이크아웃",
    "TurtleLiquidityFilter": "터틀유동성",
    "TurtleVolatilityFilter": "터틀변동성",
    "BollingerBands": "볼린저밴드",
    "CandlePatterns": "캔들패턴",
    "TripleConfirmScorer": "트리플컨펌스코어",
    "MACDPullback": "MACD눌림목",
    "HighBreakoutStrategy": "고가돌파추격",
}

universes = [
    ("nikkei225", "N225"),
    ("nikkei400", "JPX400"),
]

# Common config template (same as existing settings)
base_config = {
    "max_stocks": 5,
    "buy_strategy": "StockSplitFunds",
    "sell_strategy": "BasicLossCutManager",
    "start_time": "09:05",
    "end_time": "15:00",
    "us_market_filter": False,
    "us_market_threshold": 1.0,
}

# 3. Register 18 configs
print("\n=== Registering 18 new configs ===")
count = 0
for strategy in extraction_strategies:
    for universe_code, universe_label in universes:
        config_data = {
            **base_config,
            "target_universe": universe_code,
            "extraction_strategy": strategy,
        }
        
        name = f"{display_names[strategy]}_{universe_label}"
        
        config = AutomationConfig(
            id=None,
            name=name,
            config_json=config_data,
            is_active=True,
        )
        
        saved_id = db.save_automation_config(config)
        count += 1
        print(f"  [{count:2d}] ID={saved_id} {name} ({strategy} / {universe_code})")

print(f"\n=== Done! Registered {count} automation configs ===")

# 4. Verify
print("\n=== Verification ===")
all_configs = db.get_automation_configs()
print(f"Total configs in DB: {len(all_configs)}")
for c in all_configs:
    cfg = c.config_json
    print(f"  ID={c.id:3d} Active={c.is_active} {c.name:30s} -> {cfg['extraction_strategy']} / {cfg['target_universe']}")
