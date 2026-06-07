# -*- coding: utf-8 -*-
"""
Extraction Strategies - Stock Filtering

Based on Program Garden's "Stock Condition" logic.
Ref: https://github.com/programgarden/programgarden_community/tree/main/programgarden_community/overseas_stock/strategy_conditions
"""
from dataclasses import dataclass
from typing import Any, Dict, List, Literal, Optional, Tuple
from statistics import mean, stdev

import pandas as pd
import numpy as np

from .base import (
    BaseExtractionStrategy,
    SignalResult,
    StrategyParameter,
)


class SMAGoldenDeadCross(BaseExtractionStrategy):
    """
    SMA Golden/Dead Cross Strategy
    Ref: sma_golden_dead
    """
    name = "SMAGoldenDeadCross"
    display_name = "SMA 골든/데드 크로스"
    description = "단기 SMA가 장기 SMA를 돌파 (최근 2봉 이내 발생 및 정렬 유지)"

    @classmethod
    def get_parameters(cls) -> List[StrategyParameter]:
        return [
            StrategyParameter("short_period", "단기 SMA", "int", 20, 5, 50),
            StrategyParameter("long_period", "장기 SMA", "int", 50, 10, 200),
            StrategyParameter("signal_type", "신호 종류", "select", "golden", options=["golden", "dead", "both"]),
        ]

    async def evaluate(self, symbol: str, data: pd.DataFrame) -> SignalResult:
        short_p = self.get_param("short_period")
        long_p = self.get_param("long_period")
        signal_type = self.get_param("signal_type")

        if len(data) < long_p:
            return SignalResult(symbol=symbol, signal=False, score=0.0)

        data = data.copy()
        data["sma_short"] = data["close"].rolling(window=short_p).mean()
        data["sma_long"] = data["close"].rolling(window=long_p).mean()
        
        # Logic from Github:
        # 1. Observed a dead->golden (golden > dead_price)
        # 2. Golden occurred within recent 2 points
        # 3. Latest alignment is golden
        
        # We need to find the last crossings
        # Use numpy for faster execution on arrays
        short_arr = data["sma_short"].values
        long_arr = data["sma_long"].values
        close_arr = data["close"].values
        
        # Identify cross points
        # 1 = Short > Long, -1 = Short < Long
        diff = short_arr - long_arr
        
        # Logic implementation needs to scan backwards or track state
        # Simplified robust version:
        
        curr_diff = diff[-1]
        prev_diff = diff[-2]
        
        signal = False
        score = 0.0
        details = {
            "sma_short": short_arr[-1],
            "sma_long": long_arr[-1],
            "cross_type": "none"
        }
        
        # Golden Cross Logic
        if signal_type in ["golden", "both"]:
            # Condition 3: Latest alignment is golden
            if curr_diff > 0:
                # Check for recent cross (within last 2 bars)
                # i.e. diff[-2] < 0 or diff[-3] < 0 (and crossed recently)
                cross_idx = -1
                for i in range(1, 4): # Check last 3 bars for safety
                    if idx := len(diff) - i:
                        if idx < 0: break
                        if diff[idx-1] <= 0 and diff[idx] > 0:
                            cross_idx = idx
                            break
                
                if cross_idx != -1 and (len(diff) - cross_idx) <= 2:
                    # Condition 1: Check previous dead cross price constraint?
                    # Github logic: golden_price > last_dead_price
                    # This requires finding the LAST dead cross before this golden cross.
                    
                    # Find last dead cross
                    last_dead_price = None
                    for i in range(cross_idx, -1, -1):
                        if i > 0 and diff[i-1] >= 0 and diff[i] < 0:
                            last_dead_price = close_arr[i]
                            break
                    
                    golden_price = close_arr[cross_idx]
                    
                    if last_dead_price is not None:
                        if golden_price > last_dead_price:
                            signal = True
                            score = 80.0
                            details["cross_type"] = "golden"
                            details["golden_price"] = golden_price
                            details["last_dead_price"] = last_dead_price
                    else:
                        # If no dead cross found in history (rare), maybe just accept?
                        # Or stricter: fail. Let's pass if strong trend.
                        signal = True
                        score = 60.0
                        details["cross_type"] = "golden"

        # Dead Cross Logic
        if not signal and signal_type in ["dead", "both"]:
            if curr_diff < 0: # Latest dead
                cross_idx = -1
                for i in range(1, 4):
                    if idx := len(diff) - i:
                        if idx < 0: break
                        if diff[idx-1] >= 0 and diff[idx] < 0:
                            cross_idx = idx
                            break
                
                if cross_idx != -1 and (len(diff) - cross_idx) <= 2:
                     # Find last golden cross
                    last_golden_price = None
                    for i in range(cross_idx, -1, -1):
                        if i > 0 and diff[i-1] <= 0 and diff[i] > 0:
                            last_golden_price = close_arr[i]
                            break
                    
                    dead_price = close_arr[cross_idx]
                    
                    if last_golden_price is not None:
                        if dead_price < last_golden_price:
                            signal = True
                            score = 80.0
                            details["cross_type"] = "dead"

        return SignalResult(symbol, signal, score, details)


class StockSMAEMACross(BaseExtractionStrategy):
    """
    SMA/EMA Trend Cross
    Ref: sma_ema_trend_cross
    """
    name = "StockSMAEMACross"
    display_name = "SMA/EMA 추세 크로스"
    description = "EMA(신호선)와 SMA(추세선)의 교차 및 정배열/역배열 감지"

    @classmethod
    def get_parameters(cls) -> List[StrategyParameter]:
        return [
            StrategyParameter("period_sma", "Slow SMA", "int", 55, 10, 200),
            StrategyParameter("period_ema", "Fast EMA", "int", 21, 5, 100),
            StrategyParameter("lookback", "신호 감지 기간", "int", 3, 1, 10),
            StrategyParameter("focus_direction", "방향", "select", "both", options=["bullish", "bearish", "both"]),
        ]

    async def evaluate(self, symbol: str, data: pd.DataFrame) -> SignalResult:
        sma_p = self.get_param("period_sma")
        ema_p = self.get_param("period_ema")
        lookback = self.get_param("lookback")
        direction = self.get_param("focus_direction")

        if len(data) < max(sma_p, ema_p) + 5:
            return SignalResult(symbol, False, 0.0)

        data = data.copy()
        data["sma"] = data["close"].rolling(window=sma_p).mean()
        data["ema"] = data["close"].ewm(span=ema_p, adjust=False).mean()
        
        sma = data["sma"].values
        ema = data["ema"].values
        
        # Determine signals
        # bullish_cross: prev_ema <= prev_sma and ema > sma
        # trend_up: ema > sma
        # trend_down: ema < sma
        
        found_signal = False
        last_signal_type = "neutral"
        
        # Check lookback window
        for i in range(len(data) - lookback, len(data)):
            if i < 1: continue
            
            p_ema, p_sma = ema[i-1], sma[i-1]
            c_ema, c_sma = ema[i], sma[i]
            
            sig = "neutral"
            if p_ema <= p_sma and c_ema > c_sma:
                sig = "bullish_cross"
            elif p_ema >= p_sma and c_ema < c_sma:
                sig = "bearish_cross"
            elif c_ema > c_sma:
                sig = "trend_up"
            elif c_ema < c_sma:
                sig = "trend_down"
            
            last_signal_type = sig
            
            # Check match
            is_match = False
            if direction == "both":
                if sig != "neutral": is_match = True
            elif direction == "bullish":
                if sig in ["bullish_cross", "trend_up"]: is_match = True
            elif direction == "bearish":
                if sig in ["bearish_cross", "trend_down"]: is_match = True
                
            if is_match:
                found_signal = True

        score = 80.0 if found_signal else 0.0
        
        return SignalResult(
            symbol, 
            found_signal, 
            score, 
            {"last_signal": last_signal_type, "ema": ema[-1], "sma": sma[-1]}
        )


class StockMACDShift(BaseExtractionStrategy):
    """
    MACD Momentum Shift
    Ref: macd_momentum_shift
    """
    name = "StockMACDShift"
    display_name = "MACD 모멘텀 전환"
    description = "MACD선과 시그널선의 교차(크로스오버) 감지"

    @classmethod
    def get_parameters(cls) -> List[StrategyParameter]:
        return [
            StrategyParameter("fast_period", "Fast EMA", "int", 12, 2, 50), # Modified default to standard 12
            StrategyParameter("slow_period", "Slow EMA", "int", 26, 5, 100), # Modified default to standard 26
            StrategyParameter("signal_period", "Signal", "int", 9, 2, 30),
            StrategyParameter("lookback", "감지 기간", "int", 4, 1, 10),
            StrategyParameter("focus_direction", "방향", "select", "both", options=["bullish", "bearish", "both"]),
        ]

    async def evaluate(self, symbol: str, data: pd.DataFrame) -> SignalResult:
        fast_p = self.get_param("fast_period")
        slow_p = self.get_param("slow_period")
        sig_p = self.get_param("signal_period")
        lookback = self.get_param("lookback")
        direction = self.get_param("focus_direction")

        if len(data) < slow_p + sig_p:
            return SignalResult(symbol, False, 0.0)

        data = data.copy()
        data["ema_fast"] = data["close"].ewm(span=fast_p, adjust=False).mean()
        data["ema_slow"] = data["close"].ewm(span=slow_p, adjust=False).mean()
        data["macd"] = data["ema_fast"] - data["ema_slow"]
        data["signal"] = data["macd"].ewm(span=sig_p, adjust=False).mean()
        
        macd = data["macd"].values
        signal_line = data["signal"].values
        
        found = False
        last_type = "none"
        
        # Check recent crossovers
        for i in range(len(data) - lookback, len(data)):
            if i < 1: continue
            
            p_m, p_s = macd[i-1], signal_line[i-1]
            c_m, c_s = macd[i], signal_line[i]
            
            cross = "none"
            if p_m <= p_s and c_m > c_s:
                cross = "bullish"
            elif p_m >= p_s and c_m < c_s:
                cross = "bearish"
            
            if cross != "none":
                last_type = cross
                if direction == "both":
                    found = True
                elif direction == "bullish" and cross == "bullish":
                    found = True
                elif direction == "bearish" and cross == "bearish":
                    found = True

        return SignalResult(
            symbol,
            found,
            80.0 if found else 0.0,
            {"last_crossover": last_type, "macd": macd[-1], "signal": signal_line[-1]}
        )


class StockRSIStochastic(BaseExtractionStrategy):
    """
    RSI & Stochastic Oscillator
    Ref: rsi_stochastic_oscillator
    """
    name = "StockRSIStochastic"
    display_name = "RSI & 스토캐스틱"
    description = "RSI와 스토캐스틱이 동시에 과매수/과매도에 진입"

    @classmethod
    def get_parameters(cls) -> List[StrategyParameter]:
        return [
            StrategyParameter("rsi_period", "RSI 기간", "int", 14, 2, 50),
            StrategyParameter("stoch_k", "Stoch %K", "int", 14, 2, 50),
            StrategyParameter("stoch_d", "Stoch %D", "int", 3, 1, 20),
            StrategyParameter("overbought", "과매수 기준", "float", 70.0, 50.0, 100.0),
            StrategyParameter("oversold", "과매도 기준", "float", 30.0, 0.0, 50.0),
            StrategyParameter("focus_signal", "감지 신호", "select", "both", options=["overbought", "oversold", "both"]),
        ]

    async def evaluate(self, symbol: str, data: pd.DataFrame) -> SignalResult:
        rsi_p = self.get_param("rsi_period")
        k_p = self.get_param("stoch_k")
        d_p = self.get_param("stoch_d")
        ob = self.get_param("overbought")
        os = self.get_param("oversold")
        focus = self.get_param("focus_signal")

        if len(data) < max(rsi_p, k_p) + d_p:
            return SignalResult(symbol, False, 0.0)

        # RSI (Wilder's Smoothing)
        delta = data["close"].diff()
        gain = delta.where(delta > 0, 0)
        loss = -delta.where(delta < 0, 0)
        
        # Wilder's Smoothing: alpha = 1/n
        avg_gain = gain.ewm(alpha=1/rsi_p, adjust=False).mean()
        avg_loss = loss.ewm(alpha=1/rsi_p, adjust=False).mean()
        
        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
        
        # Stochastic
        low_min = data["low"].rolling(window=k_p).min()
        high_max = data["high"].rolling(window=k_p).max()
        k_val = 100 * (data["close"] - low_min) / (high_max - low_min)
        d_val = k_val.rolling(window=d_p).mean()
        
        curr_rsi = rsi.iloc[-1]
        curr_d = d_val.iloc[-1]
        
        signal = False
        sig_type = "neutral"
        
        if pd.isna(curr_rsi) or pd.isna(curr_d):
            return SignalResult(symbol, False, 0.0)

        is_ob = (curr_rsi >= ob) and (curr_d >= ob)
        is_os = (curr_rsi <= os) and (curr_d <= os)
        
        if is_ob: sig_type = "overbought"
        if is_os: sig_type = "oversold"
        
        if focus == "both":
            if is_ob or is_os: signal = True
        elif focus == "overbought" and is_ob:
            signal = True
        elif focus == "oversold" and is_os:
            signal = True
            
        return SignalResult(
            symbol,
            signal,
            90.0 if signal else 0.0,
            {"rsi": curr_rsi, "stoch_d": curr_d, "signal": sig_type}
        )


class TurtleBreakoutFilter(BaseExtractionStrategy):
    """
    Turtle Breakout Filter
    Ref: turtle_breakout_filter
    """
    name = "TurtleBreakoutFilter"
    display_name = "터틀 브레이크아웃 & 필터"
    description = "신고가/신저가 돌파 + 유동성/변동성 필터 (종합)"

    @classmethod
    def get_parameters(cls) -> List[StrategyParameter]:
        return [
            StrategyParameter("entry_period", "진입 기간", "int", 20, 10, 100),
            StrategyParameter("strong_period", "강한 진입", "int", 55, 20, 200),
            StrategyParameter("min_turnover", "최소 거래대금", "int", 1000000, 0, 100000000),
            StrategyParameter("min_atr", "최소 ATR", "float", 0.5, 0.1, 10.0),
        ]

    async def evaluate(self, symbol: str, data: pd.DataFrame) -> SignalResult:
        entry_p = self.get_param("entry_period")
        strong_p = self.get_param("strong_period")
        min_to = self.get_param("min_turnover")
        min_atr = self.get_param("min_atr")

        if len(data) < strong_p + 1:
            return SignalResult(symbol, False, 0.0)

        # 1. Liquidity Check (Turnover)
        # Using 20-day avg roughly
        avg_turnover = (data["close"] * data["volume"]).rolling(window=20).mean().iloc[-1]
        if avg_turnover < min_to:
            return SignalResult(symbol, False, 0.0, {"fail": "Liquidity"})

        # 2. Volatility Check (ATR)
        high = data["high"]
        low = data["low"]
        close = data["close"]
        prev_close = close.shift(1)
        tr = pd.concat([
            high - low,
            (high - prev_close).abs(),
            (low - prev_close).abs()
        ], axis=1).max(axis=1)
        atr = tr.rolling(window=20).mean().iloc[-1]
        
        if atr < min_atr:
            return SignalResult(symbol, False, 0.0, {"fail": "Low Volatility", "atr": atr})

        # 3. Trend Check (Breakout)
        # 55-day High
        high_55 = high.iloc[-strong_p-1:-1].max()
        curr_high = high.iloc[-1]
        
        signal = False
        score = 0.0
        
        if curr_high > high_55:
            signal = True
            score = 100.0
        else:
             # Check 20-day High
            high_20 = high.iloc[-entry_p-1:-1].max()
            if curr_high > high_20:
                signal = True
                score = 80.0
        
        return SignalResult(
            symbol,
            signal,
            score,
            {"atr": atr, "avg_turnover": avg_turnover}
        )


class TurtleLiquidityFilter(BaseExtractionStrategy):
    """
    Turtle Liquidity Filter
    Ref: turtle_liquidity_filter
    """
    name = "TurtleLiquidityFilter"
    display_name = "터틀 유동성 필터"
    description = "거래대금과 거래량이 기준 이상인 종목 선별"

    @classmethod
    def get_parameters(cls) -> List[StrategyParameter]:
        return [
            StrategyParameter("lookback_days", "산정 일수", "int", 20, 5, 60),
            StrategyParameter("min_turnover", "최소 거래대금", "int", 1000000, 0, 100000000),
            StrategyParameter("min_volume", "최소 거래량", "int", 300000, 0, 10000000),
        ]

    async def evaluate(self, symbol: str, data: pd.DataFrame) -> SignalResult:
        lookback = self.get_param("lookback_days")
        min_to = self.get_param("min_turnover")
        min_vol = self.get_param("min_volume")

        if len(data) < lookback:
            return SignalResult(symbol, False, 0.0)

        recent = data.iloc[-lookback:]
        avg_vol = recent["volume"].mean()
        avg_to = (recent["close"] * recent["volume"]).mean()
        
        pass_vol = avg_vol >= min_vol
        pass_to = avg_to >= min_to
        
        signal = pass_vol and pass_to
        score = 100.0 if signal else 0.0
        
        return SignalResult(
            symbol, 
            signal, 
            score, 
            {"avg_volume": avg_vol, "avg_turnover": avg_to}
        )


class TurtleVolatilityFilter(BaseExtractionStrategy):
    """
    Turtle Volatility Filter
    Ref: turtle_volatility_filter
    """
    name = "TurtleVolatilityFilter"
    display_name = "터틀 변동성 필터"
    description = "ATR 진폭이 일정 수준 이상인 종목 선별"

    @classmethod
    def get_parameters(cls) -> List[StrategyParameter]:
        return [
            StrategyParameter("atr_period", "ATR 기간", "int", 20, 5, 50),
            StrategyParameter("min_atr", "최소 ATR", "float", 0.5, 0.01, 50.0),
        ]

    async def evaluate(self, symbol: str, data: pd.DataFrame) -> SignalResult:
        period = self.get_param("atr_period")
        min_ref = self.get_param("min_atr")

        if len(data) < period + 1:
            return SignalResult(symbol, False, 0.0)

        high = data["high"]
        low = data["low"]
        close = data["close"]
        prev_close = close.shift(1)
        
        tr = pd.concat([
            high - low,
            (high - prev_close).abs(),
            (low - prev_close).abs()
        ], axis=1).max(axis=1)
        
        atr = tr.rolling(window=period).mean().iloc[-1]
        
        signal = atr >= min_ref
        
        return SignalResult(
            symbol,
            signal,
            100.0 if signal else 0.0,
            {"atr": atr}
        )


class BollingerBands(BaseExtractionStrategy):
    """
    Bollinger Bands Strategy
    Ref: bollinger_bands
    """
    name = "BollingerBands"
    display_name = "볼린저 밴드"
    description = "밴드 터치(과열/침체) 및 스퀴즈/확장 감지"

    @classmethod
    def get_parameters(cls) -> List[StrategyParameter]:
        return [
            StrategyParameter("period", "기간", "int", 20, 5, 100),
            StrategyParameter("std_dev", "표준편차", "float", 2.0, 1.0, 4.0),
            StrategyParameter("squeeze_threshold", "스퀴즈 기준", "float", 0.05, 0.01, 0.2),
        ]

    async def evaluate(self, symbol: str, data: pd.DataFrame) -> SignalResult:
        period = self.get_param("period")
        std_dev = self.get_param("std_dev")
        sq_thresh = self.get_param("squeeze_threshold")

        if len(data) < period:
            return SignalResult(symbol, False, 0.0)

        data = data.copy()
        data["sma"] = data["close"].rolling(window=period).mean()
        data["std"] = data["close"].rolling(window=period).std()
        data["upper"] = data["sma"] + (std_dev * data["std"])
        data["lower"] = data["sma"] - (std_dev * data["std"])
        
        # Bandwidth
        data["bandwidth"] = (data["upper"] - data["lower"]) / data["sma"]
        
        curr = data.iloc[-1]
        close = curr["close"]
        upper = curr["upper"]
        lower = curr["lower"]
        bw = curr["bandwidth"]
        
        signal_type = "neutral"
        
        # Logic from Github:
        # upper_touch: close >= upper
        # lower_touch: close <= lower
        # squeeze: bandwidth <= threshold
        # expansion: bandwidth > prev_bandwidth * 1.5
        
        prev_bw = data["bandwidth"].iloc[-2] if len(data) > 1 else bw
        
        if close >= upper:
            signal_type = "upper_touch"
        elif close <= lower:
            signal_type = "lower_touch"
        elif bw <= sq_thresh:
            signal_type = "squeeze"
        elif bw > prev_bw * 1.5:
            signal_type = "expansion"

        signal = signal_type != "neutral"
        
        return SignalResult(
            symbol,
            signal,
            90.0 if signal else 0.0,
            {"signal": signal_type, "bandwidth": bw, "upper": upper, "lower": lower}
        )


class CandlePatterns(BaseExtractionStrategy):
    """
    Candle Patterns
    Ref: candle_patterns
    """
    name = "CandlePatterns"
    display_name = "캔들 패턴 인식"
    description = "도지, 해머, 장악형 등 주요 캔들 패턴 감지"

    @classmethod
    def get_parameters(cls) -> List[StrategyParameter]:
        return [
            StrategyParameter("pattern_type", "패턴 종류", "select", "all", options=["all", "bullish", "bearish"]),
        ]

    async def evaluate(self, symbol: str, data: pd.DataFrame) -> SignalResult:
        ptype = self.get_param("pattern_type")
        
        if len(data) < 5:
            return SignalResult(symbol, False, 0.0)
            
        # Helper helpers
        def is_bullish(row): return row["close"] > row["open"]
        def is_bearish(row): return row["close"] < row["open"]
        def body(row): return abs(row["close"] - row["open"])
        def upper_shadow(row): return row["high"] - max(row["open"], row["close"])
        def lower_shadow(row): return min(row["open"], row["close"]) - row["low"]
        
        curr = data.iloc[-1]
        prev = data.iloc[-2]
        
        patterns = []
        
        # 1. Doji
        if body(curr) < (curr["close"] * 0.001):
            patterns.append("DOJI")
            
        # 2. Hammer (Bullish Reversal)
        if lower_shadow(curr) > body(curr) * 2 and upper_shadow(curr) < body(curr) * 0.5 and is_bullish(curr):
            patterns.append("HAMMER")
            
        # 3. Shooting Star (Bearish Reversal)
        if upper_shadow(curr) > body(curr) * 2 and lower_shadow(curr) < body(curr) * 0.5 and is_bearish(curr):
            patterns.append("SHOOTING_STAR")
            
        # 4. Bullish Engulfing
        if is_bearish(prev) and is_bullish(curr) and \
           curr["open"] < prev["close"] and curr["close"] > prev["open"]:
               patterns.append("BULLISH_ENGULFING")
               
        # 5. Bearish Engulfing
        if is_bullish(prev) and is_bearish(curr) and \
           curr["open"] > prev["close"] and curr["close"] < prev["open"]:
               patterns.append("BEARISH_ENGULFING")
               
        # Filter by requested type
        bullish_set = {"HAMMER", "BULLISH_ENGULFING"}
        bearish_set = {"SHOOTING_STAR", "BEARISH_ENGULFING"}
        
        final_patterns = []
        if ptype == "all":
            final_patterns = patterns
        elif ptype == "bullish":
            final_patterns = [p for p in patterns if p in bullish_set]
        elif ptype == "bearish":
            final_patterns = [p for p in patterns if p in bearish_set]
            
        signal = len(final_patterns) > 0
        return SignalResult(
            symbol,
            signal,
            len(final_patterns) * 20.0,
            {"patterns": final_patterns}
        )

class MACDPullback(BaseExtractionStrategy):
    """
    MACD Pullback Strategy
    Ref: macd_pullback
    """
    name = "MACDPullback"
    display_name = "MACD 눌림목"
    description = "MACD 상승 추세(골든) 하에서 주가가 5일 이평선 부근으로 조정을 받을 때 매수"

    @classmethod
    def get_parameters(cls) -> List[StrategyParameter]:
        return [
            StrategyParameter("pullback_tolerance", "눌림목 이격도(%)", "float", 1.5, 0.1, 5.0),
        ]

    async def evaluate(self, symbol: str, data: pd.DataFrame) -> SignalResult:
        if len(data) < 26:
            return SignalResult(symbol, False, 0.0)

        df = data.copy()
        # Calculate moving average and MACD
        df["sma5"] = df["close"].rolling(window=5).mean()
        df["ema12"] = df["close"].ewm(span=12, adjust=False).mean()
        df["ema26"] = df["close"].ewm(span=26, adjust=False).mean()
        df["macd"] = df["ema12"] - df["ema26"]
        df["signal"] = df["macd"].ewm(span=9, adjust=False).mean()

        last = df.iloc[-1]
        
        if pd.isna(last["macd"]) or pd.isna(last["sma5"]):
            return SignalResult(symbol, False, 0.0)

        # 1. 추세 확인: MACD > Signal (상승 모멘텀 유지)
        trend_ok = last["macd"] > last["signal"]
        
        # 2. 눌림목 확인: 종가가 5일 이평선 근처인지 확인
        tolerance = self.get_param("pullback_tolerance") / 100.0
        dist_pct = abs(last["close"] - last["sma5"]) / last["sma5"]
        pullback_ok = dist_pct <= tolerance

        signal = trend_ok and pullback_ok
        
        score = 0.0
        if signal:
            # 이격도가 0에 가까울 수록 높은 점수 부여
            score = 100.0 - (dist_pct / tolerance * 20.0) 

        return SignalResult(
            symbol,
            signal,
            score,
            {"macd_trend": "Bullish", "dist_to_sma5": f"{dist_pct*100:.2f}%"}
        )


class TripleConfirmScorer(BaseExtractionStrategy):
    """
    Triple Confirm Scorer Strategy
    Ref: triple_confirm_scorer
    """
    name = "TripleConfirmScorer"
    display_name = "트리플 컨펌 스코어"
    description = "MACD, RSI, 거래량 지표를 10점 만점으로 종합 분석"

    @classmethod
    def get_parameters(cls) -> List[StrategyParameter]:
        return [
            StrategyParameter("min_score", "매수 최소 점수", "float", 6.0, 1.0, 10.0),
        ]

    async def evaluate(self, symbol: str, data: pd.DataFrame) -> SignalResult:
        if len(data) < 30: # Need at least 26+9 bars for MACD, 20 for Vol MA
            return SignalResult(symbol, False, 0.0)

        df = data.copy()
        
        # 1. MACD (12, 26, 9)
        df["ema_fast"] = df["close"].ewm(span=12, adjust=False).mean()
        df["ema_slow"] = df["close"].ewm(span=26, adjust=False).mean()
        df["macd"] = df["ema_fast"] - df["ema_slow"]
        df["signal"] = df["macd"].ewm(span=9, adjust=False).mean()
        df["macd_hist"] = df["macd"] - df["signal"]

        # 2. RSI (14) - Using Wilder's Smoothing to match common tools
        delta = df["close"].diff()
        gain = delta.where(delta > 0, 0)
        loss = -delta.where(delta < 0, 0)
        avg_gain = gain.ewm(alpha=1/14, adjust=False).mean()
        avg_loss = loss.ewm(alpha=1/14, adjust=False).mean()
        rs = avg_gain / avg_loss
        df["rsi"] = 100 - (100 / (1 + rs))

        # 3. Volume MA (20)
        df["vol_ma20"] = df["volume"].rolling(window=20).mean()

        last = df.iloc[-1]
        prev = df.iloc[-2]
        
        score = 0.0
        
        # --- MACD Score (Max 3.0) ---
        if last["macd"] > last["signal"]: score += 2.0  # 골든크로스 상태
        if last["macd_hist"] > prev["macd_hist"]: score += 1.0 # 히스토그램 우상향
        
        # --- RSI Score (Max 3.0) ---
        if 50 <= last["rsi"] <= 70: score += 2.0                      # 불마켓 영역
        if prev["rsi"] < 50 and last["rsi"] >= 50: score += 1.0        # 50 상향 돌파(모멘텀)
        
        # --- Volume Score (Max 4.0) ---
        vol_ma20 = last["vol_ma20"] if last["vol_ma20"] > 0 else 1
        vol_ratio = last["volume"] / vol_ma20

        if vol_ratio >= 2.0: score += 4.0                              # 압도적 거래량
        elif vol_ratio >= 1.5: score += 2.5                            # 강한 거래량
        elif vol_ratio >= 1.0: score += 1.0                            # 평균 이상
        
        # --- Penalty for Overheating (Gap Up / Whipsaw Defense) ---
        # RSI가 지나치게 높거나 단기 과열(SMA5 이격도) 발생 시 감점
        if last["rsi"] >= 75:
            score -= 3.0
            
        sma5 = df["close"].rolling(window=5).mean().iloc[-1]
        if last["close"] > sma5 * 1.05: # SMA 5 대비 5% 이상 갭업/슈팅 시
            score -= 3.0

        min_score = self.get_param("min_score")
        signal = score >= min_score
        
        return SignalResult(
            symbol,
            signal,
            score * 10.0, # Map to 0~100 (since max score is 10)
            {
                "Score": score,
                "RSI": round(last["rsi"], 2),
                "Vol_Ratio": f"{round(vol_ratio * 100, 1)}%",
                "MACD_Sig": "Bullish" if last["macd_hist"] > 0 else "Neutral",
            }
        )

