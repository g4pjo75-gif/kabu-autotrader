# -*- coding: utf-8 -*-
"""
Settings & Connection Page

KabuStation API 연결 (本番/検証) + Telegram 설정 UI.
"""
import logging
import asyncio
from nicegui import ui
from typing import Any, Dict

from config import (
    KABU_API_PORT_PRODUCTION,
    KABU_API_PORT_TEST,
    KABU_API_BASE_URL_PRODUCTION,
    KABU_API_BASE_URL_TEST,
    SIMULATION_MODE,
)

logger = logging.getLogger(__name__)


async def settings_page(app_state: Dict[str, Any]) -> None:
    """
    Settings & Connection Page
    
    - KabuStation API 연결 (本番 / 検証 환경 선택)
    - API 비밀번호 입력 및 토큰 발행
    - 주문 시뮬레이션 모드 관리
    - Telegram 알림 설정
    """
    
    # Page title
    ui.label("설정 및 연결").classes("text-2xl font-bold text-white mb-6")
    
    with ui.row().classes("w-full gap-6"):
        # === Connection Panel ===
        with ui.card().classes("flex-1 bg-gray-800 rounded-lg p-6"):
            with ui.row().classes("items-center mb-4"):
                ui.icon("link").classes("text-indigo-400 mr-2")
                ui.label("KabuStation API 연결 설정").classes("text-lg font-semibold text-white")
            
            ui.separator().classes("mb-4")
            
            # --- Environment Selection ---
            ui.label("접속 환경 선택").classes("text-white font-medium mb-2")
            
            # Load saved environment from DB
            db = app_state.get("database")
            saved_env = "test"
            if db:
                saved_env = db.get_setting("api_environment") or "test"
            
            env_selector = ui.toggle(
                {
                    "production": f"本番 (포트: {KABU_API_PORT_PRODUCTION})",
                    "test": f"検証 (포트: {KABU_API_PORT_TEST})",
                },
                value=saved_env,
            ).classes("w-full mb-4").props("color=indigo spread no-caps")
            
            # Environment description
            env_desc = ui.label("").classes("text-xs text-gray-400 mb-4")
            
            def update_env_desc():
                if env_selector.value == "production":
                    env_desc.text = "⚠️ 本番環境: 실제 계좌 연결 (포트 18080)"
                    env_desc.classes(remove="text-gray-400 text-cyan-400", add="text-amber-400")
                else:
                    env_desc.text = "🧪 検証環境: 테스트/데모 연결 (포트 18081)"
                    env_desc.classes(remove="text-gray-400 text-amber-400", add="text-cyan-400")
            
            env_selector.on_value_change(lambda _: update_env_desc())
            update_env_desc()
            
            ui.separator().classes("mb-4")
            
            # --- API Password Section ---
            ui.label("API 비밀번호").classes("text-white font-medium mb-2")
            
            # Load saved passwords from DB
            saved_prod_pw = ""
            saved_test_pw = ""
            if db:
                saved_prod_pw = db.get_setting("api_password_production") or ""
                saved_test_pw = db.get_setting("api_password_test") or ""
            
            # 本番 API Password
            with ui.row().classes("w-full items-center gap-2 mb-2"):
                ui.label("本番").classes("text-amber-400 text-sm w-12")
                api_password_prod = ui.input(
                    label="本番 API 비밀번호",
                    value=saved_prod_pw,
                    password=True,
                    password_toggle_button=True,
                ).classes("flex-1").props("filled dark dense")
            
            # 検証 API Password
            with ui.row().classes("w-full items-center gap-2 mb-4"):
                ui.label("検証").classes("text-cyan-400 text-sm w-12")
                api_password_test = ui.input(
                    label="検証 API 비밀번호",
                    value=saved_test_pw,
                    password=True,
                    password_toggle_button=True,
                ).classes("flex-1").props("filled dark dense")
            
            # Save Passwords Button
            def save_passwords():
                if db:
                    try:
                        db.set_setting("api_password_production", api_password_prod.value)
                        db.set_setting("api_password_test", api_password_test.value)
                        db.set_setting("api_environment", env_selector.value)
                        ui.notify("API 비밀번호가 저장되었습니다", type="positive")
                    except Exception as e:
                        ui.notify(f"저장 오류: {e}", type="negative")
            
            ui.button(
                "비밀번호 저장",
                on_click=save_passwords,
                icon="save",
            ).classes("bg-gray-600 text-white mb-4").props("dense")
            
            ui.separator().classes("mb-4")
            
            # --- Trading Mode (Simulation / Live) ---
            with ui.row().classes("items-center justify-between w-full mb-2"):
                with ui.column():
                    ui.label("매매 실행 모드").classes("text-white font-medium")
                    mode_desc = ui.label("").classes("text-xs")
                
                simulation_switch = ui.switch(value=True).props("color=orange")
            
            # 주문 비밀번호 (注文パスワード / 取引パスワード) — 실매매에 필수
            with ui.row().classes("w-full items-center gap-2 mb-2"):
                ui.label("注文パスワード").classes("text-white text-sm w-28")
                saved_order_pw = ""
                if db:
                    saved_order_pw = db.get_setting("order_password") or ""
                order_password_input = ui.input(
                    label="주문 비밀번호 (取引パスワード)",
                    value=saved_order_pw,
                    password=True,
                    password_toggle_button=True,
                ).classes("flex-1").props("filled dark dense")
            
            ui.label(
                "※ API 비밀번호와 별도. 증권 계좌 개설 시 설정한 취引パスワード입니다."
            ).classes("text-gray-500 text-xs mb-2")
            
            def save_order_password():
                if db:
                    db.set_setting("order_password", order_password_input.value)
                    ui.notify("주문 비밀번호 저장 완료", type="positive")
            
            ui.button(
                "주문 비밀번호 저장", on_click=save_order_password, icon="lock"
            ).classes("bg-gray-600 text-white mb-2").props("dense")
            
            ui.separator().classes("mb-2")
            
            # 일일 최대 손실 한도 설정
            with ui.row().classes("w-full items-center gap-2 mb-2"):
                ui.label("일일 최대 손실 한도").classes("text-white text-sm")
                saved_max_loss = "30000"
                if db:
                    saved_max_loss = db.get_setting("daily_max_loss") or "30000"
                daily_max_loss_input = ui.number(
                    label="¥",
                    value=float(saved_max_loss),
                    min=5000,
                    max=500000,
                    step=5000,
                ).classes("w-32").props("filled dark dense")
                ui.label("엔").classes("text-gray-400 text-sm")
            
            # 손실 한도 저장 버튼
            def save_daily_max_loss():
                val = daily_max_loss_input.value
                if val and val >= 5000:
                    app_state["daily_max_loss"] = float(val)
                    if db:
                        db.set_setting("daily_max_loss", str(int(val)))
                    ui.notify(f"일일 최대 손실 한도: ¥{val:,.0f} 저장 완료", type="positive")
                else:
                    ui.notify("최소 ¥5,000 이상으로 설정해주세요", type="warning")
            
            ui.button(
                "한도 저장", on_click=save_daily_max_loss, icon="save"
            ).classes("bg-gray-600 text-white mb-2").props("dense")

            ui.separator().classes("mb-2")

            # --- 발주 하드캡 설정 (発注ハードキャップ / Order Hard Caps) ---
            ui.label("발주 하드캡 (発注ハードキャップ)").classes("text-white font-medium mb-1")
            ui.label("주문 폭주를 막는 안전 상한값입니다. 운용 중 화면에서 변경할 수 있습니다.").classes("text-gray-400 text-xs mb-2")

            # 1注文金額上限 (max_order_notional)
            with ui.row().classes("w-full items-center gap-2 mb-2"):
                ui.label("1주문 금액 상한").classes("text-white text-sm w-32")
                saved_max_order_notional = "500000"
                if db:
                    saved_max_order_notional = db.get_setting("max_order_notional") or "500000"
                max_order_notional_input = ui.number(
                    label="¥",
                    value=float(saved_max_order_notional),
                    min=10000,
                    max=10000000,
                    step=10000,
                ).classes("w-36").props("filled dark dense")
                ui.label("엔").classes("text-gray-400 text-sm")

            def save_max_order_notional():
                val = max_order_notional_input.value
                if val and val > 0:
                    app_state["max_order_notional"] = float(val)
                    if db:
                        db.set_setting("max_order_notional", str(int(val)))
                    ui.notify(f"1주문 금액 상한: ¥{val:,.0f} 저장 완료", type="positive")
                else:
                    ui.notify("0보다 큰 값으로 설정해주세요", type="warning")

            ui.button(
                "1주문 금액 상한 저장", on_click=save_max_order_notional, icon="save"
            ).classes("bg-gray-600 text-white mb-2").props("dense")

            # 1日発注回数上限 (daily_max_order_count)
            with ui.row().classes("w-full items-center gap-2 mb-2"):
                ui.label("1일 발주 횟수 상한").classes("text-white text-sm w-32")
                saved_daily_max_order_count = "20"
                if db:
                    saved_daily_max_order_count = db.get_setting("daily_max_order_count") or "20"
                daily_max_order_count_input = ui.number(
                    label="회",
                    value=int(saved_daily_max_order_count),
                    min=1,
                    max=1000,
                    step=1,
                ).classes("w-36").props("filled dark dense")
                ui.label("회").classes("text-gray-400 text-sm")

            def save_daily_max_order_count():
                val = daily_max_order_count_input.value
                if val and val > 0:
                    app_state["daily_max_order_count"] = int(val)
                    if db:
                        db.set_setting("daily_max_order_count", str(int(val)))
                    ui.notify(f"1일 발주 횟수 상한: {int(val)}회 저장 완료", type="positive")
                else:
                    ui.notify("1 이상으로 설정해주세요", type="warning")

            ui.button(
                "1일 발주 횟수 상한 저장", on_click=save_daily_max_order_count, icon="save"
            ).classes("bg-gray-600 text-white mb-2").props("dense")

            # 1日約定代金上限 (daily_max_turnover)
            with ui.row().classes("w-full items-center gap-2 mb-2"):
                ui.label("1일 약정 대금 상한").classes("text-white text-sm w-32")
                saved_daily_max_turnover = "2000000"
                if db:
                    saved_daily_max_turnover = db.get_setting("daily_max_turnover") or "2000000"
                daily_max_turnover_input = ui.number(
                    label="¥",
                    value=float(saved_daily_max_turnover),
                    min=10000,
                    max=100000000,
                    step=100000,
                ).classes("w-36").props("filled dark dense")
                ui.label("엔").classes("text-gray-400 text-sm")

            def save_daily_max_turnover():
                val = daily_max_turnover_input.value
                if val and val > 0:
                    app_state["daily_max_turnover"] = float(val)
                    if db:
                        db.set_setting("daily_max_turnover", str(int(val)))
                    ui.notify(f"1일 약정 대금 상한: ¥{val:,.0f} 저장 완료", type="positive")
                else:
                    ui.notify("0보다 큰 값으로 설정해주세요", type="warning")

            ui.button(
                "1일 약정 대금 상한 저장", on_click=save_daily_max_turnover, icon="save"
            ).classes("bg-gray-600 text-white mb-2").props("dense")

            # 同時建玉総額上限 (max_total_position_value)
            with ui.row().classes("w-full items-center gap-2 mb-2"):
                ui.label("동시 보유 총액 상한").classes("text-white text-sm w-32")
                saved_max_total_position_value = "1000000"
                if db:
                    saved_max_total_position_value = db.get_setting("max_total_position_value") or "1000000"
                max_total_position_value_input = ui.number(
                    label="¥",
                    value=float(saved_max_total_position_value),
                    min=10000,
                    max=100000000,
                    step=100000,
                ).classes("w-36").props("filled dark dense")
                ui.label("엔").classes("text-gray-400 text-sm")

            def save_max_total_position_value():
                val = max_total_position_value_input.value
                if val and val > 0:
                    app_state["max_total_position_value"] = float(val)
                    if db:
                        db.set_setting("max_total_position_value", str(int(val)))
                    ui.notify(f"동시 보유 총액 상한: ¥{val:,.0f} 저장 완료", type="positive")
                else:
                    ui.notify("0보다 큰 값으로 설정해주세요", type="warning")

            ui.button(
                "동시 보유 총액 상한 저장", on_click=save_max_total_position_value, icon="save"
            ).classes("bg-gray-600 text-white mb-2").props("dense")

            ui.separator().classes("mb-2")

            # --- 동적 매수 수량 설정 (Dynamic Lot Sizing) ---
            with ui.row().classes("w-full items-center justify-between mb-2"):
                ui.label("동적 매수 수량 설정").classes("text-white font-medium")
                
                saved_dynamic_enabled = True
                if db:
                    val = db.get_setting("dynamic_lot_enabled")
                    if val is not None:
                        saved_dynamic_enabled = val == "1"
                
                dynamic_lot_switch = ui.switch(value=saved_dynamic_enabled).props("color=indigo")
            
            ui.label("설정된 기준가 미만의 종목은 추가 수량으로 매수합니다.").classes("text-gray-400 text-xs mb-2")
            
            with ui.row().classes("w-full items-center gap-2 mb-2"):
                ui.label("기준 가격 미만").classes("text-white text-sm w-24")
                saved_threshold = "2000"
                if db:
                    saved_threshold = db.get_setting("dynamic_lot_threshold") or "2000"
                dynamic_threshold_input = ui.number(
                    value=float(saved_threshold), min=100, max=10000, step=100
                ).classes("w-24").props("filled dark dense")
                ui.label("엔").classes("text-gray-400 text-sm mr-4")
                
                ui.label("매수 수량").classes("text-white text-sm")
                saved_dynamic_size = "200"
                if db:
                    saved_dynamic_size = db.get_setting("dynamic_lot_size") or "200"
                dynamic_size_input = ui.number(
                    value=int(saved_dynamic_size), min=100, max=1000, step=100
                ).classes("w-24").props("filled dark dense")
                ui.label("주").classes("text-gray-400 text-sm")
                
            def save_dynamic_lot_settings():
                if db:
                    db.set_setting("dynamic_lot_enabled", "1" if dynamic_lot_switch.value else "0")
                    db.set_setting("dynamic_lot_threshold", str(int(dynamic_threshold_input.value)))
                    db.set_setting("dynamic_lot_size", str(int(dynamic_size_input.value)))
                    
                    app_state["dynamic_lot_enabled"] = dynamic_lot_switch.value
                    app_state["dynamic_lot_threshold"] = float(dynamic_threshold_input.value)
                    app_state["dynamic_lot_size"] = int(dynamic_size_input.value)
                    
                    ui.notify("동적 매수 수량 설정 저장 완료", type="positive")
            
            ui.button(
                "동적 수량 저장", on_click=save_dynamic_lot_settings, icon="save"
            ).classes("bg-gray-600 text-white mb-2").props("dense")
            
            ui.separator().classes("mb-4")
            
            # 모드 안내 배너
            mode_banner = ui.element("div").classes(
                "w-full p-3 rounded-lg mb-4"
            )
            mode_banner_label = ui.label("").classes("text-xs")
            
            def update_mode_display():
                """시뮬레이션/실매매 모드에 따른 UI 업데이트"""
                is_sim = simulation_switch.value
                api_env = app_state.get("api_environment")
                api_token = app_state.get("api_token")
                is_production_connected = (api_token and api_env == "production")
                
                if is_sim:
                    mode_desc.text = "주문은 시뮬레이션으로만 실행됩니다"
                    mode_desc.classes(remove="text-red-400", add="text-gray-400")
                    simulation_switch.props(remove="color=red", add="color=orange")
                    mode_banner.classes(
                        remove="bg-red-900/30 border-red-700/50",
                        add="bg-orange-900/30 border border-orange-700/50"
                    )
                    mode_banner_label.text = (
                        "🛡️ 안전 모드: 주문은 시뮬레이션으로만 실행됩니다. "
                        "KabuStation API 연결 시 실시간 시세·잔고만 조회합니다."
                    )
                    mode_banner_label.classes(remove="text-red-300", add="text-orange-300")
                else:
                    mode_desc.text = "🔴 실제 주문이 실행됩니다 (성행 주문)"
                    mode_desc.classes(remove="text-gray-400", add="text-red-400")
                    simulation_switch.props(remove="color=orange", add="color=red")
                    mode_banner.classes(
                        remove="bg-orange-900/30 border-orange-700/50",
                        add="bg-red-900/30 border border-red-700/50"
                    )
                    max_loss = app_state.get("daily_max_loss", 30000)
                    mode_banner_label.text = (
                        f"🔴 실매매 모드: 실제 주문이 KabuStation API를 통해 실행됩니다. "
                        f"성행(成行) 주문 | 기본 100주 (동적 수량 적용) | 일일 손실 한도: ¥{max_loss:,.0f}"
                    )
                    mode_banner_label.classes(remove="text-orange-300", add="text-red-300")
                
                # 本番 API 미연결 시 스위치 비활성화
                if not is_production_connected:
                    simulation_switch.value = True
                    simulation_switch.disable()
                    mode_desc.text = "本番 API 연결 후 실매매 전환 가능"
                    mode_desc.classes(remove="text-red-400", add="text-gray-400")
                else:
                    simulation_switch.enable()
            
            async def on_mode_switch_change(e):
                """모드 전환 시 확인 다이얼로그"""
                new_is_sim = e.value  # True = 시뮬레이션, False = 실매매
                
                if not new_is_sim:
                    # 실매매로 전환 → 2중 확인
                    client = app_state.get("client")
                    
                    # 本番 환경 체크
                    if not (app_state.get("api_token") and app_state.get("api_environment") == "production"):
                        ui.notify("本番 API에 먼저 연결해주세요", type="negative")
                        simulation_switch.value = True
                        return
                    
                    # 확인 다이얼로그
                    with ui.dialog() as confirm_dialog, ui.card().classes("bg-gray-800 p-6"):
                        ui.label("🔴 실매매 모드 전환").classes("text-xl font-bold text-red-400 mb-4")
                        ui.separator()
                        ui.label(
                            "실제 주문이 KabuStation을 통해 실행됩니다.\n"
                            "실제 자금으로 매매가 이루어집니다."
                        ).classes("text-white my-4 whitespace-pre-line")
                        
                        max_loss = app_state.get("daily_max_loss", 30000)
                        with ui.element("div").classes("p-3 rounded bg-gray-700 mb-4"):
                            ui.label(f"• 주문 방식: 성행 (成行)").classes("text-gray-300 text-sm")
                            ui.label(f"• 주문 수량: 기본 100주 (동적 수량 적용)").classes("text-gray-300 text-sm")
                            ui.label(f"• 일일 손실 한도: ¥{max_loss:,.0f}").classes("text-gray-300 text-sm")
                            ui.label(f"• 텔레그램 주문 알림: 활성화").classes("text-gray-300 text-sm")
                        
                        ui.label("정말로 실매매 모드로 전환하시겠습니까?").classes("text-amber-400 font-bold mb-4")
                        
                        with ui.row().classes("gap-4 justify-end"):
                            def cancel():
                                simulation_switch.value = True
                                confirm_dialog.close()
                                update_mode_display()
                            
                            def confirm():
                                try:
                                    # 주문 비밀번호 확인
                                    order_pw = order_password_input.value
                                    if not order_pw:
                                        ui.notify(
                                            "주문 비밀번호(注文パスワード)를 먼저 입력해주세요",
                                            type="negative",
                                        )
                                        simulation_switch.value = True
                                        confirm_dialog.close()
                                        update_mode_display()
                                        return
                                    
                                    if hasattr(client, 'enable_live_trading'):
                                        client.enable_live_trading(order_password=order_pw)
                                    app_state["simulation_mode"] = False
                                    ui.notify(
                                        "🔴 실매매 모드 활성화! 실제 주문이 실행됩니다.",
                                        type="negative",
                                        close_button=True,
                                    )
                                    

                                except Exception as ex:
                                    ui.notify(f"전환 실패: {ex}", type="negative")
                                    simulation_switch.value = True
                                finally:
                                    confirm_dialog.close()
                                    update_mode_display()
                            
                            ui.button("취소", on_click=cancel).classes("bg-gray-600 text-white")
                            ui.button(
                                "실매매 전환", on_click=confirm, icon="warning"
                            ).classes("bg-red-600 text-white")
                    
                    confirm_dialog.open()
                else:
                    # 시뮬레이션으로 복귀
                    client = app_state.get("client")
                    if hasattr(client, 'disable_live_trading'):
                        client.disable_live_trading()
                    app_state["simulation_mode"] = True
                    ui.notify("🟡 시뮬레이션 모드로 복귀했습니다", type="info")
                    update_mode_display()
            
            simulation_switch.on_value_change(on_mode_switch_change)
            update_mode_display()
            
            ui.separator().classes("mb-4")
            
            # --- Connection Controls ---
            async def connect():
                """KabuStation API에 실제 연결"""
                env = env_selector.value
                
                # Get password for selected environment
                if env == "production":
                    password = api_password_prod.value
                else:
                    password = api_password_test.value
                
                if not password:
                    ui.notify(
                        f"{'本番' if env == 'production' else '検証'} API 비밀번호를 입력해주세요",
                        type="negative",
                    )
                    return
                
                # Determine base URL
                base_url = (
                    KABU_API_BASE_URL_PRODUCTION
                    if env == "production"
                    else KABU_API_BASE_URL_TEST
                )
                port = (
                    KABU_API_PORT_PRODUCTION
                    if env == "production"
                    else KABU_API_PORT_TEST
                )
                
                env_label = "本番" if env == "production" else "検証"
                
                try:
                    ui.notify(f"{env_label} ({base_url}) 연결 시도 중...", type="info")
                    
                    # Import and create real client
                    from backend.kabu_client import KabuClient, HybridKabuClient
                    
                    real_client = KabuClient(base_url=base_url)
                    token = await real_client.get_token(password)
                    
                    if not token:
                        ui.notify("토큰 발행 실패: 빈 토큰이 반환되었습니다", type="negative")
                        await real_client.close()
                        return
                    
                    # Create hybrid client (real data + simulated orders)
                    hybrid_client = HybridKabuClient(real_client)
                    hybrid_client.api_environment = env
                    
                    # Close old client
                    old_client = app_state.get("client")
                    if old_client:
                        try:
                            await old_client.close()
                        except Exception:
                            pass
                    
                    # Update app_state with new client
                    app_state["client"] = hybrid_client
                    app_state["connected"] = True
                    app_state["simulation_mode"] = True  # Orders remain simulated
                    app_state["api_environment"] = env
                    app_state["api_token"] = token
                    app_state["api_base_url"] = base_url
                    
                    # Update services that hold direct client references
                    if app_state.get("universe"):
                        app_state["universe"].client = hybrid_client
                    if app_state.get("analysis_service"):
                        app_state["analysis_service"].client = hybrid_client
                    
                    # Save environment to DB
                    if db:
                        db.set_setting("api_environment", env)
                    
                    logger.info(
                        f"[Settings] Connected to KabuStation API "
                        f"({env_label}, port={port}, token={token[:8]}...)"
                    )
                    
                    ui.notify(
                        f"✅ {env_label} API 연결 성공! 토큰: {token[:8]}...",
                        type="positive",
                    )
                    
                except Exception as e:
                    error_msg = str(e)
                    logger.error(f"[Settings] API connection failed: {error_msg}")
                    
                    if "ConnectError" in error_msg or "Connection refused" in error_msg:
                        ui.notify(
                            f"❌ 연결 실패: KabuStation이 실행 중인지 확인해주세요.\n"
                            f"(포트: {port}, URL: {base_url})",
                            type="negative",
                            multi_line=True,
                            close_button=True,
                        )
                    elif "401" in error_msg or "Unauthorized" in error_msg:
                        ui.notify(
                            f"❌ 인증 실패: {env_label} API 비밀번호를 확인해주세요.",
                            type="negative",
                        )
                    else:
                        ui.notify(f"❌ 연결 오류: {error_msg}", type="negative")
                
                update_ui_state()
                update_mode_display()
            
            async def disconnect():
                """API 연결 해제 → Mock 클라이언트로 복원"""
                from backend.kabu_client import MockKabuClient
                
                old_client = app_state.get("client")
                if old_client:
                    try:
                        await old_client.close()
                    except Exception:
                        pass
                
                # Restore mock client
                mock_client = MockKabuClient()
                app_state["client"] = mock_client
                app_state["connected"] = True  # Mock is always "connected"
                app_state["simulation_mode"] = True
                app_state["api_environment"] = None
                app_state["api_token"] = None
                app_state["api_base_url"] = None
                
                # 실매매 모드 강제 해제 + 스위치 리셋
                simulation_switch.value = True
                
                # Update services
                if app_state.get("universe"):
                    app_state["universe"].client = mock_client
                if app_state.get("analysis_service"):
                    app_state["analysis_service"].client = mock_client
                
                ui.notify("연결 해제됨 — Mock 시뮬레이션 모드로 복원", type="info")
                logger.info("[Settings] Disconnected from KabuStation API, restored MockClient")
                update_ui_state()
                update_mode_display()
            
            async def test_connection():
                """API 연결 테스트 (get_board로 간단 조회)"""
                client = app_state.get("client")
                if not client or not app_state.get("api_token"):
                    ui.notify("먼저 API에 연결해주세요", type="warning")
                    return
                
                try:
                    # Test with Toyota (7203) - always available
                    board = await client.get_board("7203")
                    ui.notify(
                        f"✅ API 정상 동작! 7203(トヨタ): ¥{board.current_price:,.0f}",
                        type="positive",
                    )
                except Exception as e:
                    ui.notify(f"❌ 테스트 실패: {e}", type="negative")
            
            with ui.row().classes("gap-3"):
                btn_connect = ui.button(
                    "API 연결",
                    on_click=connect,
                    icon="power",
                ).classes("bg-indigo-600 text-white")
                
                btn_disconnect = ui.button(
                    "연결 해제",
                    on_click=disconnect,
                    icon="power_off",
                ).classes("bg-gray-600 text-white")
                
                btn_test = ui.button(
                    "연결 테스트",
                    on_click=test_connection,
                    icon="science",
                ).classes("bg-teal-600 text-white")
            
            # --- Connection Status Display ---
            with ui.card().classes("w-full mt-4 p-4 bg-gray-900 rounded-lg"):
                ui.label("연결 상태").classes("text-gray-400 text-xs mb-2")
                
                with ui.row().classes("items-center"):
                    status_icon = ui.icon("circle").classes("text-xs mr-2")
                    status_label = ui.label("미연결").classes("text-sm")
                
                status_detail = ui.label("").classes("text-xs text-gray-500 mt-1")

            def update_ui_state():
                connected = app_state.get("connected", False)
                api_token = app_state.get("api_token")
                api_env = app_state.get("api_environment")
                
                if connected and api_token:
                    # Real API connected (Hybrid mode)
                    env_label = "本番" if api_env == "production" else "検証"
                    port = KABU_API_PORT_PRODUCTION if api_env == "production" else KABU_API_PORT_TEST
                    is_live = not app_state.get("simulation_mode", True)
                    
                    btn_connect.disable()
                    btn_connect.classes(replace="bg-green-700 text-white")
                    btn_connect.text = "연결됨"
                    
                    btn_disconnect.enable()
                    btn_disconnect.classes(replace="bg-red-600 text-white")
                    
                    btn_test.enable()
                    
                    order_mode = "🔴 실매매 (成行)" if is_live else "시뮬레이션"
                    
                    if api_env == "production":
                        if is_live:
                            status_icon.classes(remove="text-red-500 text-orange-500 text-cyan-500", add="text-green-500")
                            status_label.text = f"🔴 {env_label} API 연결됨 (주문: 실매매)"
                            status_label.classes(remove="text-gray-400 text-orange-400 text-cyan-400 text-green-400", add="text-red-400")
                        else:
                            status_icon.classes(remove="text-red-500 text-orange-500 text-cyan-500", add="text-green-500")
                            status_label.text = f"🟢 {env_label} API 연결됨 (주문: 시뮬레이션)"
                            status_label.classes(remove="text-gray-400 text-orange-400 text-cyan-400 text-red-400", add="text-green-400")
                    else:
                        status_icon.classes(remove="text-red-500 text-orange-500 text-green-500", add="text-cyan-500")
                        status_label.text = f"🔵 {env_label} API 연결됨 (주문: 시뮬레이션)"
                        status_label.classes(remove="text-gray-400 text-orange-400 text-green-400 text-red-400", add="text-cyan-400")
                    
                    status_detail.text = f"포트: {port} | 토큰: {api_token[:8]}... | 시세: 실시간 | 주문: {order_mode}"
                    
                elif connected:
                    # Mock mode (no real API)
                    btn_connect.enable()
                    btn_connect.classes(replace="bg-indigo-600 text-white")
                    btn_connect.text = "API 연결"
                    
                    btn_disconnect.disable()
                    btn_disconnect.classes(replace="bg-gray-600 text-white")
                    
                    btn_test.disable()
                    
                    status_icon.classes(remove="text-red-500 text-green-500 text-cyan-500", add="text-orange-500")
                    status_label.text = "🟠 Mock 시뮬레이션 모드 (yfinance)"
                    status_label.classes(remove="text-gray-400 text-green-400 text-cyan-400", add="text-orange-400")
                    status_detail.text = "시세: yfinance (15분 지연) | 주문: 시뮬레이션"
                    
                else:
                    # Disconnected
                    btn_connect.enable()
                    btn_connect.classes(replace="bg-indigo-600 text-white")
                    btn_connect.text = "API 연결"
                    
                    btn_disconnect.disable()
                    btn_disconnect.classes(replace="bg-gray-600 text-white")
                    
                    btn_test.disable()
                    
                    status_icon.classes(remove="text-green-500 text-orange-500 text-cyan-500", add="text-red-500")
                    status_label.text = "미연결"
                    status_label.classes(remove="text-green-400 text-orange-400 text-cyan-400", add="text-gray-400")
                    status_detail.text = ""

            # Initial state update
            update_ui_state()

        
        # === Telegram Notification Panel ===
        with ui.card().classes("flex-1 bg-gray-800 rounded-lg p-6"):
            with ui.row().classes("items-center mb-4"):
                ui.icon("telegram").classes("text-cyan-400 mr-2")
                ui.label("텔레그램 알림 설정").classes("text-lg font-semibold text-white")
            
            ui.separator().classes("mb-4")
            
            # Bot Token
            bot_token = ui.input(
                label="봇 토큰 (Bot Token)",
                value=app_state.get("telegram_token", ""),
                password=True,
                password_toggle_button=True,
            ).classes("w-full mb-4").props("filled dark")
            
            # Chat ID
            chat_id = ui.input(
                label="채팅 ID (Chat ID)",
                value=app_state.get("telegram_chat_id", ""),
            ).classes("w-full mb-4").props("filled dark")
            
            # Help text
            with ui.expansion("설정 방법").classes("w-full mb-4"):
                ui.markdown("""
                1. 텔레그램에서 **@BotFather** 검색
                2. `/newbot` 명령어로 봇 생성
                3. 발급된 Bot Token을 복사하여 위 칸에 입력
                4. **@userinfobot** 을 통해 Chat ID 확인 후 입력
                """).classes("text-gray-300 text-sm")
            
            # Test Button
            async def test_telegram():
                if not bot_token.value or not chat_id.value:
                    ui.notify("봇 토큰과 채팅 ID를 입력해주세요", type="warning")
                    return
                
                # Update app state
                app_state["telegram_token"] = bot_token.value
                app_state["telegram_chat_id"] = chat_id.value
                
                # Get notifier from app state
                notifier = app_state.get("notifier")
                if notifier:
                    # Update notifier configuration
                    notifier.configure(bot_token.value, chat_id.value)
                    
                    try:
                        # Send actual test message
                        success = await notifier.send_test_message()
                        if success:
                            ui.notify("테스트 메시지를 전송했습니다", type="positive")
                        else:
                            ui.notify("메시지 전송 실패. 토큰과 ID를 확인해주세요.", type="negative")
                    except Exception as e:
                        ui.notify(f"전송 오류: {e}", type="negative")
                else:
                    ui.notify("알림 서비스가 초기화되지 않았습니다.", type="negative")
            
            ui.button(
                "테스트 메시지 전송",
                on_click=test_telegram,
                icon="send",
            ).classes("bg-cyan-600 text-white")
            
            # Save Button
            def save_telegram():
                app_state["telegram_token"] = bot_token.value
                app_state["telegram_chat_id"] = chat_id.value
                
                # Save to database
                if db:
                    try:
                        db.set_setting("telegram_bot_token", bot_token.value)
                        db.set_setting("telegram_chat_id", chat_id.value)
                        ui.notify("텔레그램 설정이 데이터베이스에 저장되었습니다", type="positive")
                    except Exception as e:
                        ui.notify(f"설정 저장 오류: {e}", type="negative")
                else:
                    ui.notify("데이터베이스 연결 오류", type="negative")
            
            ui.button(
                "설정 저장",
                on_click=save_telegram,
                icon="save",
            ).classes("bg-gray-600 text-white ml-2")

    # === [NEW] System & Automation Service Control Panel ===
    ui.label("시스템 및 매매 서비스 제어").classes("text-xl font-bold text-white mt-8 mb-4")
    
    with ui.row().classes("w-full gap-6 mb-12"):
        # --- 1. Automation Service (Scheduler) Control ---
        with ui.card().classes("flex-1 bg-gray-800 rounded-lg p-6"):
            with ui.row().classes("items-center mb-4"):
                ui.icon("precision_manufacturing").classes("text-indigo-400 mr-2")
                ui.label("매매 자동화 엔진 제어 (스케줄러)").classes("text-lg font-semibold text-white")
            
            ui.separator().classes("mb-4")
            
            # Status Indicator
            with ui.row().classes("items-center mb-6 bg-gray-900 p-3 rounded-lg w-full"):
                ui.label("엔진 상태:").classes("text-gray-400 text-sm")
                status_dot = ui.icon("circle").classes("text-xs mx-2")
                status_text = ui.label("로딩 중...").classes("text-sm font-bold")
                jobs_count = ui.label("").classes("text-xs text-gray-500 ml-auto")
                
            def refresh_scheduler_status():
                scheduler = app_state.get("scheduler")
                if not scheduler:
                    status_dot.classes(replace="text-red-500")
                    status_text.text = "초기화 안 됨"
                    status_text.classes(replace="text-red-400")
                    jobs_count.text = ""
                    return
                    
                is_run = scheduler.is_running
                jobs = scheduler.get_jobs() if is_run else []
                
                if is_run:
                    status_dot.classes(replace="text-green-500")
                    status_text.text = "작동 중 (Active)"
                    status_text.classes(replace="text-green-400")
                    jobs_count.text = f"등록된 배치 작업: {len(jobs)}개"
                else:
                    status_dot.classes(replace="text-red-500")
                    status_text.text = "정지됨 (Stopped)"
                    status_text.classes(replace="text-red-400")
                    jobs_count.text = "대기 중"
            
            # Timer to refresh status
            ui.timer(2.0, refresh_scheduler_status)
            
            async def start_automation():
                scheduler = app_state.get("scheduler")
                auto_service = app_state.get("automation_service")
                if not scheduler or not auto_service:
                    ui.notify("서비스가 아직 로드되지 않았습니다", type="negative")
                    return
                    
                if scheduler.is_running:
                    ui.notify("매매 자동화 엔진이 이미 작동 중입니다", type="warning")
                    return
                    
                try:
                    scheduler.start()
                    auto_service.schedule_jobs()
                    ui.notify("🚀 매매 자동화 엔진이 성공적으로 기동되었습니다!", type="positive")
                    
                    # Notify telegram
                    notifier = app_state.get("notifier")
                    if notifier and notifier.is_configured:
                        await notifier.send_system_alert("☀️ <b>아침 매매 감시가 시작되었습니다.</b>\n오늘도 성공 투자를 기원합니다!", "INFO")
                except Exception as e:
                    ui.notify(f"기동 실패: {e}", type="negative")
                refresh_scheduler_status()
                
            async def stop_automation():
                scheduler = app_state.get("scheduler")
                if not scheduler:
                    return
                    
                if not scheduler.is_running:
                    ui.notify("매매 자동화 엔진이 이미 정지된 상태입니다", type="warning")
                    return
                    
                try:
                    scheduler.stop()
                    ui.notify("📴 매매 자동화 엔진이 안전하게 정지되었습니다.", type="warning")
                    

                except Exception as e:
                    ui.notify(f"정지 실패: {e}", type="negative")
                refresh_scheduler_status()
                
            async def reload_automation():
                scheduler = app_state.get("scheduler")
                auto_service = app_state.get("automation_service")
                if not scheduler or not auto_service:
                    return
                    
                try:
                    ui.notify("🔄 매매 설정을 재설정하고 있습니다...", type="info")
                    
                    # Full reload
                    if scheduler.is_running:
                        scheduler.stop()
                    
                    # Re-load from DB
                    auto_service._load_configs()
                    
                    scheduler.start()
                    auto_service.schedule_jobs()
                    ui.notify("✅ DB 설정을 반영하여 매매 엔진이 재기동되었습니다!", type="positive")
                    

                except Exception as e:
                    ui.notify(f"재로드 실패: {e}", type="negative")
                refresh_scheduler_status()

            with ui.row().classes("gap-3 w-full"):
                ui.button("엔진 기동", on_click=start_automation, icon="play_arrow").classes("bg-green-600 text-white flex-1")
                ui.button("엔진 정지", on_click=stop_automation, icon="pause").classes("bg-red-600 text-white flex-1")
                ui.button("설정 재로드", on_click=reload_automation, icon="refresh").classes("bg-gray-600 text-white flex-1")
                
        # --- 2. OS Server Process Control ---
        with ui.card().classes("flex-1 bg-gray-800 rounded-lg p-6"):
            with ui.row().classes("items-center mb-4"):
                ui.icon("dns").classes("text-cyan-400 mr-2")
                ui.label("서버 호스트 프로세스 제어").classes("text-lg font-semibold text-white")
            
            ui.separator().classes("mb-4")
            
            # Process Info Display
            import sys
            import os
            pid = os.getpid()
            python_ver = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
            
            with ui.column().classes("w-full bg-gray-900 p-3 rounded-lg text-xs text-gray-400 gap-1 mb-6"):
                ui.label(f"• 프로세스 ID (PID): {pid}").classes("font-mono")
                ui.label(f"• Python 버전: {python_ver}").classes("font-mono")
                ui.label(f"• 실행 파일: {os.path.basename(sys.executable)}").classes("font-mono")
                ui.label(f"• 작업 디렉토리: {os.path.basename(os.getcwd())}").classes("font-mono")
            
            async def ask_restart_server():
                with ui.dialog() as restart_dialog, ui.card().classes("bg-gray-800 p-6"):
                    ui.label("🔄 서버 프로세스 재기동").classes("text-xl font-bold text-amber-400 mb-4")
                    ui.separator()
                    ui.label(
                        "현재 구동 중인 NiceGUI 서버 프로세스(main.py)를 완전히 내렸다가 자가 재기동합니다.\n"
                        "재기동 중에는 약 2~4초간 웹 페이지 연결이 끊어집니다."
                    ).classes("text-white my-4 whitespace-pre-line text-sm")
                    
                    with ui.row().classes("gap-4 justify-end w-full"):
                        def cancel():
                            restart_dialog.close()
                            
                        async def confirm():
                            restart_dialog.close()
                            ui.notify("🔄 서버 프로세스를 재시작합니다. 잠시 후 새로고침 해주세요...", type="warning", close_button=True)
                            

                            
                            # Sleep a bit to allow notification to show on web UI
                            await asyncio.sleep(1.5)
                            
                            # Robust self restart for Windows/Unix
                            import sys
                            import os
                            import subprocess
                            try:
                                # Launch a completely new process
                                subprocess.Popen(
                                    [sys.executable] + sys.argv,
                                    creationflags=subprocess.CREATE_NEW_CONSOLE if os.name == 'nt' else 0,
                                    close_fds=True
                                )
                                # Immediately terminate current process to release port 8080
                                os.kill(os.getpid(), 9)
                            except Exception as err:
                                logger.error(f"[Settings] Self restart failed: {err}")
                                ui.notify(f"재기동 실패: {err}", type="negative")
                            
                        ui.button("취소", on_click=cancel).classes("bg-gray-600 text-white")
                        ui.button("서버 재기동", on_click=confirm, icon="restart_alt").classes("bg-amber-600 text-white")
                restart_dialog.open()
                
            async def ask_shutdown_server():
                with ui.dialog() as shutdown_dialog, ui.card().classes("bg-gray-800 p-6"):
                    ui.label("🚨 서버 프로세스 완전 종료").classes("text-xl font-bold text-red-500 mb-4")
                    ui.separator()
                    ui.label(
                        "NiceGUI 트레이딩 서버(main.py)를 완전히 정지시킵니다.\n"
                        "종료 후에는 웹 화면에 더 이상 접속할 수 없으며, 서버를 다시 기동하려면 직접 호스트 PC의 터미널/파워셀에서 python main.py를 수동 실행해주셔야 합니다."
                    ).classes("text-white my-4 whitespace-pre-line text-sm")
                    
                    with ui.row().classes("gap-4 justify-end w-full"):
                        def cancel():
                            shutdown_dialog.close()
                            
                        async def confirm():
                            shutdown_dialog.close()
                            ui.notify("🚨 서버 프로세스를 영구 종료합니다...", type="negative")
                            

                            
                            await asyncio.sleep(1.5)
                            
                            # 100% reliable hard kill
                            import os
                            os.kill(os.getpid(), 9)
                            
                        ui.button("취소", on_click=cancel).classes("bg-gray-600 text-white")
                        ui.button("서버 종료", on_click=confirm, icon="power_settings_new").classes("bg-red-600 text-white")
                shutdown_dialog.open()
                
            with ui.row().classes("gap-3 w-full"):
                ui.button("서버 재기동", on_click=ask_restart_server, icon="restart_alt").classes("bg-amber-700 text-white flex-1")
                ui.button("서버 종료", on_click=ask_shutdown_server, icon="power_settings_new").classes("bg-red-700 text-white flex-1")

