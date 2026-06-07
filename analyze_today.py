# -*- coding: utf-8 -*-
"""Analyze today's trading results"""
import sqlite3
import json

conn = sqlite3.connect("data/antigravity.db")
conn.row_factory = sqlite3.Row
c = conn.cursor()

# List all tables
c.execute("SELECT name FROM sqlite_master WHERE type='table'")
print("=== TABLES ===")
for r in c.fetchall():
    print(f"  {r[0]}")

# Get automation configs
print("\n=== AUTOMATION CONFIGS ===")
try:
    c.execute("SELECT * FROM automation_configs")
    for r in c.fetchall():
        print(dict(r))
except Exception as e:
    try:
        c.execute("SELECT * FROM automation_config")
        for r in c.fetchall():
            print(dict(r))
    except Exception as e2:
        print(f"  Error: {e2}")

# Get today's trades (2026-02-25)
print("\n=== TODAY TRADES (2026-02-25) ===")
c.execute("""SELECT id, symbol, symbol_name, side, price, qty, strategy_name, 
             realized_pnl, status, order_id, timestamp 
             FROM trade_history 
             WHERE timestamp LIKE '2026-02-25%' 
             ORDER BY timestamp ASC""")
trades = c.fetchall()
print(f"Total trades today: {len(trades)}")
for r in trades:
    d = dict(r)
    print(f"  [{d['side']:4s}] {d['symbol_name']:20s} ({d['symbol']}) "
          f"price={d['price']:>8.0f} qty={d['qty']:>4d} "
          f"pnl={d['realized_pnl'] or 0:>8.0f} "
          f"strategy={d['strategy_name']} @ {d['timestamp']}")

# Summary by strategy
print("\n=== TODAY SUMMARY BY STRATEGY ===")
c.execute("""SELECT strategy_name, side, COUNT(*) as cnt, 
             SUM(price*qty) as total_amount, SUM(realized_pnl) as total_pnl
             FROM trade_history 
             WHERE timestamp LIKE '2026-02-25%'
             GROUP BY strategy_name, side
             ORDER BY strategy_name, side""")
for r in c.fetchall():
    d = dict(r)
    pnl = d['total_pnl'] or 0
    amt = d['total_amount'] or 0
    print(f"  {d['strategy_name']:20s} {d['side']:4s}: "
          f"{d['cnt']} trades, amount={amt:>12,.0f}, pnl={pnl:>8,.0f}")

# Overall summary
print("\n=== TODAY OVERALL ===")
c.execute("""SELECT COUNT(*) as cnt FROM trade_history WHERE timestamp LIKE '2026-02-25%' AND side='BUY'""")
buy_cnt = c.fetchone()['cnt']
c.execute("""SELECT COUNT(*) as cnt FROM trade_history WHERE timestamp LIKE '2026-02-25%' AND side='SELL'""")
sell_cnt = c.fetchone()['cnt']
c.execute("""SELECT COALESCE(SUM(realized_pnl),0) as pnl FROM trade_history WHERE timestamp LIKE '2026-02-25%' AND side='SELL'""")
total_pnl = c.fetchone()['pnl']
print(f"  Buy trades: {buy_cnt}")
print(f"  Sell trades: {sell_cnt}")
print(f"  Total realized PnL: {total_pnl:,.0f}")

# Per-symbol PnL (matching buy/sell pairs)
print("\n=== PER-SYMBOL ANALYSIS ===")
c.execute("""SELECT symbol, symbol_name, strategy_name, side, price, qty, realized_pnl, timestamp 
             FROM trade_history 
             WHERE timestamp LIKE '2026-02-25%' 
             ORDER BY symbol, timestamp""")
rows = c.fetchall()
symbols = {}
for r in rows:
    d = dict(r)
    sym = d['symbol']
    if sym not in symbols:
        symbols[sym] = {'name': d['symbol_name'], 'strategy': d['strategy_name'], 'buys': [], 'sells': []}
    if d['side'] == 'BUY':
        symbols[sym]['buys'].append(d)
    else:
        symbols[sym]['sells'].append(d)

for sym, data in symbols.items():
    print(f"\n  {data['name']} ({sym}) - Strategy: {data['strategy']}")
    for b in data['buys']:
        print(f"    BUY  price={b['price']:>8.0f} qty={b['qty']:>4d} total={b['price']*b['qty']:>10,.0f} @ {b['timestamp']}")
    for s in data['sells']:
        print(f"    SELL price={s['price']:>8.0f} qty={s['qty']:>4d} total={s['price']*s['qty']:>10,.0f} pnl={s['realized_pnl'] or 0:>8,.0f} @ {s['timestamp']}")
    if data['buys'] and data['sells']:
        avg_buy = sum(b['price'] for b in data['buys']) / len(data['buys'])
        avg_sell = sum(s['price'] for s in data['sells']) / len(data['sells'])
        pnl_pct = ((avg_sell - avg_buy) / avg_buy) * 100 if avg_buy > 0 else 0
        print(f"    => Avg Buy: {avg_buy:,.0f}, Avg Sell: {avg_sell:,.0f}, Return: {pnl_pct:+.2f}%")
    elif data['buys'] and not data['sells']:
        total_invested = sum(b['price']*b['qty'] for b in data['buys'])
        print(f"    => OPEN POSITION (no sell), invested: {total_invested:>10,.0f}")

# Recent historical comparison
print("\n=== RECENT DAYS COMPARISON ===")
c.execute("""SELECT DATE(timestamp) as trade_date, 
             COUNT(*) as total_trades,
             SUM(CASE WHEN side='BUY' THEN 1 ELSE 0 END) as buys,
             SUM(CASE WHEN side='SELL' THEN 1 ELSE 0 END) as sells,
             COALESCE(SUM(CASE WHEN side='SELL' THEN realized_pnl ELSE 0 END),0) as daily_pnl
             FROM trade_history 
             GROUP BY DATE(timestamp)
             ORDER BY trade_date DESC
             LIMIT 10""")
for r in c.fetchall():
    d = dict(r)
    print(f"  {d['trade_date']}: {d['total_trades']} trades (B:{d['buys']}/S:{d['sells']}) PnL={d['daily_pnl']:>8,.0f}")

conn.close()
