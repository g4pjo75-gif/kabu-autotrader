# -*- coding: utf-8 -*-
"""
Antigravity - Global Configuration
"""

# Kabu Station API Settings
KABU_API_HOST = "localhost"
KABU_API_PORT = 18080  # Default (本番)
KABU_API_PORT_PRODUCTION = 18080  # 本番 (Production)
KABU_API_PORT_TEST = 18081  # 検証 (Test/Demo)
KABU_API_BASE_URL = f"http://{KABU_API_HOST}:{KABU_API_PORT}/kabusapi"
KABU_API_BASE_URL_PRODUCTION = f"http://{KABU_API_HOST}:{KABU_API_PORT_PRODUCTION}/kabusapi"
KABU_API_BASE_URL_TEST = f"http://{KABU_API_HOST}:{KABU_API_PORT_TEST}/kabusapi"

# NiceGUI Server Settings
WEB_HOST = "0.0.0.0"
WEB_PORT = 8080

# Rate Limiting (requests per second)
API_RATE_LIMIT = 10

# Database
DATABASE_PATH = "data/antigravity.db"

# Simulation Mode (Default)
SIMULATION_MODE = True

# Default Strategy Parameters
DEFAULT_SMA_SHORT = 5
DEFAULT_SMA_LONG = 20
DEFAULT_RSI_PERIOD = 14
DEFAULT_RSI_OVERSOLD = 30
DEFAULT_RSI_OVERBOUGHT = 70
DEFAULT_ATR_PERIOD = 14
DEFAULT_BOLLINGER_PERIOD = 20
DEFAULT_BOLLINGER_STD = 2.0

# Order Defaults
DEFAULT_EXCHANGE_ID = 1  # Toushou (Tokyo Stock Exchange)
DEFAULT_SECURITY_TYPE = 1  # Stock
DEFAULT_DELIV_TYPE = 2  # Cash
DEFAULT_ACCOUNT_TYPE = 4  # Tokutei (Specific Account)

# Loss Cut Defaults
DEFAULT_LOSS_CUT_PERCENT = 5.0
DEFAULT_TRAILING_STOP_PERCENT = 3.0

# Live Trading Safety
DEFAULT_DAILY_MAX_LOSS = 30000  # 일일 최대 손실 한도 (엔)
