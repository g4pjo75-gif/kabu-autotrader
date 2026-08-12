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
        # --- 가격 스파이크 필터 (Board API 비정상 가격 방지) ---
        self._prev_prices: Dict[str, float] = {}      # 종목별 이전 주기 가격
        self._spike_count: Dict[str, int] = {}         # 종목별 급락 횟수 추적
        self._SPIKE_CONFIRM_COUNT = 3                  # 3회 연속 확인 시 정상 가격으로 인정
        # --- 매도 주문 거절 추적 (무한 재시도 방지) ---
        self._sell_reject_count: Dict[str, int] = {}   # 종목별 연속 매도 거절 횟수
        self._SELL_REJECT_MAX = 3                      # 3회 연속 거절 시 재시도 중단

    def _validate_price(self, symbol: str, new_price: float) -> tuple:
        """
        가격 스파이크 필터.
        
        Board API가 특별기배/연속약정기배 등의 상황에서 비정상적인 가격을 반환할 수 있다.
        이전 주기 대비 급격한 가격 변동을 감지하고, 연속 확인될 때까지 '비신뢰'로 표시한다.
        
        Returns:
            (validated_price, is_reliable)
            - validated_price: 사용할 가격 (항상 new_price를 반환)
            - is_reliable: False이면 트레일링 스탑 고점 업데이트에 사용하지 않음
        """
        prev_price = self._prev_prices.get(symbol)
        
        # 첫 가격이면 그대로 신뢰
        if prev_price is None or prev_price <= 0:
            self._prev_prices[symbol] = new_price
            self._spike_count[symbol] = 0
            return new_price, True
        
        change_pct = abs(new_price - prev_price) / prev_price * 100
        
        spike_threshold = float(self.app_state.get("spike_threshold_pct", 1.5))
        if change_pct > spike_threshold:
            # 스파이크 감지: 카운트 증가
            self._spike_count[symbol] = self._spike_count.get(symbol, 0) + 1
            
            if self._spike_count[symbol] < self._SPIKE_CONFIRM_COUNT:
                # 아직 확인 안 됨 → 가격은 사용하되 고점 갱신은 방지
                logger.warning(
                    f"[Trading] ⚠️ {symbol}: 가격 스파이크 감지 "
                    f"(이전={prev_price:.0f} → 현재={new_price:.0f}, "
                    f"변동={change_pct:.2f}%, "
                    f"확인 {self._spike_count[symbol]}/{self._SPIKE_CONFIRM_COUNT})"
                )
                return new_price, False  # 가격은 사용하되 고점 갱신은 방지
            else:
                # N회 연속 같은 수준 → 정상 가격으로 인정
                logger.info(
                    f"[Trading] ✅ {symbol}: 가격 변동 확인 완료 "
                    f"({prev_price:.0f} → {new_price:.0f}, {self._SPIKE_CONFIRM_COUNT}회 연속 확인)"
                )
                self._spike_count[symbol] = 0
                self._prev_prices[symbol] = new_price
                return new_price, True
        else:
            # 정상 변동 범위
            self._spike_count[symbol] = 0
            self._prev_prices[symbol] = new_price
            return new_price, True

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
            
            # 봇의 설정된 계좌 및 거래 방식
            bot_account = int(self.app_state.get("account_type", 4))
            bot_margin = int(self.app_state.get("cash_margin", 1))
            
            for p in raw_positions:
                # 봇이 관리하지 않는 포지션(타 계좌, 신용 등) 무시
                p_account = int(p.get("AccountType", 4))
                p_security = int(p.get("SecurityType", 1))
                if p_account != bot_account or p_security != bot_margin:
                    continue
                    
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
                logger.warning(f"[Trading] Skip sell check for {symbol}: price={current_price}")
                continue
            
            # --- 가격 스파이크 필터 적용 ---
            validated_price, is_reliable = self._validate_price(symbol, current_price)
            
            entry_price = pos.get("avg_price", 0)
            pos_qty = pos.get("qty", 0)
            pnl_pct = ((current_price - entry_price) / entry_price * 100) if entry_price > 0 else 0
            reliability_tag = "" if is_reliable else " ⚠️SPIKE"
            logger.info(f"[Trading] Position {symbol}: entry={entry_price:.0f}, current={current_price:.0f}, pnl={pnl_pct:+.2f}%, qty={pos_qty}{reliability_tag}")
            
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
            # Priority: SteppedTrailing (if enabled) > TakeProfit > TrailingStop > DynamicLossCut
            sell_strategies = []
            
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
            sell_strategies.append(
                DynamicLossCutManager(loss_cut_percent=lc_pct, time_stop_minutes=time_stop_mins)
            )
            
            # --- 비신뢰 가격일 때 트레일링 스탑 고점 보호 ---
            # 스파이크 가격이 고점을 갱신하지 않도록, 평가 전에 현재 고점을 저장
            saved_high_trailing = None
            saved_high_stepped = None
            if not is_reliable:
                saved_high_trailing = TrailingStopManager._high_prices.get(symbol)
                saved_high_stepped = SteppedTrailingManager._high_prices.get(symbol)
            
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
            
            # --- 비신뢰 가격에 의한 고점 갱신 롤백 ---
            if not is_reliable:
                # 트레일링 스탑이 발동하지 않았으면, 스파이크 가격에 의한 고점 갱신을 원복
                if not (triggered_strategy and isinstance(triggered_strategy, (TrailingStopManager, SteppedTrailingManager))):
                    if saved_high_trailing is not None:
                        TrailingStopManager._high_prices[symbol] = saved_high_trailing
                        logger.debug(f"[Trading] {symbol}: TrailingStop 고점 롤백 → {saved_high_trailing:.0f} (스파이크 가격 무시)")
                    elif symbol in TrailingStopManager._high_prices:
                        # 스파이크로 인해 새로 생성된 고점 삭제
                        del TrailingStopManager._high_prices[symbol]
                    
                    if saved_high_stepped is not None:
                        SteppedTrailingManager._high_prices[symbol] = saved_high_stepped
                        logger.debug(f"[Trading] {symbol}: SteppedTrailing 고점 롤백 → {saved_high_stepped:.0f} (스파이크 가격 무시)")
                    elif symbol in SteppedTrailingManager._high_prices:
                        del SteppedTrailingManager._high_prices[symbol]
            
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
                    order_params["avg_price"] = avg_price
                    # Fix #4: Preserve symbol_name for DB recording
                    order_params["name"] = getattr(board, 'symbol_name', pos.get("name", symbol))
                    
                    self._log(f"Executing SELL: {symbol} qty={qty}, price={sell_price:.0f}, pnl={pnl:+,.0f}")
                    
                    # 매도 거절 횟수 체크 — 무한 재시도 방지
                    reject_count = self._sell_reject_count.get(symbol, 0)
                    if reject_count >= self._SELL_REJECT_MAX:
                        # 무한 텔레그램 발송 방지를 위해 카운터 계속 증가
                        self._sell_reject_count[symbol] = reject_count + 1
                        
                        # 최대 5회까지만 텔레그램 경고 발송
                        if reject_count < self._SELL_REJECT_MAX + 5:
                            self._log(
                                f"🚨 {symbol} 매도 주문 {reject_count}회 연속 거절! 재시도 중단. "
                                f"증권사 앱에서 수동 매도 필요!", "ERROR"
                            )
                            # 텔레그램 긴급 알림
                            notifier = self.app_state.get("notifier")
                            if notifier and notifier.is_configured:
                                asyncio.create_task(notifier.send_system_alert(
                                    f"🚨 매도 주문 연속 거절!\n"
                                    f"종목: {symbol}\n"
                                    f"상태: 자동 매도 중단 (수동 처리 요망)\n"
                                    f"이 알림은 최대 5회까지만 발송됩니다.",
                                    "ERROR"
                                ))
                        continue
                    
                    ext_strategy = self._symbol_extraction_map.get(symbol, "")
                    target_universe = self._symbol_universe_map.get(symbol, "")
                    buy_rank = self._symbol_rank_map.get(symbol, 0)
                    success = await self._execute_order(client, order_params, "SELL", triggered_strategy.name, ext_strategy, target_universe, buy_rank)
                    if success:
                        sold_this_cycle.add(symbol)
                        self._sell_reject_count.pop(symbol, None)  # 성공 시 거절 카운터 리셋
                        
                        # Reset trailing stop tracking for this symbol
                        TrailingStopManager.reset_tracking(symbol)
                        SteppedTrailingManager.reset_tracking(symbol)
                        # 스파이크 필터 추적도 리셋
                        self._prev_prices.pop(symbol, None)
                        self._spike_count.pop(symbol, None)
                    else:
                        # 매도 실패 시 거절 카운터 증가
                        self._sell_reject_count[symbol] = reject_count + 1
                        self._log(
                            f"⚠️ {symbol} 매도 거절 ({reject_count + 1}/{self._SELL_REJECT_MAX}회)", "WARNING"
                        )
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
            
            # --- 매수 측 가격 스파이크 필터 ---
            validated_price, is_reliable = self._validate_price(symbol, current_price)
            if not is_reliable:
                logger.warning(
                    f"[Trading] {symbol}: 매수 스킵 (가격 스파이크 미확인, "
                    f"다음 사이클에서 재시도)"
                )
                continue
            
            # VWAP 전략 파라미터를 개별 전략 설정(config_json)에서 가져오기
            config_id = stock.get("strategy_id")
            automation_service = self.app_state.get("automation_service")
            strategy_config = None
            if automation_service and config_id:
                strategy_config = automation_service.get_config(config_id)
            
            cfg = strategy_config.config_json if strategy_config else {}
            
            vwap_upper = float(cfg.get("vwap_upper_band", self.app_state.get("vwap_upper_band", 1.5)))
            vwap_lower = float(cfg.get("vwap_lower_band", self.app_state.get("vwap_lower_band", 1.5)))
            vwap_bounce = float(cfg.get("vwap_bounce_ratio", self.app_state.get("vwap_bounce_ratio", 20.0)))
            vwap_max_pullback = float(cfg.get("max_pullback_pct", self.app_state.get("max_pullback_pct", 5.0)))
            vwap_min_pullback = float(cfg.get("min_pullback_pct", self.app_state.get("min_pullback_pct", 1.2)))
            vwap_bounce_wait_minutes = float(cfg.get("vwap_bounce_wait_minutes", self.app_state.get("vwap_bounce_wait_minutes", 2.0)))
            vwap_abs_bounce = float(cfg.get("vwap_absolute_min_bounce_pct", 0.8)) # Default 0.8% for backward compat
            vwap_breakdown_limit = float(cfg.get("vwap_breakdown_limit_pct", 1.0)) # Default 1.0%

            min_intraday_range_pct = float(self.app_state.get("min_intraday_range_pct", 1.2))

            self._vwap_strategy.set_param("vwap_upper_band", vwap_upper)
            self._vwap_strategy.set_param("vwap_lower_band", vwap_lower)
            self._vwap_strategy.set_param("vwap_bounce_ratio", vwap_bounce)
            self._vwap_strategy.set_param("min_pullback_pct", vwap_min_pullback)
            self._vwap_strategy.set_param("max_pullback_pct", vwap_max_pullback)
            self._vwap_strategy.set_param("bounce_wait_minutes", vwap_bounce_wait_minutes)
            self._vwap_strategy.set_param("absolute_min_bounce_pct", vwap_abs_bounce)
            self._vwap_strategy.set_param("breakdown_limit_pct", vwap_breakdown_limit)
            self._vwap_strategy.set_param("min_intraday_range_pct", min_intraday_range_pct)
            
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
                vwap_bounce = float(self.app_state.get("vwap_bounce_ratio", 30.0))
                vwap_max_pullback = float(self.app_state.get("max_pullback_pct", 5.0))
                vwap_min_pullback = float(self.app_state.get("min_pullback_pct", 1.5))
                vwap_bounce_wait_minutes = float(self.app_state.get("vwap_bounce_wait_minutes", 3.0))
                min_intraday_range_pct = float(self.app_state.get("min_intraday_range_pct", 1.2))
                
                self._vwap_strategy.set_param("vwap_upper_band", vwap_upper)
                self._vwap_strategy.set_param("vwap_lower_band", vwap_lower)
                self._vwap_strategy.set_param("vwap_bounce_ratio", vwap_bounce)
                self._vwap_strategy.set_param("min_pullback_pct", vwap_min_pullback)
                self._vwap_strategy.set_param("max_pullback_pct", vwap_max_pullback)
                self._vwap_strategy.set_param("bounce_wait_minutes", vwap_bounce_wait_minutes)
                self._vwap_strategy.set_param("min_intraday_range_pct", min_intraday_range_pct)
                
                # Real-time evaluation (VWAP, etc.)
                # 증권사 API의 당일 전체 누적 VWAP과 당일 최고가를 최우선으로 사용하여 오전 데이터 누락 방지
                vwap = getattr(board, 'vwap', 0.0) if getattr(board, 'vwap', 0.0) > 0 else vwap_state.vwap
                vwap_history = getattr(vwap_state, "vwap_history", [])
                
                result = self._vwap_strategy.evaluate_realtime(
                    symbol=symbol,
                    current_price=current_price,
                    open_price=getattr(board, 'open_price', 0) or vwap_state.open_price,
                    day_high=getattr(board, 'high_price', 0) or vwap_state.day_high,
                    vwap=vwap,
                    recent_low=vwap_state.pullback_low,
                    recent_prices=vwap_state.recent_prices,
                    vwap_history=vwap_history,
                    market_trend=self._market_trend,
                    vwap_state=vwap_state
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
                    fail_reasons = result.details.get("fail_reasons", [])
                    fail_summary = ", ".join(fail_reasons) if fail_reasons else "unknown"
                    logger.info(
                        f"[Trading] {symbol}: VWAP 미충족 [{fail_summary}] "
                        f"(price={current_price:.0f}, VWAP={vwap_state.vwap:.0f}, "
                        f"high={result.details.get('day_high', 0)}, low={result.details.get('recent_low', 0)})"
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
                
                # 심층 붕괴(Drawdown) 판단을 위한 pullback_low 전달
                # bar_accumulator가 수집한 현재 종목의 상태 정보를 가져옴
                vwap_state = None
                if accumulator:
                    vwap_state = accumulator.get_vwap_state(symbol)
                pullback_low = getattr(vwap_state, "pullback_low", 0.0) if vwap_state else 0.0
                
                result = self._breakout_strategy.evaluate_realtime(
                    symbol=symbol,
                    current_price=current_price,
                    open_price=open_price,
                    day_high=prev_high,
                    cumulative_volume=cumulative_volume,
                    market_trend=self._market_trend,
                    pullback_low=pullback_low
                )
                
                # 평가 이후 이전 최고가 업데이트 (현재 고가와 현재가 중 최대값으로 업데이트)
                # 스파이크 가격일 경우 이전 최고가를 보호 (current_price 제외)
                if is_reliable:
                    self._prev_day_highs[symbol] = max(prev_high, high_price, current_price)
                else:
                    self._prev_day_highs[symbol] = max(prev_high, high_price)
                    logger.debug(f"[Trading] {symbol}: 고가돌파 고점 업데이트에서 스파이크 가격 제외 (current_price={current_price:.0f})")
                
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
        
        try:
            # 1. Send Order to API
            # 실매매: 하이브리드 주문 (지정가 → 5분 후 미체결 시 성행 전환)
            # 시뮬레이션: 지정가(Limit)
            if is_live:
                front_order_type = 20  # 20: Limit (指値) — 먼저 지정가로 시도
                order_price = float(price)
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
                      (f"指値@¥{order_price:,.0f}" if is_live else f"@¥{price:,.0f}"))
            
            result = await client.send_order(order_schema)
            
            if result.get("Result") == 0:
                order_id = result.get("OrderId", "")
                self._log(f"[{mode_tag}] Order Sent: {symbol} {side} {qty}@{price}")
                
                # 실매매: 하이브리드 주문 — 지정가 체결 대기 후 미체결 시 성행 전환
                # 매수: 지정가 대기 (유리한 가격에 체결될 때까지 여유 있게 대기)
                # 매도: 지정가 대기 (손절/익절 시 빠르게 체결해야 하므로 짧게)
                if side == "SELL":
                    hybrid_timeout = int(self.app_state.get("hybrid_sell_timeout_sec", 60))
                else:
                    hybrid_timeout = int(self.app_state.get("hybrid_buy_timeout_sec", 300))
                final_price = price
                if is_live:
                    filled = await self._wait_for_fill_or_convert_market(
                        client=client,
                        order_id=order_id,
                        symbol=symbol,
                        side=side,
                        qty=qty,
                        price=price,
                        order_deliv_type=order_deliv_type,
                        order_fund_type=order_fund_type,
                        timeout_seconds=hybrid_timeout,
                    )
                    if not filled:
                        self._log(f"[{mode_tag}] Hybrid order failed: {symbol} {side} — 체결 실패", "ERROR")
                        return False
                
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
                
                # 실매매/시뮬레이션 모두 텔레그램 실시간 알림
                notifier = self.app_state.get("notifier")
                if notifier and notifier.is_configured:
                    mode_prefix = "" if is_live else "[SIM] "
                    alert = TradeAlert(
                        symbol=symbol,
                        symbol_name=f"{mode_prefix}{params.get('name', symbol)}",
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
                
                # 실매매: 체결가 조회 및 DB 업데이트 (비동기)
                if is_live:
                    asyncio.create_task(
                        self._update_live_execution(
                            client=client,
                            order_id=order_id,
                            symbol=symbol,
                            side=side,
                            qty=qty,
                            params=params,
                        )
                    )
                    
                return True
            else:
                error_msg = result.get("Message", "Unknown error")
                self._log(f"[{mode_tag}] Order REJECTED: {symbol} {side} — {error_msg}", "ERROR")
                return False
                
        except Exception as e:
            self._log(f"Order execution failed: {e}", "ERROR")
            return False

    async def _wait_for_fill_or_convert_market(
        self, client, order_id: str, symbol: str, side: str, qty: int, price: float,
        order_deliv_type: int, order_fund_type: str, timeout_seconds: int = 300,
    ) -> bool:
        """
        하이브리드 주문: 지정가 체결 대기 → 타임아웃 시 성행 전환.
        
        지정가 주문을 넣은 후, 30초 간격으로 체결 여부를 확인합니다.
        timeout_seconds(기본 5분) 내에 체결되지 않으면:
          1. 기존 지정가 주문을 취소
          2. 성행(Market) 주문으로 재주문
        
        Returns:
            True: 체결 성공 (지정가 또는 성행)
            False: 체결 실패
        """
        check_interval = 30  # 30초 간격으로 체결 확인
        elapsed = 0
        
        self._log(f"[🔴 LIVE] {symbol} {side} 지정가 @¥{price:,.0f} 체결 대기 시작 (최대 {timeout_seconds}초)")
        
        last_order = None
        while elapsed < timeout_seconds:
            await asyncio.sleep(check_interval)
            elapsed += check_interval
            
            try:
                # 주문 상태 조회
                orders = await client.get_orders()
                order = next((o for o in orders if str(o.get("OrderId")) == str(order_id)), None)
                
                if not order:
                    # 주문을 찾지 못한 경우 — 포지션 API로 실제 체결 여부 확인
                    try:
                        positions = await client.get_positions()
                        still_holding = any(
                            str(p.get("Symbol", "")) == str(symbol) and int(p.get("LeavesQty", 0)) > 0
                            for p in positions
                        )
                        if not still_holding:
                            self._log(f"[🔴 LIVE] {symbol} {side} 체결 완료 확인 (주문 조회 불가 + 포지션 없음)")
                            return True
                        else:
                            self._log(f"[🔴 LIVE] {symbol} {side} 주문 조회 불가하나 포지션 잔존 — 미체결로 판단", "WARNING")
                            # 포지션이 남아있으면 체결 안 된 것 → 타임아웃 로직으로 빠짐
                            break
                    except Exception as pos_e:
                        logger.error(f"[Hybrid] 포지션 확인 중 오류: {pos_e}")
                        # 포지션 확인 실패 시 안전하게 미체결로 판단
                        break
                
                last_order = order
                order_state = order.get("State", 0)
                # kabu API State: 1=대기, 2=처리중, 3=처리완료, 4=정정취소대기, 5=주문완료, 6=취소완료
                
                if order_state == 5:  # 체결 완료
                    self._log(f"[🔴 LIVE] {symbol} {side} 지정가 @¥{price:,.0f} 체결 완료! ({elapsed}초 경과)")
                    return True
                elif order_state == 6:  # 이미 취소됨 (외부 취소)
                    self._log(f"[🔴 LIVE] {symbol} {side} 주문이 외부에서 취소됨", "WARNING")
                    return False
                else:
                    # 미체결 — 대기 계속
                    self._log(f"[🔴 LIVE] {symbol} {side} 지정가 미체결 대기 중... ({elapsed}/{timeout_seconds}초)")
                    
            except Exception as e:
                logger.error(f"[Hybrid] 체결 확인 중 오류: {e}")
                # 오류 시 다음 체크까지 대기 계속
                continue
        
        # === 타임아웃: 지정가 취소 → 성행 전환 ===
        unfilled_qty = int(qty)
        if last_order:
            cum_qty = int(last_order.get("CumQty", 0))
            unfilled_qty = int(qty) - cum_qty
            
        if unfilled_qty <= 0:
            self._log(f"[🔴 LIVE] {symbol} {side} 지정가 전량 체결 완료 확인 (타임아웃 시점)")
            return True
            
        self._log(f"[🔴 LIVE] {symbol} {side} 지정가 미체결 ({timeout_seconds}초 초과) → 잔량 {unfilled_qty}주 성행 전환 시작")
        
        try:
            # 1. 기존 지정가 주문 취소
            cancel_result = await client.cancel_order(order_id)
            if cancel_result.get("Result") == 0:
                self._log(f"[🔴 LIVE] {symbol} {side} 지정가 주문 취소 완료 (OrderId: {order_id})")
            else:
                cancel_msg = cancel_result.get("Message", "Unknown")
                self._log(f"[🔴 LIVE] {symbol} {side} 지정가 취소 실패: {cancel_msg}", "WARNING")
                # 취소 실패 시 — 이미 체결되었을 가능성이 있으므로 True 반환
                return True
            
            await asyncio.sleep(1.0)  # 취소 처리 대기
            
            # 2. 성행(Market) 주문으로 재주문
            market_schema = OrderSchema(
                symbol=symbol,
                side="2" if side == "BUY" else "1",
                qty=unfilled_qty,
                price=0.0,  # 성행은 가격 0
                front_order_type=10,  # 10: Market (成行)
                fund_type=order_fund_type,
                deliv_type=order_deliv_type,
            )
            
            self._log(f"[🔴 LIVE] {symbol} {side} 성행 전환 주문 발송")
            market_result = await client.send_order(market_schema)
            
            if market_result.get("Result") == 0:
                new_order_id = market_result.get("OrderId", "")
                self._log(f"[🔴 LIVE] {symbol} {side} 성행 주문 체결 완료 (OrderId: {new_order_id})")
                return True
            else:
                error_msg = market_result.get("Message", "Unknown error")
                self._log(f"[🔴 LIVE] {symbol} {side} 성행 주문 실패: {error_msg}", "ERROR")
                
                # 하한가 지정가 우회 (성행 금지 종목 대응)
                if side == "SELL":
                    self._log(f"[🔴 LIVE] {symbol} {side} 성행 주문 거절됨. 하한가 지정가 우회 주문 시도...")
                    try:
                        board = await client.get_board(symbol)
                        lower_limit = getattr(board, 'lower_limit', 0.0)
                        if lower_limit > 0:
                            fallback_schema = OrderSchema(
                                symbol=symbol,
                                side="1", # SELL
                                qty=unfilled_qty,
                                price=lower_limit,
                                front_order_type=20,  # 20: Limit (지정가)
                                fund_type=order_fund_type,
                                deliv_type=order_deliv_type,
                            )
                            fb_result = await client.send_order(fallback_schema)
                            if fb_result.get("Result") == 0:
                                self._log(f"[🔴 LIVE] {symbol} {side} 하한가 우회 주문 접수 완료 (OrderId: {fb_result.get('OrderId', '')})")
                                return True
                            else:
                                self._log(f"[🔴 LIVE] {symbol} {side} 하한가 우회 주문 실패: {fb_result.get('Message', '')}", "ERROR")
                        else:
                            self._log(f"[🔴 LIVE] {symbol} 하한가 정보를 가져올 수 없어 우회 불가", "WARNING")
                    except Exception as fe:
                        self._log(f"[🔴 LIVE] {symbol} 하한가 우회 시도 중 오류: {fe}", "ERROR")
                        
                return False
                
        except Exception as e:
            self._log(f"[Hybrid] 성행 전환 중 오류: {e}", "ERROR")
            return False

    async def _update_live_execution(self, client, order_id: str, symbol: str, side: str, qty: int, params: Dict):
        """실매매 성행 주문 후 실제 체결가를 조회하여 DB를 업데이트합니다."""
        await asyncio.sleep(2.0)  # 체결 대기
        try:
            executed_price = 0.0
            
            # 1. 매수: 포지션에서 확인 (성행 체결 후 포지션에 반영됨)
            if side == "BUY":
                positions = await client.get_positions()
                pos = next((p for p in positions if p.get("Symbol") == symbol), None)
                if pos and pos.get("Price", 0) > 0:
                    executed_price = float(pos.get("Price"))
                    
            # 2. 매도: (또는 포지션에서 못 찾은 경우) 주문 내역에서 확인
            if executed_price <= 0:
                orders = await client.get_orders()
                order = next((o for o in orders if o.get("OrderId") == order_id), None)
                if order:
                    details = order.get("Details", [])
                    if details and details[0].get("Price"):
                        executed_price = float(details[0].get("Price"))
            
            if executed_price > 0:
                self._log(f"[🔴 LIVE] {symbol} {side} 실제 체결가 확인: ¥{executed_price:,.0f} (주문가: ¥{params.get('price', 0):,.0f})")
                
                # 매도인 경우 PNL 재계산
                new_pnl = None
                if side == "SELL":
                    avg_price = float(params.get("avg_price", 0))
                    if avg_price > 0:
                        new_pnl = (executed_price - avg_price) * qty
                        # 누적 손익 보정 (기존 추정 pnl을 빼고 새 pnl 더하기)
                        old_pnl = float(params.get("realized_pnl", 0))
                        today = datetime.now().strftime("%Y-%m-%d")
                        if self._daily_pnl_date == today:
                            self._daily_realized_pnl = self._daily_realized_pnl - old_pnl + new_pnl
                            self._log(f"[🔴 LIVE] 일일 누적 손익 보정: 확정 P&L ¥{new_pnl:+,.0f} (오차: ¥{new_pnl - old_pnl:+,.0f}) → 누적: ¥{self._daily_realized_pnl:+,.0f}")
                
                # DB 업데이트
                self.db.update_trade_price(order_id, executed_price, new_pnl)
        except Exception as e:
            logger.error(f"[_update_live_execution] Failed to update execution price for {symbol}: {e}")
