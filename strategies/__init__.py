# -*- coding: utf-8 -*-
"""
Antigravity Strategies Module
"""
from .base import BaseStrategy
from .extraction import (
    SMAGoldenDeadCross,
    StockSMAEMACross,
    StockMACDShift,
    StockRSIStochastic,
    TurtleBreakoutFilter,
    TurtleLiquidityFilter,
    TurtleVolatilityFilter,
    BollingerBands,
    CandlePatterns,
    TripleConfirmScorer,
    MACDPullback,
)
from .vwap_strategy import VWAPPullbackStrategy
from .breakout_strategy import HighBreakoutStrategy
from .execution import (
    StockSplitFunds,
    BasicLossCutManager,
    DynamicLossCutManager,
    ATRLossCutManager,
    TakeProfitManager,
    TrailingStopManager,
    SteppedTrailingManager,
    TurtlePyramidNewOrder,
    TrackingPriceModifyBuy,
    TurtleSafetyCancel,
    PriceRangeCanceller,
)

__all__ = [
    # Base
    "BaseStrategy",
    # Extraction Strategies
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
    "VWAPPullbackStrategy",
    "HighBreakoutStrategy",
    # Execution Strategies
    "StockSplitFunds",
    "BasicLossCutManager",
    "DynamicLossCutManager",
    "ATRLossCutManager",
    "TakeProfitManager",
    "TrailingStopManager",
    "SteppedTrailingManager",
    "TurtlePyramidNewOrder",
    "TrackingPriceModifyBuy",
    "TurtleSafetyCancel",
    "PriceRangeCanceller",
]
