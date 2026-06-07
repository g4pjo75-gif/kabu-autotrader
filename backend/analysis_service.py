import asyncio
from typing import List, Dict, Any, Type
import pandas as pd
from datetime import datetime

from backend.universe import Universe
from backend.kabu_client import BaseKabuClient

# Strategies
from strategies import (
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
    VWAPPullbackStrategy,
    HighBreakoutStrategy,
)

EXTRACTION_STRATEGIES = {
    cls.name: cls for cls in [
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
        VWAPPullbackStrategy,
        HighBreakoutStrategy,
    ]
}

class AnalysisService:
    """
    Service for running stock analysis strategies in background or foreground.
    Decoupled from UI.
    """
    def __init__(self, universe_manager: Universe, client: BaseKabuClient, app_state: Dict[str, Any] = None):
        self.universe_manager = universe_manager
        self.client = client
        self.app_state = app_state or {}

    async def analyze_universe(
        self, 
        universe_code: str, 
        strategy_name: str, 
        params: Dict[str, Any] = None,
        progress_callback = None
    ) -> List[Dict[str, Any]]:
        """
        Run analysis on a specific universe with a strategy.
        """
        if params is None:
            params = {}

        # 1. Get Universe
        stocks = self.universe_manager.get_universe(universe_code)
        if not stocks:
            return []

        # 2. Get Strategy Class
        strategy_cls = EXTRACTION_STRATEGIES.get(strategy_name)
        if not strategy_cls:
            raise ValueError(f"Unknown strategy: {strategy_name}")

        strategy = strategy_cls(**params)
        
        # 3. Prepare Parallel Tasks
        tasks = []
        semaphore = asyncio.Semaphore(3)  # Concurrency limit lowered to prevent YF rate limits

        async def analyze_stock(stock_code: str, stock_name: str):
            async with semaphore:
                try:
                    # Fetch Data (Delay to prevent rate limiting)
                    await asyncio.sleep(0.2)
                    df = await self.client.get_stock_history(
                        stock_code, 
                        days=365 # Sufficient history
                    )
                    if df is None or df.empty:
                        return None
                    
                    # Run Strategy
                    # Fix: Call evaluate (async) and handle SignalResult object
                    result = await strategy.evaluate(stock_code, df)
                    
                    if result and result.signal:
                        current_price = float(df["close"].iloc[-1])
                        
                        # GLOBAL FILTER: Skip stocks above max buy price
                        # (Since minimum lot is 100 shares, e.g. 5000 JPY = 500,000 JPY per lot)
                        max_buy_price = self.app_state.get("max_buy_price", 5000)
                        if current_price >= max_buy_price:
                            return None
                            
                        # Extract signal type from details with fallbacks
                        d = result.details
                        sig_type = d.get("cross_type") or d.get("signal") or d.get("last_crossover") or d.get("pattern") or "Signal"
                        
                        return {
                            "symbol": stock_code,
                            "name": stock_name,
                            "price": current_price,
                            "signal": sig_type,
                            "strength": result.score,
                            "reason": str(d),
                            "timestamp": datetime.now().isoformat()
                        }
                except Exception as e:
                    print(f"Error analyzing {stock_code}: {e}")
                    pass
                finally:
                    if progress_callback:
                        await progress_callback()
                return None

        # 4. Create Tasks
        # Pre-load names
        stock_map = self.universe_manager.load_stock_map()
        
        total_stocks = len(stocks)
        for stock in stocks:
            if isinstance(stock, str):
                stock_code = stock
                stock_name = stock_map.get(stock_code, stock_code)
            else:
                stock_code = stock.get("code")
                stock_name = stock.get("name")
                
            tasks.append(analyze_stock(stock_code, stock_name))

        # 5. Run
        results = await asyncio.gather(*tasks)
        
        # 6. Filter None and Sort
        matched_stocks = [r for r in results if r is not None]
        # Sort by strength (desc) or price as fallback
        matched_stocks.sort(key=lambda x: x.get("strength", 0), reverse=True)
        
        return matched_stocks
