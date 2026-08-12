# -*- coding: utf-8 -*-
"""
High Breakout Strategy - Day Trading

당일 최고가를 실시간으로 돌파할 때 
거래량 급증 동반 여부를 확인하고 추격 매수하는 전략입니다.
상한가 근처 추격 매수를 방지하기 위한 최대 상승률 제한 안전장치가 포함되어 있습니다.
"""
from collections import defaultdict
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import pandas as pd

from .base import (
    BaseExtractionStrategy,
    SignalResult,
    StrategyParameter,
)


class HighBreakoutStrategy(BaseExtractionStrategy):
    """
    당일 고가 돌파 추격 매수 전략 (단타 전용)
    
    장중 실시간 고가를 상향 돌파 시 거래량 급증을 동반하였는지 확인 후 즉시 진입합니다.
    """
    name = "HighBreakoutStrategy"
    display_name = "고가 돌파 (단타)"
    description = "당일 고가 상향 돌파 시 거래량 급증을 동반한 추격 매수"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # 종목별 거래량 이력 추적 (거래량 급증 필터용)
        # {symbol: [vol_delta1, vol_delta2, ...]}
        self._volume_deltas = defaultdict(list)
        # {symbol: last_cumulative_volume}
        self._last_volumes = defaultdict(int)

    @classmethod
    def get_parameters(cls) -> List[StrategyParameter]:
        return [
            StrategyParameter(
                "breakout_margin_pct", "돌파 마진 비율 (%)",
                "float", 0.1, 0.0, 1.0,
                description="당일 고가 대비 최소 이 비율 이상 돌파 시 진입 허용"
            ),
            StrategyParameter(
                "volume_spurt_ratio", "거래량 급증 배수",
                "float", 1.5, 1.0, 5.0,
                description="최근 5주기(약 25초) 평균 대비 현재 거래량 변화 배수"
            ),
            StrategyParameter(
                "max_daily_rise_pct", "당일 최대 상승률 제한 (%)",
                "float", 25.0, 5.0, 30.0,
                description="시가 대비 이 비율 초과 폭등 시 추격 매수 금지 (상한가 추격 방지)"
            ),
            StrategyParameter(
                "max_drawdown_limit_pct", "당일 고가 대비 최대 허용 낙폭 (%)",
                "float", 3.0, 0.5, 10.0,
                description="당일 고가 대비 이 비율 이상 크게 하락했던 종목은 돌파하더라도 가짜 돌파로 간주하여 매수 금지"
            ),
            StrategyParameter(
                "morning_wait_minutes", "장 시작 후 매수 보류 시간 (분)",
                "int", 30, 0, 120,
                description="개장 직후 이 시간 동안은 고가 돌파 매수를 하지 않고 관망하여 진짜 당일 고가를 탐색"
            ),
        ]

    async def evaluate(self, symbol: str, data: pd.DataFrame) -> SignalResult:
        """
        일봉 DataFrame 기반 간이 평가 (기존 인터페이스 호환용).
        """
        if len(data) < 5:
            return SignalResult(symbol=symbol, signal=False, score=0.0)
            
        recent = data.tail(5).copy()
        current_price = float(data["close"].iloc[-1])
        open_price = float(data["open"].iloc[-1])
        
        # 일봉 기준: 최근 5일 중 고점을 오늘 종가로 돌파했는지 간이 체크
        prev_high = float(recent["high"].iloc[:-1].max())
        is_breakout = current_price >= prev_high
        
        # 상승률 한도 체크
        rise_pct = (current_price - open_price) / open_price * 100
        max_rise = self.get_param("max_daily_rise_pct")
        safe_rise = rise_pct <= max_rise
        
        signal = is_breakout and safe_rise
        score = 0.0
        if signal:
            score = 80.0
            
        return SignalResult(
            symbol=symbol,
            signal=signal,
            score=score,
            details={
                "prev_high": prev_high,
                "rise_pct": f"{rise_pct:.2f}%",
                "mode": "daily_fallback"
            }
        )

    def evaluate_realtime(
        self,
        symbol: str,
        current_price: float,
        open_price: float,
        day_high: float,
        cumulative_volume: int,
        market_trend: str = "Neutral",
        pullback_low: float = 0.0,
    ) -> SignalResult:
        """
        실시간 Board 데이터 기반 고가 돌파 평가.
        
        TradingService의 매 사이클에서 호출됩니다.
        
        Args:
            symbol: 종목 코드
            current_price: 현재가
            open_price: 당일 시가
            day_high: 당일 최고가 (갱신 전 기준)
            cumulative_volume: 당일 누적 거래량
            market_trend: 시장 지수 트렌드
            pullback_low: 고점 형성 이후 최저가 (낙폭 계산용)
        """
        if current_price <= 0 or open_price <= 0 or cumulative_volume <= 0:
            return SignalResult(symbol=symbol, signal=False, score=0.0,
                              details={"reason": "insufficient_data"})
                              
        margin_pct = self.get_param("breakout_margin_pct") / 100
        spurt_ratio = self.get_param("volume_spurt_ratio")
        max_rise_pct = self.get_param("max_daily_rise_pct")
        max_drawdown_pct = self.get_param("max_drawdown_limit_pct")
        morning_wait_minutes = self.get_param("morning_wait_minutes")
        
        # ── 0. 아침 관망 시간 필터 ──
        import datetime
        now = datetime.datetime.now()
        market_open = now.replace(hour=9, minute=0, second=0, microsecond=0)
        minutes_since_open = (now - market_open).total_seconds() / 60.0
        
        if morning_wait_minutes > 0 and 0 <= minutes_since_open < morning_wait_minutes:
            return SignalResult(
                symbol=symbol, signal=False, score=0.0,
                details={
                    "reason": "morning_wait", 
                    "msg": f"개장 후 {morning_wait_minutes}분 관망 중 ({minutes_since_open:.0f}분 경과)"
                }
            )
        
        # ── 1. 거래량 증가폭(Delta) 계산 ──
        last_vol = self._last_volumes[symbol]
        vol_delta = 0
        if last_vol > 0:
            vol_delta = max(0, cumulative_volume - last_vol)
        
        # 현재 누적 거래량 갱신
        self._last_volumes[symbol] = cumulative_volume
        
        # ── 2. 최근 거래량 이력 관리 (최근 5주기) ──
        recent_deltas = self._volume_deltas[symbol]
        if vol_delta > 0:
            recent_deltas.append(vol_delta)
            if len(recent_deltas) > 5:
                recent_deltas.pop(0)
        
        # ── 3. 거래량 급증 조건 판단 ──
        volume_ok = True
        avg_delta = 0.0
        
        # 이력이 최소 3개 이상 쌓여야 유의미한 평균과 비교 가능
        if len(recent_deltas) >= 3:
            # 현재 틱(마지막 델타)을 제외한 직전 평균
            prev_deltas = recent_deltas[:-1]
            avg_delta = sum(prev_deltas) / len(prev_deltas) if prev_deltas else 0.0
            
            if avg_delta > 0:
                volume_ok = vol_delta >= (avg_delta * spurt_ratio)
            else:
                volume_ok = True  # 이전 거래량이 아예 없었다면 첫 거래량 유입으로 인정
        
        # ── 4. 고가 돌파 조건 판단 ──
        # day_high가 0이 아니며 현재가가 이전 고가보다 일정 마진 이상 높음
        breakout_ok = False
        if day_high > 0:
            # 돌파 임계가 계산 (고가 + 마진)
            breakout_threshold = day_high * (1 + margin_pct)
            breakout_ok = current_price >= breakout_threshold
            
        # ── 5. 상승 폭 안전장치 (상한가 추격 매수 방지) ──
        rise_pct = (current_price - open_price) / open_price * 100
        not_too_high = rise_pct <= max_rise_pct
        
        # ── 6. 고가 대비 심층 붕괴(Drawdown) 방어 ──
        # 고점 형성 이후 한 번이라도 -N% 이상 크게 무너진 적이 있다면
        # 현재 반등하여 고가를 돌파하더라도 가짜 돌파(데드캣 바운스)로 간주
        drawdown_ok = True
        actual_drawdown = 0.0
        if day_high > 0 and pullback_low > 0 and day_high > pullback_low:
            actual_drawdown = (day_high - pullback_low) / day_high * 100.0
            if actual_drawdown >= max_drawdown_pct:
                drawdown_ok = False
        
        # ── 7. 시장 지수 필터 ──
        market_ok = market_trend != "Down"
        
        # ── 최종 매수 승인 판단 ──
        # 돌파 + 거래량 급증 + 상승폭 안전 + 심층 붕괴 없음 + 지수 안정
        signal = breakout_ok and volume_ok and not_too_high and drawdown_ok and market_ok
        
        score = 0.0
        if signal:
            # 상승세 강도 및 거래량 강도에 따른 보너스 점수
            vol_bonus = min(20.0, (vol_delta / (avg_delta if avg_delta > 0 else 1) * 5.0))
            score = 70.0 + vol_bonus + min(10.0, rise_pct / max_rise_pct * 10.0)
            
        return SignalResult(
            symbol=symbol,
            signal=signal,
            score=round(score, 1),
            details={
                "day_high": round(day_high, 1),
                "threshold": round(day_high * (1 + margin_pct), 1),
                "rise_pct": f"{rise_pct:.2f}%",
                "vol_delta": vol_delta,
                "avg_delta": round(avg_delta, 1),
                "drawdown": f"-{actual_drawdown:.1f}%",
                "breakout_ok": breakout_ok,
                "volume_spurt": volume_ok,
                "not_too_high": not_too_high,
                "drawdown_ok": drawdown_ok,
                "market_ok": market_ok,
                "mode": "realtime"
            }
        )
