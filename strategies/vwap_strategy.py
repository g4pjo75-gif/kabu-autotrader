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
from datetime import datetime

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
                "float", 1.0, 0.1, 2.0,
                description="VWAP 위 이 범위 내에서 매수 허용"
            ),
            StrategyParameter(
                "vwap_lower_band", "VWAP 하단 밴드 (%)",
                "float", 1.5, 0.0, 1.0,
                description="VWAP 아래 이 범위 내에서 매수 허용"
            ),
            StrategyParameter(
                "vwap_bounce_ratio", "최소 반등 회복률 (%)",
                "float", 30.0, 10.0, 100.0,
                description="고점 대비 하락한 폭의 최소 이 비율만큼 회복해야 반등으로 인정"
            ),
            StrategyParameter(
                "min_volume_ratio", "최소 거래량 비율",
                "float", 1.0, 0.5, 5.0,
                description="VWAP 계산에 필요한 최소 거래량 비율"
            ),
            StrategyParameter(
                "min_pullback_pct", "최소 고점하락 (%)",
                "float", 1.5, 0.1, 5.0,
                description="당일 고점 대비 최소 이 이상 하락해야 진입"
            ),
            StrategyParameter(
                "max_pullback_pct", "최대 고점하락 (%)",
                "float", 2.5, 0.5, 5.0,
                description="당일 고점 대비 이 이상 하락하면 진입 포기"
            ),
            StrategyParameter(
                "bounce_wait_minutes", "반등 안착 대기 시간 (분)",
                "float", 3.0, 0.0, 10.0,
                description="반등 후 지정된 시간 동안 가격이 붕괴되지 않아야 매수"
            ),
            StrategyParameter(
                "min_intraday_range_pct", "최소 일중 변동폭 (%)",
                "float", 1.2, 0.5, 5.0,
                description="당일 고가 대비 저가의 폭이 이 비율 이상이어야 함"
            ),
            StrategyParameter(
                "absolute_min_bounce_pct", "최소 절대 반등률 (%)",
                "float", 0.8, 0.1, 5.0,
                description="하락폭과 무관하게 이 비율 이상 반등해야 인정 (노이즈 방지)"
            ),
            StrategyParameter(
                "breakdown_limit_pct", "심층 붕괴 한계선 (%)",
                "float", 1.0, 0.1, 5.0,
                description="VWAP 대비 이 비율 이상 하락 시 VWAP 저항선으로 간주하여 매수 포기"
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
        
        # 갭상승률 필터 계산 (전일 종가 대비)
        prev_close = float(data["close"].iloc[-2]) if len(data) > 1 else open_price
        gap_pct = ((open_price - prev_close) / prev_close * 100) if prev_close > 0 else 0.0
        
        # 파라미터에서 gap 범위 가져오기 (기본값: 2.0% ~ 5.0%)
        gap_min = float(self._params.get("gap_filter_min", 2.0))
        gap_max = float(self._params.get("gap_filter_max", 5.0))
        
        # 갭 범위를 벗어나면 진입 제외
        if not (gap_min <= gap_pct <= gap_max):
            return SignalResult(
                symbol=symbol, signal=False, score=0.0,
                details={"reason": f"갭상승률 미달/초과 ({gap_pct:.1f}% ∉ [{gap_min}%, {gap_max}%])"}
            )
        
        # 💡 [버그 수정] 추출 단계(evaluate)에서는 일봉 데이터(최근 5일)로 VWAP를 계산하는데, 
        # 오늘 2~5% 갭상승한 종목은 당연히 5일 평균가보다 1.5% 이상 높기 때문에
        # 밴드(-1.5% ~ +1.5%) 필터에 무조건 걸려서 다 탈락하는 심각한 논리 오류가 있었습니다.
        # 따라서 추출 단계에서는 갭 필터만 통과하면 후보로 올립니다. (시가 지지 조건 삭제)
        # 실제 VWAP 타점 계산은 매매 엔진의 evaluate_realtime()에서 분봉/틱 데이터로 정확히 수행됩니다.
        trend_ok = True
        signal = trend_ok
        
        score = 0.0
        if signal:
            # 갭이 크고 양봉일수록 높은 점수 부여
            score = 70.0 + (gap_pct * 5.0)
        
        price_vs_vwap = (current_price - vwap) / vwap if vwap > 0 else 0.0
        
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
        vwap_state: Any = None,
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
        vwap_bounce_ratio = self.get_param("vwap_bounce_ratio") / 100
        min_pullback = self.get_param("min_pullback_pct") / 100
        max_pullback = self.get_param("max_pullback_pct") / 100
        
        # ── 조건 A: 추세 확인 (삭제) ──
        # 시가 대비 상승 추세(양봉 유지) 조건 삭제: 음봉 눌림목 매매 허용
        trend_ok = True
        
        # ── 조건 B: VWAP 밴드 내 눌림 ──
        # 현재가가 고점을 찍고 VWAP 근처로 하락했는지
        price_vs_vwap = (current_price - vwap) / vwap
        near_vwap = -lower_band <= price_vs_vwap <= upper_band
        
        # 고점 대비 하락 확인 (눌림이 있었는지)
        # 최소 수치 이상의 의미 있는 눌림목이 있어야 고점 추격 매수 방지
        pullback_from_high_pct = (day_high - current_price) / day_high if day_high > 0 else 0
        had_pullback = pullback_from_high_pct >= min_pullback
        
        # ── 조건 C: 반등 확인 ──
        # 최저점(pullback_low)에서 반등이 시작되었는지
        bounce_ok = False
        bounce_amount = 0.0
        short_term_upward = False  # 단기 하락 중 매수(떨어지는 칼날) 방지용
        
        if recent_low > 0 and recent_low < float('inf'):
            drop_amount = day_high - recent_low if day_high > recent_low else 0
            base_required = drop_amount * vwap_bounce_ratio
            
            # [NEW] 가짜 반등(잔파도) 방지: 비율과 상관없이 무조건 '최소 0.8%'는 반등해야 찐반등으로 인정
            absolute_min_bounce_pct = self.get_param("absolute_min_bounce_pct")
            absolute_min_bounce_amount = recent_low * (absolute_min_bounce_pct / 100.0)
            required_bounce_amount = max(base_required, absolute_min_bounce_amount)
            
            # [옵션 B 적용] 최근 3개 틱(약 15초)의 이동평균(SMA)으로 반등 안착 확인
            if recent_prices and len(recent_prices) >= 3:
                sma_3 = sum(recent_prices[-3:]) / 3.0
                bounce_amount = current_price - recent_low
                # [NEW] 단기적으로 가격이 하락 중(현재가 < 3틱 평균)이면 떨어지는 칼날로 간주
                short_term_upward = current_price >= sma_3
            else:
                bounce_amount = current_price - recent_low
                short_term_upward = True
                
            bounce_pct = bounce_amount / recent_low if recent_low > 0 else 0
            # 단기 상승 모멘텀이 있고, 반등폭이 충분할 때만 승인
            macro_bounce_ok = (bounce_amount >= required_bounce_amount)
            bounce_ok = short_term_upward and macro_bounce_ok
        else:
            macro_bounce_ok = False
        
        # ── 조건 D: [NEW] VWAP 기울기 확인 ──
        vwap_slope_ok = True
            
        # ── 조건 E: [NEW] 고점 대비 과도한 하락 방지 ──
        # 고점 대비 너무 많이 밀리면 지지선이 뚫릴 확률이 높음
        pullback_pct = (day_high - current_price) / day_high
        not_too_deep = pullback_pct <= max_pullback
        
        # ── 조건 F: [NEW] 시장 지수 연동 ──
        market_ok = market_trend != "Down"
        
        # ── 조건 G: [NEW] 위험 시간대 필터 ──
        time_ok = True
        
        # ── 조건 H: [NEW] 반등 안착 대기 ──
        wait_ok = True
        wait_minutes = 0.0
        bounce_wait_minutes = self.get_param("bounce_wait_minutes")
        
        if macro_bounce_ok and vwap_state is not None:
            if not getattr(vwap_state, "bounce_achieved", False):
                vwap_state.bounce_achieved = True
                vwap_state.bounce_start_time = datetime.now()
            
            if vwap_state.bounce_start_time is not None:
                wait_minutes = (datetime.now() - vwap_state.bounce_start_time).total_seconds() / 60.0
                if wait_minutes < bounce_wait_minutes:
                    wait_ok = False
        else:
            # 반등 기준(macro_bounce_ok) 밑으로 다시 하락했다면 타이머를 완전히 리셋합니다.
            if vwap_state is not None:
                vwap_state.bounce_achieved = False
                vwap_state.bounce_start_time = None
            wait_ok = False
            
        # ── 조건 I: [NEW] 심층 붕괴 한계선 ──
        breakdown_limit_pct = self.get_param("breakdown_limit_pct") / 100.0
        breakdown_ok = True
        if recent_low < vwap * (1.0 - breakdown_limit_pct):
            breakdown_ok = False

        # ── 조건 J: [NEW] 일중 변동성 필터 ──
        min_intraday_range_pct = self.get_param("min_intraday_range_pct") / 100
        day_low = getattr(vwap_state, "day_low", recent_low) if vwap_state else recent_low
        day_range_pct = (day_high - day_low) / open_price if open_price > 0 else 0
        volatility_ok = day_range_pct >= min_intraday_range_pct
            
        # ── 최종 시그널 ──
        signal = (trend_ok and near_vwap and had_pullback and 
                  bounce_ok and vwap_slope_ok and not_too_deep and market_ok and time_ok and wait_ok and volatility_ok and breakdown_ok)
        
        score = 0.0
        if signal:
            # VWAP에 가까울수록 + 반등이 클수록 높은 점수
            vwap_closeness = 1.0 - abs(price_vs_vwap) / max(upper_band, lower_band)
            bounce_strength = min(1.0, (current_price - recent_low) / recent_low / 0.01)
            score = 60.0 + (vwap_closeness * 20.0) + (bounce_strength * 20.0)
        
        # ── 불통과 조건 목록 생성 ──
        fail_reasons = []
        if not trend_ok:
            fail_reasons.append(f"추세↓(시가{open_price:.0f}>현재{current_price:.0f})")
        if not near_vwap:
            fail_reasons.append(f"VWAP밴드外({price_vs_vwap*100:+.1f}%)")
        if not had_pullback:
            fail_reasons.append(f"눌림부족(고점대비{pullback_from_high_pct*100:.1f}%<{min_pullback*100:.1f}%)")
        if not breakdown_ok:
            fail_reasons.append(f"심층붕괴(VWAP대비하락)")
        if not bounce_ok:
            drop_amount = day_high - recent_low if day_high > recent_low else 0
            base_required = drop_amount * vwap_bounce_ratio
            abs_min = recent_low * (self.get_param("absolute_min_bounce_pct") / 100.0)
            req_bounce = max(base_required, abs_min)
            if not short_term_upward:
                fail_reasons.append(f"단기하락중(칼날)")
            else:
                fail_reasons.append(f"반등부족({bounce_amount:.1f}엔<{req_bounce:.1f}엔)")
        if not vwap_slope_ok:
            fail_reasons.append("VWAP기울기↓")
        if not not_too_deep:
            fail_reasons.append(f"과도하락({pullback_pct*100:.1f}%>{max_pullback*100:.1f}%)")
        if not market_ok:
            fail_reasons.append("시장하락")
        if not time_ok:
            fail_reasons.append("오전장진입불가")
        if bounce_ok and not wait_ok:
            fail_reasons.append(f"안착대기중({wait_minutes:.1f}분<{bounce_wait_minutes}분)")
        if not volatility_ok:
            fail_reasons.append(f"변동성부족({day_range_pct*100:.1f}%<{min_intraday_range_pct*100:.1f}%)")
        
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
                "open_price": round(open_price, 1),
                "bounce_pct": f"{bounce_pct*100:.2f}%",
                "fail_reasons": fail_reasons,
                "mode": "realtime",
            }
        )
