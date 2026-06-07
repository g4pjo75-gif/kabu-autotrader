# -*- coding: utf-8 -*-
"""
Antigravity - Japanese Stock Auto-Trading System

Entry point for NiceGUI application.
Run with: python main.py
"""
import sys
import os
import shutil
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))



# === Logging Configuration ===
import logging
from logging.handlers import RotatingFileHandler

LOG_DIR = Path(__file__).parent / "logs"
LOG_DIR.mkdir(exist_ok=True)
LOG_FILE = LOG_DIR / "app.log"

# Configure Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        RotatingFileHandler(LOG_FILE, maxBytes=10*1024*1024, backupCount=5, encoding="utf-8")
    ]
)
logger = logging.getLogger("Antigravity")
logger.info("Application starting...")


from nicegui import ui, app

from config import WEB_HOST, WEB_PORT, SIMULATION_MODE
from frontend.layout import create_layout, create_sidebar, create_header
from frontend.pages import settings_page, extraction_page, trading_page, dashboard_page
from backend import MockKabuClient, KabuClient, HybridKabuClient, Database, TelegramNotifier, Scheduler


# Global application state
app_state = {
    "connected": False,
    "simulation_mode": SIMULATION_MODE,
    "trading_active": False,
    "client": None,
    "notifier": None,
    "database": None,
    "scheduler": None,
    "extraction_results": [],
    "target_stocks": [],
    "positions": [],
    "orders": [],
    "nikkei_gap_pct": None,
}


def init_services():
    """Initialize backend services"""
    # Initialize Services
    database = Database()
    notifier = TelegramNotifier()
    
    # Load settings from DB
    telegram_token = database.get_setting("telegram_bot_token")
    telegram_chat_id = database.get_setting("telegram_chat_id")
    
    # Load global sell settings
    app_state["take_profit_pct"] = float(database.get_setting("take_profit_pct") or "1.0")
    app_state["loss_cut_pct"] = float(database.get_setting("loss_cut_pct") or "3.0")
    app_state["trailing_stop_pct"] = float(database.get_setting("trailing_stop_pct") or "3.0")
    app_state["max_trades_per_symbol"] = int(database.get_setting("max_trades_per_symbol") or "1")
    app_state["max_buy_price"] = float(database.get_setting("max_buy_price") or "5000")
    app_state["dip_buy_pct"] = float(database.get_setting("dip_buy_pct") or "1.5")
    
    # Live Trading Safety
    app_state["daily_max_loss"] = float(database.get_setting("daily_max_loss") or "30000")
    
    # Market Index Filter Settings
    app_state["market_index_down_threshold"] = float(database.get_setting("market_index_down_threshold") or "0.1")
    app_state["market_index_up_threshold"] = float(database.get_setting("market_index_up_threshold") or "0.05")
    app_state["global_nikkei_gap_threshold"] = float(database.get_setting("global_nikkei_gap_threshold") or "1.0")
    
    # VWAP Strategy Settings
    app_state["vwap_upper_band"] = float(database.get_setting("vwap_upper_band") or "0.5")
    app_state["vwap_lower_band"] = float(database.get_setting("vwap_lower_band") or "0.2")
    app_state["vwap_min_bounce"] = float(database.get_setting("vwap_min_bounce") or "0.2")
    app_state["max_pullback_pct"] = float(database.get_setting("max_pullback_pct") or "1.5")
    
    # High Breakout Strategy Settings
    app_state["breakout_margin_pct"] = float(database.get_setting("breakout_margin_pct") or "0.1")
    app_state["volume_spurt_ratio"] = float(database.get_setting("volume_spurt_ratio") or "1.5")
    app_state["max_daily_rise_pct"] = float(database.get_setting("max_daily_rise_pct") or "25.0")
    
    # Target Waiting Timeout
    app_state["target_timeout_minutes"] = float(database.get_setting("target_timeout_minutes") or "60")
    
    # Stepped Trailing Stop Settings
    app_state["stepped_trailing_enabled"] = (database.get_setting("stepped_trailing_enabled") or "true").lower() == "true"
    app_state["stepped_trailing_activate_pct"] = float(database.get_setting("stepped_trailing_activate_pct") or "0.8")
    app_state["stepped_trailing_step1_pct"] = float(database.get_setting("stepped_trailing_step1_pct") or "0.5")
    app_state["stepped_trailing_step2_pct"] = float(database.get_setting("stepped_trailing_step2_pct") or "2.0")
    app_state["stepped_trailing_step2_trail_pct"] = float(database.get_setting("stepped_trailing_step2_trail_pct") or "0.3")
    
    if telegram_token and telegram_chat_id:
        notifier.configure(telegram_token, telegram_chat_id)
        # Pre-populate app_state so UI can verify it
        app_state["telegram_token"] = telegram_token
        app_state["telegram_chat_id"] = telegram_chat_id
        
    scheduler = Scheduler()
    
    # Client
    if SIMULATION_MODE:
        app_state["simulation_mode"] = True
        app_state["connected"] = True  # Auto-connect in simulation
        kabu_client = MockKabuClient()
    else:
        app_state["simulation_mode"] = False
        kabu_client = KabuClient()
        
    # Register Core Services first (Dependencies for TradingService)
    app_state.update({
        "client": kabu_client,
        "database": database,
        "notifier": notifier,
        "scheduler": scheduler,
    })

    # Analysis & Trading Services
    from backend.universe import Universe
    universe_manager = Universe(kabu_client)
    
    from backend.analysis_service import AnalysisService
    analysis_service = AnalysisService(universe_manager, kabu_client, app_state)
    
    from backend.trading_service import TradingService
    trading_service = TradingService(app_state)
    
    from backend.automation_service import AutomationService
    automation_service = AutomationService(app_state)
    
    from backend.report_service import ReportService
    report_service = ReportService(app_state)
    
    from backend.market_index_service import MarketIndexService
    market_index_service = MarketIndexService()
    
    # WebSocket PUSH & Intraday Bar Accumulator
    from backend.websocket_service import WebSocketPushService, IntradayBarAccumulator
    bar_accumulator = IntradayBarAccumulator(bar_interval_minutes=5)
    
    # Determine API base URL for WebSocket
    from config import KABU_API_BASE_URL
    ws_service = WebSocketPushService(
        base_url=KABU_API_BASE_URL,
        accumulator=bar_accumulator,
    )
    
    # Register High-level Services
    app_state.update({
        "trading_service": trading_service,
        "analysis_service": analysis_service,
        "automation_service": automation_service,
        "universe": universe_manager,
        "report_service": report_service,
        "market_index_service": market_index_service,
        "ws_service": ws_service,
        "bar_accumulator": bar_accumulator,
    })
    
    # Initialize Automation Config (Schedule Jobs)
    # Initialize Automation Config (Schedule Jobs)
    automation_service.schedule_jobs()
    
    print("[Antigravity] Services initialized")


@ui.page("/")
async def home():
    create_layout(app_state)
    drawer = create_sidebar(app_state)
    create_header(drawer, "설정 및 연결")
    
    with ui.column().classes("w-full max-w-6xl mx-auto p-6"):
        await settings_page(app_state)


@ui.page("/extraction")
async def extraction():
    """Stock extraction page"""
    create_layout(app_state)
    drawer = create_sidebar(app_state)
    create_header(drawer, "종목 발굴")
    
    with ui.column().classes("w-full max-w-6xl mx-auto p-6"):
        await extraction_page(app_state)


@ui.page("/trading")
async def trading():
    """Auto-trading page"""
    create_layout(app_state)
    drawer = create_sidebar(app_state)
    create_header(drawer, "자동 매매")
    
    with ui.column().classes("w-full max-w-6xl mx-auto p-6"):
        await trading_page(app_state)


@ui.page("/dashboard")
async def dashboard():
    """Dashboard/monitoring page"""
    create_layout(app_state)
    drawer = create_sidebar(app_state)
    create_header(drawer, "대시보드")
    
    with ui.column().classes("w-full max-w-6xl mx-auto p-6"):
        await dashboard_page(app_state)


# Lifecycle hooks
@app.on_startup
async def startup():
    """Application startup hook"""
    init_services()
    print(f"[Antigravity] Starting server on http://{WEB_HOST}:{WEB_PORT}")


@app.on_shutdown
async def shutdown():
    """Application shutdown hook"""
    if app_state.get("ws_service"):
        app_state["ws_service"].stop()
    if app_state["client"]:
        await app_state["client"].close()
    if app_state["scheduler"] and app_state["scheduler"].is_running:
        app_state["scheduler"].stop()
    print("[Antigravity] Shutdown complete")


def clear_cache():
    """Clear pycache directories"""
    try:
        root = Path(__file__).parent
        for p in root.rglob("__pycache__"):
            if p.is_dir():
                shutil.rmtree(p)
        print("[Antigravity] Cache cleared")
    except Exception as e:
        print(f"[Antigravity] Warning: Failed to clear cache: {e}")


if __name__ in {"__main__", "__mp_main__"}:
    try:
        # Clear cache before starting
        clear_cache()
        
        ui.run(
            host=WEB_HOST,
            port=WEB_PORT,
            title="Antigravity",
            favicon="🚀",
            dark=True,
            reload=False,
        )
    except Exception as e:
        logger.critical(f"Application crashed: {e}", exc_info=True)
        print(f"CRITICAL ERROR: {e}")
        import time
        time.sleep(30)

