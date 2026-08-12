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
                        
                    # 실시간 현재가 보정 (yfinance 지연 데이터 문제 해결)
                    try:
                        board = await self.client.get_board(stock_code)
                        if board and board.current_price > 0:
                            from datetime import date as _date
                            today_ts = pd.Timestamp(_date.today().strftime('%Y-%m-%d'), tz=df.index.tz if hasattr(df.index, 'tz') else None)
                            
                            # 데이터프레임의 마지막 행 날짜 확인
                            last_ts = df.index[-1]
                            if last_ts.strftime('%Y-%m-%d') != today_ts.strftime('%Y-%m-%d'):
                                # 오늘 날짜의 행이 없으면 추가
                                new_row = pd.DataFrame([{
                                    'open': board.open_price or board.previous_close or board.current_price,
                                    'high': board.high_price or board.current_price,
                                    'low': board.low_price or board.current_price,
                                    'close': board.current_price,
                                    'volume': board.volume
                                }], index=[today_ts])
                                df = pd.concat([df, new_row])
                            else:
                                # 오늘 날짜의 행이 있으면 덮어쓰기 (실시간 데이터로 갱신)
                                df.loc[last_ts, 'open'] = board.open_price or board.previous_close or board.current_price
                                df.loc[last_ts, 'high'] = board.high_price or board.current_price
                                df.loc[last_ts, 'low'] = board.low_price or board.current_price
                                df.loc[last_ts, 'close'] = board.current_price
                                df.loc[last_ts, 'volume'] = board.volume
                    except Exception as e:
                        print(f"[{stock_code}] Real-time board fetch failed: {e}")
                        pass

                    # Run Strategy
                    # Fix: Call evaluate (async) and handle SignalResult object
                    result = await strategy.evaluate(stock_code, df)
                    
                    if result and result.signal:
                        current_price = float(df["close"].iloc[-1])
                        
                        # GLOBAL FILTER: Skip stocks above max buy price
                        max_buy_price = float(self.app_state.get("max_buy_price", 5000))
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
                    return None
                except Exception as e:
                    import logging
                    logging.getLogger(__name__).error(f"Error in analyze_stock({stock_code}): {e}")
                    return e
                finally:
                    if progress_callback:
                        await progress_callback()

        # 4. Process in Batches of 40 (API Registration Limit)
        # Clear any leftover registrations
        try:
            await self.client.unregister_all_symbols()
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(f"Failed to unregister all: {e}")
            
        stock_map = self.universe_manager.load_stock_map()
        
        parsed_stocks = []
        for stock in stocks:
            if isinstance(stock, str):
                stock_code = stock
                stock_name = stock_map.get(stock_code, stock_code)
            else:
                stock_code = stock.get("code")
                stock_name = stock.get("name")
            parsed_stocks.append((stock_code, stock_name))
            
        matched_stocks = []
        batch_size = 40
        
        for i in range(0, len(parsed_stocks), batch_size):
            batch = parsed_stocks[i:i + batch_size]
            batch_symbols = [code for code, name in batch]
            
            # Register batch for real-time board data
            try:
                await self.client.register_symbols(batch_symbols)
            except Exception as e:
                import logging
                logging.getLogger(__name__).error(f"Failed to register batch: {e}")
                
            # Create tasks for this batch
            tasks = [analyze_stock(code, name) for code, name in batch]
            
            # Run batch
            batch_results = await asyncio.gather(*tasks, return_exceptions=True)
            
            for r in batch_results:
                if isinstance(r, Exception):
                    import logging
                    logging.getLogger(__name__).error(f"Exception from gather: {r}")
                elif r is not None:
                    matched_stocks.append(r)
                    
            # Unregister batch
            try:
                await self.client.unregister_symbols(batch_symbols)
            except Exception as e:
                import logging
                logging.getLogger(__name__).error(f"Failed to unregister batch: {e}")
        
        # Sort by strength (desc) or price as fallback
        matched_stocks.sort(key=lambda x: x.get("strength", 0), reverse=True)
        
        return matched_stocks
