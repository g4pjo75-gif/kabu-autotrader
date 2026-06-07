import asyncio
import sys
from datetime import datetime
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.websocket_service import IntradayBarAccumulator
from strategies.vwap_strategy import VWAPPullbackStrategy

def test_vwap_calculation():
    print("--- Testing VWAP Calculation ---")
    accumulator = IntradayBarAccumulator(bar_interval_minutes=5)
    symbol = "TEST.T"
    
    # Simulate a morning session with 5 updates
    updates = [
        # (price, total_volume)
        (1000, 100),   # vol delta: 100
        (1010, 250),   # vol delta: 150
        (1020, 500),   # vol delta: 250
        (1015, 600),   # vol delta: 100
        (1005, 800),   # vol delta: 200
    ]
    
    for price, total_volume in updates:
        accumulator.update(symbol, price, total_volume)
        state = accumulator.get_vwap_state(symbol)
        print(f"Price: {price}, Total Vol: {total_volume} => VWAP: {state.vwap:.2f}, Cumulative Vol: {state.cumulative_volume}")
        
    final_state = accumulator.get_vwap_state(symbol)
    
    # Expected VWAP calculation:
    # 1000*100 = 100000
    # 1010*150 = 151500
    # 1020*250 = 255000
    # 1015*100 = 101500
    # 1005*200 = 201000
    # Total PV = 809000
    # Total Vol = 800
    # Expected VWAP = 1011.25
    
    expected_vwap = 1011.25
    assert abs(final_state.vwap - expected_vwap) < 0.01, f"Expected {expected_vwap}, got {final_state.vwap}"
    print(f"VWAP calculation correct: {final_state.vwap:.2f}")

def test_vwap_pullback_strategy():
    print("\n--- Testing VWAPPullbackStrategy ---")
    strategy = VWAPPullbackStrategy()
    
    # 1. 상승 추세 중, VWAP 위에서 눌림목, 반등 조건 만족
    symbol = "7203.T"
    open_price = 1000
    current_price = 1015
    vwap = 1011.25
    day_high = 1020
    recent_low = 1010
    recent_prices = [1020, 1015, 1015, 1010, 1015] # 하락 후 반등 패턴
    
    result = strategy.evaluate_realtime(
        symbol=symbol,
        current_price=current_price,
        open_price=open_price,
        day_high=day_high,
        vwap=vwap,
        recent_low=recent_low,
        recent_prices=recent_prices
    )
    
    print(f"Signal Result 1 (Ideal Entry): {result.signal}, Score: {result.score}, Details: {result.details}")
    assert result.signal == True, "Should trigger a buy signal"
    
    # 2. VWAP 밴드 이탈 (너무 높음)
    current_price_high = 1030
    result_high = strategy.evaluate_realtime(
        symbol=symbol,
        current_price=current_price_high,
        open_price=open_price,
        day_high=day_high,
        vwap=vwap,
        recent_low=recent_low,
        recent_prices=recent_prices
    )
    print(f"Signal Result 2 (Too High): {result_high.signal}")
    assert result_high.signal == False, "Should not trigger (too far from VWAP)"
    
    # 3. 반등 없음 (계속 하락 중)
    current_price_falling = 1011
    recent_prices_falling = [1020, 1018, 1015, 1013, 1011]
    result_falling = strategy.evaluate_realtime(
        symbol=symbol,
        current_price=current_price_falling,
        open_price=open_price,
        day_high=day_high,
        vwap=vwap,
        recent_low=1011, # 현재가가 최저점
        recent_prices=recent_prices_falling
    )
    print(f"Signal Result 3 (Falling): {result_falling.signal}")
    assert result_falling.signal == False, "Should not trigger (no bounce)"
    
    print("VWAP Pullback Strategy logic correct")

if __name__ == "__main__":
    test_vwap_calculation()
    test_vwap_pullback_strategy()
