# -*- coding: utf-8 -*-
"""
VWAP Pullback Strategy - Day Trading

Board 데이터 기반 실시간 VWAP 눌림목 매수 전략.
5분봉 차트 없이 get_board() 실시간 데이터와 
IntradayBarAccumulator의 VWAP 상태를 활용합니다.

진입 조건:
  A. 추세: 현재가 > 당일 시가 (상승 추세)
  B. 눌림: 현재가가 VWAP의 +0.5% ~ -0.2% 밴드 내
  C. 반등: 최근 저점에서 반등 시작 (price > recent_low * 1.002)
"""
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import pandas as pd

from .base import (
    BaseExtractionStrategy,
    SignalResult,
    StrategyParameter,
)


class VWAPPullbackStrategy(BaseExtractionStrategy):
    """
    VWAP 눌림목 전략 (데이 트레이딩 전용)
    
    Board 데이터 기반으로 실시간 VWAP 근접 매수 시그널을 생성합니다.
    - 고점 추격 매수를 방지
    - 기관의 지지선(VWAP)에서 매수
    - IntradayBarAccumulator의 VWAPState를 활용
    """
    name = "VWAPPullback"
    display_name = "VWAP 눌림목 (단타)"
    description = "VWAP 기반 실시간 눌림목 매수 전략 (데이 트레이딩)"

    @classmethod
    def get_parameters(cls) -> List[StrategyParameter]:
        return [
            StrategyParameter(
                "vwap_upper_band", "VWAP 상단 밴드 (%)",
                "float", 0.5, 0.1, 2.0,
                description="VWAP 위 이 범위 내에서 매수 허용"
            ),
            StrategyParameter(
                "vwap_lower_band", "VWAP 하단 밴드 (%)",
                "float", 0.2, 0.0, 1.0,
                description="VWAP 아래 이 범위 내에서 매수 허용"
            ),
            StrategyParameter(
                "min_bounce_pct", "최소 반등률 (%)",
                "float", 0.2, 0.05, 1.0,
                description="최근 저점 대비 이 이상 반등 시 진입"
            ),
            StrategyParameter(
                "min_volume_ratio", "최소 거래량 비율",
                "float", 1.0, 0.5, 5.0,
                description="VWAP 계산에 필요한 최소 거래량 비율"
            ),
            StrategyParameter(
                "max_pullback_pct", "최대 고점대비 하락률 (%)",
                "float", 1.5, 0.5, 5.0,
                description="고점 대비 이 이상 하락 시 '추세 이탈'로 간주하여 진입 제한"
            ),
        ]

    async def evaluate(self, symbol: str, data: pd.DataFrame) -> SignalResult:
        """
        일봉 DataFrame 기반 평가 (기존 인터페이스 호환).
        
        Note: VWAP 전략은 주로 evaluate_realtime()을 통해
        Board 데이터로 실시간 평가하지만, 기존 시스템 호환을 위해
        일봉 데이터로도 간이 평가를 수행합니다.
        """
        if len(data) < 5:
            return SignalResult(symbol=symbol, signal=False, score=0.0)
        
        # 일봉 기반 간이 VWAP 계산 (최근 5일)
        recent = data.tail(5).copy()
        typical_price = (recent["high"] + recent["low"] + recent["close"]) / 3
        vwap = (typical_price * recent["volume"]).sum() / recent["volume"].sum()
        
        current_price = float(data["close"].iloc[-1])
        open_price = float(data["open"].iloc[-1])
        
        # 간이 조건 체크
        trend_ok = current_price > open_price
        
        upper = self.get_param("vwap_upper_band") / 100
        lower = self.get_param("vwap_lower_band") / 100
        
        price_vs_vwap = (current_price - vwap) / vwap
        near_vwap = -lower <= price_vs_vwap <= upper
        
        signal = trend_ok and near_vwap
        score = 0.0
        if signal:
            # VWAP에 가까울수록 높은 점수
            closeness = 1.0 - abs(price_vs_vwap) / max(upper, lower)
            score = 70.0 + (closeness * 30.0)
        
        return SignalResult(
            symbol=symbol,
            signal=signal,
            score=score,
            details={
                "vwap": round(vwap, 1),
                "price_vs_vwap": f"{price_vs_vwap*100:+.2f}%",
                "trend": "Up" if trend_ok else "Down",
                "mode": "daily_fallback",
            }
        )

    def evaluate_realtime(
        self,
        symbol: str,
        current_price: float,
        open_price: float,
        day_high: float,
        vwap: float,
        recent_low: float,
        recent_prices: List[float],
        vwap_history: List[float] = None,
        market_trend: str = "Neutral",
    ) -> SignalResult:
        """
        실시간 Board 데이터 기반 VWAP 눌림목 평가.
        
        TradingService의 매 사이클에서 호출됩니다.
        
        Args:
            symbol: 종목 코드
            current_price: 현재가
            open_price: 당일 시가
            day_high: 당일 고가
            vwap: 현재 VWAP 값
            recent_low: 최근 N틱 저점
            recent_prices: 최근 가격 리스트
        """
        if vwap <= 0 or current_price <= 0 or open_price <= 0:
            return SignalResult(symbol=symbol, signal=False, score=0.0,
                              details={"reason": "insufficient_data"})
        
        upper_band = self.get_param("vwap_upper_band") / 100
        lower_band = self.get_param("vwap_lower_band") / 100
        min_bounce = self.get_param("min_bounce_pct") / 100
        max_pullback = self.get_param("max_pullback_pct") / 100
        
        # ── 조건 A: 추세 확인 ──
        # 현재가가 시가 대비 상승 추세
        trend_ok = current_price > open_price
        
        # ── 조건 B: VWAP 밴드 내 눌림 ──
        # 현재가가 고점을 찍고 VWAP 근처로 하락했는지
        price_vs_vwap = (current_price - vwap) / vwap
        near_vwap = -lower_band <= price_vs_vwap <= upper_band
        
        # 고점 대비 하락 확인 (눌림이 있었는지)
        had_pullback = day_high > current_price and day_high > vwap
        
        # ── 조건 C: 반등 확인 ──
        # 최근 저점에서 반등이 시작되었는지
        bounce_ok = False
        if recent_low > 0 and len(recent_prices) >= 3:
            bounce_pct = (current_price - recent_low) / recent_low
            bounce_ok = bounce_pct >= min_bounce
            
            # 추가: 직전 가격들이 하락→상승 패턴인지
            if len(recent_prices) >= 3:
                prev2, prev1, curr = recent_prices[-3], recent_prices[-2], recent_prices[-1]
                # 직전이 하락(음봉)이었고, 현재가 반등 중
                price_turning = prev2 > prev1 and curr > prev1
                bounce_ok = bounce_ok and price_turning
        
        # ── 조건 D: [NEW] VWAP 기울기 확인 ──
        # VWAP이 평평하거나 우상향하고 있어야 함
        vwap_slope_ok = True
        if vwap_history and len(vwap_history) >= 5:
            # 최근 5개 포인트 대비 VWAP이 유지되거나 상승
            vwap_slope_ok = vwap >= vwap_history[-5]
            
        # ── 조건 E: [NEW] 고점 대비 과도한 하락 방지 ──
        # 고점 대비 너무 많이 밀리면 지지선이 뚫릴 확률이 높음
        pullback_pct = (day_high - current_price) / day_high
        not_too_deep = pullback_pct <= max_pullback
        
        # ── 조건 F: [NEW] 시장 지수 연동 ──
        market_ok = market_trend != "Down"
        
        # ── 최종 시그널 ──
        signal = (trend_ok and near_vwap and (had_pullback or True) and 
                  bounce_ok and vwap_slope_ok and not_too_deep and market_ok)
        
        score = 0.0
        if signal:
            # VWAP에 가까울수록 + 반등이 클수록 높은 점수
            vwap_closeness = 1.0 - abs(price_vs_vwap) / max(upper_band, lower_band)
            bounce_strength = min(1.0, (current_price - recent_low) / recent_low / 0.01)
            score = 60.0 + (vwap_closeness * 20.0) + (bounce_strength * 20.0)
        
        return SignalResult(
            symbol=symbol,
            signal=signal,
            score=round(score, 1),
            details={
                "vwap": round(vwap, 1),
                "price_vs_vwap": f"{price_vs_vwap*100:+.2f}%",
                "trend": "Up" if trend_ok else "Down",
                "near_vwap": near_vwap,
                "bounce": bounce_ok,
                "pullback": had_pullback,
                "vwap_slope": vwap_slope_ok,
                "not_too_deep": not_too_deep,
                "market_ok": market_ok,
                "day_high": round(day_high, 1),
                "recent_low": round(recent_low, 1),
                "mode": "realtime",
            }
        )
