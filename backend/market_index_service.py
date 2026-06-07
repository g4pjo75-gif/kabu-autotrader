# -*- coding: utf-8 -*-
"""
Market Index Service Module

Collects and stores US/JP market index data for daily trading reports.
- US indices: S&P 500, Dow Jones, NASDAQ (previous day close)
- JP indices: Nikkei 225, TOPIX ETF (intraday snapshots at 09:05, 09:10, 15:00)
"""
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import yfinance as yf

logger = logging.getLogger(__name__)

MARKET_DATA_DIR = Path(__file__).parent.parent / "data" / "market_indices"
MARKET_DATA_DIR.mkdir(parents=True, exist_ok=True)

# Ticker definitions
US_TICKERS = {
    "^GSPC": "S&P 500",
    "^DJI": "Dow Jones",
    "^IXIC": "NASDAQ",
}

JP_TICKERS = {
    "^N225": "Nikkei 225",
    "1306.T": "TOPIX(ETF)",
}


class MarketIndexService:
    """
    Collects and persists market index snapshots for reporting.
    
    Data is stored as JSON files: data/market_indices/YYYY-MM-DD.json
    """

    def __init__(self):
        self._today_data: Dict[str, Any] = {}

    def _get_data_path(self, date_str: str) -> Path:
        return MARKET_DATA_DIR / f"{date_str}.json"

    def _load_data(self, date_str: str) -> Dict[str, Any]:
        """Load saved market data for a date."""
        path = self._get_data_path(date_str)
        if path.exists():
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except Exception as e:
                logger.error(f"[MarketIndex] Failed to load {path}: {e}")
        return {}

    def _save_data(self, date_str: str, data: Dict[str, Any]):
        """Save market data for a date."""
        path = self._get_data_path(date_str)
        try:
            path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            logger.info(f"[MarketIndex] Saved data to {path}")
        except Exception as e:
            logger.error(f"[MarketIndex] Failed to save {path}: {e}")

    def fetch_us_market_close(self, date_str: str = None) -> Dict[str, Any]:
        """
        Fetch US market previous-day closing data.
        
        Returns dict with ticker -> {name, close, prev_close, change, change_pct, direction}
        """
        if not date_str:
            date_str = datetime.now().strftime("%Y-%m-%d")

        data = self._load_data(date_str)

        try:
            logger.info("[MarketIndex] Fetching US market close data...")
            tickers = list(US_TICKERS.keys())
            df = yf.download(tickers, period="5d", progress=False)

            if df.empty:
                logger.warning("[MarketIndex] No US market data returned from yfinance")
                return {}

            us_data = {}
            closes = df["Close"]

            for ticker, name in US_TICKERS.items():
                if ticker not in closes.columns:
                    continue

                series = closes[ticker].dropna()
                if len(series) < 2:
                    continue

                prev_close = float(series.iloc[-2])
                last_close = float(series.iloc[-1])
                change = last_close - prev_close
                change_pct = (change / prev_close) * 100

                us_data[ticker] = {
                    "name": name,
                    "close": round(last_close, 2),
                    "prev_close": round(prev_close, 2),
                    "change": round(change, 2),
                    "change_pct": round(change_pct, 2),
                    "direction": "up" if change >= 0 else "down",
                }
                logger.info(
                    f"[MarketIndex] {name}: {last_close:,.2f} ({change:+,.2f}, {change_pct:+.2f}%)"
                )

            data["us_market"] = us_data
            data["us_fetched_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            self._save_data(date_str, data)

            return us_data

        except Exception as e:
            logger.error(f"[MarketIndex] US market fetch failed: {e}")
            return {}

    def fetch_jp_index_snapshot(self, label: str, date_str: str = None) -> Dict[str, Any]:
        """
        Fetch current JP market index values as a snapshot.
        
        Args:
            label: Snapshot label (e.g., "09:05", "09:10", "15:00")
            date_str: Date string (YYYY-MM-DD). Defaults to today.
            
        Returns:
            dict with ticker -> {name, price, timestamp}
        """
        if not date_str:
            date_str = datetime.now().strftime("%Y-%m-%d")

        data = self._load_data(date_str)

        try:
            logger.info(f"[MarketIndex] Fetching JP index snapshot ({label})...")
            snapshot = {}

            for ticker, name in JP_TICKERS.items():
                try:
                    info = yf.Ticker(ticker)
                    # Use fast_info for current price
                    fast = info.fast_info
                    price = float(fast.get("lastPrice", 0) or fast.get("last_price", 0) or 0)
                    
                    if price <= 0:
                        # Fallback: use recent history
                        hist = info.history(period="1d")
                        if not hist.empty:
                            price = float(hist["Close"].iloc[-1])

                    if price > 0:
                        snapshot[ticker] = {
                            "name": name,
                            "price": round(price, 2),
                            "timestamp": datetime.now().strftime("%H:%M:%S"),
                        }
                        logger.info(f"[MarketIndex] {name}: {price:,.2f}")
                    else:
                        logger.warning(f"[MarketIndex] {name}: No price data available")
                except Exception as e:
                    logger.error(f"[MarketIndex] Failed to fetch {name}: {e}")

            if snapshot:
                if "jp_snapshots" not in data:
                    data["jp_snapshots"] = {}
                data["jp_snapshots"][label] = {
                    "data": snapshot,
                    "fetched_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                }
                self._save_data(date_str, data)

            return snapshot

        except Exception as e:
            logger.error(f"[MarketIndex] JP index snapshot failed: {e}")
            return {}

    def get_market_data(self, date_str: str = None) -> Dict[str, Any]:
        """
        Get all saved market data for a date.
        
        Returns:
            {
                "us_market": {...},
                "jp_snapshots": {"09:05": {...}, "09:10": {...}, "15:00": {...}},
                ...
            }
        """
        if not date_str:
            date_str = datetime.now().strftime("%Y-%m-%d")
        return self._load_data(date_str)
