import sys
import os
import asyncio
from pathlib import Path

# Add project root to path
sys.path.insert(0, r"d:\ainigravity\work\kabu\antigravity")

from main import init_services, app_state
from backend.database import Database
from backend.trading_service import TradingService
from backend.kabu_client import MockKabuClient

async def test():
    # 1. Modify DB settings manually to test values
    db = Database()
    db.set_setting("take_profit_pct", "2.5")
    db.set_setting("loss_cut_pct", "4.5")
    db.set_setting("trailing_stop_pct", "3.5")
    print("Set DB settings: TP 2.5%, LC 4.5%, TS 3.5%")

    # 2. Call init_services to see if it loads into app_state
    init_services()
    print("App State TP:", app_state.get("take_profit_pct"))
    print("App State LC:", app_state.get("loss_cut_pct"))
    print("App State TS:", app_state.get("trailing_stop_pct"))

    # 3. Test the TradingService execution
    trading_service = TradingService(app_state)
    
    # Fake a position that is +3% in profit. TP is 2.5%, so it SHOULD sell.
    entry_price = 1000
    current_price = 1030  # +3%
    
    app_state["positions"] = [
        {"symbol": "1234", "qty": 100, "avg_price": entry_price}
    ]
    
    client = MockKabuClient()
    # Mock get_board to return current_price
    class MockBoard:
        current_price = 1030
        symbol_name = "Mock Stock"
        
    async def mock_get_board(symbol):
        return MockBoard()
        
    client.get_board = mock_get_board
    
    # We override _execute_order to see what happens
    executed = []
    async def mock_execute_order(*args, **kwargs):
        executed.append(args)
        
    trading_service._execute_order = mock_execute_order

    print("Running _manage_positions with 1000 -> 1030 (+3%)")
    await trading_service._manage_positions(client)
    
    if executed:
        for order in executed:
            # order is (client, order_params, "SELL", triggered_strategy.name, ...)
            params = order[1]
            strat = order[3]
            print(f"EXECUTED SELL via {strat} | Reason: {params.get('reason')}")
    else:
        print("NO ORDERS EXECUTED.")
        
    # Reset DB settings back to default
    db.set_setting("take_profit_pct", "1.0")
    db.set_setting("loss_cut_pct", "3.0")
    db.set_setting("trailing_stop_pct", "3.0")
    print("Reset DB to default.")

if __name__ == "__main__":
    asyncio.run(test())
