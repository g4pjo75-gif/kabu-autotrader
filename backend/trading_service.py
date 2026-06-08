# -*- coding: utf-8 -*-
"""
Trading Service Module

Handles the core trading loop:
1. Fetch market data
2. Evaluate strategies (Buy/Sell)
3. Execute orders
4. Persist trade history
"""
import asyncio
import logging
import time as _time
from datetime import datetime
from typing import Any, Dict, List, Optional

from backend.database import Database, TradeRecord
from backend.kabu_client import KabuClient, OrderSchema
from backend.notifier import TradeAlert
from strategies import (
    BasicLossCutManager,
    DynamicLossCutManager,
    TakeProfitManager,
    TrailingStopManager,
    SteppedTrailingManager,
    HighBreakoutStrategy,
)
from strategies.vwap_strategy import VWAPPullbackStrategy

logger = logging.getLogger(__name__)


class TradingService:
    
    def __init__(self, app_state: Dict[str, Any]):
        self.app_state = app_state
        self.db: Database = app_state.get("database") or Database()
        self._last_idle_log_time = 0
        # Track max trades per day per symbol
        self._buy_count_today = {}
        self._buy_today_date = ""
        self._market_trend = "Neutral"
        self._last_n225_price = 0.0
        self._n225_history = []  # 최근 5분간의 지수 흐름
        # Track extraction strategy per symbol for sell-side recording
        self._symbol_extraction_map: Dict[str, str] = {}
        # Track target universe per symbol for sell-side recording
        self._symbol_universe_map: Dict[str, str] = {}
        # Track buy rank per symbol for sell-side recording
        self._symbol_rank_map: Dict[str, int] = {}
        # VWAP strategy instance (shared across cycles)
        self._vwap_strategy = VWAPPullbackStrategy()
        # 일일 실현 손익 추적 (실매매 안전장치)
        self._daily_realized_pnl: float = 0.0
        self._daily_pnl_date: str = ""
        # N225 지수 캐시 (yfinance 과도한 호출 방지)
        self._n225_cached_price: float = 0.0
        self._n225_cache_time: float = 0.0
        self._N225_CACHE_TTL: float = 60.0  # 60초 캐시
        # 대기 타임아웃: 종목별 감시 시작 시각 추적
        self._target_added_time: Dict[str, datetime] = {}
        # High Breakout Strategy instance
        self._breakout_strategy = HighBreakoutStrategy()
        # 종목별 이전 당일 고가 기록
        self._prev_day_highs = {}
        # 口座レベル発注ハードキャップ用 日次カウンタ (買いのみ適用)
        self._daily_order_count = 0
        self._daily_turnover = 0.0
        self._caps_date = None   # 日付が変わったらリセット

    def _log(self, message: str, level: str = "INFO"):
        """Log to console, app_state for UI, and file logger"""
        from datetime import datetime
        timestamp = datetime.now().strftime("%H:%M:%S")
        print(f"[{level}] {message}")
        
        if level == "ERROR":
            logger.error(message)
        elif level == "WARNING":
            logger.warning(message)
        else:
            logger.info(message)
        
        if "logs" not in self.app_state:
            self.app_state["logs"] = []
            
        self.app_state["logs"].insert(0, {
            "time": timestamp,
            "type": level,
            "msg": message
        })
        
        # Keep log size manageable
        if len(self.app_state["logs"]) > 100:
            self.app_state["logs"] = self.app_state["logs"][:100]


    async def _fetch_n225_price(self, client) -> float:
        """Nikkei 225 지수 현재가 조회.
        
        조회 우선순위:
        1. 캐시 (60초 TTL) — 5초 주기 호출에서 yfinance 과부하 방지
        2. Kabu Station API — 닛케이225선물미니 (NK225M@2001) 또는 지수 (101@2001)
        3. yfinance ^N225 — API 실패 시 폴백
        """
        # 1. 캐시 유효하면 즉시 반환
        elapsed = _time.time() - self._n225_cache_time
        if self._n225_cached_price > 0 and elapsed < self._N225_CACHE_TTL:
            return self._n225_cached_price
        
        # 2. Kabu Station API 시도
        # 닛케이 지수는 /board/ 엔드포인트에서 일반 주식과 다른 심볼 형식을 사용
        # 101 = 日経225 지수 코드, 1 = 東証 (東京証券取引所)
        kabu_n225_symbols = [
            ("101", 1),   # 日経225 지수 (東証)
        ]
        
        for symbol, exchange in kabu_n225_symbols:
            try:
                board = await client.get_board(symbol, exchange=exchange)
                if board and board.current_price > 0:
                    self._n225_cached_price = board.current_price
                    self._n225_cache_time = _time.time()
                    logger.info(
                        f"[Trading] N225 지수 = ¥{board.current_price:,.0f} "
                        f"(via Kabu API {symbol}@{exchange})"
                    )
                    return board.current_price
            except Exception as e:
                logger.debug(f"[Trading] Kabu N225 ({symbol}@{exchange}) failed: {e}")
        
        # 3. yfinance 폴백 (^N225)
        try:
            import yfinance as yf
            ticker = yf.Ticker("^N225")
            info = ticker.fast_info
            price = float(info.get("lastPrice", 0.0))
            if price > 0:
                self._n225_cached_price = price
                self._n225_cache_time = _time.time()
                logger.info(f"[Trading] N225 지수 = ¥{price:,.0f} (via yfinance ^N225)")
                return price
        except Exception as e:
            logger.debug(f"[Trading] yfinance ^N225 failed: {e}")
        
        # 모든 소스 실패 → 마지막 캐시 값 반환 (있으면), 없으면 0
        if self._n225_cached_price > 0:
            logger.debug(f"[Trading] N225 모든 소스 실패, 캐시 값 사용: ¥{self._n225_cached_price:,.0f}")
            return self._n225_cached_price
        
        logger.warning("[Trading] N225 지수 조회 실패 (모든 소스). Market=Neutral로 유지.")
        return 0.0

        
    async def run_trading_cycle(self):
        """
        Execute one cycle of trading logic.
        Called periodically by the scheduler.
        """
        if not self.app_state.get("trading_active", False):
            if self._last_idle_log_time == 0:
                 self._log("Trading cycle skipped: Trading is inactive (OFF)", "WARNING")
                 self._last_idle_log_time = 1
            return
        
        # Reset idle flag when active
        self._last_idle_log_time = 0
        
        client = self.app_state.get("client")
        if not client:
            self._log("No client available", "ERROR")
            return



        # Check for idle state (no positions, no targets)
        positions = self.app_state.get("positions", [])
        targets = self.app_state.get("extraction_results", [])
        
        if not positions and not targets:
            return

        logger.debug(f"[Trading] Cycle: positions={len(positions)}, targets={len(targets)}")
        
        # 1. Update Portfolio & Positions
        await self._update_portfolio(client)
        
        # 2. Manage Existing Positions (Sell / Risk Management)
        await self._manage_positions(client)
        
        # 3. Evaluate New Entries (Buy)
        await self._evaluate_entries(client)

    async def _update_portfolio(self, client):
        """Update cash and positions from broker"""
        try:
            # 1. Sync Positions
            raw_positions = await client.get_positions()
            
            # Normalize keys to lowercase for internal use
            normalized_positions = []
            for p in raw_positions:
                qty = p.get("Qty", p.get("LeavesQty", 0))
                # API may return float (e.g. 100.0) — convert to int
                qty = int(float(qty)) if qty else 0
                
                # Skip zero-qty positions (already sold / settled)
                if qty <= 0:
                    continue
                
                normalized_positions.append({
                    "symbol": p.get("Symbol"),
                    "name": p.get("SymbolName", p.get("symbol_name", "")),
                    "qty": qty,
                    "avg_price": p.get("Price", p.get("AveragePrice", 0)),
                    "current_price": p.get("CurrentPrice", 0),
                })
            
            self.app_state["positions"] = normalized_positions
            
            # Re-populate mapping for positions and sync entry time from database
            for pos in normalized_positions:
                symbol = pos["symbol"]
                with self.db._get_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute("""
                        SELECT timestamp, extraction_strategy, target_universe, buy_rank 
                        FROM trade_history 
                        WHERE symbol = ? AND side = 'BUY'
                        ORDER BY timestamp DESC LIMIT 1
                    """, (symbol,))
                    row = cursor.fetchone()
                    if row:
                        pos["entry_time"] = row["timestamp"]
                        if symbol not in self._symbol_extraction_map:
                            self._symbol_extraction_map[symbol] = row["extraction_strategy"]
                            self._symbol_universe_map[symbol] = row["target_universe"]
                            self._symbol_rank_map[symbol] = row["buy_rank"]
                            logger.info(f"[Trading] Restored mapping and entry_time for {symbol}: {row['extraction_strategy']} at {row['timestamp']}")
            
            # 2. Sync Active Orders (Optional, for UI)
            raw_orders = await client.get_orders()
            self.app_state["orders"] = raw_orders # Keep raw for now or normalize if needed
            
        except Exception as e:
            self._log(f"Portfolio update failed: {e}", "ERROR")

    async def _manage_positions(self, client):
        """Evaluate sell/exit logic for current positions"""
        positions = self.app_state.get("positions", [])
        
        if not positions:
            logger.debug("[Trading] No positions to manage")
            return
        
        logger.info(f"[Trading] Managing {len(positions)} position(s)")
        
        # Per-cycle dedup: prevent selling the same symbol twice in one cycle
        # (This does NOT block re-selling after a re-buy in a later cycle)
        sold_this_cycle = set()
        
        for pos in positions:
            symbol = pos["symbol"]
            
            if symbol in sold_this_cycle:
                continue
            
            current_price = pos.get("avg_price", 0)
            
            # Fetch Real-time price
            try:
                board = await client.get_board(symbol)
                current_price = board.current_price
            except Exception as e:
                self._log(f"Failed to get price for {symbol}: {e}", "ERROR")
            
            if current_price <= 0:
                # SAFETY (Critical#2): price fetch failed -> loss-cut CANNOT be evaluated here.
                # We still skip (avoid mis-ordering on an unknown price), but this position is
                # left unprotected this cycle and REQUIRES MONITORING until a valid price returns.
                logger.warning(f"[Trading] Skip sell check for {symbol}: price={current_price} "
                               f"(loss-cut not evaluated - requires monitoring)")
                continue
            
            entry_price = pos.get("avg_price", 0)
            pos_qty = pos.get("qty", 0)
            pnl_pct = ((current_price - entry_price) / entry_price * 100) if entry_price > 0 else 0
            logger.info(f"[Trading] Position {symbol}: entry={entry_price:.0f}, current={current_price:.0f}, pnl={pnl_pct:+.2f}%, qty={pos_qty}")
            
            # Price validity check: skip if price deviates >20% from entry (likely data error)
            # Japanese stocks have daily price limits (値幅制限), moves >20% are abnormal
            if entry_price > 0:
                price_diff_pct = abs(current_price - entry_price) / entry_price * 100
                if price_diff_pct > 20:
                    logger.warning(f"[Trading] Skip {symbol}: abnormal price detected "
                                  f"(entry={entry_price:.0f}, current={current_price:.0f}, diff={price_diff_pct:.1f}%)")
                    continue
            
            # Get global sell settings
            tp_pct = float(self.app_state.get("take_profit_pct", 1.0))
            lc_pct = float(self.app_state.get("loss_cut_pct", 3.0))
            ts_pct = float(self.app_state.get("trailing_stop_pct", 3.0))
            time_stop_mins = int(self.app_state.get("time_stop_minutes", 60))
            
            # Stepped Trailing Stop settings
            st_activate = float(self.app_state.get("stepped_trailing_activate_pct", 0.8))
            st_step1 = float(self.app_state.get("stepped_trailing_step1_pct", 0.5))
            st_step2_threshold = float(self.app_state.get("stepped_trailing_step2_pct", 2.0))
            st_step2_trail = float(self.app_state.get("stepped_trailing_step2_trail_pct", 0.3))
            stepped_trailing_enabled = self.app_state.get("stepped_trailing_enabled", True)
            
            # Apply Sell Strategies
            # Priority: DynamicLossCut (hard stop, FIRST) > SteppedTrailing (if enabled) > TakeProfit > TrailingStop
            # SAFETY (Critical#2): Loss-cut is evaluated FIRST so that a sudden drop triggers
            # the stop-loss before any looser exit strategy can fill above the stop level.
            # The loop below breaks on the first triggered strategy, so order == priority.
            sell_strategies = []

            # Hard stop: dynamic loss-cut must be the highest-priority sell strategy.
            sell_strategies.append(
                DynamicLossCutManager(loss_cut_percent=lc_pct, time_stop_minutes=time_stop_mins)
            )

            if stepped_trailing_enabled:
                # Stepped Trailing takes priority over fixed TakeProfit
                sell_strategies.append(
                    SteppedTrailingManager(
                        trailing_activate_pct=st_activate,
                        trailing_step1_pct=st_step1,
                        trailing_step2_pct=st_step2_threshold,
                        trailing_step2_trail_pct=st_step2_trail,
                    )
                )

            # Fallback: fixed take-profit (acts as safety net / ceiling)
            sell_strategies.append(TakeProfitManager(take_profit_percent=tp_pct))
            sell_strategies.append(TrailingStopManager(trailing_stop_percent=ts_pct))
            
            order_params = None
            triggered_strategy = None
            
            for strategy in sell_strategies:
                order_params = await strategy.calculate_order(
                    symbol=symbol,
                    current_price=current_price,
                    available_cash=0,
                    current_position=pos
                )
                if order_params and order_params.get("qty", 0) > 0:
                    triggered_strategy = strategy
                    logger.info(f"[Trading] Sell strategy triggered: {strategy.name} -> {order_params.get('reason', '')}")
                    break
                else:
                    logger.debug(f"[Trading] {symbol}: {strategy.name} not triggered")
            
            # Execute if any strategy triggered
            if order_params and triggered_strategy and order_params.get("qty", 0) > 0:
                self._log(f"Sell Signal for {symbol} [{triggered_strategy.name}]: {order_params.get('reason', '')}")

                if order_params.get("action") == "cancel":
                    pass
                else:
                    # 매도 수량은 보유 수량 전체
                    qty = pos_qty
                    avg_price = float(pos.get("avg_price", 0))
                    sell_price = float(order_params.get("price", current_price))
                    
                    pnl = (sell_price - avg_price) * qty
                    order_params["qty"] = qty
                    order_params["realized_pnl"] = pnl
                    # Fix #4: Preserve symbol_name for DB recording
                    order_params["name"] = getattr(board, 'symbol_name', pos.get("name", symbol))
                    
                    self._log(f"Executing SELL: {symbol} qty={qty}, price={sell_price:.0f}, pnl={pnl:+,.0f}")
                    ext_strategy = self._symbol_extraction_map.get(symbol, "")
                    target_universe = self._symbol_universe_map.get(symbol, "")
                    buy_rank = self._symbol_rank_map.get(symbol, 0)
                    success = await self._execute_order(client, order_params, "SELL", triggered_strategy.name, ext_strategy, target_universe, buy_rank)
                    if success:
                        sold_this_cycle.add(symbol)
                        
                        # Reset trailing stop tracking for this symbol
                        TrailingStopManager.reset_tracking(symbol)
                        SteppedTrailingManager.reset_tracking(symbol)
            else:
                logger.debug(f"[Trading] {symbol}: no sell signal triggered")
        
    async def _evaluate_entries(self, client):
        """Evaluate buy logic for target stocks"""
        targets = self.app_state.get("extraction_results", [])
        
        if not targets:
            return
        
        # Reset buy count tracking on new day
        today = datetime.now().strftime("%Y-%m-%d")
        now = datetime.now()
        if getattr(self, "_buy_today_date", "") != today:
            self._buy_count_today.clear()
            self._target_added_time.clear()  # 일자 변경 시 초기화
        
        # --- 대기 타임아웃 체크 ---
        target_timeout_min = float(self.app_state.get("target_timeout_minutes", 60))
        if target_timeout_min > 0:
            timed_out_symbols = []
            for t in targets:
                symbol = t.get("symbol", "")
                config_name = t.get("config_name", t.get("extraction_strategy", ""))
                target_universe = t.get("target_universe", "")
                
                # 감시 시작 시각 기록 (최초 1회)
                if symbol not in self._target_added_time:
                    # added_at 필드가 있으면 사용, 없으면 현재 시각
                    added_at_str = t.get("added_at")
                    if added_at_str:
                        try:
                            self._target_added_time[symbol] = datetime.fromisoformat(added_at_str)
                        except (ValueError, TypeError):
                            self._target_added_time[symbol] = now
                    else:
                        self._target_added_time[symbol] = now
                
                # 타임아웃 체크
                added_at = self._target_added_time.get(symbol, now)
                elapsed_min = (now - added_at).total_seconds() / 60.0
                
                if elapsed_min >= target_timeout_min:
                    timed_out_symbols.append(symbol)
                    logger.info(
                        f"[Trading] ⏰ {symbol}: 대기 타임아웃 ({elapsed_min:.0f}분 "
                        f">= {target_timeout_min:.0f}분). 감시 목록에서 제거합니다."
                    )
                    self._log(
                        f"⏰ {symbol}: {target_timeout_min:.0f}분 대기 후 타임아웃 → 목록에서 제거",
                        "WARNING"
                    )
                    # DB 상태 업데이트
                    try:
                        self.db.update_candidate_status(
                            today, config_name, target_universe, symbol,
                            "SKIPPED", f"대기 타임아웃 ({target_timeout_min:.0f}분 초과)"
                        )
                    except Exception as e:
                        logger.error(f"[Trading] Failed to update timeout status: {e}")
            
            # 타임아웃된 종목 제거
            if timed_out_symbols:
                self.app_state["extraction_results"] = [
                    t for t in self.app_state.get("extraction_results", [])
                    if t.get("symbol") not in timed_out_symbols
                ]
                targets = self.app_state.get("extraction_results", [])
                # 메모리에서도 제거
                for sym in timed_out_symbols:
                    self._target_added_time.pop(sym, None)
                
                if not targets:
                    return
            self._buy_today_date = today
        
        # Get Cash
        cash = await client.get_wallet_cash()
        
        # --- Market Trend Check (Nikkei 225) ---
        try:
            current_n225 = await self._fetch_n225_price(client)
            if current_n225 > 0:
                if self._last_n225_price > 0:
                    self._n225_history.append(current_n225)
                    if len(self._n225_history) > 60:  # 5초 주기 * 60 = 5분
                        self._n225_history.pop(0)
                    
                    # 1분 전(12틱 전) 대비 하락폭 체크
                    if len(self._n225_history) >= 12:
                        prev_n225 = self._n225_history[-12]
                        change_pct = (current_n225 - prev_n225) / prev_n225 * 100
                        
                        # 설정값 로드 (기본값 0.1% / 0.05%)
                        down_thresh = -abs(float(self.app_state.get("market_index_down_threshold", 0.1)))
                        up_thresh = abs(float(self.app_state.get("market_index_up_threshold", 0.05)))
                        
                        if change_pct < down_thresh:  # 예: 1분에 0.1% 이상 하락 시
                            self._market_trend = "Down"
                        elif change_pct > up_thresh:
                            self._market_trend = "Up"
                        else:
                            self._market_trend = "Neutral"
                
                self._last_n225_price = current_n225
        except Exception as e:
            logger.debug(f"[Trading] Failed to fetch Nikkei trend: {e}")

        logger.info(f"[Trading] Evaluating {len(targets)} targets, cash={cash:,.0f}, Market={self._market_trend}")
        
        # Track which strategy is monitoring/buying a symbol (for skip reason detail)
        monitoring_strategy = {}
        bought_by_strategy = {}
        
        for stock in targets:
            symbol = stock["symbol"]
            ext_strategy = stock.get("extraction_strategy", "")
            target_universe = stock.get("target_universe", "")
            config_name = stock.get("config_name", ext_strategy)
            
            # Fix #1: Skip duplicate symbols from different strategies
            if symbol in monitoring_strategy:
                logger.debug(f"[Trading] Skip {symbol}: duplicate target from another strategy")
                # Update candidate status: skipped due to duplicate
                prev_strategy = monitoring_strategy.get(symbol, "다른 전략")
                
                # Check if it was actually bought by the previous strategy
                if symbol in bought_by_strategy:
                    skip_reason = f"중복: {prev_strategy}에서 이미 매수"
                else:
                    skip_reason = f"중복: {prev_strategy}에서 이미 감시 중"
                
                try:
                    self.db.update_candidate_status(
                        today, config_name, target_universe, symbol,
                        "SKIPPED", skip_reason, prev_strategy
                    )
                except Exception as e:
                    logger.error(f"[Trading] Failed to update candidate status: {e}")
                continue
            
            monitoring_strategy[symbol] = config_name
            # If it's already in positions, we also count it as bought by its original strategy
            # (Note: _symbol_extraction_map handles the lookup for existing positions)
            existing_pos = next((p for p in self.app_state.get("positions", []) if p["symbol"] == symbol), None)
            if existing_pos:
                bought_by_strategy[symbol] = self._symbol_extraction_map.get(symbol, "다른 전략")
            
            # Check max trades per symbol today
            max_trades = int(self.app_state.get("max_trades_per_symbol", 1))
            current_buy_count = self._buy_count_today.get(symbol, 0)
            if current_buy_count >= max_trades:
                logger.debug(f"[Trading] Skip {symbol}: max trades reached ({current_buy_count}/{max_trades})")
                try:
                    self.db.update_candidate_status(
                        today, config_name, target_universe, symbol,
                        "SKIPPED", f"당일 최대 진입 횟수 도달 ({max_trades}회)"
                    )
                except Exception as e:
                    logger.error(f"[Trading] Failed to update candidate status: {e}")
                self._remove_target_from_extraction(symbol)
                continue
            
            # Check if we already have position (skip if so)
            existing = next((p for p in self.app_state.get("positions", []) if p["symbol"] == symbol), None)
            if existing:
                logger.debug(f"[Trading] Skip {symbol}: already have position (qty={existing.get('qty', 0)})")
                try:
                    self.db.update_candidate_status(
                        today, config_name, target_universe, symbol,
                        "SKIPPED", "이미 보유 중"
                    )
                except Exception as e:
                    logger.error(f"[Trading] Failed to update candidate status: {e}")
                self._remove_target_from_extraction(symbol)
                continue
            
            # Fetch Current Price (Real-time or Mock-Real)
            try:
                board = await client.get_board(symbol)
                current_price = board.current_price
            except Exception as e:
                self._log(f"Failed to get price for {symbol}: {e}", "ERROR")
                current_price = 0
            
            if current_price <= 0:
                # No today's intraday data yet — skip this cycle, retry next cycle
                # Target remains in extraction_results, so it will be retried automatically
                logger.debug(f"[Trading] {symbol}: 당일 가격 미확인, 다음 사이클에서 재시도")
                continue
            
            stock_name = getattr(board, 'symbol_name', stock.get("name", ""))
            
            # Update IntradayBarAccumulator with board data (for VWAP tracking)
            accumulator = self.app_state.get("bar_accumulator")
            if accumulator:
                accumulator.update(
                    symbol=symbol,
                    price=current_price,
                    volume=getattr(board, 'volume', 0),
                )
            
            # Price limit check (3rd safety layer - real-time price)
            max_buy_price = float(self.app_state.get("max_buy_price", 5000))
            if current_price >= max_buy_price:
                logger.info(f"[Trading] Skip {symbol}: price ¥{current_price:,.0f} >= ¥{max_buy_price:,.0f} limit")
                try:
                    self.db.update_candidate_status(
                        today, config_name, target_universe, symbol,
                        "SKIPPED", f"가격 초과 (¥{current_price:,.0f} >= ¥{max_buy_price:,.0f})"
                    )
                except Exception as e:
                    logger.error(f"[Trading] Failed to update candidate status: {e}")
                continue
            
            # ── 매수 전략 분기 ──
            # VWAP 전략이 설정되어 있으면 실시간 VWAP 평가, 고가돌파면 breakout 평가, 아니면 기존 눌림목 로직
            use_vwap = ext_strategy == "VWAPPullback" and accumulator is not None
            use_breakout = ext_strategy == "HighBreakoutStrategy"
            buy_approved = False
            buy_strategy_name = "MarketBuy"
            
            if use_vwap:
                # ── VWAP 눌림목 실시간 평가 ──
                vwap_state = accumulator.get_vwap_state(symbol)
                
                vwap_min_ticks = int(self.app_state.get("vwap_min_ticks", 60))
                current_ticks = getattr(vwap_state, "tick_count", 0)
                
                if vwap_state.vwap <= 0 or vwap_state.cumulative_volume <= 0 or current_ticks < vwap_min_ticks:
                    # VWAP 데이터 부족 → 다음 사이클 대기
                    logger.debug(f"[Trading] {symbol}: VWAP 데이터 축적 중 (volume={vwap_state.cumulative_volume}, ticks={current_ticks}/{vwap_min_ticks})")
                    continue
                
                # VWAP 전략 파라미터를 앱 설정에서 가져오기
                vwap_upper = float(self.app_state.get("vwap_upper_band", 0.5))
                vwap_lower = float(self.app_state.get("vwap_lower_band", 0.2))
                vwap_bounce = float(self.app_state.get("vwap_min_bounce", 0.2))
                vwap_max_pullback = float(self.app_state.get("max_pullback_pct", 1.5))
                
                self._vwap_strategy.set_param("vwap_upper_band", vwap_upper)
                self._vwap_strategy.set_param("vwap_lower_band", vwap_lower)
                self._vwap_strategy.set_param("min_bounce_pct", vwap_bounce)
                self._vwap_strategy.set_param("max_pullback_pct", vwap_max_pullback)
                
                # Real-time evaluation (VWAP, etc.)
                vwap = vwap_state.vwap
                vwap_history = getattr(vwap_state, "vwap_history", [])
                
                result = self._vwap_strategy.evaluate_realtime(
                    symbol=symbol,
                    current_price=current_price,
                    open_price=vwap_state.open_price or getattr(board, 'open_price', 0),
                    day_high=vwap_state.day_high or getattr(board, 'high_price', 0),
                    vwap=vwap,
                    recent_low=vwap_state.recent_low,
                    recent_prices=vwap_state.recent_prices,
                    vwap_history=vwap_history,
                    market_trend=self._market_trend
                )
                
                if result.signal:
                    buy_approved = True
                    buy_strategy_name = "VWAPPullback"
                    logger.info(
                        f"[Trading] {symbol}: VWAP 매수 시그널! "
                        f"(VWAP={vwap_state.vwap:.0f}, price={current_price:.0f}, "
                        f"score={result.score:.1f}, {result.details})"
                    )
                else:
                    logger.debug(
                        f"[Trading] {symbol}: VWAP 조건 미충족 "
                        f"(VWAP={vwap_state.vwap:.0f}, {result.details})"
                    )
                    continue
            elif use_breakout:
                # ── 고가 돌파 실시간 평가 ──
                open_price = getattr(board, 'open_price', 0)
                high_price = getattr(board, 'high_price', 0)
                cumulative_volume = getattr(board, 'volume', 0)
                
                # 이전 최고가 관리
                if symbol not in self._prev_day_highs:
                    self._prev_day_highs[symbol] = high_price
                
                prev_high = self._prev_day_highs[symbol]
                
                # HighBreakoutStrategy 파라미터 로드
                breakout_margin = float(self.app_state.get("breakout_margin_pct", 0.1))
                volume_spurt = float(self.app_state.get("volume_spurt_ratio", 1.5))
                max_daily_rise = float(self.app_state.get("max_daily_rise_pct", 25.0))
                
                self._breakout_strategy.set_param("breakout_margin_pct", breakout_margin)
                self._breakout_strategy.set_param("volume_spurt_ratio", volume_spurt)
                self._breakout_strategy.set_param("max_daily_rise_pct", max_daily_rise)
                
                result = self._breakout_strategy.evaluate_realtime(
                    symbol=symbol,
                    current_price=current_price,
                    open_price=open_price,
                    day_high=prev_high,
                    cumulative_volume=cumulative_volume,
                    market_trend=self._market_trend
                )
                
                # 평가 이후 이전 최고가 업데이트 (현재 고가와 현재가 중 최대값으로 업데이트)
                self._prev_day_highs[symbol] = max(prev_high, high_price, current_price)
                
                if result.signal:
                    buy_approved = True
                    buy_strategy_name = "HighBreakoutStrategy"
                    logger.info(
                        f"[Trading] {symbol}: 고가 돌파 매수 시그널! "
                        f"(이전고가={prev_high:.0f}, 현재가={current_price:.0f}, "
                        f"score={result.score:.1f}, {result.details})"
                    )
                else:
                    logger.debug(
                        f"[Trading] {symbol}: 고가 돌파 조건 미충족 "
                        f"(이전고가={prev_high:.0f}, 현재가={current_price:.0f}, {result.details})"
                    )
                    continue
            else:
                # ── 기존 눌림목 매수 (Dip Buy) 로직 ──
                dip_buy_pct = float(self.app_state.get("dip_buy_pct", 1.5))
                
                if dip_buy_pct > 0:
                    # 무조건 당일 시가를 우선 기준으로 사용
                    reference_price = getattr(board, 'open_price', 0)
                    
                    if reference_price <= 0:
                        logger.debug(f"[Trading] {symbol}: 당일 시가(Open) 아직 미형성. 시가 형성 대기 중...")
                        continue
                    
                    dip_threshold = reference_price * (1 - dip_buy_pct / 100)
                    if current_price > dip_threshold:
                        logger.debug(
                            f"[Trading] {symbol}: 눌림목 대기 중 "
                            f"(당일시가={reference_price:.0f}, 현재가={current_price:.0f}, "
                            f"매수 목표={dip_threshold:.0f}, 필요 하락={dip_buy_pct}%)"
                        )
                        continue
                    else:
                        logger.info(
                            f"[Trading] {symbol}: 눌림목 매수 조건 충족! "
                            f"(당일시가={reference_price:.0f}, 현재가={current_price:.0f}, "
                            f"목표={dip_threshold:.0f})"
                        )
                
                buy_approved = True
                buy_strategy_name = "DipBuy" if dip_buy_pct > 0 else "MarketBuy"
            
            if not buy_approved:
                continue
            
            # 동적 매수 수량 산정 (Dynamic Lot Sizing)
            dynamic_lot_enabled = self.app_state.get("dynamic_lot_enabled", True)
            dynamic_lot_threshold = float(self.app_state.get("dynamic_lot_threshold", 2000))
            dynamic_lot_size = int(self.app_state.get("dynamic_lot_size", 200))
            default_lot_size = int(self.app_state.get("default_lot_size", 100))
            
            buy_qty = default_lot_size
            if dynamic_lot_enabled and current_price < dynamic_lot_threshold:
                buy_qty = dynamic_lot_size

            # Cash sufficiency check (before sending order to API)
            estimated_cost = current_price * buy_qty
            # 성행(Market) 주문은 슬리피지 가능성 있으므로 5% 여유 확보
            cost_with_margin = estimated_cost * 1.05
            if cash < cost_with_margin:
                logger.info(
                    f"[Trading] Skip {symbol}: 자금 부족 "
                    f"(필요: ¥{cost_with_margin:,.0f}, 가용: ¥{cash:,.0f}, 주가: ¥{current_price:,.0f})"
                )
                try:
                    self.db.update_candidate_status(
                        today, config_name, target_universe, symbol,
                        "SKIPPED", f"자금 부족 (필요 ¥{estimated_cost:,.0f} > 가용 ¥{cash:,.0f})"
                    )
                except Exception as e:
                    logger.error(f"[Trading] Failed to update candidate status: {e}")
                continue
            
            logger.info(f"[Trading] {symbol} ({stock_name}): price={current_price}, 매수 진행 (수량={buy_qty})")
            
            # 주문 생성
            order_params = {
                "symbol": symbol,
                "side": "2",  # Buy
                "qty": buy_qty,
                "price": current_price,
                "order_type": "limit",
                "name": stock_name,
            }
            
            # Get extraction strategy from target stock config
            if not ext_strategy:
                strategy_id = stock.get("strategy_id")
                if strategy_id:
                    automation = self.app_state.get("automation_service")
                    if automation:
                        cfg = automation.get_config(strategy_id)
                        if cfg:
                            ext_strategy = cfg.config_json.get("extraction_strategy", "")
            
            # Track extraction strategy for this symbol (for sell-side lookup)
            self._symbol_extraction_map[symbol] = config_name
            
            # Get target universe from target stock config
            if not target_universe:
                strategy_id = stock.get("strategy_id")
                if strategy_id:
                    automation = self.app_state.get("automation_service")
                    if automation:
                        cfg = automation.get_config(strategy_id)
                        if cfg:
                            target_universe = cfg.config_json.get("target_universe", "")
            
            # Track target universe for this symbol (for sell-side lookup)
            self._symbol_universe_map[symbol] = target_universe
            
            # Get buy rank from target stock config
            buy_rank = stock.get("buy_rank", 0)
            # Track buy rank for this symbol (for sell-side lookup)
            self._symbol_rank_map[symbol] = buy_rank
            
            self._log(f"Buy Signal for {symbol} [{buy_strategy_name}]: qty={order_params['qty']}, price={order_params['price']}")
            success = await self._execute_order(client, order_params, "BUY", buy_strategy_name, config_name, target_universe, buy_rank)
            
            if success:
                self._buy_count_today[symbol] = self._buy_count_today.get(symbol, 0) + 1
                
                # Update candidate status to BOUGHT
                strategy_display = f"{config_name} ({target_universe})" if target_universe else config_name
                bought_by_strategy[symbol] = strategy_display
                try:
                    self.db.update_candidate_status(
                        today, config_name, target_universe, symbol,
                        "BOUGHT", ""
                    )
                except Exception as e:
                    logger.error(f"[Trading] Failed to update candidate status: {e}")
                    
                self._remove_target_from_extraction(symbol)

    def _remove_target_from_extraction(self, symbol: str):
        if "extraction_results" in self.app_state:
            self.app_state["extraction_results"] = [
                t for t in self.app_state["extraction_results"] if t.get("symbol") != symbol
            ]
            
    async def _execute_order(self, client, params: Dict, side: str, strategy_name: str, extraction_strategy: str = "", target_universe: str = "", buy_rank: int = 0) -> bool:
        """Execute order and save to DB. Returns True if successful, False otherwise."""
        symbol = params["symbol"]
        qty = params.get("qty", 0)
        price = params.get("price", 0)
        
        # 실매매 여부 확인
        is_live = getattr(client, 'live_trading', False)
        
        # 일일 손실 한도 체크 (실매매 + 매수 시에만)
        if is_live and side == "BUY":
            today = datetime.now().strftime("%Y-%m-%d")
            if self._daily_pnl_date != today:
                self._daily_realized_pnl = 0.0
                self._daily_pnl_date = today
            
            max_loss = float(self.app_state.get("daily_max_loss", 30000))
            if self._daily_realized_pnl < -max_loss:
                self._log(
                    f"🚨 일일 손실 한도 초과! (손실: ¥{self._daily_realized_pnl:,.0f} / 한도: -¥{max_loss:,.0f}) → 신규 매수 중단",
                    "ERROR"
                )
                self.app_state["trading_active"] = False
                
                # 텔레그램 긴급 알림
                notifier = self.app_state.get("notifier")
                if notifier and notifier.is_configured:
                    await notifier.send_system_alert(
                        f"🚨 일일 손실 한도 초과!\n"
                        f"누적 손실: ¥{self._daily_realized_pnl:,.0f}\n"
                        f"한도: -¥{max_loss:,.0f}\n"
                        f"자동매매를 긴급 중단합니다.",
                        "ERROR"
                    )
                return False

        # ─────────────────────────────────────────────────────────────
        # 口座レベル発注ハードキャップ (買い注文のみ適用)
        # 売り(SELL=決済/損切り)は資金保全のため一切ブロックしない
        # ─────────────────────────────────────────────────────────────
        if side == "BUY":
            # 日跨ぎリセット
            caps_today = datetime.now().strftime("%Y-%m-%d")
            if self._caps_date != caps_today:
                self._daily_order_count = 0
                self._daily_turnover = 0.0
                self._caps_date = caps_today

            # キャップ設定 (main.py 未load環境でも壊れないよう default fallback)
            cap_order_notional = float(self.app_state.get("max_order_notional", 500000))
            cap_order_count = int(self.app_state.get("daily_max_order_count", 20))
            cap_turnover = float(self.app_state.get("daily_max_turnover", 2000000))
            cap_total_position = float(self.app_state.get("max_total_position_value", 1000000))

            # notional 算出 (price 取得不可/0以下なら notional 系チェックはスキップ)
            try:
                notional = float(qty) * float(price)
            except (TypeError, ValueError):
                notional = 0.0
            notional_valid = notional > 0

            cap_blocked_reason = None

            # 1) 1注文あたり金額上限
            if notional_valid and notional > cap_order_notional:
                cap_blocked_reason = (
                    f"1注文金額上限超過 (注文額: ¥{notional:,.0f} > 上限: ¥{cap_order_notional:,.0f})"
                )
            # 2) 1日の総発注回数上限
            elif self._daily_order_count >= cap_order_count:
                cap_blocked_reason = (
                    f"1日発注回数上限到達 (本日: {self._daily_order_count}回 >= 上限: {cap_order_count}回)"
                )
            # 3) 1日の総約定代金上限
            elif notional_valid and (self._daily_turnover + notional) > cap_turnover:
                cap_blocked_reason = (
                    f"1日約定代金上限超過 (累計: ¥{self._daily_turnover:,.0f} + 注文: ¥{notional:,.0f} "
                    f"> 上限: ¥{cap_turnover:,.0f})"
                )
            # 4) 同時建玉総額上限 (建玉総額が算出できなければスキップ)
            elif notional_valid:
                current_position_value = 0.0
                position_value_computed = False
                try:
                    for pos in self.app_state.get("positions", []) or []:
                        pos_price = pos.get("avg_price", pos.get("entry", 0)) or 0
                        pos_qty = pos.get("qty", 0) or 0
                        current_position_value += float(pos_price) * float(pos_qty)
                    position_value_computed = True
                except (TypeError, ValueError):
                    position_value_computed = False
                if position_value_computed and (current_position_value + notional) > cap_total_position:
                    cap_blocked_reason = (
                        f"同時建玉総額上限超過 (現建玉: ¥{current_position_value:,.0f} + 注文: ¥{notional:,.0f} "
                        f"> 上限: ¥{cap_total_position:,.0f})"
                    )

            if cap_blocked_reason:
                msg = f"🛑 発注ハードキャップ: {symbol} 買い注文をブロック — {cap_blocked_reason}"
                self._log(msg, "WARNING")
                logger.warning(f"[Trading] {msg}")
                notifier = self.app_state.get("notifier")
                if notifier and getattr(notifier, "is_configured", False):
                    try:
                        await notifier.send_system_alert(msg, "WARNING")
                    except Exception as e:
                        logger.error(f"[Trading] Cap-block alert failed: {e}")
                return False

        try:
            # 1. Send Order to API
            # 실매매: 성행(Market) 주문, 시뮬레이션: 지정가(Limit)
            if is_live:
                front_order_type = 10  # 10: Market (成行)
                order_price = 0.0  # 성행은 가격 0
            else:
                front_order_type = 20  # 20: Limit (指値)
                order_price = float(price)
            
            # 現物売: DelivType=0, FundType="  " / 現物買: DelivType=2, FundType="AA"
            if side == "SELL":
                order_deliv_type = 0    # 指定なし (現物売)
                order_fund_type = "  "  # 半角スペース2つ (現物売)
            else:
                order_deliv_type = 2    # 預り金 (現物買)
                order_fund_type = "AA"  # 自動振替 (現物買)
            
            order_schema = OrderSchema(
                symbol=symbol,
                side="2" if side == "BUY" else "1",
                qty=int(qty),
                price=order_price,
                front_order_type=front_order_type,
                fund_type=order_fund_type,
                deliv_type=order_deliv_type,
            )
            
            mode_tag = "🔴 LIVE" if is_live else "SIM"
            self._log(f"[{mode_tag}] Sending {side}: {symbol} qty={qty} " +
                      (f"成行" if is_live else f"@¥{price:,.0f}"))
            
            result = await client.send_order(order_schema)
            
            if result.get("Result") == 0:
                order_id = result.get("OrderId", "")
                self._log(f"[{mode_tag}] Order Sent: {symbol} {side} {qty}@{price}")
                
                trade_record = TradeRecord(
                    id=None,
                    symbol=symbol,
                    symbol_name=params.get("name", symbol),
                    side=side,
                    price=price,
                    qty=qty,
                    strategy_name=strategy_name,
                    timestamp=datetime.now(),
                    order_id=order_id,
                    status="FILLED",
                    realized_pnl=params.get("realized_pnl", 0.0),
                    extraction_strategy=extraction_strategy,
                    target_universe=target_universe,
                    buy_rank=buy_rank,
                )
                
                self.db.add_trade(trade_record)
                self._log(f"[{mode_tag}] Trade saved to DB: {order_id}")
                
                # 실매매: 텔레그램 실시간 알림
                if is_live:
                    notifier = self.app_state.get("notifier")
                    if notifier and notifier.is_configured:
                        alert = TradeAlert(
                            symbol=symbol,
                            symbol_name=params.get("name", symbol),
                            side=side,
                            qty=qty,
                            price=price,
                            status="FILLED",
                            strategy=strategy_name,
                            timestamp=datetime.now(),
                        )
                        try:
                            await notifier.send_trade_alert(alert)
                        except Exception as e:
                            logger.error(f"[Trading] Telegram alert failed: {e}")
                
                # 일일 손익 누적 (매도 시)
                if is_live and side == "SELL":
                    realized_pnl = params.get("realized_pnl", 0.0)
                    today = datetime.now().strftime("%Y-%m-%d")
                    if self._daily_pnl_date != today:
                        self._daily_realized_pnl = 0.0
                        self._daily_pnl_date = today
                    self._daily_realized_pnl += realized_pnl
                    self._log(
                        f"[{mode_tag}] 일일 누적 손익: ¥{self._daily_realized_pnl:+,.0f}"
                    )

                # 口座レベル発注ハードキャップ: 発注成功時のみ買いカウンタ加算
                if side == "BUY":
                    try:
                        cap_notional = float(qty) * float(price)
                    except (TypeError, ValueError):
                        cap_notional = 0.0
                    self._daily_order_count += 1
                    if cap_notional > 0:
                        self._daily_turnover += cap_notional
                return True
            else:
                error_msg = result.get("Message", "Unknown error")
                self._log(f"[{mode_tag}] Order REJECTED: {symbol} {side} — {error_msg}", "ERROR")
                return False
                
        except Exception as e:
            self._log(f"Order execution failed: {e}", "ERROR")
            return False
