# -*- coding: utf-8 -*-
"""
Automation Service Module

Manages multiple daily automation routines with persistent configurations.
- Checks US market condition
- Runs analysis per strategy
- Updates target list per strategy
- Starts trading

Enhanced with detailed logging for debugging.
"""
import asyncio
from typing import Dict, Any, List, Optional
from datetime import datetime
import yfinance as yf
import logging

from backend.database import Database, AutomationConfig, AnalysisCandidate, ExtractionLogEntry

logger = logging.getLogger(__name__)

# Default config template for new strategies
DEFAULT_CONFIG = {
    "target_universe": "nikkei225",
    "extraction_strategy": "SMAGoldenDeadCross",
    "max_stocks": 3,
    "market_safety_filter": False,
    "sp500_threshold": 1.0,
    "nasdaq_threshold": 1.5,
    "nikkei_gap_threshold": 1.5,
    "start_time": "09:00",
    "extraction_end_time": "11:00",
    "extraction_interval": 120,
    "end_time": "15:00",
}

# Circuit breaker: stop the trading loop after this many consecutive failed
# cycles to prevent runaway execution when the API is unhealthy.
MAX_CONSECUTIVE_ERRORS = 5


class AutomationService:
    """
    Manages daily automation routines with support for multiple strategies.
    Each strategy has its own configuration stored in the database.
    """
    def __init__(self, app_state: Dict[str, Any]):
        self.app_state = app_state
        self.db: Database = app_state.get("database") or Database()
        
        # In-memory cache of configs: Dict[config_id, AutomationConfig]
        self.configs: Dict[int, AutomationConfig] = {}
        
        # Circuit breaker state: consecutive failed trading cycles.
        self._consecutive_errors = 0

        # Load configs from DB
        self._load_configs()

    def _log_to_dashboard(self, message: str, level: str = "INFO"):
        """Log to console and app_state for UI"""
        from datetime import datetime
        timestamp = datetime.now().strftime("%H:%M:%S")
        logger.info(f"[{level}] {message}")
        
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
    
    def _load_configs(self):
        """Load all automation configs from database into memory"""
        try:
            db_configs = self.db.get_automation_configs()
            self.configs = {c.id: c for c in db_configs}
            logger.info(f"[Automation] Loaded {len(self.configs)} strategies from DB")
        except Exception as e:
            logger.error(f"[Automation] Failed to load configs: {e}")
            self.configs = {}
    
    def get_all_configs(self) -> List[AutomationConfig]:
        """Get all automation configurations sorted by sort_order and id"""
        configs = list(self.configs.values())
        return sorted(configs, key=lambda c: (c.sort_order, c.id))
    
    def get_config(self, config_id: int) -> Optional[AutomationConfig]:
        """Get a single config by ID"""
        return self.configs.get(config_id)
    
    def save_config(self, name: str, config_data: Dict[str, Any], config_id: Optional[int] = None, is_active: bool = True) -> int:
        """
        Save or update an automation configuration.
        Returns the config ID.
        """
        config = AutomationConfig(
            id=config_id,
            name=name,
            config_json=config_data,
            is_active=is_active,
        )
        
        saved_id = self.db.save_automation_config(config)
        
        # Refresh memory cache
        saved_config = self.db.get_automation_config(saved_id)
        if saved_config:
            self.configs[saved_id] = saved_config
        
        logger.info(f"[Automation] Saved config '{name}' (ID: {saved_id})")
        return saved_id
    
    def delete_config(self, config_id: int):
        """Delete an automation configuration"""
        self.db.delete_automation_config(config_id)
        if config_id in self.configs:
            del self.configs[config_id]
        
        # Remove scheduled jobs for this config
        self._unschedule_config_jobs(config_id)
        logger.info(f"[Automation] Deleted config ID: {config_id}")
    
    def toggle_config(self, config_id: int, is_active: bool):
        """Toggle the active state of a config"""
        self.db.toggle_automation_config(config_id, is_active)
        if config_id in self.configs:
            self.configs[config_id].is_active = is_active
        
        # Re-schedule or unschedule
        if is_active:
            self._schedule_config_jobs(config_id)
        else:
            self._unschedule_config_jobs(config_id)
        
        logger.info(f"[Automation] Config {config_id} is_active: {is_active}")

    def move_config(self, config_id: int, direction: str):
        """Move a config up or down in the list"""
        configs = self.get_all_configs()
        # Find index of target config
        idx = next((i for i, c in enumerate(configs) if c.id == config_id), -1)
        if idx == -1:
            return

        target_idx = -1
        if direction == "up" and idx > 0:
            target_idx = idx - 1
        elif direction == "down" and idx < len(configs) - 1:
            target_idx = idx + 1
            
        if target_idx != -1:
            # Swap
            configs[idx], configs[target_idx] = configs[target_idx], configs[idx]
            
            # Update order in DB
            config_ids = [c.id for c in configs]
            self.db.update_automation_config_order(config_ids)
            
            # Refresh memory cache from DB
            self._load_configs()
            logger.info(f"[Automation] Moved config {config_id} {direction}")

    async def check_market_safety(self, config_data: Dict[str, Any]) -> bool:
        """
        Unified market safety check.
        Checks S&P 500, NASDAQ (previous day), and Nikkei 225 gap (pre-computed).
        Returns True if SAFE to trade, False if DANGEROUS.
        
        Any ONE condition triggered = halt new buys.
        """
        # Check legacy config key for backward compatibility
        filter_enabled = config_data.get("market_safety_filter",
                         config_data.get("us_market_filter", False))
        if not filter_enabled:
            logger.info("[Automation] Market Safety Filter: DISABLED")
            return True, []

        sp500_threshold = float(config_data.get("sp500_threshold",
                               config_data.get("us_market_threshold", 1.0)))
        nasdaq_threshold = float(config_data.get("nasdaq_threshold", 1.5))
        nikkei_gap_threshold = float(config_data.get("nikkei_gap_threshold", 1.5))

        safe = True
        triggered_reasons = []

        # --- 1. US Market Check (S&P 500 + NASDAQ) ---
        try:
            logger.info(f"[Automation] Checking US Market (S&P500 -{sp500_threshold}%, NASDAQ -{nasdaq_threshold}%)...")
            tickers = ["^GSPC", "^IXIC"]
            data = yf.download(tickers, period="5d", progress=False)

            if not data.empty:
                closes = data["Close"]

                # S&P 500
                if "^GSPC" in closes.columns:
                    series = closes["^GSPC"].dropna()
                    if len(series) >= 2:
                        prev_close = series.iloc[-2]
                        last_close = series.iloc[-1]
                        pct_change = (last_close - prev_close) / prev_close * 100
                        logger.info(f"[Automation] S&P 500: {pct_change:.2f}%")
                        if pct_change < -sp500_threshold:
                            reason = f"S&P 500 {pct_change:.2f}% 하락 (기준: -{sp500_threshold}%)"
                            self._log_to_dashboard(f"🔴 {reason}", "WARNING")
                            triggered_reasons.append(reason)
                            safe = False

                # NASDAQ
                if "^IXIC" in closes.columns:
                    series = closes["^IXIC"].dropna()
                    if len(series) >= 2:
                        prev_close = series.iloc[-2]
                        last_close = series.iloc[-1]
                        pct_change = (last_close - prev_close) / prev_close * 100
                        logger.info(f"[Automation] NASDAQ: {pct_change:.2f}%")
                        if pct_change < -nasdaq_threshold:
                            reason = f"NASDAQ {pct_change:.2f}% 하락 (기준: -{nasdaq_threshold}%)"
                            self._log_to_dashboard(f"🔴 {reason}", "WARNING")
                            triggered_reasons.append(reason)
                            safe = False
            else:
                logger.warning("[Automation] No US market data found via yfinance")
        except Exception as e:
            logger.error(f"[Automation] US Market check failed: {e}")

        # --- 2. Nikkei 225 Gap Check (pre-computed by scheduler) ---
        nikkei_gap_pct = self.app_state.get("nikkei_gap_pct")
        if nikkei_gap_pct is not None:
            logger.info(f"[Automation] Nikkei 225 Gap: {nikkei_gap_pct:.2f}%")
            if nikkei_gap_pct < -nikkei_gap_threshold:
                reason = f"Nikkei 225 갭 {nikkei_gap_pct:.2f}% (기준: -{nikkei_gap_threshold}%)"
                self._log_to_dashboard(f"🔴 {reason}", "WARNING")
                triggered_reasons.append(reason)
                safe = False
        else:
            logger.info("[Automation] Nikkei 225 Gap: 데이터 없음 (체크 스킵)")

        # --- Result ---
        if not safe:
            logger.info("[Automation] Market Safety: DANGEROUS -> TRADING ABORTED")
            self._log_to_dashboard("🚨 매매 중단 (안전 장치 작동)", "WARNING")
            for r in triggered_reasons:
                self._log_to_dashboard(f"  → {r}", "WARNING")
            self._log_to_dashboard("[힌트] '매매 중단 (안전 장치)' 옵션을 해제하여 강제 실행할 수 있습니다.", "INFO")


        else:
            self._log_to_dashboard("✅ 시장 안전 (SAFE) - 매매 정상 진행", "INFO")

        return safe, triggered_reasons

    async def check_nikkei_gap(self):
        """
        Check Nikkei 225 opening gap.
        Called once daily at 09:01 by scheduler.
        Stores gap % in app_state["nikkei_gap_pct"].
        On API error: stores None (no fail-safe block).

        Gap = (today_open - prev_close) / prev_close * 100
        prev_close = the last trading day's close (explicitly filtered by date).
        """
        logger.info("[Automation] Checking Nikkei 225 opening gap...")
        self._log_to_dashboard("Nikkei 225 개장 갭 체크 중...", "INFO")

        try:
            ticker = yf.Ticker("^N225")

            # Use 10d to ensure enough trading days even across weekends/holidays
            hist = ticker.history(period="10d")
            if hist.empty or len(hist) < 2:
                logger.warning("[Automation] Nikkei 225: insufficient history data")
                self.app_state["nikkei_gap_pct"] = None
                self._log_to_dashboard("Nikkei 225 갭: 데이터 부족 (스킵)", "WARNING")
                return

            # Explicitly filter out today's data to get the correct previous close
            today = datetime.now().date()
            past_data = hist[hist.index.date < today]

            if past_data.empty:
                logger.warning("[Automation] Nikkei 225: no past trading data found")
                self.app_state["nikkei_gap_pct"] = None
                self._log_to_dashboard("Nikkei 225 갭: 과거 거래일 데이터 없음 (스킵)", "WARNING")
                return

            prev_close = float(past_data["Close"].iloc[-1])
            prev_date = past_data.index[-1].strftime("%Y-%m-%d")

            # Get today's open from the same hist data first, fallback to period="1d"
            today_data = hist[hist.index.date == today]
            if today_data.empty or "Open" not in today_data.columns:
                today_data = ticker.history(period="1d")
                if today_data.empty or "Open" not in today_data.columns:
                    logger.warning("[Automation] Nikkei 225: no today's open data")
                    self.app_state["nikkei_gap_pct"] = None
                    self._log_to_dashboard("Nikkei 225 갭: 당일 시가 데이터 없음 (스킵)", "WARNING")
                    return

            today_open = float(today_data["Open"].iloc[-1])

            if prev_close <= 0:
                logger.warning("[Automation] Nikkei 225: invalid previous close")
                self.app_state["nikkei_gap_pct"] = None
                return

            gap_pct = ((today_open - prev_close) / prev_close) * 100
            self.app_state["nikkei_gap_pct"] = gap_pct

            logger.info(f"[Automation] Nikkei 225 Gap: {gap_pct:.2f}% (전일종가[{prev_date}]: {prev_close:.0f}, 당일시가: {today_open:.0f})")
            self._log_to_dashboard(
                f"Nikkei 225 갭: {gap_pct:+.2f}% (종가[{prev_date}] {prev_close:.0f} → 시가 {today_open:.0f})",
                "INFO" if gap_pct > -1.0 else "WARNING"
            )

        except Exception as e:
            logger.error(f"[Automation] Nikkei 225 gap check failed: {e}")
            self.app_state["nikkei_gap_pct"] = None
            self._log_to_dashboard(f"Nikkei 225 갭 체크 실패: {e}", "WARNING")

    async def run_morning_routine(self, config_id: int, is_retry: bool = False):
        """
        Main entry point for daily routine for a specific strategy.
        """
        config_obj = self.configs.get(config_id)
        if not config_obj:
            logger.error(f"[Automation] Routine failed: Config {config_id} not found")
            return

        config = config_obj.config_json
        strategy_name = config_obj.name
        
        # --- [NEW] Continuous Extraction Logic ---
        now = datetime.now()
        start_time_str = config.get("start_time", "09:00")
        end_time_str = config.get("extraction_end_time", "11:00")
        
        try:
            start_time = now.replace(hour=int(start_time_str.split(":")[0]), 
                                     minute=int(start_time_str.split(":")[1]), second=0, microsecond=0)
            end_time = now.replace(hour=int(end_time_str.split(":")[0]), 
                                   minute=int(end_time_str.split(":")[1]), second=0, microsecond=0)
            
            # 검색 시간 범위 밖이면 종료
            if now < start_time or now > end_time:
                # 추출 윈도우 종료 후: 당일 후보가 없으면 더미 저장 (1회만)
                if now > end_time:
                    target_date = now.strftime("%Y-%m-%d")
                    flag_key = f"_ranking_eow_saved_{config_id}_{target_date}"
                    if not self.app_state.get(flag_key):
                        self.app_state[flag_key] = True
                        today_candidates = self.db.get_analysis_candidates(target_date)
                        has_candidates = any(
                            c.extraction_strategy == strategy_name 
                            for c in today_candidates
                        )
                        if not has_candidates:
                            nikkei_gap = self.app_state.get(f"_gap_delay_{config_id}")
                            if nikkei_gap is not None:
                                reason = f"갭상승 지연(닛케이 +{nikkei_gap:.2f}%) + 필터 통과 종목 없음"
                            else:
                                reason = "필터 조건 미충족 (매수 후보 0건)"
                            
                            dummy = AnalysisCandidate(
                                symbol="-",
                                name="NoCandidates",
                                extraction_strategy=strategy_name,
                                score=0,
                                price=0,
                                status="SKIPPED",
                                skip_reason=reason,
                                actual_strategy=""
                            )
                            try:
                                self.db.save_analysis_candidates([dummy])
                            except Exception as e:
                                logger.error(f"[{strategy_name}] Failed to save dummy EOW candidate: {e}")
                return
        except Exception as e:
            logger.error(f"[{strategy_name}] Time parsing failed: {e}")
            return

        # --- [NEW] Dual Limit Logic (Daily Max vs Concurrent Max) ---
        max_concurrent = int(config.get("max_concurrent_stocks", config.get("max_stocks", 3)))
        daily_limit = int(config.get("daily_max_trades", config.get("max_stocks", 10)))
        
        # 1. Count today's BUY trades for this strategy
        daily_count = self.db.get_strategy_buy_count_today(strategy_name)
        
        # 2. Count current active positions for this strategy
        active_positions = self.app_state.get("positions", [])
        trading_service = self.app_state.get("trading_service")
        active_count = 0
        if trading_service:
            for pos in active_positions:
                symbol = pos["symbol"]
                # Check memory map first
                if trading_service._symbol_extraction_map.get(symbol) == strategy_name:
                    active_count += 1
        
        # 3. Current pending targets in app_state
        current_results = self.app_state.get("extraction_results", [])
        strategy_targets = [t for t in current_results if t.get("strategy_id") == config_id]
        targets_count = len(strategy_targets)
        
        # Total committed slots = active positions + pending targets
        total_committed = active_count + targets_count
        
        # Check if we reached daily limit
        if daily_count + targets_count >= daily_limit:
            # Already reached or pending to reach daily limit
            logger.debug(f"[{strategy_name}] Daily limit reached ({daily_count + targets_count}/{daily_limit}). Skipping extraction.")
            return

        # Check if we reached concurrent limit
        if total_committed >= max_concurrent:
            # Already at max concurrent capacity
            logger.debug(f"[{strategy_name}] Concurrent limit reached ({total_committed}/{max_concurrent}). Skipping extraction.")
            return
            
        # Calculate how many MORE we can extract
        # We want to fill the concurrent slots, but not exceed daily limit
        slots_available = max_concurrent - total_committed
        daily_remaining = daily_limit - daily_count - targets_count
        to_extract_count = min(slots_available, daily_remaining)
        
        if to_extract_count <= 0:
            return

        logger.info(f"========== [Automation] RUN EXTRACTION CYCLE: {strategy_name} (ID: {config_id}) ==========")
        logger.info(f"[{strategy_name}] Limits: Concurrent={max_concurrent} (Active={active_count}, Targets={targets_count}), Daily={daily_limit} (Done={daily_count})")
        logger.info(f"[{strategy_name}] Extracting {to_extract_count} more stock(s)...")

        # 1. Market Safety Check (S&P 500, NASDAQ, Nikkei 225 Gap)
        is_safe, triggered_reasons = await self.check_market_safety(config)
        if not is_safe:
            self._log_to_dashboard(f"Routine ABORTED for '{strategy_name}' — 안전 장치 작동", "WARNING")
            try:
                from nicegui import ui
                ui.notify(f"자동매매 중지 ({strategy_name}): 안전 장치 작동", type="negative", close_button=True)
            except:
                pass
            
            # --- Save dummy candidate for market safety halt ---
            universe_code = config.get("target_universe", "nikkei225")
            extraction_strategy = config.get("extraction_strategy", "SMAGoldenDeadCross")
            reasons_str = ", ".join(triggered_reasons) if triggered_reasons else "이유 확인 불가"
            dummy = AnalysisCandidate(
                id=None,
                date=datetime.now().strftime("%Y-%m-%d"),
                extraction_strategy=strategy_name,
                target_universe=universe_code,
                rank=1,
                symbol="-",
                symbol_name="",
                score=0.0,
                price=0.0,
                status="SKIPPED",
                skip_reason=f"매매 중단 (안전 장치 작동: {reasons_str})",
                actual_strategy=""
            )
            try:
                self.db.save_analysis_candidates([dummy])
            except Exception as e:
                logger.error(f"[Automation] Failed to save safety dummy candidate: {e}")
                
            return

        # 1.5. Gap-Up Filter
        nikkei_gap_pct = self.app_state.get("nikkei_gap_pct")
        gap_threshold = float(self.app_state.get("global_nikkei_gap_threshold", 1.0))
        if nikkei_gap_pct is not None and nikkei_gap_pct >= gap_threshold:
            delay_target = now.replace(hour=10, minute=30, second=0, microsecond=0)
            if now < delay_target:
                self.app_state[f"_gap_delay_{config_id}"] = nikkei_gap_pct
                # 10시 30분 전이면 다음 주기에 다시 시도하도록 종료
                logger.info(f"[{strategy_name}] 닛케이 과도한 갭상승({nikkei_gap_pct:+.2f}%) 감지. 10:30 이후에 다시 시도합니다.")
                return

        # 2. Run Analysis & Select Top Stocks (with Retry Logic)
        universe_code = config.get("target_universe", "nikkei225")
        extraction_strategy = config.get("extraction_strategy", "SMAGoldenDeadCross")
        # Use the calculated to_extract_count instead of fixed max_stocks
        max_stocks = to_extract_count 
        max_buy_price = float(self.app_state.get("max_buy_price", 5000))
        max_retries = 1  # Default for ranking_leaders
        
        self._log_to_dashboard(f"[{strategy_name}] Analyzing {universe_code} with {extraction_strategy}...", "INFO")
        
        # Get symbols already traded (bought) today to prevent wash trading / margin reuse issues (Option C)
        try:
            today_trades = self.db.get_today_trades()
            already_traded_symbols = {t.symbol for t in today_trades if t.side == 'BUY'}
            if already_traded_symbols:
                logger.info(f"[{strategy_name}] Found already traded symbols today: {already_traded_symbols}")
            
            # [NEW] 연속 매수 쿨다운 필터: 최근 N일 이내 거래한 종목도 제외
            cooldown_days = int(config.get("recent_trade_cooldown_days", 2))
            if cooldown_days > 0:
                recent_symbols = self.db.get_recent_traded_symbols(
                    days=cooldown_days, strategy_name=strategy_name
                )
                if recent_symbols:
                    logger.info(
                        f"[{strategy_name}] 🛡️ 쿨다운 필터 (최근 {cooldown_days}일): "
                        f"제외 종목 = {recent_symbols}"
                    )
                    already_traded_symbols = already_traded_symbols | recent_symbols
        except Exception as e:
            logger.error(f"[Automation] Failed to fetch today's trades for filtering: {e}")
            already_traded_symbols = set()
            
        targets = []
        
        # ── ranking_leaders 모드: Ranking API 기반 당일 주도주 추출 ──
        if universe_code == "ranking_leaders":
            universe_manager = self.app_state.get("universe")
            if not universe_manager:
                logger.error("[Automation] Universe manager not found")
                return
            
            gap_min = float(config.get("gap_filter_min", 2.0))
            gap_max = float(config.get("gap_filter_max", 5.0))
            ranking_type = config.get("ranking_type", "1")  # 기본: 상승률
            secondary_ranking_type = config.get("secondary_ranking_type", "5")  # 기본: TICK 횟수
            max_rise_from_open = float(config.get("max_rise_from_open_pct", 2.5))  # 시가 대비 최대 상승률
            
            sec_log = f" + 보조({secondary_ranking_type})" if secondary_ranking_type != "none" else ""
            self._log_to_dashboard(
                f"[{strategy_name}] 랭킹 API (Type={ranking_type}{sec_log}) 주도주 추출 중... "
                f"(갭 필터: +{gap_min}% ~ +{gap_max}%, 시가 상승 한도: +{max_rise_from_open}%)", "INFO"
            )
            
            max_retries = 5
            # 1회 시도 루프
            try:
                leaders, full_log = await universe_manager.fetch_intraday_leaders(
                    ranking_type=ranking_type,
                    secondary_ranking_type=secondary_ranking_type,
                    count=150,
                    gap_min=gap_min,
                    gap_max=gap_max,
                    max_rise_from_open_pct=max_rise_from_open,
                    max_buy_price=max_buy_price,
                )
                
                if leaders:
                    # === 복합 점수 알고리즘 ===
                    # 갭%, 거래량, 시가 대비 상승률을 종합하여 점수 산출
                    scored_leaders = []
                    for leader in leaders:
                        symbol = leader["symbol"]
                        # Skip if already traded today
                        if symbol in already_traded_symbols:
                            logger.info(f"[{strategy_name}] Skipping already traded leader: {symbol}")
                            # 로그에도 기거래 표시
                            for log_e in full_log:
                                if log_e["symbol"] == symbol:
                                    log_e["filter_result"] = "기거래"
                                    log_e["filter_detail"] = "당일 이미 거래한 종목"
                            continue
                            
                        price = leader.get("current_price", 0)
                        if price >= max_buy_price:
                            # 로그에도 가격초과 표시
                            for log_e in full_log:
                                if log_e["symbol"] == symbol:
                                    log_e["filter_result"] = "가격초과"
                                    log_e["filter_detail"] = f"현재가 ¥{price:,.0f} >= 상한 ¥{max_buy_price:,.0f}"
                            continue
                        
                        # --- 복합 점수 산출 ---
                        gap = leader.get("gap_pct", 0)
                        volume = leader.get("volume", 0)
                        open_price = 0
                        prev_close = leader.get("previous_close", 0)
                        
                        # 해당 종목의 시가 정보를 full_log에서 가져옴
                        for log_e in full_log:
                            if log_e["symbol"] == symbol:
                                open_price = log_e.get("open_price", 0)
                                break
                        
                        # 1. 갭 점수 (30점 만점): 적정 갭(3~4%)이 최고, 너무 낮거나 높으면 감점
                        ideal_gap = (gap_min + gap_max) / 2
                        gap_deviation = abs(gap - ideal_gap)
                        gap_range = (gap_max - gap_min) / 2
                        gap_score = max(0, 30.0 * (1 - gap_deviation / gap_range)) if gap_range > 0 else 15.0
                        
                        # 2. 거래량 점수 (30점 만점): 거래량이 높을수록 유동성 좋음
                        # 상대 비교: 현재 리스트 내 최대 거래량 기준
                        max_vol = max(l.get("volume", 1) for l in leaders) or 1
                        vol_ratio = volume / max_vol
                        vol_score = min(30.0, 30.0 * vol_ratio)
                        
                        # 3. 시가 대비 상승 모멘텀 점수 (20점 만점)
                        if open_price > 0 and price > 0:
                            rise_from_open = ((price - open_price) / open_price) * 100
                            # 시가 대비 0.5~1.5% 상승이 이상적 (상승 모멘텀 + 과열 아님)
                            if 0 <= rise_from_open <= max_rise_from_open:
                                momentum_score = 20.0 * min(1.0, rise_from_open / 1.0) if rise_from_open <= 1.5 else 20.0 * (1 - (rise_from_open - 1.5) / (max_rise_from_open - 1.5))
                                momentum_score = max(0, momentum_score)
                            else:
                                momentum_score = 0
                        else:
                            momentum_score = 10.0  # 시가 정보 없으면 중간값
                        
                        # 4. 가격대 점수 (20점 만점): 단타에 적합한 가격대 보너스
                        if 300 <= price <= 2000:
                            price_score = 20.0  # 최적 가격대
                        elif 2000 < price <= 3500:
                            price_score = 15.0
                        elif price < 300:
                            price_score = 10.0  # 너무 저가
                        else:
                            price_score = 8.0   # 고가
                        
                        composite_score = gap_score + vol_score + momentum_score + price_score
                        score_reason = (
                            f"갭{gap_score:.0f} + 거래량{vol_score:.0f} + "
                            f"모멘텀{momentum_score:.0f} + 가격대{price_score:.0f} = {composite_score:.1f}"
                        )
                        
                        scored_leaders.append({
                            "symbol": symbol,
                            "name": leader.get("name", ""),
                            "price": price,
                            "signal": f"Gap +{gap:.1f}%",
                            "strength": composite_score,
                            "reason": f"[복합점수] {score_reason}",
                            "gap_pct": gap,
                        })
                    
                    # 복합 점수순으로 정렬 (높은 순)
                    scored_leaders.sort(key=lambda x: x["strength"], reverse=True)
                    
                    # 상위 max_stocks개 선택
                    for leader in scored_leaders[:max_stocks]:
                        targets.append(leader)
                    
                    # full_log에 최종 순위와 점수 기록
                    final_symbols = {t["symbol"]: (i+1, t["strength"]) for i, t in enumerate(targets)}
                    for log_e in full_log:
                        if log_e["symbol"] in final_symbols:
                            rank, score = final_symbols[log_e["symbol"]]
                            log_e["final_rank"] = rank
                            log_e["score"] = score
                    
                    if targets:
                        self._log_to_dashboard(
                            f"[{strategy_name}] 랭킹 기반 {len(targets)}개 종목 추출 완료 (복합점수 적용)", "INFO"
                        )
                        for t in targets:
                            self._log_to_dashboard(
                                f"  → {t['symbol']} ({t['name']}) 점수={t['strength']:.1f} {t['reason']}", "INFO"
                            )
                else:
                    # 이번 주기에는 결과가 없으므로 로그만 남김 (종료하지 않음)
                    logger.info(f"[{strategy_name}] No ranking candidates found in this cycle.")
                
                # === 전체 검색 로그 DB 저장 ===
                if full_log:
                    cycle_time = datetime.now().strftime("%H:%M:%S")
                    today_str = datetime.now().strftime("%Y-%m-%d")
                    log_entries = []
                    for log_e in full_log:
                        log_entries.append(ExtractionLogEntry(
                            date=today_str,
                            extraction_strategy=strategy_name,
                            target_universe=universe_code,
                            cycle_time=cycle_time,
                            symbol=log_e["symbol"],
                            symbol_name=log_e.get("name", ""),
                            ranking_position=log_e.get("ranking_position", 0),
                            gap_pct=log_e.get("gap_pct", 0),
                            current_price=log_e.get("current_price", 0),
                            open_price=log_e.get("open_price", 0),
                            previous_close=log_e.get("previous_close", 0),
                            volume=log_e.get("volume", 0),
                            filter_result=log_e.get("filter_result", ""),
                            filter_detail=log_e.get("filter_detail", ""),
                            final_rank=log_e.get("final_rank", 0),
                            score=log_e.get("score", 0),
                        ))
                    try:
                        self.db.save_extraction_log(log_entries)
                        logger.info(f"[{strategy_name}] Saved {len(log_entries)} extraction log entries to DB")
                    except Exception as e:
                        logger.error(f"[{strategy_name}] Failed to save extraction log: {e}")
                    
            except Exception as e:
                logger.error(f"[Automation] Ranking-based extraction failed: {e}")
                self._log_to_dashboard(f"[{strategy_name}] 랭킹 추출 실패: {e}", "ERROR")
        else:
            # ── 기존 모드: 일봉 기반 전략 분석 ──
            analysis_service = self.app_state.get("analysis_service")
            if not analysis_service:
                logger.error("[Automation] AnalysisService not found inside app_state")
                return

            max_retries = 5
            retry_delay = 180  # seconds

            for attempt in range(1, max_retries + 1):
                try:
                    results = await analysis_service.analyze_universe(
                        universe_code=universe_code,
                        strategy_name=extraction_strategy
                    )
                    
                    # Filter out stocks above max buy price and already traded today
                    before_filter = len(results)
                    results = [
                        r for r in results 
                        if r.get("price", 0) < max_buy_price and r.get("symbol") not in already_traded_symbols
                    ]
                    filtered_count = before_filter - len(results)
                    
                    targets = results[:max_stocks]
                    
                    if targets:
                        self._log_to_dashboard(
                            f"[{strategy_name}] Analysis attempt {attempt} complete. Found {len(targets)} targets "
                            f"(filtered {filtered_count} items > ¥{max_buy_price:,.0f}).", "INFO"
                        )
                        break
                    else:
                        self._log_to_dashboard(f"[{strategy_name}] ⚠️ No candidates found on attempt {attempt}.", "WARNING")
                        
                except Exception as e:
                    logger.error(f"[Automation] Analysis attempt {attempt} failed: {e}")
                    self._log_to_dashboard(f"[{strategy_name}] 분석 실패 (시도 {attempt}/{max_retries}): {e}", "ERROR")

                if attempt < max_retries:
                    self._log_to_dashboard(f"[{strategy_name}] {retry_delay}초 후 데이터 재수집 및 분석을 재시도합니다...", "WARNING")
                    await asyncio.sleep(retry_delay)

            self._log_to_dashboard(f"[{strategy_name}] ❌ {max_retries}회 재시도에도 불구하고 최종 대상을 찾지 못했습니다.", "WARNING")
            
            # --- Save dummy candidate for NO TARGETS or FAILURE ---
            dummy = AnalysisCandidate(
                id=None,
                date=datetime.now().strftime("%Y-%m-%d"),
                extraction_strategy=strategy_name,
                target_universe=universe_code,
                rank=1,
                symbol="-",
                symbol_name="",
                score=0.0,
                price=0.0,
                status="SKIPPED",
                skip_reason=f"매수 후보 미발견 또는 실행/데이터 오류 ({max_retries}회 재시도 실패)",
                actual_strategy=""
            )
            try:
                self.db.save_analysis_candidates([dummy])
            except Exception as e:
                logger.error(f"[Automation] Failed to save no-target dummy candidate: {e}")
                
            logger.info(f"========== [Automation] END ROUTINE: {strategy_name} (NO TARGETS) ==========")
            return
        
        # 3. Filter targets: Remove symbols already in strategy_targets to prevent duplicates
        existing_symbols = {t["symbol"] for t in strategy_targets}
        targets = [t for t in targets if t["symbol"] not in existing_symbols]

        if not targets:
            logger.debug(f"[{strategy_name}] All extracted symbols are already in the target list. Skipping update.")
            return

        # Tag targets with strategy info
        target_symbols = []
        for rank, t in enumerate(targets, 1):
            t["strategy_id"] = config_id
            t["strategy_name"] = strategy_name
            t["config_name"] = strategy_name
            t["extraction_strategy"] = extraction_strategy
            t["target_universe"] = universe_code
            t["buy_rank"] = rank  # 순위 (1=최상위)
            t["added_at"] = datetime.now().isoformat()  # 대기 타임아웃 기준 시각
            target_symbols.append(f"{t['symbol']} ({t['price']}JPY)")
            
        self._log_to_dashboard(f"[{strategy_name}] Selected Top {len(targets)}: {', '.join(target_symbols)}", "INFO")
        
        # Save analysis candidates to DB for full-rank tracking in reports
        today_str = datetime.now().strftime("%Y-%m-%d")
        db_candidates = []
        for rank, t in enumerate(targets, 1):
            db_candidates.append(AnalysisCandidate(
                id=None,
                date=today_str,
                extraction_strategy=strategy_name,
                target_universe=universe_code,
                rank=rank,
                symbol=t["symbol"],
                symbol_name=t.get("name", ""),
                score=t.get("strength", 0.0),
                price=t.get("price", 0.0),
                status="PENDING",
                skip_reason="",
                actual_strategy="",
            ))
        try:
            self.db.save_analysis_candidates(db_candidates)
            logger.info(f"[Automation] Saved {len(db_candidates)} analysis candidates to DB for {extraction_strategy} ({universe_code})")
        except Exception as e:
            logger.error(f"[Automation] Failed to save analysis candidates: {e}")
        
        # 4. Update Target List (Append to global list, don't replace)
        if "extraction_results" not in self.app_state:
            self.app_state["extraction_results"] = []
        
        # Remove old targets from this strategy (but we might want to KEEP them if they are still pending?)
        # Actually, if we keep them, they are already counted in total_committed.
        # So we should APPEND the new targets to the existing ones for this strategy.
        old_other_targets = [
            t for t in self.app_state["extraction_results"] 
            if t.get("strategy_id") != config_id
        ]
        
        # Add new targets to existing targets for this strategy
        self.app_state["extraction_results"] = old_other_targets + strategy_targets + targets
        
        # Register target symbols for WebSocket PUSH (VWAP tracking)
        ws_service = self.app_state.get("ws_service")
        if ws_service and targets:
            push_symbols = [t["symbol"] for t in targets]
            try:
                await ws_service.register_symbols(push_symbols)
                logger.info(f"[Automation] Registered {len(push_symbols)} symbols for WebSocket PUSH")
            except Exception as e:
                logger.warning(f"[Automation] WebSocket registration failed (non-fatal): {e}")
        
        # 5. Start Trading (if not already running)
        self._ensure_trading_loop_running()
        
        try:
            from nicegui import ui
            ui.notify(f"자동매매 시작 ({strategy_name}): {len(targets)}개 종목", type="positive")
        except:
            pass
            
        logger.info(f"========== [Automation] END ROUTINE: {strategy_name} (TRADING STARTED) ==========")

    async def run_trading_cycle(self):
        """
        Circuit-breaker wrapper around TradingService.run_trading_cycle.

        Runs one trading cycle and tracks consecutive failures. If the
        underlying cycle raises an exception MAX_CONSECUTIVE_ERRORS times in a
        row, trading is force-disabled (trading_active=False), the trading_loop
        job is removed, an alert is sent (if a notifier is configured) and a
        CRITICAL log is emitted — preventing runaway execution against an
        unhealthy API. A successful cycle resets the counter.

        The actual trading/order logic is untouched; this only adds a guard.
        """
        trading_service = self.app_state.get("trading_service")
        if not trading_service:
            logger.error("[Automation] run_trading_cycle: trading_service missing")
            return

        try:
            await trading_service.run_trading_cycle()
            # Success: reset the consecutive-error counter.
            if self._consecutive_errors:
                logger.info(
                    f"[Automation] Trading cycle recovered after "
                    f"{self._consecutive_errors} consecutive error(s)."
                )
            self._consecutive_errors = 0
        except Exception as e:
            self._consecutive_errors += 1
            logger.error(
                f"[Automation] Trading cycle failed "
                f"({self._consecutive_errors}/{MAX_CONSECUTIVE_ERRORS}): {e}"
            )
            self._log_to_dashboard(
                f"매매 사이클 오류 ({self._consecutive_errors}/{MAX_CONSECUTIVE_ERRORS}): {e}",
                "WARNING",
            )

            if self._consecutive_errors >= MAX_CONSECUTIVE_ERRORS:
                # Trip the circuit breaker: stop the loop.
                self.app_state["trading_active"] = False
                scheduler = self.app_state.get("scheduler")
                if scheduler:
                    try:
                        scheduler.remove_job("trading_loop")
                    except Exception:
                        pass

                logger.critical(
                    f"[Automation] CIRCUIT BREAKER TRIPPED: "
                    f"{self._consecutive_errors} consecutive trading-cycle "
                    f"failures. Trading loop STOPPED to prevent runaway "
                    f"execution. Last error: {e}"
                )
                self._log_to_dashboard(
                    f"🚨 서킷 브레이커 작동: 연속 {self._consecutive_errors}회 오류로 "
                    f"자동매매 루프를 중단했습니다.",
                    "ERROR",
                )

                notifier = self.app_state.get("notifier")
                if notifier and getattr(notifier, "is_configured", False):
                    try:
                        await notifier.send_system_alert(
                            f"서킷 브레이커 작동: 연속 {self._consecutive_errors}회 "
                            f"매매 사이클 실패로 자동매매를 중단했습니다. "
                            f"마지막 오류: {e}",
                            level="ERROR",
                        )
                    except Exception as alert_err:
                        logger.error(
                            f"[Automation] Failed to send circuit-breaker alert: {alert_err}"
                        )

    def _ensure_trading_loop_running(self):
        """Ensure the trading loop is running"""
        if self.app_state.get("trading_active"):
            return
        
        trading_service = self.app_state.get("trading_service")
        scheduler = self.app_state.get("scheduler")
        
        if trading_service and scheduler:
            if not scheduler.get_job("trading_loop"):
                 logger.info("[Automation] Starting Trading Loop Job...")
                 scheduler.start()
                 # Reset circuit breaker on fresh loop start.
                 self._consecutive_errors = 0
                 # Use the circuit-breaker wrapper (self.run_trading_cycle) so
                 # consecutive API failures auto-stop the loop. max_instances/
                 # coalesce prevent duplicate concurrent cycles (double orders).
                 scheduler.add_interval_job(
                     self.run_trading_cycle,
                     job_id="trading_loop",
                     seconds=5,
                     max_instances=1,
                     coalesce=True,
                 )
            self.app_state["trading_active"] = True
            logger.info("[Automation] Trading loop ACTIVATED.")
        else:
            logger.error("[Automation] Cannot start trading loop: Service or Scheduler missing")

    def _schedule_config_jobs(self, config_id: int):
        """Schedule cron jobs for a specific config"""
        config_obj = self.configs.get(config_id)
        if not config_obj or not config_obj.is_active:
            return
        
        config = config_obj.config_json
        scheduler = self.app_state.get("scheduler")
        if not scheduler:
            logger.error("[Automation] Scheduler not found")
            return
        
        scheduler.start()  # Ensure scheduler is running
        
        # Extraction Job (Interval based during window)
        start_time_str = config.get("start_time", "09:00")
        interval_seconds = int(config.get("extraction_interval", 120))
        
        async def run_extraction():
            await self.run_morning_routine(config_id)
        
        scheduler.add_interval_job(
            job_id=f"automation_start_{config_id}",
            func=run_extraction,
            seconds=interval_seconds
        )
        logger.info(f"[Automation] Scheduled Periodic EXTRACTION for config {config_id} (Every {interval_seconds}s, Window: {start_time_str} ~ {config.get('extraction_end_time', '11:00')})")
        
        # Stop Job
        end_time_str = config.get("end_time", "15:00")
        try:
            end_hour, end_minute = map(int, end_time_str.split(":"))
            
            async def stop_routine():
                # Remove targets from this strategy
                if "extraction_results" in self.app_state:
                    self.app_state["extraction_results"] = [
                        t for t in self.app_state["extraction_results"]
                        if t.get("strategy_id") != config_id
                    ]
                
                # If no more targets, stop trading loop
                remaining_targets = self.app_state.get("extraction_results", [])
                if not remaining_targets:
                    if scheduler:
                        try:
                            scheduler.remove_job("trading_loop")
                        except:
                            pass
                    self.app_state["trading_active"] = False
                    logger.info(f"[Automation] Trading stopped (no more targets)")
                
                try:
                    from nicegui import ui
                    ui.notify(f"자동매매 종료 ({config_obj.name})", type="info")
                except:
                    pass
                logger.info(f"[Automation] STOP ROUTINE executed for config {config_id}")
            
            scheduler.add_cron_job(
                job_id=f"automation_stop_{config_id}",
                func=stop_routine,
                hour=end_hour,
                minute=end_minute,
                replace_existing=True
            )
            logger.info(f"[Automation] Scheduled STOP for config {config_id} at {end_time_str}")
        except ValueError:
            logger.error(f"[Automation] Invalid end time format: {end_time_str}")
        
        # End-of-Day Liquidation Job (15:20 — 10 min before market close at 15:30)
        # Only schedule once globally (not per config)
        if not scheduler.get_job("automation_eod_close"):
            async def close_all_positions():
                """Sell all open positions before market close"""
                # FIRST: Disable trading and clear targets to prevent new buys
                self.app_state["extraction_results"] = []
                self.app_state["trading_active"] = False
                logger.info("[Automation] EOD Close: Trading disabled, targets cleared")
                self._log_to_dashboard("EOD 청산 (15:20): 매수 중단 및 대상 종목 클리어", "TRADE")
                
                positions = self.app_state.get("positions", [])
                if not positions:
                    logger.info("[Automation] EOD Close: No positions to liquidate")
                    return
                
                client = self.app_state.get("client")
                trading_service = self.app_state.get("trading_service")
                if not client or not trading_service:
                    logger.error("[Automation] EOD Close: client or trading_service not available")
                    return
                
                logger.info(f"[Automation] EOD Close: Liquidating {len(positions)} position(s)")
                self._log_to_dashboard(f"장마감 10분전 (15:20) 전량 청산 시작: {len(positions)}개 포지션", "TRADE")
                
                for pos in positions:
                    symbol = pos["symbol"]
                    qty = pos.get("qty", 0)
                    if qty <= 0:
                        continue
                    
                    # Get current price
                    try:
                        board = await client.get_board(symbol)
                        current_price = board.current_price
                    except Exception as e:
                        logger.error(f"[Automation] EOD Close: Failed to get price for {symbol}: {e}")
                        current_price = pos.get("avg_price", 0)
                    
                    if current_price <= 0:
                        logger.warning(f"[Automation] EOD Close: Skip {symbol}, price={current_price}")
                        continue
                    
                    entry_price = pos.get("avg_price", 0)
                    pnl = (current_price - entry_price) * qty
                    
                    # Fix #4: Use board's symbol_name for correct DB recording
                    stock_name = getattr(board, 'symbol_name', pos.get("name", symbol))
                    
                    # Look up extraction strategy and target universe from trading service map
                    ext_strategy = ""
                    target_universe = ""
                    buy_rank = 0
                    if trading_service and hasattr(trading_service, '_symbol_extraction_map'):
                        ext_strategy = trading_service._symbol_extraction_map.get(symbol, "")
                    if trading_service and hasattr(trading_service, '_symbol_universe_map'):
                        target_universe = trading_service._symbol_universe_map.get(symbol, "")
                    if trading_service and hasattr(trading_service, '_symbol_rank_map'):
                        buy_rank = trading_service._symbol_rank_map.get(symbol, 0)
                    
                    order_params = {
                        "symbol": symbol,
                        "qty": qty,
                        "price": current_price,
                        "name": stock_name,
                        "realized_pnl": pnl,
                    }
                    
                    self._log_to_dashboard(
                        f"EOD 매도: {symbol} qty={qty} price={current_price:.0f} pnl={pnl:+,.0f}", "TRADE"
                    )
                    await trading_service._execute_order(
                        client, order_params, "SELL", "EndOfDayLiquidation", ext_strategy, target_universe, buy_rank
                    )
                
                logger.info("[Automation] EOD Close: Liquidation completed")
                self._log_to_dashboard("장마감 전 전량 청산 완료", "TRADE")
                
                try:
                    from nicegui import ui
                    ui.notify("장마감 10분전 전량 청산 완료", type="warning")
                except:
                    pass
            
            scheduler.add_cron_job(
                job_id="automation_eod_close",
                func=close_all_positions,
                hour=15,
                minute=20,
                replace_existing=True
            )
            logger.info("[Automation] Scheduled EOD Close at 15:20")

        # Daily Report Generation Job (15:35 — 5 min after market close at 15:30)
        # Only schedule once globally (not per config)
        if not scheduler.get_job("automation_daily_report"):
            async def generate_daily_report():
                """Generate daily trading report after market close"""
                report_service = self.app_state.get("report_service")
                if not report_service:
                    logger.warning("[Automation] ReportService not found, skipping report")
                    return
                
                try:
                    report = await report_service.generate_daily_report()
                    logger.info("[Automation] Daily report generated successfully")
                    self._log_to_dashboard("일일 매매 보고서 생성 완료", "INFO")
                except Exception as e:
                    logger.error(f"[Automation] Daily report generation failed: {e}")
                    self._log_to_dashboard(f"보고서 생성 실패: {e}", "ERROR")

            scheduler.add_cron_job(
                job_id="automation_daily_report",
                func=generate_daily_report,
                hour=15,
                minute=35,
                replace_existing=True
            )
            logger.info("[Automation] Scheduled Daily Report at 15:35")

        # Nikkei 225 Gap Check Job (global, once at 09:01)
        if not scheduler.get_job("nikkei_gap_check"):
            async def run_nikkei_gap():
                await self.check_nikkei_gap()

            scheduler.add_cron_job(
                job_id="nikkei_gap_check",
                func=run_nikkei_gap,
                hour=9,
                minute=1,
                replace_existing=True
            )
            logger.info("[Automation] Scheduled Nikkei 225 Gap Check at 09:01")

        # Market Index Collection Jobs (global, once)
        if not scheduler.get_job("market_index_us_close"):
            async def collect_us_market_close():
                """Collect US market previous-day close data before JP market opens"""
                market_index_service = self.app_state.get("market_index_service")
                if not market_index_service:
                    logger.warning("[Automation] MarketIndexService not found, skipping US data")
                    return
                try:
                    us_data = market_index_service.fetch_us_market_close()
                    if us_data:
                        self._log_to_dashboard(
                            f"미국 지수 수집 완료: {', '.join(d['name'] for d in us_data.values())}",
                            "INFO"
                        )
                    else:
                        self._log_to_dashboard("미국 지수 데이터 수집 실패", "WARNING")
                except Exception as e:
                    logger.error(f"[Automation] US market data collection failed: {e}")

            scheduler.add_cron_job(
                job_id="market_index_us_close",
                func=collect_us_market_close,
                hour=9,
                minute=4,
                replace_existing=True
            )
            logger.info("[Automation] Scheduled US Market Close collection at 09:04")

        # JP Index Snapshots at 09:05, 09:10, 15:30 (종가)
        jp_snapshot_times = [("09:05", 9, 5), ("09:10", 9, 10), ("15:30", 15, 31)]
        for label, snap_hour, snap_minute in jp_snapshot_times:
            job_id = f"market_index_jp_{label.replace(':', '')}"
            if not scheduler.get_job(job_id):
                async def collect_jp_snapshot(lbl=label):
                    """Collect JP market index snapshot"""
                    market_index_service = self.app_state.get("market_index_service")
                    if not market_index_service:
                        logger.warning("[Automation] MarketIndexService not found, skipping JP snapshot")
                        return
                    try:
                        jp_data = market_index_service.fetch_jp_index_snapshot(lbl)
                        if jp_data:
                            self._log_to_dashboard(
                                f"일본 지수 스냅샷({lbl}) 수집 완료", "INFO"
                            )
                        else:
                            self._log_to_dashboard(
                                f"일본 지수 스냅샷({lbl}) 수집 실패", "WARNING"
                            )
                    except Exception as e:
                        logger.error(f"[Automation] JP snapshot ({lbl}) failed: {e}")

                scheduler.add_cron_job(
                    job_id=job_id,
                    func=collect_jp_snapshot,
                    hour=snap_hour,
                    minute=snap_minute,
                    replace_existing=True
                )
                logger.info(f"[Automation] Scheduled JP Index Snapshot at {snap_hour:02d}:{snap_minute:02d} ({label})")
    
    def _unschedule_config_jobs(self, config_id: int):
        """Remove scheduled jobs for a specific config"""
        scheduler = self.app_state.get("scheduler")
        if not scheduler:
            return
        
        try:
            scheduler.remove_job(f"automation_start_{config_id}")
        except:
            pass
        try:
            scheduler.remove_job(f"automation_stop_{config_id}")
        except:
            pass
        logger.info(f"[Automation] Unscheduled jobs for config {config_id}")

    def schedule_jobs(self):
        """
        Register cron jobs for all active configs.
        Called on application startup.
        """
        logger.info("[Automation] Scheduling jobs for all active configs...")
        for config_id, config_obj in self.configs.items():
            if config_obj.is_active:
                self._schedule_config_jobs(config_id)

    # Legacy compatibility - single config access (for gradual migration)
    @property
    def config(self) -> Dict[str, Any]:
        """Return first config for backward compatibility"""
        if self.configs:
            first = next(iter(self.configs.values()))
            return first.config_json
        return DEFAULT_CONFIG.copy()
    
    def update_config(self, new_config: Dict[str, Any]):
        """Legacy method for backward compatibility"""
        # If we have existing configs, update the first one
        if self.configs:
            first_id = next(iter(self.configs.keys()))
            first_cfg = self.configs[first_id]
            self.save_config(first_cfg.name, new_config, config_id=first_id, is_active=first_cfg.is_active)
        else:
            # Create new config
            self.save_config("Default Strategy", new_config)
        self.schedule_jobs()
