# -*- coding: utf-8 -*-
"""
Notification Module - Telegram Integration

Sends trade alerts and system notifications via Telegram Bot API.
"""
import asyncio
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

import httpx


@dataclass
class TradeAlert:
    """Trade alert data structure"""
    symbol: str
    symbol_name: str
    side: str  # "BUY" or "SELL"
    qty: int
    price: float
    status: str  # "SENT", "FILLED", "CANCELLED"
    strategy: str
    timestamp: datetime


class TelegramNotifier:
    """
    Telegram Bot Notifier
    
    Sends notifications to a Telegram chat via Bot API.
    Supports trade alerts and system messages.
    """

    TELEGRAM_API_URL = "https://api.telegram.org/bot{token}/sendMessage"

    def __init__(self, bot_token: str = "", chat_id: str = ""):
        self.bot_token = bot_token
        self.chat_id = chat_id
        self._client = httpx.AsyncClient(timeout=10.0)

    def configure(self, bot_token: str, chat_id: str):
        """Update bot credentials"""
        self.bot_token = bot_token
        self.chat_id = chat_id

    @property
    def is_configured(self) -> bool:
        """Check if notifier is properly configured"""
        return bool(self.bot_token and self.chat_id)

    async def _send_message(self, text: str, parse_mode: str = "HTML") -> bool:
        """
        Send a message via Telegram Bot API.
        
        Returns:
            True if message sent successfully, False otherwise
        """
        if not self.is_configured:
            return False

        url = self.TELEGRAM_API_URL.format(token=self.bot_token)
        payload = {
            "chat_id": self.chat_id,
            "text": text,
            "parse_mode": parse_mode,
        }

        try:
            response = await self._client.post(url, json=payload)
            response.raise_for_status()
            return True
        except Exception as e:
            print(f"Telegram send error: {e}")
            return False

    async def send_trade_alert(self, alert: TradeAlert) -> bool:
        """
        Send trade execution alert.
        
        Args:
            alert: TradeAlert with order details
            
        Returns:
            True if sent successfully
        """
        emoji = "🟢" if alert.side == "BUY" else "🔴"
        status_emoji = {
            "SENT": "📤",
            "FILLED": "✅",
            "CANCELLED": "❌",
        }.get(alert.status, "❓")

        message = f"""
{emoji} <b>【{alert.side}】{alert.symbol}</b>
━━━━━━━━━━━━━━━━
📊 銘柄: {alert.symbol_name}
💰 価格: ¥{alert.price:,.0f}
📦 数量: {alert.qty}株
📈 戦略: {alert.strategy}
{status_emoji} 状態: {alert.status}
🕐 時刻: {alert.timestamp.strftime("%H:%M:%S")}
"""
        return await self._send_message(message.strip())

    async def send_system_alert(self, msg: str, level: str = "INFO") -> bool:
        """
        Send system notification.
        
        Args:
            msg: System message
            level: "INFO", "WARNING", "ERROR"
            
        Returns:
            True if sent successfully
        """
        emoji = {
            "INFO": "ℹ️",
            "WARNING": "⚠️",
            "ERROR": "🚨",
        }.get(level, "📢")

        message = f"""
{emoji} <b>【システム通知】</b>
━━━━━━━━━━━━━━━━
{msg}
🕐 {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
"""
        return await self._send_message(message.strip())

    async def send_test_message(self) -> bool:
        """
        Send a test message to verify configuration.
        
        Returns:
            True if test message sent successfully
        """
        message = """
✅ <b>Antigravity 接続テスト</b>
━━━━━━━━━━━━━━━━
Telegram通知が正常に設定されました！
取引アラートがこのチャットに送信されます。
"""
        return await self._send_message(message.strip())

    async def close(self):
        """Close the HTTP client"""
        await self._client.aclose()


class MockNotifier(TelegramNotifier):
    """Mock notifier for testing without actual Telegram API"""

    def __init__(self):
        super().__init__("mock_token", "mock_chat")
        self.sent_messages: list = []

    async def _send_message(self, text: str, parse_mode: str = "HTML") -> bool:
        """Store message instead of sending"""
        self.sent_messages.append({
            "text": text,
            "parse_mode": parse_mode,
            "timestamp": datetime.now(),
        })
        print(f"[MockNotifier] Message logged: {text[:50]}...")
        return True
