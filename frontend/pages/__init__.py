# -*- coding: utf-8 -*-
"""
Frontend Pages Module
"""
from .settings import settings_page
from .extraction import extraction_page
from .trading import trading_page
from .dashboard import dashboard_page

__all__ = [
    "settings_page",
    "extraction_page",
    "trading_page",
    "dashboard_page",
]
