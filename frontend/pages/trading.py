# -*- coding: utf-8 -*-
"""
Auto-Trading Page

Trading controls and execution strategy configuration.
Supports multiple strategy configurations with persistence.
"""
from nicegui import ui
from typing import Any, Dict, Optional


# Strategy Guide Content
STRATEGY_GUIDE_MD = """
### 🟢 매수 전략 (Dip Buy Logic)

**눌림목 매수 (Dip Buy)**
- 종목 추출 전략에 의해 검색된 종목의 **분석 시점 가격(기준가)**을 기록합니다.
- 이후 매 사이클(5초)마다 현재가를 확인하여, 기준가 대비 **설정된 %만큼 하락**하면 매수합니다.
- 예: 기준가 1,000엔, 눌림목 1.5% 설정 → 985엔 이하에서 매수 실행.
- 눌림목 %를 0으로 설정하면 종목 검색 즉시 매수합니다.
- 수량은 **100주 고정**입니다.

---

### 🔴 매도 및 리스크 관리 (Sell & Risk Logic)

**1. 기본 손절 (BasicLossCutManager)**
- 가장 기본적인 손절 로직입니다.
- 진입 가격 대비 **-X% 손실** 발생 시 즉시 시장가로 매도(손절)합니다.
- 예: 손절 5% 설정 시, 10,000원 매수 -> 9,500원 도달 시 매도.

**2. 터틀 안전 취소 (TurtleSafetyCancel)**
- 주문을 낸 후 일정 시간(예: 60초) 동안 **체결되지 않으면 자동으로 주문을 취소**합니다.
- 시장 상황이 급변하거나, 주문이 잊혀지는 것을 방지합니다.

**3. 가격 괴리 취소 (PriceRangeCanceller)**
- 주문 가격과 현재 시장 가격의 **괴리(Gap)가 너무 커지면** 주문을 취소합니다.
- 예: 10,000원에 매수 걸어뒀는데 호재로 11,000원으로 급등 시, 추격 매수하지 않고 취소.

---

### 🛡️ 매매 중단 안전 장치 (Market Safety Filter)

아래 조건 중 **하나라도 만족**하면 당일 신규 매수를 전면 정지합니다.
(이미 보유 중인 종목의 매도/청산은 정상 작동)

1. **S&P 500 전일 하락률 ≤ -1.0%** — 글로벌 증시 전체 투심 악화
2. **NASDAQ 전일 하락률 ≤ -1.5%** — 기술주/반도체 투매 ➡️ 닛케이 직격탄 예상
3. **Nikkei 225 당일 시가 갭하락 ≤ -1.5%** — 외국인/기관의 일본 시장 엑소더스 확인

각 임계값은 전략별 설정에서 조정 가능합니다.
"""


async def trading_page(app_state: Dict[str, Any]) -> None:
    """
    Auto-Trading Page
    
    - Multiple strategy management
    - Start/Stop controls
    - Target stocks per strategy
    """
    
    automation_service = app_state.get("automation_service")
    
    # ========== Strategy Edit Dialog ==========
    # State for the dialog
    edit_config_id = {"value": None}  # None = new, int = edit existing
    
    with ui.dialog() as strategy_dialog, ui.card().classes("w-[650px] bg-gray-800 p-6"):
        dialog_title = ui.label("새 전략 추가").classes("text-xl font-bold text-white mb-4")
        
        with ui.column().classes("w-full gap-4"):
            # Strategy Name
            strategy_name_input = ui.input(
                label="전략 이름",
                placeholder="예: 공격적 골든크로스",
            ).classes("w-full").props("filled dark")
            
            ui.separator().classes("bg-gray-600")
            
            # 1. Target & Strategy
            ui.label("1. 발굴 및 전략").classes("text-indigo-300 font-semibold")
            with ui.grid(columns=2).classes("w-full gap-4"):
                universe_select = ui.select(
                    options={
                        "nikkei225": "Nikkei 225",
                        "nikkei400": "JPX-Nikkei 400",
                        "ranking_leaders": "📊 당일 주도주 (랭킹)"
                    },
                    value="nikkei225",
                    label="대상 종목군"
                ).props("filled dark")
                
                from backend.analysis_service import EXTRACTION_STRATEGIES as EXT_STRATS
                extract_strategies = {name: cls.display_name for name, cls in EXT_STRATS.items()}
                
                extract_select = ui.select(
                    options=extract_strategies,
                    value="SMAGoldenDeadCross",
                    label="종목 추출 전략"
                ).props("filled dark")

            # 2. 매매 설정
            ui.label("2. 매매 설정").classes("text-indigo-300 font-semibold mt-2")
            with ui.grid(columns=2).classes("w-full gap-4"):
                max_concurrent_input = ui.number(
                    "한번에 거래 가능한 종목 수", value=2, min=1, max=10
                ).props("filled dark").tooltip("동시에 보유하거나 감시할 최대 종목 수")
                
                daily_limit_input = ui.number(
                    "하루 최대 매매 종목 수", value=5, min=1, max=50
                ).props("filled dark").tooltip("당일 누적으로 최대 몇 개 종목까지 진입할지 설정")
                
                cooldown_days_input = ui.number(
                    "연속 거래 제한 (일)", value=2, min=0, max=10
                ).props("filled dark").tooltip("최근 N일 이내 매수 종목 재진입 방지 (0=미사용)")
            
            # 2.5 랭킹 전용 설정 (ranking_leaders 선택 시에만 표시)
            ranking_settings_container = ui.column().classes("w-full gap-3 mt-2")
            
            with ranking_settings_container:
                ui.label("📊 랭킹 추출 설정").classes("text-amber-300 font-semibold")
                
                with ui.row().classes("gap-4"):
                    ranking_type_select = ui.select(
                        options={
                            "5": "TICK 횟수",
                            "1": "상승률",
                            "4": "거래대금",
                            "6": "거래량 급증",
                            "7": "거래대금 급증",
                        },
                        value="1",
                        label="메인 랭킹 (필수)"
                    ).props("filled dark").classes("w-40")
                    
                    ranking_type2_select = ui.select(
                        options={
                            "none": "사용 안함",
                            "5": "TICK 횟수",
                            "1": "상승률",
                            "4": "거래대금",
                            "6": "거래량 급증",
                            "7": "거래대금 급증",
                        },
                        value="5",
                        label="보조 랭킹 (옵션)"
                    ).props("filled dark").classes("w-40").tooltip("선택 시 메인 랭킹과 보조 랭킹 모두에 포함된 종목만 추출합니다.")
                
                with ui.row().classes("gap-4 items-end"):
                    gap_min_input = ui.number(
                        "갭상승률 하한 (%)", value=2.0, step=0.5, min=0.0, max=10.0
                    ).props("filled dark suffix=%").classes("w-40").tooltip("전일 종가 대비 최소 갭상승률")
                    gap_max_input = ui.number(
                        "갭상승률 상한 (%)", value=5.0, step=0.5, min=0.5, max=20.0
                    ).props("filled dark suffix=%").classes("w-40").tooltip("전일 종가 대비 최대 갭상승률")
                    max_rise_input = ui.number(
                        "시가 대비 최대 상승률 (%)", value=2.5, step=0.5, min=0.5, max=10.0
                    ).props("filled dark suffix=%").classes("w-48").tooltip("스파이크 꼭대기 추격 매수 방지 (이 수치 초과 상승 시 진입 제외)")
            
            # ranking_leaders 선택 시에만 표시
            ranking_settings_container.bind_visibility_from(
                universe_select, "value",
                backward=lambda v: v == "ranking_leaders"
            )

            # 3. Time & Condition
            ui.label("3. 시간 및 조건").classes("text-indigo-300 font-semibold mt-2")
            with ui.grid(columns=2).classes("w-full gap-4"):
                start_time_input = ui.input("매매 시작 시간", value="09:00").props("filled dark type=time")
                end_time_input = ui.input("매매 종료 시간", value="15:00").props("filled dark type=time")
            
            with ui.grid(columns=2).classes("w-full gap-4 mt-2"):
                ext_end_time_input = ui.input("종목 검색 종료 시간", value="11:00").props("filled dark type=time").tooltip("이 시간까지만 새 종목을 검색합니다.")
                ext_interval_input = ui.number("검색 주기 (초)", value=120, min=30, max=3600).props("filled dark suffix=초").tooltip("몇 초마다 랭킹을 확인할지 설정합니다. (30초~1시간)")
            
            with ui.row().classes("items-center mt-2"):
                safety_filter_check = ui.checkbox("매매 중단 (안전 장치)", value=False).classes("text-white")
            
            with ui.column().classes("ml-8 mt-2 gap-2"):
                with ui.row().classes("gap-4 items-end"):
                    sp500_threshold_input = ui.number(
                        "S&P 500 하락 기준 (%)", value=1.0, step=0.1, min=0.1
                    ).props("filled dark suffix=%").classes("w-40")
                    nasdaq_threshold_input = ui.number(
                        "NASDAQ 하락 기준 (%)", value=1.5, step=0.1, min=0.1
                    ).props("filled dark suffix=%").classes("w-40")
                    nikkei_gap_threshold_input = ui.number(
                        "Nikkei 225 갭 기준 (%)", value=1.5, step=0.1, min=0.1
                    ).props("filled dark suffix=%").classes("w-40")
                sp500_threshold_input.bind_visibility_from(safety_filter_check, "value")
                nasdaq_threshold_input.bind_visibility_from(safety_filter_check, "value")
                nikkei_gap_threshold_input.bind_visibility_from(safety_filter_check, "value")

            ui.separator().classes("bg-gray-600 mt-4")
            
            # Save Button
            async def save_strategy():
                name = strategy_name_input.value.strip()
                if not name:
                    ui.notify("전략 이름을 입력해주세요", type="warning")
                    return
                
                config_data = {
                    "target_universe": universe_select.value,
                    "extraction_strategy": extract_select.value,
                    "max_concurrent_stocks": int(max_concurrent_input.value),
                    "daily_max_trades": int(daily_limit_input.value),
                    "recent_trade_cooldown_days": int(cooldown_days_input.value),
                    "max_stocks": int(max_concurrent_input.value), # For backward compatibility
                    "start_time": start_time_input.value,
                    "end_time": end_time_input.value,
                    "extraction_end_time": ext_end_time_input.value,
                    "extraction_interval": int(ext_interval_input.value),
                    "market_safety_filter": safety_filter_check.value,
                    "sp500_threshold": float(sp500_threshold_input.value),
                    "nasdaq_threshold": float(nasdaq_threshold_input.value),
                    "nikkei_gap_threshold": float(nikkei_gap_threshold_input.value),
                }
                
                # 랭킹 전용 설정 추가
                if universe_select.value == "ranking_leaders":
                    config_data["ranking_type"] = ranking_type_select.value
                    config_data["secondary_ranking_type"] = ranking_type2_select.value
                    config_data["gap_filter_min"] = float(gap_min_input.value)
                    config_data["gap_filter_max"] = float(gap_max_input.value)
                    config_data["max_rise_from_open_pct"] = float(max_rise_input.value)
                    # 사용자가 선택한 추출 전략을 그대로 사용 (VWAPPullback, HighBreakoutStrategy 등)
                
                if automation_service:
                    automation_service.save_config(
                        name=name,
                        config_data=config_data,
                        config_id=edit_config_id["value"],
                        is_active=True
                    )
                    automation_service.schedule_jobs()
                    ui.notify(f"전략 '{name}' 저장됨", type="positive")
                    strategy_dialog.close()
                    render_strategy_list()
                else:
                    ui.notify("자동화 서비스를 찾을 수 없습니다.", type="negative")

            with ui.row().classes("w-full justify-end"):
                ui.button("취소", on_click=strategy_dialog.close).classes("text-gray-400 mr-2")
                ui.button("저장", on_click=save_strategy, icon="save").classes("bg-indigo-600 text-white")
    
    def open_new_strategy_dialog():
        """Open dialog for new strategy"""
        edit_config_id["value"] = None
        dialog_title.text = "새 전략 추가"
        strategy_name_input.value = ""
        universe_select.value = "nikkei225"
        extract_select.value = "SMAGoldenDeadCross"
        max_concurrent_input.value = 2
        daily_limit_input.value = 5
        cooldown_days_input.value = 2
        start_time_input.value = "09:00"
        end_time_input.value = "15:00"
        safety_filter_check.value = False
        sp500_threshold_input.value = 1.0
        nasdaq_threshold_input.value = 1.5
        nikkei_gap_threshold_input.value = 1.5
        ext_end_time_input.value = "11:00"
        ext_interval_input.value = 120
        gap_min_input.value = 2.0
        gap_max_input.value = 5.0
        max_rise_input.value = 2.5
        strategy_dialog.open()
    
    def open_edit_strategy_dialog(config_id: int):
        """Open dialog for editing existing strategy"""
        config = automation_service.get_config(config_id)
        if not config:
            ui.notify("전략을 찾을 수 없습니다", type="negative")
            return
        
        edit_config_id["value"] = config_id
        dialog_title.text = f"전략 수정: {config.name}"
        cfg = config.config_json
        
        strategy_name_input.value = config.name
        universe_select.value = cfg.get("target_universe", "nikkei225")
        extract_select.value = cfg.get("extraction_strategy", "SMAGoldenDeadCross")
        max_concurrent_input.value = cfg.get("max_concurrent_stocks", cfg.get("max_stocks", 2))
        daily_limit_input.value = cfg.get("daily_max_trades", cfg.get("max_stocks", 5))
        cooldown_days_input.value = cfg.get("recent_trade_cooldown_days", 2)
        start_time_input.value = cfg.get("start_time", "09:00")
        end_time_input.value = cfg.get("end_time", "15:00")
        safety_filter_check.value = cfg.get("market_safety_filter", cfg.get("us_market_filter", False))
        sp500_threshold_input.value = cfg.get("sp500_threshold", cfg.get("us_market_threshold", 1.0))
        nasdaq_threshold_input.value = cfg.get("nasdaq_threshold", 1.5)
        nikkei_gap_threshold_input.value = cfg.get("nikkei_gap_threshold", 1.5)
        ext_end_time_input.value = cfg.get("extraction_end_time", "11:00")
        ext_interval_input.value = cfg.get("extraction_interval", 120)
        # 랭킹 전용 설정 복원
        ranking_type_select.value = cfg.get("ranking_type", "5")
        ranking_type2_select.value = cfg.get("secondary_ranking_type", "none")
        gap_min_input.value = cfg.get("gap_filter_min", 2.0)
        gap_max_input.value = cfg.get("gap_filter_max", 5.0)
        max_rise_input.value = cfg.get("max_rise_from_open_pct", 2.5)
        strategy_dialog.open()
    
    # Dialog for Strategy Guide
    with ui.dialog() as guide_dialog, ui.card().classes("w-full max-w-3xl"):
        with ui.row().classes("w-full items-center justify-between mb-4"):
            with ui.row().classes("items-center"):
                ui.icon("school").classes("text-indigo-500 text-xl mr-2")
                ui.label("매매 전략 가이드").classes("text-xl font-bold text-white")
            ui.button(icon="close", on_click=guide_dialog.close).props("flat round dense").classes("text-gray-400")
        
        ui.separator().classes("mb-4")
        ui.markdown(STRATEGY_GUIDE_MD).classes("text-gray-300 w-full")
        
        with ui.row().classes("w-full justify-end mt-6"):
            ui.button("닫기", on_click=guide_dialog.close).classes("bg-gray-700 text-white")

    # Header
    with ui.row().classes("w-full items-center justify-between mb-6"):
        title_text = "자동 매매 (모의 투자 - Real Data)" if app_state.get("simulation_mode") else "자동 매매 (실전 투자)"
        ui.label(title_text).classes("text-2xl font-bold text-white")
        
        with ui.row().classes("gap-2"):
            ui.button("가이드", icon="help_outline", on_click=guide_dialog.open).classes("bg-gray-700 text-white")
            ui.button("새 전략 추가", icon="add", on_click=open_new_strategy_dialog).classes("bg-indigo-600 text-white")

    # Status Banner
    with ui.card().classes("w-full bg-gray-800 rounded-lg p-4 mb-6"):
        with ui.row().classes("items-center justify-between"):
            with ui.row().classes("items-center"):
                is_running = app_state.get("trading_active", False)
                status_class = "bg-green-500" if is_running else "bg-red-500"
                ui.element("div").classes(f"w-3 h-3 rounded-full {status_class} mr-3")
                ui.label(
                    "자동 매매 가동 중" if is_running else "자동 매매 중지됨"
                ).classes("text-lg font-semibold text-white")
                
                # Market Trend indicator
                market_trend = app_state.get("trading_service")._market_trend if app_state.get("trading_service") else "Neutral"
                trend_color = "text-green-400" if market_trend == "Up" else "text-red-400" if market_trend == "Down" else "text-gray-400"
                trend_icon = "trending_up" if market_trend == "Up" else "trending_down" if market_trend == "Down" else "trending_flat"
                
                with ui.row().classes("ml-6 items-center"):
                    ui.icon(trend_icon).classes(f"{trend_color} mr-1")
                    ui.label(f"Nikkei Trend: {market_trend}").classes(f"text-sm font-medium {trend_color}")
            
            with ui.row().classes("gap-2"):
                async def start_trading():
                    if not app_state.get("connected"):
                        ui.notify("먼저 API 연결을 해주세요", type="warning")
                        return
                    
                    scheduler = app_state.get("scheduler")
                    trading_service = app_state.get("trading_service")
                    
                    if scheduler and trading_service:
                        scheduler.start()
                        scheduler.add_interval_job(
                            trading_service.run_trading_cycle,
                            job_id="trading_loop",
                            seconds=5,
                        )
                    
                    app_state["trading_active"] = True
                    ui.notify("자동 매매를 시작했습니다 (5초 주기)", type="positive")
                
                async def stop_trading():
                    app_state["trading_active"] = False
                    
                    scheduler = app_state.get("scheduler")
                    if scheduler:
                        try:
                            scheduler.remove_job("trading_loop")
                        except:
                            pass
                        
                    ui.notify("자동 매매를 중지했습니다", type="info")
                
                ui.button("시작", on_click=start_trading, icon="play_arrow").classes("bg-green-600 text-white")
                ui.button("중지", on_click=stop_trading, icon="stop").classes("bg-red-600 text-white")
    
    # ========== Global Trading Settings ==========
    with ui.card().classes("w-full bg-gray-800 rounded-lg p-6 mb-6"):
        with ui.row().classes("items-center mb-4"):
            ui.icon("settings_suggest").classes("text-indigo-400 mr-2")
            ui.label("전역 매매 설정 (공통)").classes("text-lg font-semibold text-white")
        
        ui.separator().classes("mb-4")
        
        with ui.row().classes("w-full gap-4 items-end flex-wrap"):
            tp_pct = app_state.get("take_profit_pct", 1.0)
            lc_pct = app_state.get("loss_cut_pct", 3.0)
            ts_pct = app_state.get("trailing_stop_pct", 3.0)
            max_trades = app_state.get("max_trades_per_symbol", 1)
            max_buy_price = app_state.get("max_buy_price", 5000)
            dip_buy = app_state.get("dip_buy_pct", 1.5)
            
            tp_input = ui.number("익절 % (+)", value=tp_pct, step=0.1, min=0.1).props("filled dark suffix=%").classes("w-32")
            lc_input = ui.number("손절 % (-)", value=lc_pct, step=0.1, min=0.1).props("filled dark suffix=%").classes("w-32")
            ts_input = ui.number("트레일링 스탑 % (-)", value=ts_pct, step=0.1, min=0.1).props("filled dark suffix=%").classes("w-32")
            dip_input = ui.number("눌림목 매수 %", value=dip_buy, step=0.1, min=0.0, max=5.0).props("filled dark suffix=%").classes("w-32").tooltip("기준가 대비 N% 하락 시 매수 (0=즉시 매수)")
            max_trades_input = ui.number("당일 매수 제한 (종목당)", value=max_trades, step=1, min=1).props("filled dark suffix=회").classes("w-40")
            max_buy_price_input = ui.number("매수 상한가", value=max_buy_price, step=500, min=100).props("filled dark suffix=¥").classes("w-40")
            
            target_timeout = app_state.get("target_timeout_minutes", 60)
            target_timeout_input = ui.number("대기 타임아웃", value=target_timeout, step=10, min=0, max=480).props("filled dark suffix=분").classes("w-32").tooltip("매수 조건 미충족 시 자동 제거 시간 (0=무제한 대기)")
        
        # 단계별 트레일링 스톱 설정 섹션
        with ui.row().classes("w-full gap-4 items-end flex-wrap mt-2"):
            ui.icon("trending_up").classes("text-indigo-400")
            ui.label("단계별 트레일링 스톱 설정").classes("text-indigo-300 font-semibold mr-4")
            
            st_enabled = app_state.get("stepped_trailing_enabled", True)
            st_activate = app_state.get("stepped_trailing_activate_pct", 0.8)
            st_step1 = app_state.get("stepped_trailing_step1_pct", 0.5)
            st_step2 = app_state.get("stepped_trailing_step2_pct", 2.0)
            st_step2_trail = app_state.get("stepped_trailing_step2_trail_pct", 0.3)
            
            st_enabled_input = ui.checkbox("활성화", value=st_enabled).props("dark").classes("mb-2")
            st_activate_input = ui.number("1단계 활성화 %", value=st_activate, step=0.1, min=0.1).props("filled dark suffix=%").classes("w-36").tooltip("이 수익률 도달 시 트레일링 스톱 활성화 (이전에는 고정 익절 대기)")
            st_step1_input = ui.number("1단계 트레일링 %", value=st_step1, step=0.1, min=0.1).props("filled dark suffix=%").classes("w-36").tooltip("고점 대비 N% 하락 시 익절 매도")
            st_step2_input = ui.number("2단계 강화 기준 %", value=st_step2, step=0.1, min=0.1).props("filled dark suffix=%").classes("w-40").tooltip("이 수익률 도달 시 트레일링 스톱 폭을 더 좁힘")
            st_step2_trail_input = ui.number("2단계 트레일링 %", value=st_step2_trail, step=0.1, min=0.1).props("filled dark suffix=%").classes("w-36").tooltip("2단계 도달 후 고점 대비 N% 하락 시 익절 매도")
            
        # VWAP 전략 설정 섹션
        with ui.row().classes("w-full gap-4 items-end flex-wrap mt-2"):
            ui.icon("show_chart").classes("text-amber-400")
            ui.label("VWAP 전략 설정").classes("text-amber-300 font-semibold mr-4")
            
            vwap_upper = app_state.get("vwap_upper_band", 0.5)
            vwap_lower = app_state.get("vwap_lower_band", 0.2)
            vwap_bounce = app_state.get("vwap_min_bounce", 0.2)
            
            vwap_upper_input = ui.number("VWAP 상단 밴드 (%)", value=vwap_upper, step=0.1, min=0.1, max=3.0).props("filled dark suffix=%").classes("w-32").tooltip("VWAP 위 이 범위 내에서 매수 허용")
            vwap_lower_input = ui.number("VWAP 하단 밴드 (%)", value=vwap_lower, step=0.1, min=0.0, max=2.0).props("filled dark suffix=%").classes("w-32").tooltip("VWAP 아래 이 범위 내에서 매수 허용")
            vwap_bounce_input = ui.number("최소 반등률 (%)", value=vwap_bounce, step=0.05, min=0.05, max=2.0).props("filled dark suffix=%").classes("w-32").tooltip("최근 저점 대비 이 이상 반등 시 진입")
            
            vwap_pullback = app_state.get("max_pullback_pct", 1.5)
            vwap_pullback_input = ui.number("최대 고점하락 %", value=vwap_pullback, step=0.1, min=0.5, max=5.0).props("filled dark suffix=%").classes("w-32").tooltip("고점 대비 이 이상 하락 시 진입 제한")
            
        # 고가 돌파 전략 설정 섹션
        with ui.row().classes("w-full gap-4 items-end flex-wrap mt-2"):
            ui.icon("trending_up").classes("text-green-400")
            ui.label("고가 돌파 전략 설정").classes("text-green-300 font-semibold mr-4")
            
            breakout_margin = app_state.get("breakout_margin_pct", 0.1)
            volume_spurt = app_state.get("volume_spurt_ratio", 1.5)
            max_daily_rise = app_state.get("max_daily_rise_pct", 25.0)
            
            breakout_margin_input = ui.number("돌파 마진율 (%)", value=breakout_margin, step=0.05, min=0.0, max=2.0).props("filled dark suffix=%").classes("w-32").tooltip("당일 고가 대비 최소 이 비율 이상 돌파 시 진입 허용")
            volume_spurt_input = ui.number("거래량 급증 배수", value=volume_spurt, step=0.1, min=1.0, max=5.0).props("filled dark").classes("w-32").tooltip("최근 평균 대비 현재 거래량 변화 배수")
            max_daily_rise_input = ui.number("당일 최대 상승률 (%)", value=max_daily_rise, step=1.0, min=5.0, max=30.0).props("filled dark suffix=%").classes("w-40").tooltip("시가 대비 이 비율 초과 폭등 시 추격 매수 금지 (상한가 추격 방지)")
            
        # 시장 지수 필터 설정 섹션
        with ui.row().classes("w-full gap-4 items-end flex-wrap mt-2"):
            ui.icon("analytics").classes("text-blue-400")
            ui.label("시장 지수(Nikkei) 필터 설정").classes("text-blue-300 font-semibold mr-4")
            
            n225_down = app_state.get("market_index_down_threshold", 0.1)
            n225_up = app_state.get("market_index_up_threshold", 0.05)
            global_gap_threshold = app_state.get("global_nikkei_gap_threshold", 1.0)
            
            n225_down_input = ui.number("지수 급락 기준 (%)", value=n225_down, step=0.01, min=0.01, max=1.0).props("filled dark suffix=%").classes("w-40").tooltip("1분간 이 이상 하락 시 매수 중단 (예: 0.1)")
            n225_up_input = ui.number("지수 회복 기준 (%)", value=n225_up, step=0.01, min=0.01, max=1.0).props("filled dark suffix=%").classes("w-40").tooltip("1분간 이 이상 상승 시 매수 재개 (예: 0.05)")
            global_gap_threshold_input = ui.number("갭상승 추출 지연 기준 (%)", value=global_gap_threshold, step=0.1, min=0.5, max=5.0).props("filled dark suffix=%").classes("w-48").tooltip("닛케이 시가가 이 수치 이상 갭상승 시, 오전 장(10:30)까지 종목 추출을 지연합니다.")
            
            def save_global_sell_settings():
                if automation_service:
                    db = automation_service.db
                    db.set_setting("take_profit_pct", str(tp_input.value))
                    db.set_setting("loss_cut_pct", str(lc_input.value))
                    db.set_setting("trailing_stop_pct", str(ts_input.value))
                    db.set_setting("dip_buy_pct", str(float(dip_input.value)))
                    db.set_setting("max_trades_per_symbol", str(int(max_trades_input.value)))
                    db.set_setting("max_buy_price", str(float(max_buy_price_input.value)))
                    db.set_setting("target_timeout_minutes", str(float(target_timeout_input.value)))
                    # Stepped Trailing Stop settings
                    db.set_setting("stepped_trailing_enabled", "true" if st_enabled_input.value else "false")
                    db.set_setting("stepped_trailing_activate_pct", str(float(st_activate_input.value)))
                    db.set_setting("stepped_trailing_step1_pct", str(float(st_step1_input.value)))
                    db.set_setting("stepped_trailing_step2_pct", str(float(st_step2_input.value)))
                    db.set_setting("stepped_trailing_step2_trail_pct", str(float(st_step2_trail_input.value)))
                    # VWAP settings
                    db.set_setting("vwap_upper_band", str(float(vwap_upper_input.value)))
                    db.set_setting("vwap_lower_band", str(float(vwap_lower_input.value)))
                    db.set_setting("vwap_min_bounce", str(float(vwap_bounce_input.value)))
                    db.set_setting("max_pullback_pct", str(float(vwap_pullback_input.value)))
                    # High Breakout settings
                    db.set_setting("breakout_margin_pct", str(float(breakout_margin_input.value)))
                    db.set_setting("volume_spurt_ratio", str(float(volume_spurt_input.value)))
                    db.set_setting("max_daily_rise_pct", str(float(max_daily_rise_input.value)))
                    # Market settings
                    db.set_setting("market_index_down_threshold", str(float(n225_down_input.value)))
                    db.set_setting("market_index_up_threshold", str(float(n225_up_input.value)))
                    db.set_setting("global_nikkei_gap_threshold", str(float(global_gap_threshold_input.value)))
                    
                    app_state["take_profit_pct"] = float(tp_input.value)
                    app_state["loss_cut_pct"] = float(lc_input.value)
                    app_state["trailing_stop_pct"] = float(ts_input.value)
                    app_state["dip_buy_pct"] = float(dip_input.value)
                    app_state["max_trades_per_symbol"] = int(max_trades_input.value)
                    app_state["max_buy_price"] = float(max_buy_price_input.value)
                    app_state["target_timeout_minutes"] = float(target_timeout_input.value)
                    # Stepped Trailing Stop settings
                    app_state["stepped_trailing_enabled"] = st_enabled_input.value
                    app_state["stepped_trailing_activate_pct"] = float(st_activate_input.value)
                    app_state["stepped_trailing_step1_pct"] = float(st_step1_input.value)
                    app_state["stepped_trailing_step2_pct"] = float(st_step2_input.value)
                    app_state["stepped_trailing_step2_trail_pct"] = float(st_step2_trail_input.value)
                    # VWAP settings
                    app_state["vwap_upper_band"] = float(vwap_upper_input.value)
                    app_state["vwap_lower_band"] = float(vwap_lower_input.value)
                    app_state["vwap_min_bounce"] = float(vwap_bounce_input.value)
                    app_state["max_pullback_pct"] = float(vwap_pullback_input.value)
                    # High Breakout settings
                    app_state["breakout_margin_pct"] = float(breakout_margin_input.value)
                    app_state["volume_spurt_ratio"] = float(volume_spurt_input.value)
                    app_state["max_daily_rise_pct"] = float(max_daily_rise_input.value)
                    # Market Index settings
                    app_state["market_index_down_threshold"] = float(n225_down_input.value)
                    app_state["market_index_up_threshold"] = float(n225_up_input.value)
                    app_state["global_nikkei_gap_threshold"] = float(global_gap_threshold_input.value)
                    
                    ui.notify("전역 매매 설정이 실시간으로 저장/적용되었습니다.", type="positive")
                else:
                    ui.notify("자동화 서비스를 찾을 수 없습니다.", type="negative")
            
            ui.button("설정 저장", on_click=save_global_sell_settings, icon="save").classes("bg-indigo-600 text-white ml-auto")

    # ========== Strategy List Section ==========
    with ui.card().classes("w-full bg-gray-800 rounded-lg p-6 mb-6"):
        with ui.row().classes("items-center justify-between w-full mb-4"):
            with ui.row().classes("items-center"):
                ui.icon("auto_awesome").classes("text-amber-400 mr-2")
                ui.label("전략 목록").classes("text-lg font-semibold text-white")
            
            ui.label("").bind_text_from(
                automation_service, "configs",
                backward=lambda c: f"{len(c)}개 전략 등록됨"
            ).classes("text-gray-400 text-sm") if automation_service else None
        
        ui.separator().classes("mb-4")
        
        strategy_list_container = ui.column().classes("w-full")
        
        def render_strategy_list():
            strategy_list_container.clear()
            
            if not automation_service:
                with strategy_list_container:
                    ui.label("자동화 서비스를 찾을 수 없습니다").classes("text-red-400")
                return
            
            configs = automation_service.get_all_configs()
            
            with strategy_list_container:
                if not configs:
                    with ui.row().classes("w-full justify-center py-8"):
                        with ui.column().classes("items-center"):
                            ui.icon("inbox").classes("text-gray-500 text-4xl mb-2")
                            ui.label("아직 등록된 전략이 없습니다").classes("text-gray-400")
                            ui.button("첫 전략 만들기", icon="add", on_click=open_new_strategy_dialog).classes(
                                "bg-indigo-600 text-white mt-2"
                            )
                    return
                
                for i, cfg in enumerate(configs):
                    config_data = cfg.config_json
                    is_first = (i == 0)
                    is_last = (i == len(configs) - 1)
                    
                    with ui.card().classes(
                        f"w-full p-4 mb-3 {'bg-gray-700' if cfg.is_active else 'bg-gray-900 opacity-60'}"
                    ):
                        with ui.row().classes("items-center justify-between w-full"):
                            # Left: Info
                            with ui.column().classes("flex-1"):
                                with ui.row().classes("items-center mb-1"):
                                    status_dot = "🟢" if cfg.is_active else "⭕"
                                    ui.label(f"{status_dot} {cfg.name}").classes("text-white font-semibold text-lg")
                                
                                # Details row
                                details = [
                                    f"📊 {config_data.get('target_universe', 'nikkei225').upper()}",
                                    f"📈 {config_data.get('extraction_strategy', '-')}",
                                    f"🕐 {config_data.get('start_time', '09:00')} - {config_data.get('end_time', '15:00')}",
                                    f"동시 {config_data.get('max_concurrent_stocks', config_data.get('max_stocks', 2))} / 하루 {config_data.get('daily_max_trades', config_data.get('max_stocks', 5))}",
                                ]
                                ui.label(" | ".join(details)).classes("text-gray-400 text-sm")
                            
                            # Right: Actions
                            with ui.row().classes("gap-1"):
                                # Move Up
                                def create_move_up_handler(cid):
                                    async def move_up():
                                        automation_service.move_config(cid, "up")
                                        render_strategy_list()
                                    return move_up
                                
                                ui.button(
                                    icon="keyboard_arrow_up",
                                    on_click=create_move_up_handler(cfg.id)
                                ).props("flat round dense").classes(
                                    "text-gray-500" if is_first else "text-blue-400"
                                ).tooltip("위로 이동").disable() if is_first else ui.button(
                                    icon="keyboard_arrow_up",
                                    on_click=create_move_up_handler(cfg.id)
                                ).props("flat round dense").classes("text-blue-400").tooltip("위로 이동")
                                
                                # Move Down
                                def create_move_down_handler(cid):
                                    async def move_down():
                                        automation_service.move_config(cid, "down")
                                        render_strategy_list()
                                    return move_down
                                
                                ui.button(
                                    icon="keyboard_arrow_down",
                                    on_click=create_move_down_handler(cfg.id)
                                ).props("flat round dense").classes(
                                    "text-gray-500" if is_last else "text-blue-400"
                                ).tooltip("아래로 이동").disable() if is_last else ui.button(
                                    icon="keyboard_arrow_down",
                                    on_click=create_move_down_handler(cfg.id)
                                ).props("flat round dense").classes("text-blue-400").tooltip("아래로 이동")
                                
                                ui.separator().props("vertical").classes("mx-1 bg-gray-600")

                                # Toggle Active
                                def create_toggle_handler(cid, current_active):
                                    async def toggle():
                                        automation_service.toggle_config(cid, not current_active)
                                        render_strategy_list()
                                        state = "활성화" if not current_active else "비활성화"
                                        ui.notify(f"전략 {state}됨", type="info")
                                    return toggle
                                
                                ui.button(
                                    icon="pause" if cfg.is_active else "play_arrow",
                                    on_click=create_toggle_handler(cfg.id, cfg.is_active)
                                ).props("flat round dense").classes(
                                    "text-amber-400" if cfg.is_active else "text-green-400"
                                ).tooltip("비활성화" if cfg.is_active else "활성화")
                                
                                # Edit
                                def create_edit_handler(cid):
                                    def edit():
                                        open_edit_strategy_dialog(cid)
                                    return edit
                                
                                ui.button(icon="edit", on_click=create_edit_handler(cfg.id)).props(
                                    "flat round dense"
                                ).classes("text-indigo-400").tooltip("수정")
                                
                                # Run Now
                                def create_run_handler(cid, name):
                                    async def run():
                                        ui.notify(f"'{name}' 실행 중...", type="info")
                                        await automation_service.run_morning_routine(cid)
                                        render_target_list()
                                    return run
                                
                                ui.button(icon="rocket_launch", on_click=create_run_handler(cfg.id, cfg.name)).props(
                                    "flat round dense"
                                ).classes("text-cyan-400").tooltip("지금 실행")
                                
                                # Delete
                                def create_delete_handler(cid, name):
                                    async def delete():
                                        automation_service.delete_config(cid)
                                        render_strategy_list()
                                        ui.notify(f"'{name}' 삭제됨", type="warning")
                                    return delete
                                
                                ui.button(icon="delete", on_click=create_delete_handler(cfg.id, cfg.name)).props(
                                    "flat round dense"
                                ).classes("text-red-400").tooltip("삭제")
        
        # Initial render
        render_strategy_list()
    
    # ========== Target Stocks & Trade Log Row ==========
    with ui.row().classes("w-full gap-6"):
        # === Left Panel: Target Stocks ===
        with ui.card().classes("flex-1 bg-gray-800 rounded-lg p-6"):
            with ui.row().classes("items-center mb-4"):
                ui.icon("inventory").classes("text-indigo-400 mr-2")
                ui.label("대상 종목").classes("text-lg font-semibold text-white")
            
            ui.separator().classes("mb-4")
            
            stock_list_container = ui.column().classes("w-full max-h-64 overflow-y-auto")

            def render_target_list():
                stock_list_container.clear()
                target_stocks = app_state.get("extraction_results", [])
                
                with stock_list_container:
                    if target_stocks:
                        for stock in target_stocks:
                            with ui.row().classes(
                                "w-full items-center justify-between p-2 bg-gray-700 rounded mb-2"
                            ):
                                with ui.column():
                                    # Show strategy name if tagged
                                    strat_name = stock.get("strategy_name", "")
                                    label_text = f"{stock['symbol']} {stock.get('name', '')}"
                                    ui.label(label_text).classes("text-white")
                                    
                                    price = stock.get('price', 0)
                                    price_str = f"¥{price:,.0f}" if price else "가격 미정"
                                    if strat_name:
                                        ui.label(f"{price_str} • {strat_name}").classes("text-gray-400 text-sm")
                                    else:
                                        ui.label(price_str).classes("text-gray-400 text-sm")
                                
                                def create_delete_handler(s):
                                    def delete():
                                        if s in target_stocks:
                                            target_stocks.remove(s)
                                            render_target_list()
                                            ui.notify(f"{s['symbol']} 삭제됨", type="info")
                                    return delete

                                ui.button(icon="close", on_click=create_delete_handler(stock)).props(
                                    "flat round dense"
                                ).classes("text-gray-400 hover:text-red-400")
                    else:
                        ui.label("대상 종목이 없습니다").classes("text-gray-400 text-sm italic")

            render_target_list()
            
            # Manual add
            with ui.row().classes("mt-4 gap-2"):
                symbol_input = ui.input(
                    label="종목 코드",
                    placeholder="7203",
                ).classes("flex-1").props("filled dark dense")
                
                async def add_manual_stock():
                    symbol = symbol_input.value
                    if not symbol:
                        ui.notify("종목 코드를 입력해주세요", type="warning")
                        return
                    
                    current_list = app_state.get("extraction_results", [])
                    if any(s['symbol'] == symbol for s in current_list):
                        ui.notify("이미 목록에 있는 종목입니다", type="warning")
                        return

                    from backend.universe import Universe
                    try:
                        u = Universe()
                        name = await u.fetch_stock_name(symbol)
                    except Exception as e:
                        print(f"Error fetching stock name: {e}")
                        name = "직접 추가"

                    new_stock = {
                        "symbol": symbol,
                        "name": name, 
                        "price": 0,
                        "change": 0.0
                    }
                    
                    if "extraction_results" not in app_state:
                        app_state["extraction_results"] = []
                        
                    app_state["extraction_results"].append(new_stock)
                    symbol_input.value = ""
                    render_target_list()
                    ui.notify(f"{symbol} ({name}) 추가됨", type="positive")

                ui.button(icon="add", on_click=add_manual_stock).classes("bg-indigo-600 text-white")
        
        # === Right Panel: Trade Log ===
        with ui.card().classes("flex-1 bg-gray-800 rounded-lg p-6"):
            with ui.row().classes("items-center mb-4"):
                ui.icon("receipt_long").classes("text-cyan-400 mr-2")
                ui.label("거래 로그").classes("text-lg font-semibold text-white")
            
            ui.separator().classes("mb-4")
            
            log_container = ui.column().classes("w-full max-h-64 overflow-y-auto")
            
            with log_container:
                logs = app_state.get("logs", [])
                
                if not logs:
                    ui.label("로그가 없습니다").classes("text-gray-500 italic")
                
                for log in logs:
                    level = log.get("type", "INFO")
                    color = "text-cyan-400" if level == "INFO" else "text-yellow-400"
                    msg = log.get("msg", "")
                    time_str = log.get("time", "")
                    
                    ui.label(f"[{time_str}] [{level}] {msg}").classes(f"font-mono text-sm {color}")
