import sqlite3

conn = sqlite3.connect("data/antigravity.db")
conn.row_factory = sqlite3.Row
c = conn.cursor()

c.execute("SELECT COUNT(*) as cnt FROM trade_history")
print(f"Total records: {c.fetchone()['cnt']}")

c.execute("SELECT COUNT(*) as cnt FROM trade_history WHERE side='SELL' AND price=0 AND qty=0")
print(f"Bad records remaining: {c.fetchone()['cnt']}")

c.execute("SELECT side, COUNT(*) as cnt, SUM(realized_pnl) as pnl FROM trade_history GROUP BY side")
for r in c.fetchall():
    pnl = r["pnl"] or 0
    print(f"  {r['side']}: {r['cnt']} trades, PnL={pnl:,.0f}")

print()
c.execute("SELECT id, symbol, symbol_name, side, price, qty, strategy_name, realized_pnl, timestamp FROM trade_history ORDER BY timestamp DESC LIMIT 10")
for r in c.fetchall():
    print(f"  [{r['side']}] {r['symbol_name']} ({r['symbol']}) price={r['price']} qty={r['qty']} pnl={r['realized_pnl']} @ {r['timestamp']}")

conn.close()
