# -*- coding: utf-8 -*-
"""
Database Module - SQLite Handler

Manages trade history and application settings.
"""
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import json

from config import DATABASE_PATH


@dataclass
class AutomationConfig:
    """Automation strategy configuration"""
    id: Optional[int]
    name: str
    config_json: Dict[str, Any]
    is_active: bool = True
    sort_order: int = 0
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


@dataclass
class TradeRecord:
    """Trade history record"""
    id: Optional[int]
    symbol: str
    symbol_name: str
    side: str  # "BUY" or "SELL"
    price: float
    qty: int
    strategy_name: str
    timestamp: datetime
    order_id: str = ""
    status: str = "FILLED"
    realized_pnl: Optional[float] = 0.0
    extraction_strategy: str = ""  # 종목 추출 전략명
    target_universe: str = ""  # 대상 유니버스 (nikkei225, nikkei400)
    buy_rank: int = 0  # 매수 순위 (1=최상위, 0=미설정)


@dataclass
class AnalysisCandidate:
    """Analysis candidate record - tracks all strategy candidates with buy/skip status"""
    id: Optional[int]
    date: str  # YYYY-MM-DD
    extraction_strategy: str
    target_universe: str
    rank: int
    symbol: str
    symbol_name: str = ""
    score: float = 0.0
    price: float = 0.0
    status: str = "PENDING"  # PENDING / BOUGHT / SKIPPED
    skip_reason: str = ""
    actual_strategy: str = ""  # 실제 매수된 전략명 (중복 skip 시)


@dataclass
class ExtractionLogEntry:
    """Full extraction log entry - tracks all candidates including filtered-out ones"""
    id: Optional[int] = None
    date: str = ""
    extraction_strategy: str = ""
    target_universe: str = ""
    cycle_time: str = ""           # 추출 시점 (HH:MM:SS)
    symbol: str = ""
    symbol_name: str = ""
    ranking_position: int = 0      # 원본 랭킹 순위
    gap_pct: float = 0.0           # 갭상승률
    current_price: float = 0.0
    open_price: float = 0.0
    previous_close: float = 0.0
    volume: int = 0
    filter_result: str = ""        # PASS / ETF제외 / 갭범위초과 / 시가약세 / 시가과열 / 가격초과 / 쿨다운 / 기거래
    filter_detail: str = ""        # 상세 사유
    final_rank: int = 0            # 최종 순위 (0=탈락)
    score: float = 0.0             # 최종 점수


class Database:
    """
    SQLite Database Handler
    
    Tables:
    - trade_history: Order execution records
    - app_settings: Telegram keys, default params (no passwords)
    """

    def __init__(self, db_path: str = DATABASE_PATH):
        self.db_path = Path(__file__).parent.parent / db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    @contextmanager
    def _get_connection(self):
        """Get database connection context manager"""
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _init_db(self):
        """Initialize database tables"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            # Trade history table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS trade_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol TEXT NOT NULL,
                    symbol_name TEXT,
                    side TEXT NOT NULL,
                    price REAL NOT NULL,
                    qty INTEGER NOT NULL,
                    strategy_name TEXT,
                    timestamp TEXT NOT NULL,
                    order_id TEXT,
                    status TEXT DEFAULT 'FILLED',
                    realized_pnl REAL DEFAULT 0.0,
                    extraction_strategy TEXT DEFAULT '',
                    target_universe TEXT DEFAULT '',
                    buy_rank INTEGER DEFAULT 0
                )
            """)
            
            # Simple migration: allow adding columns if missing
            for col, col_type in [("realized_pnl", "REAL DEFAULT 0.0"), ("extraction_strategy", "TEXT DEFAULT ''"), ("target_universe", "TEXT DEFAULT ''"), ("buy_rank", "INTEGER DEFAULT 0")]:
                try:
                    cursor.execute(f"ALTER TABLE trade_history ADD COLUMN {col} {col_type}")
                except sqlite3.OperationalError:
                    pass

            # Analysis candidates table - tracks all strategy candidates
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS analysis_candidates (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    date TEXT NOT NULL,
                    extraction_strategy TEXT NOT NULL,
                    target_universe TEXT NOT NULL,
                    rank INTEGER NOT NULL,
                    symbol TEXT NOT NULL,
                    symbol_name TEXT DEFAULT '',
                    score REAL DEFAULT 0.0,
                    price REAL DEFAULT 0.0,
                    status TEXT DEFAULT 'PENDING',
                    skip_reason TEXT DEFAULT '',
                    actual_strategy TEXT DEFAULT ''
                )
            """)

            # Extraction full log table - tracks all candidates with filter results
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS extraction_full_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    date TEXT NOT NULL,
                    extraction_strategy TEXT NOT NULL,
                    target_universe TEXT NOT NULL,
                    cycle_time TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    symbol_name TEXT DEFAULT '',
                    ranking_position INTEGER DEFAULT 0,
                    gap_pct REAL DEFAULT 0.0,
                    current_price REAL DEFAULT 0.0,
                    open_price REAL DEFAULT 0.0,
                    previous_close REAL DEFAULT 0.0,
                    volume INTEGER DEFAULT 0,
                    filter_result TEXT DEFAULT '',
                    filter_detail TEXT DEFAULT '',
                    final_rank INTEGER DEFAULT 0,
                    score REAL DEFAULT 0.0
                )
            """)

            # Automation configs table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS automation_configs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    config_json TEXT NOT NULL,
                    is_active INTEGER DEFAULT 1,
                    sort_order INTEGER DEFAULT 0,
                    created_at TEXT,
                    updated_at TEXT
                )
            """)

            # Simple migration for automation_configs
            try:
                cursor.execute("ALTER TABLE automation_configs ADD COLUMN sort_order INTEGER DEFAULT 0")
            except sqlite3.OperationalError:
                pass

            # App settings table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS app_settings (
                    key TEXT PRIMARY KEY,
                    value TEXT,
                    updated_at TEXT
                )
            """)

    # --- Trade History Methods ---

    def add_trade(self, trade: TradeRecord) -> int:
        """Add a trade record to history."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO trade_history 
                (symbol, symbol_name, side, price, qty, strategy_name, 
                 timestamp, order_id, status, realized_pnl, extraction_strategy, target_universe, buy_rank)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                trade.symbol,
                trade.symbol_name,
                trade.side,
                trade.price,
                trade.qty,
                trade.strategy_name,
                trade.timestamp.isoformat(),
                trade.order_id,
                trade.status,
                trade.realized_pnl or 0.0,
                trade.extraction_strategy or "",
                trade.target_universe or "",
                trade.buy_rank or 0,
            ))
            return cursor.lastrowid

    def get_trades(
        self, 
        symbol: Optional[str] = None,
        limit: int = 100
    ) -> List[TradeRecord]:
        """Get trade history, optionally filtered by symbol"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            if symbol:
                cursor.execute("""
                    SELECT * FROM trade_history 
                    WHERE symbol = ?
                    ORDER BY timestamp DESC
                    LIMIT ?
                """, (symbol, limit))
            else:
                cursor.execute("""
                    SELECT * FROM trade_history 
                    ORDER BY timestamp DESC
                    LIMIT ?
                """, (limit,))
            
            return [
                TradeRecord(
                    id=row["id"],
                    symbol=row["symbol"],
                    symbol_name=row["symbol_name"],
                    side=row["side"],
                    price=row["price"],
                    qty=row["qty"],
                    strategy_name=row["strategy_name"],
                    timestamp=datetime.fromisoformat(row["timestamp"]),
                    order_id=row["order_id"],
                    status=row["status"],
                    realized_pnl=row["realized_pnl"] if "realized_pnl" in row.keys() else 0.0,
                    extraction_strategy=row["extraction_strategy"] if "extraction_strategy" in row.keys() else "",
                    target_universe=row["target_universe"] if "target_universe" in row.keys() else "",
                    buy_rank=row["buy_rank"] if "buy_rank" in row.keys() else 0
                )
                for row in cursor.fetchall()
            ]

    def get_today_trades(self) -> List[TradeRecord]:
        """Get trades from today"""
        today = datetime.now().date().isoformat()
        return self.get_trades_by_date(today)

    def get_trades_by_date(self, date_str: str) -> List[TradeRecord]:
        """Get trades for a specific date (format: YYYY-MM-DD)"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM trade_history 
                WHERE date(timestamp) = date(?)
                ORDER BY timestamp DESC
            """, (date_str,))
            
            return [
                TradeRecord(
                    id=row["id"],
                    symbol=row["symbol"],
                    symbol_name=row["symbol_name"],
                    side=row["side"],
                    price=row["price"],
                    qty=row["qty"],
                    strategy_name=row["strategy_name"],
                    timestamp=datetime.fromisoformat(row["timestamp"]),
                    order_id=row["order_id"],
                    status=row["status"],
                    realized_pnl=row["realized_pnl"] if "realized_pnl" in row.keys() else 0.0,
                    extraction_strategy=row["extraction_strategy"] if "extraction_strategy" in row.keys() else "",
                    target_universe=row["target_universe"] if "target_universe" in row.keys() else "",
                    buy_rank=row["buy_rank"] if "buy_rank" in row.keys() else 0
                )
                for row in cursor.fetchall()
            ]

    def get_strategy_buy_count_today(self, strategy_name: str) -> int:
        """Count how many BUY trades were made today for a specific strategy."""
        today = datetime.now().strftime("%Y-%m-%d")
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT COUNT(*) as count FROM trade_history 
                WHERE side = 'BUY' 
                AND date(timestamp) = ? 
                AND extraction_strategy = ?
                AND status = 'FILLED'
            """, (today, strategy_name))
            return cursor.fetchone()["count"]

    def get_recent_traded_symbols(self, days: int = 2, strategy_name: str = "") -> set:
        """
        최근 N일 이내에 BUY 거래가 있었던 종목 심볼 Set을 반환합니다 (당일 제외).
        
        연속 매수 쿨다운 필터에 사용: 최근 거래한 종목의 재진입을 방지합니다.
        
        Args:
            days: 조회할 과거 일수 (기본 2일)
            strategy_name: 특정 전략으로 필터링 (빈 문자열이면 전체)
            
        Returns:
            set: 최근 N일 이내 매수한 종목 심볼 Set (예: {"6723", "7013"})
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            if strategy_name:
                cursor.execute("""
                    SELECT DISTINCT symbol FROM trade_history 
                    WHERE side = 'BUY' 
                    AND status = 'FILLED'
                    AND date(timestamp) >= date('now', ? || ' days')
                    AND date(timestamp) < date('now')
                    AND extraction_strategy = ?
                """, (f"-{days}", strategy_name))
            else:
                cursor.execute("""
                    SELECT DISTINCT symbol FROM trade_history 
                    WHERE side = 'BUY' 
                    AND status = 'FILLED'
                    AND date(timestamp) >= date('now', ? || ' days')
                    AND date(timestamp) < date('now')
                """, (f"-{days}",))
            return {row["symbol"] for row in cursor.fetchall()}

    # --- App Settings Methods ---

    def set_setting(self, key: str, value: str):
        """Set or update an application setting"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO app_settings (key, value, updated_at)
                VALUES (?, ?, ?)
            """, (key, value, datetime.now().isoformat()))

    def get_setting(self, key: str, default: str = "") -> str:
        """Get an application setting"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT value FROM app_settings WHERE key = ?", 
                (key,)
            )
            row = cursor.fetchone()
            return row["value"] if row else default

    def get_all_settings(self) -> Dict[str, str]:
        """Get all application settings"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT key, value FROM app_settings")
            return {row["key"]: row["value"] for row in cursor.fetchall()}

    def delete_setting(self, key: str):
        """Delete an application setting"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM app_settings WHERE key = ?", (key,))

    # --- Statistics Methods ---

    def get_trade_summary(self) -> Dict[str, Any]:
        """Get trade statistics summary"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            # Total trades
            cursor.execute("SELECT COUNT(*) as count FROM trade_history")
            total = cursor.fetchone()["count"]
            
            # Buy/Sell counts
            cursor.execute("""
                SELECT side, COUNT(*) as count 
                FROM trade_history 
                GROUP BY side
            """)
            by_side = {row["side"]: row["count"] for row in cursor.fetchall()}
            
            # Today's trades
            today = datetime.now().date().isoformat()
            cursor.execute("""
                SELECT COUNT(*) as count FROM trade_history 
                WHERE date(timestamp) = date(?)
            """, (today,))
            today_count = cursor.fetchone()["count"]
            
            return {
                "total_trades": total,
                "buy_count": by_side.get("BUY", 0),
                "sell_count": by_side.get("SELL", 0),
                "today_count": today_count,
            }

    # --- Automation Config Methods ---

    def get_automation_configs(self, active_only: bool = False) -> List[AutomationConfig]:
        """Get all automation configurations"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            if active_only:
                cursor.execute("SELECT * FROM automation_configs WHERE is_active = 1 ORDER BY sort_order ASC, id ASC")
            else:
                cursor.execute("SELECT * FROM automation_configs ORDER BY sort_order ASC, id ASC")
            
            return [
                AutomationConfig(
                    id=row["id"],
                    name=row["name"],
                    config_json=json.loads(row["config_json"]),
                    is_active=bool(row["is_active"]),
                    sort_order=row["sort_order"] if "sort_order" in row.keys() else 0,
                    created_at=datetime.fromisoformat(row["created_at"]) if row["created_at"] else None,
                    updated_at=datetime.fromisoformat(row["updated_at"]) if row["updated_at"] else None,
                )
                for row in cursor.fetchall()
            ]

    def get_automation_config(self, config_id: int) -> Optional[AutomationConfig]:
        """Get a single automation configuration by ID"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM automation_configs WHERE id = ?", (config_id,))
            row = cursor.fetchone()
            if row:
                return AutomationConfig(
                    id=row["id"],
                    name=row["name"],
                    config_json=json.loads(row["config_json"]),
                    is_active=bool(row["is_active"]),
                    sort_order=row["sort_order"] if "sort_order" in row.keys() else 0,
                    created_at=datetime.fromisoformat(row["created_at"]) if row["created_at"] else None,
                    updated_at=datetime.fromisoformat(row["updated_at"]) if row["updated_at"] else None,
                )
            return None

    def save_automation_config(self, config: AutomationConfig) -> int:
        """Save or update an automation configuration. Returns the ID."""
        now = datetime.now().isoformat()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            if config.id is None:
                # Insert new
                # Determine max sort_order
                cursor.execute("SELECT MAX(sort_order) as max_order FROM automation_configs")
                row = cursor.fetchone()
                next_order = (row["max_order"] or 0) + 1 if config.sort_order == 0 else config.sort_order

                cursor.execute("""
                    INSERT INTO automation_configs (name, config_json, is_active, sort_order, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (
                    config.name,
                    json.dumps(config.config_json),
                    1 if config.is_active else 0,
                    next_order,
                    now,
                    now,
                ))
                return cursor.lastrowid
            else:
                # Update existing
                cursor.execute("""
                    UPDATE automation_configs 
                    SET name = ?, config_json = ?, is_active = ?, sort_order = ?, updated_at = ?
                    WHERE id = ?
                """, (
                    config.name,
                    json.dumps(config.config_json),
                    1 if config.is_active else 0,
                    config.sort_order,
                    now,
                    config.id,
                ))
                return config.id

    def delete_automation_config(self, config_id: int):
        """Delete an automation configuration"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM automation_configs WHERE id = ?", (config_id,))

    def toggle_automation_config(self, config_id: int, is_active: bool):
        """Toggle the active state of an automation configuration"""
        now = datetime.now().isoformat()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE automation_configs SET is_active = ?, updated_at = ? WHERE id = ?
            """, (1 if is_active else 0, now, config_id))

    def update_automation_config_order(self, config_ids: List[int]):
        """Update the sort_order of multiple configs based on the list order"""
        now = datetime.now().isoformat()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            for index, cid in enumerate(config_ids):
                cursor.execute("""
                    UPDATE automation_configs SET sort_order = ?, updated_at = ? WHERE id = ?
                """, (index, now, cid))

    # --- Analysis Candidates Methods ---

    def save_analysis_candidates(self, candidates: List['AnalysisCandidate']):
        """Save analysis candidates. Updates existing ones or adds new ones without deleting previous entries.
        
        This prevents losing historical candidate records (especially BOUGHT ones) during 
        continuous extraction cycles.
        """
        if not candidates:
            return
        with self._get_connection() as conn:
            cursor = conn.cursor()
            for c in candidates:
                # Check if this symbol already exists for this date/strategy/universe
                cursor.execute("""
                    SELECT id, status FROM analysis_candidates 
                    WHERE date = ? AND extraction_strategy = ? AND target_universe = ? AND symbol = ?
                """, (c.date, c.extraction_strategy, c.target_universe, c.symbol))
                row = cursor.fetchone()
                
                if row:
                    # Update existing record. 
                    # CRITICAL: Do NOT overwrite status if it's already BOUGHT or SKIPPED.
                    current_status = row["status"]
                    target_status = current_status if current_status != "PENDING" else c.status
                    
                    cursor.execute("""
                        UPDATE analysis_candidates 
                        SET rank = ?, symbol_name = ?, score = ?, price = ?, status = ?
                        WHERE id = ?
                    """, (c.rank, c.symbol_name, c.score, c.price, target_status, row["id"]))
                else:
                    # Insert new record
                    cursor.execute("""
                        INSERT INTO analysis_candidates 
                        (date, extraction_strategy, target_universe, rank, symbol, symbol_name, score, price, status, skip_reason, actual_strategy)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (c.date, c.extraction_strategy, c.target_universe, c.rank, c.symbol, c.symbol_name, c.score, c.price, c.status, c.skip_reason, c.actual_strategy))


    def update_candidate_status(self, date: str, extraction_strategy: str, target_universe: str, symbol: str, status: str, skip_reason: str = "", actual_strategy: str = ""):
        """Update the status of an analysis candidate (BOUGHT/SKIPPED).
        
        Note: Once a candidate is marked as BOUGHT, it cannot be overwritten
        by subsequent trading cycle updates (e.g. 'already held', 'sold today').
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE analysis_candidates 
                SET status = ?, skip_reason = ?, actual_strategy = ?
                WHERE date = ? AND extraction_strategy = ? AND target_universe = ? AND symbol = ?
                AND status != 'BOUGHT'
            """, (status, skip_reason, actual_strategy, date, extraction_strategy, target_universe, symbol))

    def get_analysis_candidates(self, date: str) -> List['AnalysisCandidate']:
        """Get all analysis candidates for a specific date."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM analysis_candidates 
                WHERE date = ?
                ORDER BY extraction_strategy, target_universe, rank
            """, (date,))
            return [
                AnalysisCandidate(
                    id=row["id"],
                    date=row["date"],
                    extraction_strategy=row["extraction_strategy"],
                    target_universe=row["target_universe"],
                    rank=row["rank"],
                    symbol=row["symbol"],
                    symbol_name=row["symbol_name"],
                    score=row["score"],
                    price=row["price"],
                    status=row["status"],
                    skip_reason=row["skip_reason"],
                    actual_strategy=row["actual_strategy"],
                )
                for row in cursor.fetchall()
            ]

    # --- Extraction Full Log Methods ---

    def save_extraction_log(self, entries: List['ExtractionLogEntry']):
        """Save extraction full log entries for a cycle.
        
        Clears previous entries for the same date/strategy/universe/cycle_time
        before inserting to avoid duplicates on retries.
        """
        if not entries:
            return
        with self._get_connection() as conn:
            cursor = conn.cursor()
            # Remove old entries for this cycle
            first = entries[0]
            cursor.execute("""
                DELETE FROM extraction_full_log
                WHERE date = ? AND extraction_strategy = ? AND target_universe = ? AND cycle_time = ?
            """, (first.date, first.extraction_strategy, first.target_universe, first.cycle_time))
            
            for e in entries:
                cursor.execute("""
                    INSERT INTO extraction_full_log
                    (date, extraction_strategy, target_universe, cycle_time, symbol, symbol_name,
                     ranking_position, gap_pct, current_price, open_price, previous_close, volume,
                     filter_result, filter_detail, final_rank, score)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (e.date, e.extraction_strategy, e.target_universe, e.cycle_time,
                       e.symbol, e.symbol_name, e.ranking_position, e.gap_pct,
                       e.current_price, e.open_price, e.previous_close, e.volume,
                       e.filter_result, e.filter_detail, e.final_rank, e.score))

    def get_extraction_log(self, date: str, extraction_strategy: str = None) -> List['ExtractionLogEntry']:
        """Get extraction full log entries for a date.
        
        Returns the LATEST cycle's log for each strategy (by max cycle_time).
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            if extraction_strategy:
                # Get the latest cycle_time for this strategy
                cursor.execute("""
                    SELECT * FROM extraction_full_log
                    WHERE date = ? AND extraction_strategy = ?
                    AND cycle_time = (
                        SELECT MAX(cycle_time) FROM extraction_full_log
                        WHERE date = ? AND extraction_strategy = ?
                    )
                    ORDER BY ranking_position ASC
                """, (date, extraction_strategy, date, extraction_strategy))
            else:
                # Get the latest cycle for each strategy
                cursor.execute("""
                    SELECT e.* FROM extraction_full_log e
                    INNER JOIN (
                        SELECT extraction_strategy, target_universe, MAX(cycle_time) as max_time
                        FROM extraction_full_log
                        WHERE date = ?
                        GROUP BY extraction_strategy, target_universe
                    ) latest ON e.extraction_strategy = latest.extraction_strategy
                        AND e.target_universe = latest.target_universe
                        AND e.cycle_time = latest.max_time
                    WHERE e.date = ?
                    ORDER BY e.extraction_strategy, e.ranking_position ASC
                """, (date, date))
            
            return [
                ExtractionLogEntry(
                    id=row["id"],
                    date=row["date"],
                    extraction_strategy=row["extraction_strategy"],
                    target_universe=row["target_universe"],
                    cycle_time=row["cycle_time"],
                    symbol=row["symbol"],
                    symbol_name=row["symbol_name"],
                    ranking_position=row["ranking_position"],
                    gap_pct=row["gap_pct"],
                    current_price=row["current_price"],
                    open_price=row["open_price"],
                    previous_close=row["previous_close"],
                    volume=row["volume"],
                    filter_result=row["filter_result"],
                    filter_detail=row["filter_detail"],
                    final_rank=row["final_rank"],
                    score=row["score"],
                )
                for row in cursor.fetchall()
            ]
