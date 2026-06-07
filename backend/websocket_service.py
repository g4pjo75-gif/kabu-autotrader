# -*- coding: utf-8 -*-
"""
WebSocket PUSH API Service

Kabu Station의 PUSH API를 통해 실시간 시세 데이터를 수신하고,
5분봉 캔들 데이터를 자동으로 축적합니다.

Flow:
1. REST API로 감시 대상 종목 등록 (PUT /register, 최대 50종목)
2. WebSocket 연결 (ws://localhost:PORT/kabusapi/websocket)
3. 등록된 종목의 시세 업데이트가 실시간 Push
4. 수신 데이터를 IntradayBarAccumulator에 전달하여 5분봉 생성
"""
import json
import logging
import threading
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, List, Optional

import websocket

logger = logging.getLogger(__name__)


@dataclass
class IntradayBar:
    """5분봉 1개 (OHLCV)"""
    timestamp: datetime      # bar 시작 시간
    open: float = 0.0
    high: float = 0.0
    low: float = float('inf')
    close: float = 0.0
    volume: int = 0
    vwap_numerator: float = 0.0  # Σ(price * volume) for bar
    tick_count: int = 0


@dataclass
class VWAPState:
    """당일 VWAP 누적 상태"""
    cumulative_pv: float = 0.0        # Σ(price * volume_delta)
    cumulative_volume: int = 0         # Σ(volume_delta)
    last_total_volume: int = 0         # 직전 총 누적 거래량 (delta 계산용)
    vwap: float = 0.0                  # 현재 VWAP 값
    day_high: float = 0.0              # 당일 고가
    day_low: float = float('inf')      # 당일 저가
    open_price: float = 0.0            # 당일 시가
    last_price: float = 0.0            # 최근 체결 가격
    recent_low: float = float('inf')   # 최근 N틱 저점 (반등 감지용)
    recent_prices: List[float] = field(default_factory=list)  # 최근 가격 기록 (반등 패턴용)
    vwap_history: List[float] = field(default_factory=list)   # VWAP 히스토리 (기울기 계산용)
    tick_count: int = 0                                       # 당일 수신된 실시간 틱 카운트 (개수)
    
    def update(self, price: float, total_volume: int):
        """실시간 시세 업데이트"""
        self.tick_count += 1
        
        if self.open_price == 0.0:
            self.open_price = price
        
        # volume delta 계산 (총 누적 거래량 차이)
        volume_delta = max(0, total_volume - self.last_total_volume)
        self.last_total_volume = total_volume
        
        if volume_delta > 0:
            self.cumulative_pv += price * volume_delta
            self.cumulative_volume += volume_delta
            self.vwap = self.cumulative_pv / self.cumulative_volume
        
        self.last_price = price
        if price > self.day_high:
            self.day_high = price
        if price < self.day_low:
            self.day_low = price
        
        # 최근 가격 기록 (최대 20개 유지)
        self.recent_prices.append(price)
        if len(self.recent_prices) > 20:
            self.recent_prices = self.recent_prices[-20:]
        
        # 최근 10틱 저점 업데이트
        if len(self.recent_prices) >= 3:
            self.recent_low = min(self.recent_prices[-10:])
            
        # VWAP 히스토리 기록 (최대 100개 유지)
        if self.vwap > 0:
            if not self.vwap_history or abs(self.vwap - self.vwap_history[-1]) > 0.01: # 유의미한 변화만 기록
                self.vwap_history.append(self.vwap)
                if len(self.vwap_history) > 100:
                    self.vwap_history = self.vwap_history[-100:]


class IntradayBarAccumulator:
    """
    실시간 시세 데이터를 5분봉으로 축적하는 클래스.
    
    WebSocket PUSH 데이터 또는 get_board() 폴링 데이터를 입력받아,
    종목별로 5분 간격의 OHLCV 바를 생성합니다.
    """
    
    def __init__(self, bar_interval_minutes: int = 5):
        self.bar_interval = bar_interval_minutes
        self._bars: Dict[str, List[IntradayBar]] = defaultdict(list)
        self._current_bar: Dict[str, IntradayBar] = {}
        self._vwap_states: Dict[str, VWAPState] = defaultdict(VWAPState)
        self._lock = threading.Lock()
    
    def _get_bar_start_time(self, dt: datetime) -> datetime:
        """현재 시각의 5분봉 시작 시간 계산"""
        minute = (dt.minute // self.bar_interval) * self.bar_interval
        return dt.replace(minute=minute, second=0, microsecond=0)
    
    def update(self, symbol: str, price: float, volume: int, timestamp: datetime = None):
        """
        새 시세 데이터 입력.
        
        Args:
            symbol: 종목 코드
            price: 현재가
            volume: 당일 누적 거래량 (총량)
            timestamp: 시각 (None이면 현재)
        """
        if price <= 0:
            return
        
        ts = timestamp or datetime.now()
        bar_start = self._get_bar_start_time(ts)
        
        with self._lock:
            # VWAP 업데이트
            self._vwap_states[symbol].update(price, volume)
            
            # 현재 진행 중인 bar 확인
            current = self._current_bar.get(symbol)
            
            if current is None or current.timestamp != bar_start:
                # 이전 bar 확정 및 새 bar 시작
                if current is not None:
                    self._bars[symbol].append(current)
                
                self._current_bar[symbol] = IntradayBar(
                    timestamp=bar_start,
                    open=price,
                    high=price,
                    low=price,
                    close=price,
                    volume=0,
                    tick_count=1,
                )
            else:
                # 기존 bar 업데이트
                current.high = max(current.high, price)
                current.low = min(current.low, price)
                current.close = price
                current.tick_count += 1
    
    def get_bars(self, symbol: str) -> List[IntradayBar]:
        """확정된 5분봉 리스트 반환"""
        with self._lock:
            return list(self._bars.get(symbol, []))
    
    def get_current_bar(self, symbol: str) -> Optional[IntradayBar]:
        """현재 진행 중인 (미확정) 5분봉"""
        with self._lock:
            return self._current_bar.get(symbol)
    
    def get_vwap_state(self, symbol: str) -> VWAPState:
        """종목의 당일 VWAP 상태"""
        with self._lock:
            return self._vwap_states[symbol]
    
    def get_vwap(self, symbol: str) -> float:
        """종목의 현재 VWAP 값"""
        with self._lock:
            return self._vwap_states[symbol].vwap
    
    def reset_day(self):
        """일일 데이터 초기화 (매일 장 시작 전 호출)"""
        with self._lock:
            self._bars.clear()
            self._current_bar.clear()
            self._vwap_states.clear()
            logger.info("[BarAccumulator] Daily data reset")
    
    def get_all_symbols(self) -> List[str]:
        """현재 추적 중인 모든 종목 코드"""
        with self._lock:
            return list(set(
                list(self._current_bar.keys()) + 
                list(self._vwap_states.keys())
            ))


class WebSocketPushService:
    """
    Kabu Station WebSocket PUSH API 서비스.
    
    별도 스레드에서 WebSocket 연결을 유지하며,
    실시간 시세 데이터를 IntradayBarAccumulator에 전달합니다.
    """
    
    def __init__(
        self,
        base_url: str = "http://localhost:18080/kabusapi",
        token: str = "",
        accumulator: Optional[IntradayBarAccumulator] = None,
    ):
        self._base_url = base_url
        self._token = token
        self._accumulator = accumulator or IntradayBarAccumulator()
        self._ws: Optional[websocket.WebSocketApp] = None
        self._ws_thread: Optional[threading.Thread] = None
        self._running = False
        self._registered_symbols: List[str] = []
        self._on_update_callbacks: List[Callable] = []
        
        # WebSocket URL 생성 (http → ws)
        ws_base = base_url.replace("http://", "ws://").replace("/kabusapi", "")
        self._ws_url = f"{ws_base}/kabusapi/websocket"
    
    @property
    def accumulator(self) -> IntradayBarAccumulator:
        return self._accumulator
    
    @property
    def is_connected(self) -> bool:
        return self._running and self._ws_thread is not None and self._ws_thread.is_alive()
    
    def set_token(self, token: str):
        """API 토큰 설정 (인증 후 호출)"""
        self._token = token
    
    def add_update_callback(self, callback: Callable):
        """시세 업데이트 시 호출할 콜백 등록"""
        self._on_update_callbacks.append(callback)
    
    async def register_symbols(self, symbols: List[str], exchange: int = 1) -> bool:
        """
        감시 대상 종목 등록 (PUT /register).
        최대 50종목까지 등록 가능.
        """
        if not self._token:
            logger.error("[WebSocket] Cannot register: no API token")
            return False
        
        import httpx
        
        symbols_data = [
            {"Symbol": s, "Exchange": exchange}
            for s in symbols[:50]  # 최대 50개 제한
        ]
        
        try:
            url = f"{self._base_url}/register"
            headers = {
                "Content-Type": "application/json",
                "X-API-KEY": self._token,
            }
            
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.put(url, headers=headers, json={"Symbols": symbols_data})
                response.raise_for_status()
                
                result = response.json()
                registered = result.get("RegistList", [])
                self._registered_symbols = [r.get("Symbol", "") for r in registered]
                
                logger.info(
                    f"[WebSocket] Registered {len(self._registered_symbols)} symbols "
                    f"for PUSH delivery"
                )
                return True
                
        except Exception as e:
            logger.error(f"[WebSocket] Symbol registration failed: {e}")
            return False
    
    def start(self):
        """WebSocket 연결 시작 (별도 스레드)"""
        if self._running:
            logger.warning("[WebSocket] Already running")
            return
        
        self._running = True
        self._ws_thread = threading.Thread(
            target=self._run_websocket,
            daemon=True,
            name="KabuWebSocket"
        )
        self._ws_thread.start()
        logger.info(f"[WebSocket] Started connection to {self._ws_url}")
    
    def stop(self):
        """WebSocket 연결 종료"""
        self._running = False
        if self._ws:
            try:
                self._ws.close()
            except Exception:
                pass
        if self._ws_thread:
            self._ws_thread.join(timeout=5)
        logger.info("[WebSocket] Stopped")
    
    def _run_websocket(self):
        """WebSocket 이벤트 루프 (별도 스레드에서 실행)"""
        while self._running:
            try:
                self._ws = websocket.WebSocketApp(
                    self._ws_url,
                    on_message=self._on_message,
                    on_error=self._on_error,
                    on_close=self._on_close,
                    on_open=self._on_open,
                )
                self._ws.run_forever(ping_interval=30, ping_timeout=10)
                
            except Exception as e:
                logger.error(f"[WebSocket] Connection error: {e}")
            
            if self._running:
                logger.info("[WebSocket] Reconnecting in 5 seconds...")
                time.sleep(5)
    
    def _on_open(self, ws):
        logger.info("[WebSocket] Connected")
    
    def _on_close(self, ws, close_status_code, close_msg):
        logger.info(f"[WebSocket] Disconnected (code={close_status_code}, msg={close_msg})")
    
    def _on_error(self, ws, error):
        logger.error(f"[WebSocket] Error: {error}")
    
    def _on_message(self, ws, message):
        """PUSH 메시지 수신 처리"""
        try:
            data = json.loads(message)
            
            symbol = data.get("Symbol", "")
            current_price = data.get("CurrentPrice")
            trading_volume = data.get("TradingVolume", 0)
            
            if not symbol or current_price is None or current_price <= 0:
                return
            
            # IntradayBarAccumulator에 데이터 전달
            self._accumulator.update(
                symbol=symbol,
                price=float(current_price),
                volume=int(trading_volume or 0),
            )
            
            # 콜백 호출
            for callback in self._on_update_callbacks:
                try:
                    callback(symbol, data)
                except Exception as e:
                    logger.debug(f"[WebSocket] Callback error: {e}")
                    
        except json.JSONDecodeError:
            logger.warning(f"[WebSocket] Invalid JSON received: {message[:100]}")
        except Exception as e:
            logger.error(f"[WebSocket] Message processing error: {e}")
