# -*- coding: utf-8 -*-
"""
Base Strategy Class

All strategies must inherit from BaseStrategy to allow user selection.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

import pandas as pd


@dataclass
class StrategyParameter:
    """Strategy parameter definition"""
    name: str
    display_name: str
    param_type: str  # "int", "float", "bool", "select"
    default: Any
    min_value: Optional[float] = None
    max_value: Optional[float] = None
    options: Optional[List[str]] = None  # For "select" type
    description: str = ""


@dataclass
class SignalResult:
    """Result from a strategy signal evaluation"""
    symbol: str
    signal: bool  # True = condition met
    score: float  # Strength of signal (0.0 - 100.0)
    details: Dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)


class BaseStrategy(ABC):
    """
    Abstract base class for all strategies.
    
    All Extraction and Execution strategies must inherit from this class.
    This enables dynamic strategy selection in the frontend.
    """

    # Strategy metadata (override in subclass)
    name: str = "BaseStrategy"
    display_name: str = "Base Strategy"
    description: str = "Base strategy class"
    strategy_type: str = "base"  # "extraction" or "execution"

    def __init__(self, **params):
        """
        Initialize strategy with parameters.
        
        Args:
            **params: Strategy-specific parameters
        """
        self._params = self._get_default_params()
        self._params.update(params)

    @classmethod
    def get_parameters(cls) -> List[StrategyParameter]:
        """
        Return list of configurable parameters.
        
        Override in subclass to define strategy-specific parameters.
        """
        return []

    def _get_default_params(self) -> Dict[str, Any]:
        """Get default values for all parameters"""
        return {p.name: p.default for p in self.get_parameters()}

    def get_param(self, name: str) -> Any:
        """Get a parameter value"""
        return self._params.get(name)

    def set_param(self, name: str, value: Any):
        """Set a parameter value"""
        self._params[name] = value

    @abstractmethod
    async def evaluate(
        self, 
        symbol: str, 
        data: pd.DataFrame
    ) -> SignalResult:
        """
        Evaluate the strategy for a given symbol.
        
        Args:
            symbol: Stock symbol
            data: OHLCV DataFrame with columns: open, high, low, close, volume
            
        Returns:
            SignalResult with signal evaluation
        """
        pass

    def __str__(self) -> str:
        return f"{self.name}({self._params})"

    def __repr__(self) -> str:
        return self.__str__()


class BaseExtractionStrategy(BaseStrategy):
    """Base class for Extraction (Stock Filtering) strategies"""
    strategy_type: str = "extraction"


class BaseExecutionStrategy(BaseStrategy):
    """Base class for Execution (Trading Logic) strategies"""
    strategy_type: str = "execution"

    @abstractmethod
    async def calculate_order(
        self,
        symbol: str,
        current_price: float,
        available_cash: float,
        current_position: Optional[Dict[str, Any]] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Calculate order parameters.
        
        Args:
            symbol: Stock symbol
            current_price: Current market price
            available_cash: Available buying power
            current_position: Current position info (if any)
            
        Returns:
            Order dict with qty, price, side, etc. or None for no action
        """
        pass
