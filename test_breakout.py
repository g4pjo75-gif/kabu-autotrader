# -*- coding: utf-8 -*-
"""
HighBreakoutStrategy Real-time Logic Test Script
"""
import sys
import os
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.dirname(__file__))

from strategies.breakout_strategy import HighBreakoutStrategy

def test_high_breakout():
    print("=== Start HighBreakoutStrategy Unit Test ===")
    
    strategy = HighBreakoutStrategy()
    
    # 1. Parameter Check
    print("\n[1] Strategy Parameters:")
    for param in strategy.get_parameters():
        print(f"  - {param.name}: {param.display_name} (default={param.default})")
    
    symbol = "7203"
    
    # 2. Volume Spurt Average tracking check
    print("\n[2] Real-time Volume delta tracking & breakout evaluate test:")
    
    # T1: 10,000 (Initial)
    res = strategy.evaluate_realtime(symbol, 2000, 2000, 2000, 10000)
    print(f"  T1 (Vol=10,000): signal={res.signal}, delta={res.details.get('vol_delta')}, avg_delta={res.details.get('avg_delta')}")
    
    # T2: 10,050 (Delta = 50)
    res = strategy.evaluate_realtime(symbol, 2000, 2000, 2000, 10050)
    print(f"  T2 (Vol=10,050): signal={res.signal}, delta={res.details.get('vol_delta')}, avg_delta={res.details.get('avg_delta')}")
    
    # T3: 10,100 (Delta = 50)
    res = strategy.evaluate_realtime(symbol, 2000, 2000, 2000, 10100)
    print(f"  T3 (Vol=10,100): signal={res.signal}, delta={res.details.get('vol_delta')}, avg_delta={res.details.get('avg_delta')}")
    
    # T4: 10,150 (Delta = 50)
    res = strategy.evaluate_realtime(symbol, 2000, 2000, 2000, 10150)
    print(f"  T4 (Vol=10,150): signal={res.signal}, delta={res.details.get('vol_delta')}, avg_delta={res.details.get('avg_delta')}")
    
    # T5: 10,200 (Delta = 50)
    res = strategy.evaluate_realtime(symbol, 2000, 2000, 2000, 10200)
    print(f"  T5 (No Breakout, Normal Vol): signal={res.signal}, breakout={res.details.get('breakout_ok')}, volume_spurt={res.details.get('volume_spurt')}")
    
    # T6: 고가 돌파는 했으나 거래량 급증이 없을 때 (Delta = 50, spurt_ratio 1.5 미충족)
    res = strategy.evaluate_realtime(symbol, 2010, 2000, 2000, 10250)
    print(f"  T6 (Breakout, Normal Vol): signal={res.signal}, breakout={res.details.get('breakout_ok')}, volume_spurt={res.details.get('volume_spurt')}")
    
    # T7: 고가 돌파 및 거래량 급증 동반!
    # 현재가 2015 (고가 2000 대비 0.75% 돌파, 마진 0.1% 충족)
    # 누적 거래량 10,350 (Delta = 100, 평균 50 대비 2.0배 -> spurt_ratio 1.5 충족)
    res = strategy.evaluate_realtime(symbol, 2015, 2000, 2000, 10350)
    print(f"  T7 (Breakout + Vol Spurt): signal={res.signal}, score={res.score}, details={res.details}")
    
    # T8: 상승 제한 한도 초과 시 (시가 1500, 현재가 2000, 상승률 33.3% -> 한도 25% 초과)
    res = strategy.evaluate_realtime(symbol, 2000, 1500, 1990, 10500)
    print(f"  T8 (Limit Exceeded): signal={res.signal}, rise_pct={res.details.get('rise_pct')}, not_too_high={res.details.get('not_too_high')}")
    
    # T9: 하락 트렌드 시장 지수 필터링 (market_trend = "Down")
    res = strategy.evaluate_realtime(symbol, 2015, 2000, 2000, 10650, market_trend="Down")
    print(f"  T9 (Down Market): signal={res.signal}, market_ok={res.details.get('market_ok')}")

if __name__ == "__main__":
    test_high_breakout()
