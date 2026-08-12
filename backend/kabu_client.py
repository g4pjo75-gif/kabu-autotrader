# -*- coding: utf-8 -*-
"""
Kabu Station API Client

Handles authentication, order execution, and real-time data from kabu Station API.
Includes MockKabuClient for testing without actual API connection.
"""
import asyncio
import random
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional

import httpx
import pandas as pd
import yfinance as yf

from config import KABU_API_BASE_URL, API_RATE_LIMIT


@dataclass
class OrderSchema:
    """Order request schema for Kabu Station API"""
    symbol: str
    exchange: int = 9  # 9: SOR (最良執行) — 2026/2月〜 東証(1)は新規発注不可
    security_type: int = 1  # 1: Stock
    side: str = "1"  # 1: Sell, 2: Buy
    cash_margin: int = 1  # 1: Cash
    deliv_type: int = 2  # 2: Cash delivery
    fund_type: str = "AA"  # "AA": 自動振替 (最も汎用的), "02": 保護預り, "  ": 現物売用
    account_type: int = 4  # 4: Tokutei (Specific Account)
    qty: int = 100
    front_order_type: int = 20  # 20: Limit, 10: Market
    price: float = 0.0
    expire_day: int = 0  # 0: Today
    password: str = ""  # 注文パスワード (取引パスワード) — 実売買に必須


@dataclass
class BoardInfo:
    """Real-time board (price) information"""
    symbol: str
    symbol_name: str
    current_price: float
    bid_price: float
    ask_price: float
    bid_qty: int
    ask_qty: int
    volume: int
    high_price: float
    low_price: float
    open_price: float
    previous_close: float
    timestamp: datetime


class BaseKabuClient(ABC):
    """Abstract base class for Kabu Station API client"""

    @abstractmethod
    async def get_token(self, password: str) -> str:
        """Authenticate and get API token"""
        pass

    @abstractmethod
    async def get_board(self, symbol: str, exchange: int = 1) -> BoardInfo:
        """Get real-time price information"""
        pass

    @abstractmethod
    async def get_wallet_cash(self) -> float:
        """Get available cash balance"""
        pass

    @abstractmethod
    async def send_order(self, order: OrderSchema) -> Dict[str, Any]:
        """Execute buy/sell order"""
        pass

    @abstractmethod
    async def get_positions(self) -> List[Dict[str, Any]]:
        """Get current positions"""
        pass

    @abstractmethod
    async def get_orders(self) -> List[Dict[str, Any]]:
        """Get active orders"""
        pass

    @abstractmethod
    async def cancel_order(self, order_id: str) -> Dict[str, Any]:
        """Cancel an active order"""
        pass

    @abstractmethod
    async def get_stock_history(self, symbol: str, days: int = 100) -> pd.DataFrame:
        """Get historical stock data (using yfinance fallback)"""
        pass



    @abstractmethod
    async def register_symbols(self, symbols: list[str], exchange: int = 1) -> bool:
        pass

    @abstractmethod
    async def unregister_symbols(self, symbols: list[str], exchange: int = 1) -> bool:
        pass

    @abstractmethod
    async def unregister_all_symbols(self) -> bool:
        pass

class KabuClient(BaseKabuClient):
    """
    Real Kabu Station API Client
    
    Connects to localhost:18080 kabu Station API.
    Implements rate limiting and automatic token refresh.
    """

    def __init__(self, base_url: str = KABU_API_BASE_URL):
        self.base_url = base_url
        self.token: Optional[str] = None
        self._last_request_time = 0.0
        self._rate_limit = API_RATE_LIMIT
        self._client = httpx.AsyncClient(timeout=30.0)

    async def _rate_limit_wait(self):
        """Ensure we don't exceed rate limit"""
        if not hasattr(self, '_rate_limit_lock'):
            self._rate_limit_lock = asyncio.Lock()
            
        async with self._rate_limit_lock:
            now = asyncio.get_event_loop().time()
            elapsed = now - self._last_request_time
            min_interval = 1.0 / self._rate_limit
            if elapsed < min_interval:
                await asyncio.sleep(min_interval - elapsed)
                self._last_request_time = asyncio.get_event_loop().time()
            else:
                self._last_request_time = now

    async def _request(
        self, 
        method: str, 
        endpoint: str, 
        data: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """Make rate-limited API request"""
        await self._rate_limit_wait()
        
        headers = {}
        if self.token:
            headers["X-API-KEY"] = self.token

        url = f"{self.base_url}{endpoint}"
        
        if method == "GET":
            response = await self._client.get(url, headers=headers)
        elif method == "POST":
            response = await self._client.post(url, headers=headers, json=data)
        elif method == "PUT":
            response = await self._client.put(url, headers=headers, json=data)
        else:
            raise ValueError(f"Unsupported HTTP method: {method}")

        try:
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            # Try to parse Kabu API's specific error body (HTTP 400 usually)
            try:
                error_data = e.response.json()
                if "Message" in error_data or "Code" in error_data:
                    return error_data
            except Exception:
                pass
            raise e

    async def get_token(self, password: str) -> str:
        """Authenticate and get API token"""
        data = {"APIPassword": password}
        result = await self._request("POST", "/token", data)
        self.token = result.get("Token", "")
        return self.token

    async def get_board(self, symbol: str, exchange: int = 1) -> BoardInfo:
        """Get real-time price information"""
        result = await self._request("GET", f"/board/{symbol}@{exchange}")
        
        # API returns None for fields when market is closed (検証 mode especially)
        def _safe(val, default=0.0):
            return val if val is not None else default
        
        return BoardInfo(
            symbol=result.get("Symbol", symbol),
            symbol_name=result.get("SymbolName", "") or "",
            current_price=_safe(result.get("CurrentPrice"), 0.0),
            bid_price=_safe(result.get("BidPrice"), 0.0),
            ask_price=_safe(result.get("AskPrice"), 0.0),
            bid_qty=int(_safe(result.get("BidQty"), 0)),
            ask_qty=int(_safe(result.get("AskQty"), 0)),
            volume=int(_safe(result.get("TradingVolume"), 0)),
            high_price=_safe(result.get("HighPrice"), 0.0),
            low_price=_safe(result.get("LowPrice"), 0.0),
            open_price=_safe(result.get("OpeningPrice"), 0.0),
            previous_close=_safe(result.get("PreviousClose"), 0.0),
            timestamp=datetime.now(),
        )

    async def get_wallet_cash(self) -> float:
        """Get available cash balance"""
        result = await self._request("GET", "/wallet/cash")
        val = result.get("StockAccountWallet", 0.0)
        return float(val) if val is not None else 0.0


    async def send_order(self, order: OrderSchema) -> Dict[str, Any]:
        """Execute buy/sell order"""
        import logging
        _logger = logging.getLogger(__name__)
        
        data = {
            "Password": order.password,
            "Symbol": order.symbol,
            "Exchange": order.exchange,
            "SecurityType": order.security_type,
            "Side": order.side,
            "CashMargin": order.cash_margin,
            "DelivType": order.deliv_type,
            "FundType": order.fund_type,
            "AccountType": order.account_type,
            "Qty": order.qty,
            "FrontOrderType": order.front_order_type,
            "Price": float(order.price) if order.front_order_type != 10 else 0, # 成行(10)の場合は必ず0
            "ExpireDay": order.expire_day,
        }
        
        # Debug: Log the full payload (mask password)
        debug_data = {k: v for k, v in data.items() if k != "Password"}
        _logger.warning(f"[KabuClient] sendorder payload: {debug_data}")
        
        return await self._request("POST", "/sendorder", data)

    async def get_positions(self) -> List[Dict[str, Any]]:
        """Get current positions"""
        result = await self._request("GET", "/positions")
        return result if isinstance(result, list) else []

    async def get_orders(self) -> List[Dict[str, Any]]:
        """Get active orders"""
        result = await self._request("GET", "/orders")
        return result if isinstance(result, list) else []

    async def cancel_order(self, order_id: str) -> Dict[str, Any]:
        """Cancel an active order"""
        data = {"OrderId": order_id}
        return await self._request("PUT", "/cancelorder", data)

    async def get_ranking(
        self,
        ranking_type: str = "5",
        exchange_division: Any = "ALL"
    ) -> List[Dict[str, Any]]:
        """
        Get ranking data from Kabu Station API.
        
        Args:
            ranking_type: Ranking type
                "1"=値上がり率, "2"=値下がり率, "3"=売買高,
                "4"=売買代金, "5"=TICK回数, "6"=売買高急増,
                "7"=売買代金急増
            exchange_division: Market
                1=全市場, 2=東証, 3=東証プライム,
                4=東証スタンダード, 5=東証グロース
        
        Returns:
            List of ranking items with Symbol, CurrentPrice, etc.
        """
        import logging
        _logger = logging.getLogger(__name__)
        
        # Compatibility mapping: int -> str
        if isinstance(exchange_division, int):
            mapping = {
                1: "ALL",
                2: "TSE",
                3: "Prime",
                4: "Standard",
                5: "Growth"
            }
            exchange_division = mapping.get(exchange_division, "ALL")
        
        try:
            result = await self._request(
                "GET",
                f"/ranking?Type={ranking_type}&ExchangeDivision={exchange_division}"
            )
            
            # Response contains Type, ExchangeDivision, and Ranking list
            ranking_list = result.get("Ranking", [])
            _logger.info(
                f"[KabuClient] Ranking API: Type={ranking_type}, "
                f"Exchange={exchange_division}, Count={len(ranking_list)}"
            )
            return ranking_list
            
        except Exception as e:
            _logger.error(f"[KabuClient] Ranking API failed (Type={ranking_type}, Exchange={exchange_division}): {e}")
            return []

    async def get_stock_history(self, symbol: str, days: int = 100) -> pd.DataFrame:
        """Get historical stock data using yfinance (Kabu Station API doesn't provide easy history)"""
        try:
            # Add .T for Tokyo Stock Exchange if not present
            ticker_symbol = f"{symbol}.T" if not symbol.endswith(".T") else symbol
            
            # Fetch data with some buffer
            period = "1y" if days > 200 else "6mo"
            if days > 365: period = "2y"
            
            ticker = yf.Ticker(ticker_symbol)
            hist = await asyncio.to_thread(ticker.history, period=period)
            
            if hist.empty:
                print(f"Warning: No data found for {symbol}")
                return pd.DataFrame()
            
            # Normalize columns to lowercase
            hist.columns = [c.lower() for c in hist.columns]
            
            # Ensure required columns exist
            required = ["open", "high", "low", "close", "volume"]
            if not all(col in hist.columns for col in required):
                return pd.DataFrame()
                
            return hist.tail(days)
            
        except Exception as e:
            print(f"Error fetching history for {symbol}: {e}")
            return pd.DataFrame()

    async def close(self):
        """Close the HTTP client"""
        await self._client.aclose()



    async def register_symbols(self, symbols: list[str], exchange: int = 1) -> bool:
        if not symbols: return True
        data = {"Symbols": [{"Symbol": str(s), "Exchange": exchange} for s in symbols]}
        try:
            await self._request("PUT", "/register", data)
            return True
        except Exception as e:
            import logging
            logging.getLogger(__name__).error(f"Failed to register symbols: {e}")
            return False

    async def unregister_all_symbols(self) -> bool:
        try:
            await self._request("PUT", "/unregister/all")
            return True
        except Exception as e:
            import logging
            logging.getLogger(__name__).error(f"Failed to unregister all symbols: {e}")
            return False

    async def unregister_symbols(self, symbols: list[str], exchange: int = 1) -> bool:
        if not symbols: return True
        data = {"Symbols": [{"Symbol": str(s), "Exchange": exchange} for s in symbols]}
        try:
            await self._request("PUT", "/unregister", data)
            return True
        except Exception as e:
            import logging
            logging.getLogger(__name__).error(f"Failed to unregister symbols: {e}")
            return False

class MockKabuClient(BaseKabuClient):
    """
    Mock Kabu Station API Client for testing
    
    Simulates API responses without actual connection.
    Useful for UI testing and strategy development.
    """

    def __init__(self):
        self.token: Optional[str] = None
        self._mock_cash = 10_000_000  # 10 million yen (1000万円)
        self._mock_positions: List[Dict[str, Any]] = []
        self._mock_orders: List[Dict[str, Any]] = []
        self._order_counter = 1000
        self._mock_fetched_prices: Dict[str, float] = {}  # Cache prices to prevent wild swings
        self._price_cache_times: Dict[str, float] = {}  # TTL cache timestamps
        self._PRICE_CACHE_TTL = 5.0  # 5 seconds TTL for price cache
        
        
        # Mock price data for common stocks
        self._mock_prices: Dict[str, Dict[str, float]] = {
            "7203": {"name": "トヨタ自動車", "price": 2850.0},
            "6758": {"name": "ソニーグループ", "price": 14500.0},
            "9984": {"name": "ソフトバンクグループ", "price": 8500.0},
            "6861": {"name": "キーエンス", "price": 65000.0},
            "8306": {"name": "三菱UFJフィナンシャル", "price": 1650.0},
            "9432": {"name": "日本電信電話", "price": 175.0},
            "6501": {"name": "日立製作所", "price": 3800.0},
            "7267": {"name": "本田技研工業", "price": 1550.0},
            "4063": {"name": "信越化学工業", "price": 6200.0},
            "7741": {"name": "HOYA", "price": 19500.0},
        }

    def _simulate_price_movement(self, base_price: float) -> float:
        """Simulate random price movement within ±2%"""
        change = random.uniform(-0.02, 0.02)
        return round(base_price * (1 + change), 1)

    def _is_cache_valid(self, symbol: str) -> bool:
        """Check if cached price is still within TTL"""
        import time
        cached_time = self._price_cache_times.get(symbol, 0)
        return (time.time() - cached_time) < self._PRICE_CACHE_TTL

    async def get_token(self, password: str) -> str:
        """Simulate authentication"""
        await asyncio.sleep(0.1)  # Simulate network delay
        if password:
            self.token = f"mock_token_{random.randint(1000, 9999)}"
            return self.token
        raise ValueError("Password required")

    async def get_board(self, symbol: str, exchange: int = 1) -> BoardInfo:
        """Get simulated price information (using yfinance intraday data for realism).
        
        Only returns valid prices when TODAY's intraday data is available.
        If only stale (yesterday's) data exists, returns price=0 to prevent
        buying at yesterday's closing price.
        """
        import time
        import logging
        _logger = logging.getLogger(__name__)
        
        await asyncio.sleep(0.05)  # Simulate network delay
        
        # Return cached price if within TTL (already validated as today's data)
        if symbol in self._mock_fetched_prices and self._is_cache_valid(symbol):
            current_price = self._mock_fetched_prices[symbol]
            name = self._mock_prices.get(symbol, {}).get("name", f"銘柄{symbol}")
            spread = current_price * 0.001
            return BoardInfo(
                symbol=symbol,
                symbol_name=name,
                current_price=round(current_price, 1),
                bid_price=round(current_price - spread, 1),
                ask_price=round(current_price + spread, 1),
                bid_qty=random.randint(100, 10000) * 100,
                ask_qty=random.randint(100, 10000) * 100,
                volume=random.randint(100000, 10000000),
                high_price=round(current_price * 1.02, 1),
                low_price=round(current_price * 0.98, 1),
                open_price=round(current_price * 0.995, 1),
                previous_close=round(current_price * 0.99, 1),
                timestamp=datetime.now(),
            )
        
        current_price = 0.0
        name = self._mock_prices.get(symbol, {}).get("name", f"銘柄{symbol}")
        
        # Try fetching real intraday data from yfinance
        try:
            ticker_symbol = f"{symbol}.T" if not symbol.endswith(".T") else symbol
            ticker = yf.Ticker(ticker_symbol)
            today = datetime.now().date()
            
            # 1. Primary approach: Use fast_info for true real-time price (no 15-minute delay)
            last_price = 0.0
            fast_info_success = False
            
            try:
                # Need to verify if the fast_info data is actually from today
                info = await asyncio.to_thread(lambda: ticker.info)
                timestamp = info.get("regularMarketTime", 0)
                
                if timestamp > 0:
                    market_date = datetime.fromtimestamp(timestamp).date()
                    if market_date == today:
                        # Data is guaranteed to be from today!
                        if hasattr(ticker, 'fast_info'):
                            last_price = float(await asyncio.to_thread(lambda: ticker.fast_info.get("lastPrice", 0.0)))
                            prev_close = float(await asyncio.to_thread(lambda: ticker.fast_info.get("previousClose", 0.0)))
                            if last_price > 0:
                                # Stale check: compare lastPrice against previous close.
                                # If lastPrice ≈ previousClose (within 0.5%), yfinance may not
                                # have updated to real intraday price yet. This happens when 
                                # regularMarketTime is today but price data is still yesterday's 
                                # close (e.g., just after market open).
                                #
                                # Also cross-check with actual historical previous close to 
                                # catch cases where fast_info.previousClose differs slightly
                                # (due to dividend adjustments etc.)
                                is_stale = False
                                
                                # Check 1: Compare with fast_info previousClose
                                if prev_close > 0 and abs(last_price - prev_close) / prev_close < 0.005:
                                    is_stale = True
                                    _logger.warning(
                                        f"[MockClient] {symbol}: ⚠️ fast_info lastPrice (¥{last_price:,.0f}) "
                                        f"≈ previousClose (¥{prev_close:,.0f}). Likely stale."
                                    )
                                
                                # Check 2: Cross-validate with actual historical close
                                if not is_stale:
                                    try:
                                        hist_5d = await asyncio.to_thread(ticker.history, period="5d")
                                        if not hist_5d.empty:
                                            past_data = hist_5d[hist_5d.index.date < today]
                                            if not past_data.empty:
                                                actual_prev_close = float(past_data["Close"].iloc[-1])
                                                if actual_prev_close > 0 and abs(last_price - actual_prev_close) / actual_prev_close < 0.005:
                                                    is_stale = True
                                                    _logger.warning(
                                                        f"[MockClient] {symbol}: ⚠️ fast_info lastPrice (¥{last_price:,.0f}) "
                                                        f"≈ actual prev close (¥{actual_prev_close:,.0f}). Likely stale."
                                                    )
                                    except Exception:
                                        pass  # If cross-check fails, rely on primary check only
                                
                                if is_stale:
                                    _logger.warning(
                                        f"[MockClient] {symbol}: Stale price detected → falling back to intraday history."
                                    )
                                    fast_info_success = False
                                else:
                                    fast_info_success = True
                    else:
                        _logger.warning(f"[MockClient] {symbol}: ⚠️ yfinance info timestamp ({market_date}) is not today ({today}). Stale data blocked.")
            except Exception as e:
                _logger.debug(f"[MockClient] info/fast_info fetch failed for {symbol}: {e}")
                
            if fast_info_success:
                 _logger.info(f"[MockClient] {symbol}: Real-time fast_info price = ¥{last_price:,.0f} (Verified today's timestamp, differs from prev_close)")
                 current_price = last_price
            else:
                # 2. Fallback approach: 15-minute delayed intraday history
                hist = await asyncio.to_thread(ticker.history, period="1d", interval="1m")
                
                if not hist.empty:
                    today_data = hist[hist.index.date == today]
                    
                    if len(today_data) >= 2:
                        last_price = float(today_data["Close"].iloc[-1])
                        _logger.info(f"[MockClient] {symbol}: intraday 1m price (today_fallback) = ¥{last_price:,.0f} "
                                   f"(bars={len(today_data)}, latest={today_data.index[-1]})")
                        current_price = last_price
                    elif len(today_data) == 1:
                        # bars=1 is usually yesterday's close due to 15m delay mechanisms
                        stale_price = float(today_data["Close"].iloc[0])
                        _logger.warning(f"[MockClient] {symbol}: ⚠️ 당일 데이터 유효봉 1개뿐 (price={stale_price:,.0f}). "
                                      f"지연/stale 의심 → 매수 차단 (price=0)")
                        current_price = 0.0
                    else:
                        stale_price = float(hist["Close"].iloc[-1])
                        stale_date = hist.index[-1].date()
                        _logger.warning(f"[MockClient] {symbol}: ⚠️ 당일 데이터 없음! "
                                      f"전일({stale_date}) 종가 ¥{stale_price:,.0f}만 존재 → 매수 차단 (price=0)")
                        current_price = 0.0
                else:
                    _logger.warning(f"[MockClient] {symbol}: history empty → 매수 차단 (price=0)")
                    current_price = 0.0
            
            if current_price > 0:
                self._mock_fetched_prices[symbol] = current_price
                self._price_cache_times[symbol] = time.time()
                
        except Exception as e:
            _logger.warning(f"[MockClient] Real data fetch failed for {symbol}: {e}")
            current_price = 0.0  # Block buy on error

        spread = max(current_price * 0.001, 0.1)  # 0.1% spread

        return BoardInfo(
            symbol=symbol,
            symbol_name=name,
            current_price=round(current_price, 1),
            bid_price=round(current_price - spread, 1) if current_price > 0 else 0.0,
            ask_price=round(current_price + spread, 1) if current_price > 0 else 0.0,
            bid_qty=random.randint(100, 10000) * 100,
            ask_qty=random.randint(100, 10000) * 100,
            volume=random.randint(100000, 10000000),
            high_price=round(current_price * 1.02, 1) if current_price > 0 else 0.0,
            low_price=round(current_price * 0.98, 1) if current_price > 0 else 0.0,
            open_price=round(current_price * 0.995, 1) if current_price > 0 else 0.0,
            previous_close=round(current_price * 0.99, 1) if current_price > 0 else 0.0,
            timestamp=datetime.now(),
        )

    async def get_wallet_cash(self) -> float:
        """Get simulated cash balance"""
        await asyncio.sleep(0.05)
        return self._mock_cash

    async def send_order(self, order: OrderSchema) -> Dict[str, Any]:
        """Simulate order execution"""
        await asyncio.sleep(0.1)
        
        self._order_counter += 1
        order_id = f"MOCK{self._order_counter}"
        
        # Simulate order fill
        mock_order = {
            "OrderId": order_id,
            "Symbol": order.symbol,
            "Side": order.side,
            "Qty": order.qty,
            "Price": order.price,
            "State": 5,  # 5: Filled
            "RecvTime": datetime.now().isoformat(),
        }
        
        # Update mock positions
        if order.side == "2":  # Buy
            cost = order.price * order.qty
            if self._mock_cash >= cost:
                self._mock_cash -= cost
                
                # Check for existing position to average
                existing = next((p for p in self._mock_positions if p["Symbol"] == order.symbol), None)
                if existing:
                    # Calculate new avg price
                    total_qty = existing["Qty"] + order.qty
                    total_cost = (existing["Price"] * existing["Qty"]) + cost
                    existing["Qty"] = total_qty
                    existing["Price"] = total_cost / total_qty
                else:
                    self._mock_positions.append({
                        "Symbol": order.symbol,
                        "Qty": order.qty,
                        "Price": order.price,
                        "SymbolName": f"Test-{order.symbol}" # Simple fallback
                    })
            else:
                return {"Result": 1, "OrderId": "", "Message": "Insufficient Funds"}

        elif order.side == "1":  # Sell
            # Find position
            existing = next((p for p in self._mock_positions if p["Symbol"] == order.symbol), None)
            if existing and existing["Qty"] >= order.qty:
                revenue = order.price * order.qty
                self._mock_cash += revenue
                
                existing["Qty"] -= order.qty
                if existing["Qty"] == 0:
                    self._mock_positions.remove(existing)
            else:
                return {"Result": 1, "OrderId": "", "Message": "Insufficient Position"}
        
        return {"Result": 0, "OrderId": order_id}

    async def get_positions(self) -> List[Dict[str, Any]]:
        """Get simulated positions"""
        await asyncio.sleep(0.05)
        return self._mock_positions.copy()

    async def get_orders(self) -> List[Dict[str, Any]]:
        """Get simulated active orders"""
        await asyncio.sleep(0.05)
        return self._mock_orders.copy()

    async def cancel_order(self, order_id: str) -> Dict[str, Any]:
        """Simulate order cancellation"""
        await asyncio.sleep(0.05)
        self._mock_orders = [o for o in self._mock_orders if o["OrderId"] != order_id]
        return {"Result": 0, "OrderId": order_id}

    async def get_ranking(
        self, 
        ranking_type: str = "1", 
        exchange: int = 1
    ) -> List[Dict[str, Any]]:
        """Get simulated ranking data"""
        await asyncio.sleep(0.1)
        
        ranking = []
        for symbol, data in list(self._mock_prices.items())[:10]:
            ranking.append({
                "Symbol": symbol,
                "SymbolName": data["name"],
                "CurrentPrice": self._simulate_price_movement(data["price"]),
                "ChangeRate": random.uniform(-5, 5),
                "TradingVolume": random.randint(100000, 10000000),
            })
        return ranking

    async def get_stock_history(self, symbol: str, days: int = 100) -> pd.DataFrame:
        """Get historical stock data using yfinance (same as real KabuClient).
        
        Previously generated random prices (~1000 JPY default), causing
        analysis filters and strategy signals to work on fake data.
        Now uses real yfinance data for accurate simulation.
        """
        try:
            # Add .T for Tokyo Stock Exchange if not present
            ticker_symbol = f"{symbol}.T" if not symbol.endswith(".T") else symbol
            
            # Fetch data with some buffer
            period = "1y" if days > 200 else "6mo"
            if days > 365: period = "2y"
            
            ticker = yf.Ticker(ticker_symbol)
            hist = await asyncio.to_thread(ticker.history, period=period)
            
            if hist.empty:
                print(f"Warning: No data found for {symbol}")
                return pd.DataFrame()
            
            # Normalize columns to lowercase
            hist.columns = [c.lower() for c in hist.columns]
            
            # Ensure required columns exist
            required = ["open", "high", "low", "close", "volume"]
            if not all(col in hist.columns for col in required):
                return pd.DataFrame()
                
            return hist.tail(days)
            
        except Exception as e:
            print(f"Error fetching history for {symbol}: {e}")
            return pd.DataFrame()

    async def close(self):
        """No-op for mock client"""
        pass



    async def register_symbols(self, symbols: list[str], exchange: int = 1) -> bool:
        return True

    async def unregister_symbols(self, symbols: list[str], exchange: int = 1) -> bool:
        return True

    async def unregister_all_symbols(self) -> bool:
        return True

class HybridKabuClient(BaseKabuClient):
    """
    Hybrid Kabu Station API Client
    
    실제 KabuStation API로 시세 정보를 조회하고, 주문은 모드에 따라 전환합니다.
    
    [시뮬레이션 모드] (기본값, live_trading=False)
    - get_board(): 실제 API → 실패 시 Mock 폴백
    - get_wallet_cash(): Mock 잔고 (1,000만엔)
    - send_order(): Mock 시뮬레이션
    - get_positions(): Mock 포지션
    - get_orders(): Mock 주문
    
    [실매매 모드] (live_trading=True, 本番 환경만 가능)
    - get_board(): 실제 API → 실패 시 Mock 폴백
    - get_wallet_cash(): 실제 API 잔고
    - send_order(): 실제 API 주문 (성행)
    - get_positions(): 실제 API 포지션
    - get_orders(): 실제 API 주문
    
    - get_stock_history(): yfinance (양쪽 동일)
    - get_ranking(): 실제 API (양쪽 동일)
    """

    def __init__(self, real_client: KabuClient):
        import logging
        self._logger = logging.getLogger(__name__)
        self._real = real_client
        self._mock = MockKabuClient()
        self._mock.token = "hybrid_sim"
        self.token = real_client.token
        self._api_environment = "unknown"  # Will be set externally
        self._live_trading = False  # 실매매 모드 플래그
        self._order_password = ""  # 注文パスワード (取引パスワード)

    @property
    def live_trading(self) -> bool:
        """실매매 모드 여부"""
        return self._live_trading

    @property
    def api_environment(self) -> str:
        return self._api_environment

    @api_environment.setter
    def api_environment(self, value: str):
        self._api_environment = value
        # 환경이 본번이 아닌 경우 자동으로 실매매 비활성화
        if value != "production" and self._live_trading:
            self._live_trading = False
            self._logger.warning(
                "[HybridClient] 環境が本番以外に変更されたため、実売買モードを無効化しました"
            )

    def enable_live_trading(self, order_password: str = ""):
        """
        실매매 모드 활성화.
        本番(production) 환경에서만 활성화 가능.
        주문 비밀번호(注文パスワード) 필수.
        """
        if self._api_environment != "production":
            raise ValueError(
                "실매매는 本番(production) 환경에서만 가능합니다. "
                f"현재 환경: {self._api_environment}"
            )
        if not order_password:
            raise ValueError(
                "실매매에는 주문 비밀번호(注文パスワード)가 필요합니다."
            )
        self._order_password = order_password
        self._live_trading = True
        self._logger.warning(
            "🔴🔴🔴 [HybridClient] 실매매 모드 활성화 (LIVE TRADING ENABLED) 🔴🔴🔴"
        )

    def disable_live_trading(self):
        """실매매 모드 비활성화 → 시뮬레이션으로 복귀"""
        self._live_trading = False
        self._order_password = ""  # 비밀번호 클리어
        self._logger.info(
            "🟡 [HybridClient] 시뮬레이션 모드 복귀 (SIMULATION MODE)"
        )

    async def get_token(self, password: str) -> str:
        """토큰 발행 (실제 API)"""
        token = await self._real.get_token(password)
        self.token = token
        return token

    async def get_board(self, symbol: str, exchange: int = 1) -> BoardInfo:
        """실시간 시세 조회 (실제 API 우선, 가격 0일 경우 또는 실패 시 Mock 폴백)"""
        try:
            board = await self._real.get_board(symbol, exchange)
            if board.current_price <= 0:
                self._logger.warning(
                    f"[HybridClient] Real API returned price=0 for {symbol}. "
                    f"Falling back to yfinance mock."
                )
                return await self._mock.get_board(symbol, exchange)
            self._logger.debug(f"[HybridClient] {symbol}: Real API price = ¥{board.current_price:,.0f}")
            return board
        except Exception as e:
            self._logger.warning(
                f"[HybridClient] Real API get_board failed for {symbol}: {e}. "
                f"Falling back to yfinance mock."
            )
            return await self._mock.get_board(symbol, exchange)

    async def get_wallet_cash(self) -> float:
        """잔고 조회: 실매매 모드이면 실제 API, 시뮬레이션이면 Mock 잔고"""
        if self._live_trading:
            try:
                cash = await self._real.get_wallet_cash()
                self._logger.info(f"[HybridClient] 🔴 LIVE wallet cash = ¥{cash:,.0f}")
                return cash
            except Exception as e:
                self._logger.error(f"[HybridClient] Real wallet_cash failed: {e}")
                raise  # 실매매에서는 폴백 없이 에러 전파
        else:
            cash = await self._mock.get_wallet_cash()
            self._logger.info(f"[HybridClient] Using mock wallet cash = ¥{cash:,.0f} for simulation")
            return cash

    async def send_order(self, order: OrderSchema) -> Dict[str, Any]:
        """주문 실행 — 모드에 따라 실제 API 또는 시뮬레이션"""
        side_str = 'BUY' if order.side == '2' else 'SELL'
        
        if self._live_trading:
            # 실매매: 주문 비밀번호 자동 주입
            order.password = self._order_password
            
            self._logger.warning(
                f"🔴 [HybridClient] LIVE ORDER: {order.symbol} "
                f"side={side_str} qty={order.qty} price={order.price:.0f} "
                f"order_type={'成行' if order.front_order_type == 10 else '指値'}"
            )
            try:
                result = await self._real.send_order(order)
                self._logger.warning(
                    f"🔴 [HybridClient] LIVE ORDER RESULT: {result}"
                )
                return result
            except Exception as e:
                self._logger.error(f"🔴 [HybridClient] LIVE ORDER FAILED: {e}")
                raise  # 실매매에서는 에러 전파
        else:
            self._logger.info(
                f"⚠️ [HybridClient] SIMULATION ORDER: {order.symbol} "
                f"side={side_str} qty={order.qty} price={order.price:.0f}"
            )
            return await self._mock.send_order(order)

    async def get_positions(self) -> List[Dict[str, Any]]:
        """포지션 조회 — 실매매이면 실제 API, 아니면 시뮬레이션"""
        if self._live_trading:
            try:
                positions = await self._real.get_positions()
                self._logger.debug(f"[HybridClient] 🔴 LIVE positions: {len(positions)} items")
                return positions
            except Exception as e:
                self._logger.error(f"[HybridClient] Real positions failed: {e}")
                raise
        else:
            return await self._mock.get_positions()

    async def get_orders(self) -> List[Dict[str, Any]]:
        """주문 목록 조회 — 실매매이면 실제 API, 아니면 시뮬레이션"""
        if self._live_trading:
            try:
                orders = await self._real.get_orders()
                self._logger.debug(f"[HybridClient] 🔴 LIVE orders: {len(orders)} items")
                return orders
            except Exception as e:
                self._logger.error(f"[HybridClient] Real orders failed: {e}")
                raise
        else:
            return await self._mock.get_orders()

    async def cancel_order(self, order_id: str) -> Dict[str, Any]:
        """주문 취소 — 실매매이면 실제 API, 아니면 시뮬레이션"""
        if self._live_trading:
            self._logger.warning(f"🔴 [HybridClient] LIVE CANCEL: OrderId={order_id}")
            try:
                return await self._real.cancel_order(order_id)
            except Exception as e:
                self._logger.error(f"[HybridClient] Real cancel_order failed: {e}")
                raise
        else:
            return await self._mock.cancel_order(order_id)

    async def get_ranking(
        self,
        ranking_type: str = "5",
        exchange_division: Any = "ALL"
    ) -> List[Dict[str, Any]]:
        """랭킹 데이터 (실제 API만 사용, 실패 시 빈 리스트 반환)"""
        try:
            result = await self._real.get_ranking(ranking_type, exchange_division)
            if result:
                self._logger.info(f"[HybridClient] Real ranking data: {len(result)} items")
                return result
            else:
                self._logger.warning(f"[HybridClient] Real ranking returned no items.")
                return []
        except Exception as e:
            self._logger.error(f"[HybridClient] Real ranking failed: {e}")
            return []

    async def get_stock_history(self, symbol: str, days: int = 100) -> pd.DataFrame:
        """과거 데이터 (yfinance - 양쪽 클라이언트 동일)"""
        return await self._real.get_stock_history(symbol, days)

    async def close(self):
        """리소스 정리"""
        await self._real.close()


    async def register_symbols(self, symbols: list[str], exchange: int = 1) -> bool:
        return await self._real.register_symbols(symbols, exchange)

    async def unregister_symbols(self, symbols: list[str], exchange: int = 1) -> bool:
        return await self._real.unregister_symbols(symbols, exchange)

    async def unregister_all_symbols(self) -> bool:
        return await self._real.unregister_all_symbols()
