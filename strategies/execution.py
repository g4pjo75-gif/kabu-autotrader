# -*- coding: utf-8 -*-
"""
Execution Strategies - Trading Logic

Based on Program Garden's "Order Condition" logic.
Decides position sizing, entry, and exit.
"""
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional

import pandas as pd

from .base import (
    BaseExecutionStrategy,
    SignalResult,
    StrategyParameter,
)


class StockSplitFunds(BaseExecutionStrategy):
    """
    Split Funds Strategy
    
    Allocate 1/N of total cash per stock.
    """
    name = "StockSplitFunds"
    display_name = "자금 분할"
    description = "총 자금을 종목 수로 나누어 투자"

    @classmethod
    def get_parameters(cls) -> List[StrategyParameter]:
        return [
            StrategyParameter(
                name="num_splits",
                display_name="분할 수",
                param_type="int",
                default=5,
                min_value=1,
                max_value=20,
                description="자금을 몇 종목으로 나눌지 설정",
            ),
            StrategyParameter(
                name="min_lot",
                display_name="최소 단위",
                param_type="int",
                default=100,
                min_value=1,
                max_value=1000,
                description="최소 구매 단위 (통상 100주)",
            ),
        ]

    async def evaluate(self, symbol: str, data: pd.DataFrame) -> SignalResult:
        """Evaluate - returns True as this is for order sizing"""
        return SignalResult(symbol=symbol, signal=True, score=100.0)

    async def calculate_order(
        self,
        symbol: str,
        current_price: float,
        available_cash: float,
        current_position: Optional[Dict[str, Any]] = None
    ) -> Optional[Dict[str, Any]]:
        """Calculate order with split fund allocation"""
        num_splits = self.get_param("num_splits")
        min_lot = self.get_param("min_lot")

        # Allocate 1/N of cash
        allocation = available_cash / num_splits
        
        # Calculate number of lots
        shares_possible = int(allocation / current_price)
        shares = (shares_possible // min_lot) * min_lot  # Round to lot size

        if shares < min_lot:
            return None  # Insufficient funds

        return {
            "symbol": symbol,
            "side": "2",  # Buy
            "qty": shares,
            "price": current_price,
            "order_type": "limit",
            "allocation": allocation,
        }


class BasicLossCutManager(BaseExecutionStrategy):
    """
    Basic Loss Cut Manager
    
    Stop Loss at -X% P&L.
    """
    name = "BasicLossCutManager"
    display_name = "기본 손절"
    description = "지정 % 손실 시 손절 주문"

    @classmethod
    def get_parameters(cls) -> List[StrategyParameter]:
        return [
            StrategyParameter(
                name="loss_cut_percent",
                display_name="손절 %",
                param_type="float",
                default=5.0,
                min_value=1.0,
                max_value=20.0,
                description="이 %의 손실에서 손절",
            ),
        ]

    async def evaluate(self, symbol: str, data: pd.DataFrame) -> SignalResult:
        """Evaluate loss cut condition"""
        return SignalResult(symbol=symbol, signal=True, score=100.0)

    async def calculate_order(
        self,
        symbol: str,
        current_price: float,
        available_cash: float,
        current_position: Optional[Dict[str, Any]] = None
    ) -> Optional[Dict[str, Any]]:
        """Calculate stop loss order"""
        if not current_position:
            return None

        loss_cut_pct = self.get_param("loss_cut_percent")
        
        entry_price = current_position.get("avg_price", current_price)
        qty = current_position.get("qty", 0)
        
        # Calculate P&L
        pnl_percent = (current_price - entry_price) / entry_price * 100

        if pnl_percent <= -loss_cut_pct:
            return {
                "symbol": symbol,
                "side": "1",  # Sell
                "qty": qty,
                "price": current_price,  # Use current_price instead of 0 for proper recording
                "order_type": "market",
                "reason": f"Loss cut at {pnl_percent:.2f}%",
            }

        # Loss cut not triggered - return None (no action needed)
        return None


class TakeProfitManager(BaseExecutionStrategy):
    """
    Take Profit Manager
    
    Sell when profit reaches +X%.
    """
    name = "TakeProfitManager"
    display_name = "익절 매도"
    description = "지정 % 이익 도달 시 익절 매도"

    @classmethod
    def get_parameters(cls) -> List[StrategyParameter]:
        return [
            StrategyParameter(
                name="take_profit_percent",
                display_name="익절 %",
                param_type="float",
                default=3.0,
                min_value=0.5,
                max_value=50.0,
                description="이 %의 이익에서 익절 매도",
            ),
        ]

    async def evaluate(self, symbol: str, data: pd.DataFrame) -> SignalResult:
        """Evaluate take profit condition"""
        return SignalResult(symbol=symbol, signal=True, score=100.0)

    async def calculate_order(
        self,
        symbol: str,
        current_price: float,
        available_cash: float,
        current_position: Optional[Dict[str, Any]] = None
    ) -> Optional[Dict[str, Any]]:
        """Calculate take profit order"""
        if not current_position:
            return None

        take_profit_pct = self.get_param("take_profit_percent")
        
        entry_price = current_position.get("avg_price", current_price)
        qty = current_position.get("qty", 0)
        
        if entry_price <= 0 or qty <= 0:
            return None
        
        # Calculate P&L percentage
        pnl_percent = (current_price - entry_price) / entry_price * 100

        if pnl_percent >= take_profit_pct:
            return {
                "symbol": symbol,
                "side": "1",  # Sell
                "qty": qty,
                "price": current_price,
                "order_type": "market",
                "reason": f"Take profit at +{pnl_percent:.2f}%",
            }

        # Take profit not triggered
        return None


class TrailingStopManager(BaseExecutionStrategy):
    """
    Trailing Stop Manager
    
    Track the highest price since entry.
    Sell when price drops -X% from the peak.
    """
    name = "TrailingStopManager"
    display_name = "트레일링 스탑"
    description = "고점 대비 지정 % 하락 시 매도"

    # Class-level dict to track high prices across cycles
    _high_prices: Dict[str, float] = {}

    @classmethod
    def get_parameters(cls) -> List[StrategyParameter]:
        return [
            StrategyParameter(
                name="trailing_stop_percent",
                display_name="트레일링 스탑 %",
                param_type="float",
                default=3.0,
                min_value=0.5,
                max_value=20.0,
                description="고점 대비 이 %만큼 하락하면 매도",
            ),
        ]

    async def evaluate(self, symbol: str, data: pd.DataFrame) -> SignalResult:
        """Evaluate trailing stop condition"""
        return SignalResult(symbol=symbol, signal=True, score=100.0)

    async def calculate_order(
        self,
        symbol: str,
        current_price: float,
        available_cash: float,
        current_position: Optional[Dict[str, Any]] = None
    ) -> Optional[Dict[str, Any]]:
        """Calculate trailing stop order"""
        if not current_position:
            return None

        trailing_pct = self.get_param("trailing_stop_percent")
        
        entry_price = current_position.get("avg_price", current_price)
        qty = current_position.get("qty", 0)
        
        if entry_price <= 0 or qty <= 0:
            return None

        # Update high price tracking
        prev_high = TrailingStopManager._high_prices.get(symbol, entry_price)
        high_price = max(prev_high, current_price)
        TrailingStopManager._high_prices[symbol] = high_price
        
        # Calculate drop from high
        drop_percent = (high_price - current_price) / high_price * 100

        if drop_percent >= trailing_pct and current_price > entry_price:
            # Only trigger if we're still in profit (avoid double-dipping with loss cut)
            # Clean up tracking
            TrailingStopManager._high_prices.pop(symbol, None)
            return {
                "symbol": symbol,
                "side": "1",  # Sell
                "qty": qty,
                "price": current_price,
                "order_type": "market",
                "reason": f"Trailing stop: -{drop_percent:.2f}% from high {high_price:.0f}",
            }

        # Trailing stop not triggered
        return None

    @classmethod
    def reset_tracking(cls, symbol: str = None):
        """Reset high price tracking (e.g., after position is sold)"""
        if symbol:
            cls._high_prices.pop(symbol, None)
        else:
            cls._high_prices.clear()


class SteppedTrailingManager(BaseExecutionStrategy):
    """
    Stepped Trailing Stop Manager
    
    Combines fixed take-profit with stepped trailing stop:
    
    Stage 0: profit < trailing_activate_pct
        → No trailing. Wait for fixed take-profit or other strategies.
    Stage 1: trailing_activate_pct <= profit < trailing_step2_pct
        → Trailing stop at trailing_step1_pct from high-water mark.
    Stage 2: profit >= trailing_step2_pct
        → Trailing stop tightens to trailing_step2_trail_pct from high-water mark.
    
    This replaces both TakeProfitManager and TrailingStopManager when active.
    """
    name = "SteppedTrailingManager"
    display_name = "단계별 트레일링 스탑"
    description = "수익 구간별로 트레일링 스탑 폭을 자동 전환"

    # Class-level dict to track high prices across cycles
    _high_prices: Dict[str, float] = {}

    @classmethod
    def get_parameters(cls) -> List[StrategyParameter]:
        return [
            StrategyParameter(
                name="trailing_activate_pct",
                display_name="트레일링 전환 기준 %",
                param_type="float",
                default=0.8,
                min_value=0.1,
                max_value=10.0,
                description="이 수익률 이상이면 트레일링 스탑으로 전환",
            ),
            StrategyParameter(
                name="trailing_step1_pct",
                display_name="1단계 트레일링 %",
                param_type="float",
                default=0.5,
                min_value=0.1,
                max_value=10.0,
                description="고점 대비 이 %만큼 하락하면 매도 (1단계)",
            ),
            StrategyParameter(
                name="trailing_step2_pct",
                display_name="2단계 전환 기준 %",
                param_type="float",
                default=2.0,
                min_value=0.5,
                max_value=20.0,
                description="이 수익률 이상이면 트레일링 폭을 더 좁힘",
            ),
            StrategyParameter(
                name="trailing_step2_trail_pct",
                display_name="2단계 트레일링 %",
                param_type="float",
                default=0.3,
                min_value=0.1,
                max_value=5.0,
                description="고점 대비 이 %만큼 하락하면 매도 (2단계, 더 타이트)",
            ),
        ]

    async def evaluate(self, symbol: str, data: pd.DataFrame) -> SignalResult:
        """Evaluate stepped trailing stop condition"""
        return SignalResult(symbol=symbol, signal=True, score=100.0)

    async def calculate_order(
        self,
        symbol: str,
        current_price: float,
        available_cash: float,
        current_position: Optional[Dict[str, Any]] = None
    ) -> Optional[Dict[str, Any]]:
        """Calculate stepped trailing stop order"""
        if not current_position:
            return None

        activate_pct = self.get_param("trailing_activate_pct")
        step1_trail = self.get_param("trailing_step1_pct")
        step2_threshold = self.get_param("trailing_step2_pct")
        step2_trail = self.get_param("trailing_step2_trail_pct")
        
        entry_price = current_position.get("avg_price", current_price)
        qty = current_position.get("qty", 0)
        
        if entry_price <= 0 or qty <= 0:
            return None

        # Calculate current profit percentage
        pnl_percent = (current_price - entry_price) / entry_price * 100

        # Stage 0: profit below activation threshold → do nothing (let other strategies handle)
        if pnl_percent < activate_pct:
            # Still track high price in case we cross the threshold next cycle
            prev_high = SteppedTrailingManager._high_prices.get(symbol, entry_price)
            SteppedTrailingManager._high_prices[symbol] = max(prev_high, current_price)
            return None

        # Update high price tracking (only meaningful once trailing is active)
        prev_high = SteppedTrailingManager._high_prices.get(symbol, entry_price)
        high_price = max(prev_high, current_price)
        SteppedTrailingManager._high_prices[symbol] = high_price

        # Determine which trailing percentage to use based on highest profit reached
        high_pnl_percent = (high_price - entry_price) / entry_price * 100
        
        if high_pnl_percent >= step2_threshold:
            # Stage 2: tighter trailing
            active_trail_pct = step2_trail
            stage = 2
        else:
            # Stage 1: normal trailing
            active_trail_pct = step1_trail
            stage = 1

        # Calculate drop from high
        drop_percent = (high_price - current_price) / high_price * 100

        if drop_percent >= active_trail_pct and current_price > entry_price:
            # Trailing stop triggered — sell
            pnl_at_sell = (current_price - entry_price) / entry_price * 100
            SteppedTrailingManager._high_prices.pop(symbol, None)
            return {
                "symbol": symbol,
                "side": "1",  # Sell
                "qty": qty,
                "price": current_price,
                "order_type": "market",
                "reason": (
                    f"Stepped trailing stop (Stage {stage}): "
                    f"high={high_price:.0f}, drop=-{drop_percent:.2f}% "
                    f"(limit: -{active_trail_pct:.1f}%), "
                    f"PnL=+{pnl_at_sell:.2f}%"
                ),
            }

        # Trailing stop not triggered — continue holding
        return None

    @classmethod
    def reset_tracking(cls, symbol: str = None):
        """Reset high price tracking (e.g., after position is sold)"""
        if symbol:
            cls._high_prices.pop(symbol, None)
        else:
            cls._high_prices.clear()


class TurtlePyramidNewOrder(BaseExecutionStrategy):
    """
    Turtle Pyramid Order
    
    Scale-in (add position) on favorable trend.
    """
    name = "TurtlePyramidNewOrder"
    display_name = "터틀 피라미딩"
    description = "추세 방향으로 추가 포지션 진입"

    @classmethod
    def get_parameters(cls) -> List[StrategyParameter]:
        return [
            StrategyParameter(
                name="add_threshold_atr",
                display_name="추가 임계값 (ATR 배수)",
                param_type="float",
                default=0.5,
                min_value=0.25,
                max_value=2.0,
                description="ATR의 몇 배에서 추가",
            ),
            StrategyParameter(
                name="max_units",
                display_name="최대 유닛 수",
                param_type="int",
                default=4,
                min_value=1,
                max_value=10,
                description="최대 추가 횟수",
            ),
        ]

    async def evaluate(self, symbol: str, data: pd.DataFrame) -> SignalResult:
        """Evaluate pyramid condition"""
        return SignalResult(symbol=symbol, signal=True, score=100.0)

    async def calculate_order(
        self,
        symbol: str,
        current_price: float,
        available_cash: float,
        current_position: Optional[Dict[str, Any]] = None
    ) -> Optional[Dict[str, Any]]:
        """Calculate pyramid add order"""
        add_threshold = self.get_param("add_threshold_atr")
        max_units = self.get_param("max_units")

        if not current_position:
            return None  # No existing position to pyramid

        entry_price = current_position.get("avg_price", current_price)
        current_units = current_position.get("units", 1)
        atr = current_position.get("atr", current_price * 0.02)  # Default 2%

        if current_units >= max_units:
            return None  # Max units reached

        # Check if price moved favorably by ATR threshold
        price_move = current_price - entry_price
        if price_move >= atr * add_threshold:
            unit_size = current_position.get("unit_size", 100)
            return {
                "symbol": symbol,
                "side": "2",  # Buy (add to long)
                "qty": unit_size,
                "price": current_price,
                "order_type": "limit",
                "reason": f"Pyramid unit {current_units + 1}",
            }

        return None


class TrackingPriceModifyBuy(BaseExecutionStrategy):
    """
    Tracking Price Modify Buy
    
    If limit order not filled, move price to Bid+1 tick.
    """
    name = "TrackingPriceModifyBuy"
    display_name = "추적 가격 수정"
    description = "미체결 시 가격을 추적하여 수정"

    @classmethod
    def get_parameters(cls) -> List[StrategyParameter]:
        return [
            StrategyParameter(
                name="tick_offset",
                display_name="틱 오프셋",
                param_type="int",
                default=1,
                min_value=0,
                max_value=10,
                description="현재 가격에서의 틱 수",
            ),
            StrategyParameter(
                name="max_chases",
                display_name="최대 추적 횟수",
                param_type="int",
                default=3,
                min_value=1,
                max_value=10,
            ),
        ]

    async def evaluate(self, symbol: str, data: pd.DataFrame) -> SignalResult:
        """Evaluate tracking condition"""
        return SignalResult(symbol=symbol, signal=True, score=100.0)

    async def calculate_order(
        self,
        symbol: str,
        current_price: float,
        available_cash: float,
        current_position: Optional[Dict[str, Any]] = None
    ) -> Optional[Dict[str, Any]]:
        """Calculate price modification for unfilled order"""
        tick_offset = self.get_param("tick_offset")
        max_chases = self.get_param("max_chases")

        # This would be called with pending order info in practice
        pending_order = current_position  # Reuse for demo

        if not pending_order:
            return None

        chase_count = pending_order.get("chase_count", 0)
        if chase_count >= max_chases:
            return {"action": "cancel", "reason": "Max chases reached"}

        # Calculate tick size based on price (simplified)
        if current_price >= 5001:
            tick_size = 10
        elif current_price >= 3001:
            tick_size = 5
        elif current_price >= 1001:
            tick_size = 1
        else:
            tick_size = 0.1

        new_price = current_price + (tick_offset * tick_size)

        return {
            "symbol": symbol,
            "action": "modify",
            "new_price": new_price,
            "chase_count": chase_count + 1,
        }

        # Conditions not met - no modification needed
        return None


class TurtleSafetyCancel(BaseExecutionStrategy):
    """
    Turtle Safety Cancel
    
    Cancel order if not filled in N seconds.
    """
    name = "TurtleSafetyCancel"
    display_name = "터틀 안전 취소"
    description = "일정 시간 후 미체결 주문 취소"

    @classmethod
    def get_parameters(cls) -> List[StrategyParameter]:
        return [
            StrategyParameter(
                name="timeout_seconds",
                display_name="타임아웃 (초)",
                param_type="int",
                default=60,
                min_value=10,
                max_value=300,
            ),
        ]

    async def evaluate(self, symbol: str, data: pd.DataFrame) -> SignalResult:
        """Evaluate timeout condition"""
        return SignalResult(symbol=symbol, signal=True, score=100.0)

    async def calculate_order(
        self,
        symbol: str,
        current_price: float,
        available_cash: float,
        current_position: Optional[Dict[str, Any]] = None
    ) -> Optional[Dict[str, Any]]:
        """Check if order should be cancelled due to timeout"""
        timeout = self.get_param("timeout_seconds")
        
        pending_order = current_position  # Would contain order info
        if not pending_order:
            return None

        order_time = pending_order.get("order_time")
        if not order_time:
            return None

        elapsed = (datetime.now() - order_time).total_seconds()
        
        if elapsed >= timeout:
            return {
                "symbol": symbol,
                "action": "cancel",
                "order_id": pending_order.get("order_id"),
                "reason": f"Timeout after {elapsed:.0f}s",
            }

        # Timeout not reached - no action needed
        return None


class PriceRangeCanceller(BaseExecutionStrategy):
    """
    Price Range Canceller
    
    Cancel if price gap becomes too large.
    """
    name = "PriceRangeCanceller"
    display_name = "가격 괴리 취소"
    description = "가격이 너무 괴리되면 주문 취소"

    @classmethod
    def get_parameters(cls) -> List[StrategyParameter]:
        return [
            StrategyParameter(
                name="max_gap_percent",
                display_name="최대 괴리 %",
                param_type="float",
                default=2.0,
                min_value=0.5,
                max_value=10.0,
            ),
        ]

    async def evaluate(self, symbol: str, data: pd.DataFrame) -> SignalResult:
        """Evaluate price gap condition"""
        return SignalResult(symbol=symbol, signal=True, score=100.0)

    async def calculate_order(
        self,
        symbol: str,
        current_price: float,
        available_cash: float,
        current_position: Optional[Dict[str, Any]] = None
    ) -> Optional[Dict[str, Any]]:
        """Check if order should be cancelled due to price gap"""
        max_gap = self.get_param("max_gap_percent")

        pending_order = current_position
        if not pending_order:
            return None

        order_price = pending_order.get("order_price", current_price)
        
        gap_percent = abs(current_price - order_price) / order_price * 100

        if gap_percent >= max_gap:
            return {
                "symbol": symbol,
                "action": "cancel",
                "order_id": pending_order.get("order_id"),
                "reason": f"Price gap {gap_percent:.2f}% exceeds {max_gap}%",
            }

        # Gap within acceptable range - no action needed
        return None


class ATRLossCutManager(BaseExecutionStrategy):
    """
    ATR Loss Cut Manager
    
    Stop Loss based on ATR (Average True Range).
    Stop Price = Entry Price - (ATR * multiplier)
    """
    name = "ATRLossCutManager"
    display_name = "ATR 손절"
    description = "장중 변동성(ATR)을 반영한 동적 손절매"

    @classmethod
    def get_parameters(cls) -> List[StrategyParameter]:
        return [
            StrategyParameter(
                name="atr_multiplier",
                display_name="ATR 배수 (손절 폭)",
                param_type="float",
                default=1.5,
                min_value=0.5,
                max_value=5.0,
                description="시가 고가 저가 등을 반영한 변동성(ATR)의 N배 하락 시 손절",
            ),
        ]

    async def evaluate(self, symbol: str, data: pd.DataFrame) -> SignalResult:
        """Evaluate ATR loss cut condition"""
        return SignalResult(symbol=symbol, signal=True, score=100.0)

    async def calculate_order(
        self,
        symbol: str,
        current_price: float,
        available_cash: float,
        current_position: Optional[Dict[str, Any]] = None
    ) -> Optional[Dict[str, Any]]:
        """Calculate ATR stop loss order"""
        if not current_position:
            return None

        multiplier = self.get_param("atr_multiplier")
        
        entry_price = current_position.get("avg_price", current_price)
        qty = current_position.get("qty", 0)
        
        # ATR should ideally be recorded at entry.
        # Fallback: estimate 2% of current price if no ATR was saved.
        atr_value = current_position.get("atr", current_price * 0.02)
        
        stop_price = entry_price - (atr_value * multiplier)

        if current_price <= stop_price:
            drop_pct = (entry_price - current_price) / entry_price * 100
            return {
                "symbol": symbol,
                "side": "1",  # Sell
                "qty": qty,
                "price": current_price,
                "order_type": "market",
                "reason": f"ATR Loss cut (Stop: {stop_price:.0f}, Drop: -{drop_pct:.2f}%)",
            }

        # Loss cut not triggered
        return None


class DynamicLossCutManager(BaseExecutionStrategy):
    """
    Dynamic Loss Cut Manager with Time Stop
    
    Gradually tightens the stop loss threshold based on holding time.
    Also executes a Time Stop exit if the trade is flat after N minutes.
    """
    name = "DynamicLossCutManager"
    display_name = "시간 기반 동적 손절"
    description = "보유 시간 경과에 따라 손절 폭을 좁히고 타임스탑 청산을 수행"

    @classmethod
    def get_parameters(cls) -> List[StrategyParameter]:
        return [
            StrategyParameter(
                name="loss_cut_percent",
                display_name="기본 손절 %",
                param_type="float",
                default=2.5,
                min_value=1.0,
                max_value=10.0,
                description="진입 초기 최대 허용 손실 %",
            ),
            StrategyParameter(
                name="time_stop_minutes",
                display_name="타임스탑 시간 (분)",
                param_type="int",
                default=60,
                min_value=10,
                max_value=300,
                description="이 시간 경과 시 본전/약손실 상태에서 탈출",
            ),
        ]

    async def evaluate(self, symbol: str, data: pd.DataFrame) -> SignalResult:
        """Evaluate dynamic loss cut condition"""
        return SignalResult(symbol=symbol, signal=True, score=100.0)

    async def calculate_order(
        self,
        symbol: str,
        current_price: float,
        available_cash: float,
        current_position: Optional[Dict[str, Any]] = None
    ) -> Optional[Dict[str, Any]]:
        """Calculate dynamic stop loss and time stop order"""
        if not current_position:
            return None

        base_lc = self.get_param("loss_cut_percent")
        time_stop_mins = self.get_param("time_stop_minutes")
        
        entry_price = current_position.get("avg_price", current_price)
        qty = current_position.get("qty", 0)
        
        if entry_price <= 0 or qty <= 0:
            return None
            
        pnl_percent = (current_price - entry_price) / entry_price * 100
        
        # Calculate dynamic stop loss percentage based on holding time
        entry_time = current_position.get("entry_time")
        
        if not entry_time:
            # Fallback to base static stop loss if entry_time is missing
            lc_pct = base_lc
            hold_minutes = 0.0
        else:
            if isinstance(entry_time, str):
                try:
                    entry_time = datetime.fromisoformat(entry_time)
                except ValueError:
                    entry_time = None
                    
            if entry_time:
                hold_seconds = (datetime.now() - entry_time).total_seconds()
                hold_minutes = hold_seconds / 60
                
                # Apply step-wise tightening
                if hold_minutes < 15:
                    lc_pct = base_lc
                elif hold_minutes < 30:
                    lc_pct = base_lc * 0.8  # 80% of base stop loss (e.g. 2.5% -> 2.0%)
                elif hold_minutes < 60:
                    lc_pct = base_lc * 0.6  # 60% of base stop loss (e.g. 2.5% -> 1.5%)
                else:
                    lc_pct = base_lc * 0.4  # 40% of base stop loss (e.g. 2.5% -> 1.0%)
            else:
                lc_pct = base_lc
                hold_minutes = 0.0

        # 1. Check Dynamic Stop Loss
        if pnl_percent <= -lc_pct:
            return {
                "symbol": symbol,
                "side": "1",  # Sell
                "qty": qty,
                "price": current_price,
                "order_type": "market",
                "reason": f"Dynamic Loss cut at {pnl_percent:.2f}% (Limit: -{lc_pct:.2f}%, Held: {hold_minutes:.1f}m)",
            }

        # 2. Check Time Stop Exit (e.g. held for >60 mins and return is flat/losing (< +0.2%))
        if entry_time and hold_minutes >= time_stop_mins and pnl_percent < 0.2:
            return {
                "symbol": symbol,
                "side": "1",  # Sell
                "qty": qty,
                "price": current_price,
                "order_type": "market",
                "reason": f"Time stop triggered (Held: {hold_minutes:.1f}m, PnL: {pnl_percent:.2f}%)",
            }

        return None

