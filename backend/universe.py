# -*- coding: utf-8 -*-
"""
Universe Module - Target Stock Selection

Defines which stocks to analyze from the 4,000+ stocks on TSE.
Sources: Nikkei 225, API Ranking, User CSV
"""
import csv
from pathlib import Path
from typing import Any, List, Optional

from .kabu_client import BaseKabuClient


class Universe:
    """
    Manages the target stock universe for analysis.
    
    Provides multiple methods to define which stocks to scan:
    - Nikkei 225 (static list)
    - Live API Ranking (dynamic)
    - User-defined CSV watchlist
    """

    def __init__(self, client: Optional[BaseKabuClient] = None):
        self.client = client
        self._nikkei225_path = Path(__file__).parent.parent / "data" / "nikkei225.csv"
        self._nikkei400_path = Path(__file__).parent.parent / "data" / "nikkei400.csv"

    def load_nikkei_225(self) -> List[str]:
        """
        Load Nikkei 225 constituent symbols from CSV.
        
        Returns:
            List of stock symbols (e.g., ["7203", "6758", ...])
        """
        symbols = []
        if self._nikkei225_path.exists():
            with open(self._nikkei225_path, encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if "symbol" in row:
                        symbols.append(row["symbol"])
                    elif "Symbol" in row:
                        symbols.append(row["Symbol"])
        else:
            # Fallback: Top 30 Major Stocks (hardcoded)
            symbols = [
                "7203",  # トヨタ自動車
                "6758",  # ソニーグループ
                "9984",  # ソフトバンクグループ
                "6861",  # キーエンス
                "8306",  # 三菱UFJフィナンシャル
                "9432",  # 日本電信電話
                "6501",  # 日立製作所
                "7267",  # 本田技研工業
                "4063",  # 信越化学工業
                "7741",  # HOYA
                "8035",  # 東京エレクトロン
                "6902",  # デンソー
                "4519",  # 中外製薬
                "6367",  # ダイキン工業
                "9433",  # KDDI
                "8058",  # 三菱商事
                "4502",  # 武田薬品工業
                "6954",  # ファナック
                "6098",  # リクルートホールディングス
                "8766",  # 東京海上ホールディングス
                "4661",  # オリエンタルランド
                "9983",  # ファーストリテイリング
                "8001",  # 伊藤忠商事
                "7974",  # 任天堂
                "6594",  # 日本電産
                "7751",  # キヤノン
                "6702",  # 富士通
                "9020",  # 東日本旅客鉄道
                "8031",  # 三井物産
                "9022",  # 東海旅客鉄道
            ]
        return symbols

    def load_stock_map(self) -> dict:
        """
        Load a mapping of stock symbols to names from Nikkei 225 CSV.
        
        Returns:
            Dict[str, str]: { "7203": "トヨタ自動車", ... }
        """
        stock_map = {}
        if self._nikkei225_path.exists():
            with open(self._nikkei225_path, encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    symbol = None
                    if "symbol" in row:
                        symbol = row["symbol"]
                    elif "Symbol" in row:
                        symbol = row["Symbol"]
                        
                    name = row.get("name") or row.get("Name")
                    
                    if symbol and name:
                        stock_map[symbol] = name
                        
        if self._nikkei400_path.exists():
            with open(self._nikkei400_path, encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    symbol = row.get("symbol") or row.get("Symbol")
                    name = row.get("name") or row.get("Name")
                    
                    if symbol and name:
                        stock_map[symbol] = name
                        
        return stock_map

    async def fetch_ranking(
        self, 
        ranking_type: str = "1",
        exchange: int = 1,
        count: int = 50
    ) -> List[str]:
        """
        Fetch top active stocks from API ranking.
        
        Args:
            ranking_type: "1" = Tick Count, "2" = Trading Value, etc.
            exchange: 1 = Toushou
            count: Number of stocks to fetch
            
        Returns:
            List of stock symbols
        """
        if not self.client:
            raise ValueError("API client required for ranking fetch")

        # Use MockKabuClient's get_ranking if available
        if hasattr(self.client, "get_ranking"):
            ranking = await self.client.get_ranking(ranking_type, exchange)
        else:
            # Fallback for real client (not implemented in base)
            ranking = []

        return [item["Symbol"] for item in ranking[:count]]

    def load_watchlist(self, csv_path: str) -> List[str]:
        """
        Load user-defined watchlist from CSV file.
        
        Expected CSV format:
        symbol,name (optional)
        7203,トヨタ自動車
        
        Args:
            csv_path: Path to the CSV file
            
        Returns:
            List of stock symbols
        """
        symbols = []
        path = Path(csv_path)
        
        if not path.exists():
            raise FileNotFoundError(f"Watchlist file not found: {csv_path}")

        with open(path, encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                # Support multiple column names
                symbol = row.get("symbol") or row.get("Symbol") or row.get("code")
                if symbol:
                    symbols.append(symbol.strip())

        return symbols

    def get_universe(
        self, 
        source: str = "nikkei225",
        csv_path: Optional[str] = None
    ) -> List[str]:
        """
        Get stock universe from specified source.
        
        Args:
            source: "nikkei225", "ranking", or "csv"
            csv_path: Required if source is "csv"
            
        Returns:
            List of stock symbols
        """
        if source == "nikkei225":
            return self.load_nikkei_225()
        elif source == "ranking":
            raise ValueError("Use fetch_ranking() for async ranking fetch")
        elif source == "csv":
            if not csv_path:
                raise ValueError("csv_path required for CSV source")
            return self.load_watchlist(csv_path)
        elif source == "nikkei400":
            return self.load_nikkei_400_exclusive()
        elif source == "ranking_leaders":
            raise ValueError("Use fetch_intraday_leaders() for async ranking-based fetch")
        else:
            raise ValueError(f"Unknown source: {source}")

    def load_nikkei_400(self) -> List[str]:
        """Load JPX-Nikkei 400 constituent symbols."""
        symbols = []
        if self._nikkei400_path.exists():
            with open(self._nikkei400_path, encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    symbol = row.get("symbol") or row.get("Symbol")
                    if symbol:
                        symbols.append(symbol)
        return symbols

    def load_nikkei_400_exclusive(self) -> List[str]:
        """
        Load JPX-Nikkei 400 constituents EXCLUDING Nikkei 225 stocks.
        Returns: List of symbols only in JPX-Nikkei 400.
        """
        nikkei400 = self.load_nikkei_400()
        nikkei225 = self.load_nikkei_225()
        
        # Difference: 400 - 225
        exclusive = list(set(nikkei400) - set(nikkei225))
        return exclusive

    async def fetch_intraday_leaders(
        self,
        ranking_type: str = "1",
        secondary_ranking_type: str = "5",
        exchange_division: Any = "ALL",
        count: int = 50,
        gap_min: float = 2.0,
        gap_max: float = 5.0,
        max_rise_from_open_pct: float = 2.5,
        max_buy_price: float = 0,
    ) -> tuple:
        """
        당일 주도주 추출 (Ranking API + 보조 랭킹 교집합 + 갭상승률 필터링).
        
        1. 메인 Ranking API(예: TICK 횟수)에서 상위 종목을 가져옵니다.
        2. 보조 Ranking API(예: 거래대금)가 설정된 경우 교집합을 구합니다.
        3. 전일 종가 대비 시가 갭상승률로 필터링합니다.
        4. 시가 대비 과도한 상승 종목을 필터링합니다 (아침 스파이크 방지).
        5. 시가 기준 갭 검증으로 과도 갭업 종목을 이중 체크합니다.
        6. 단타에 적합한 종목 리스트를 반환합니다.
        
        Args:
            ranking_type: 메인 랭킹 종류 ("5"=TICK回数 기본)
            secondary_ranking_type: 보조 랭킹 종류 ("none"이면 사용 안함)
            exchange_division: 시장 (1=전체, 2=동증, 3=프라임)
            count: 상위 N개 종목
            gap_min: 갭상승률 하한 (%) - 이 이상만 포함
            gap_max: 갭상승률 상한 (%) - 이 이하만 포함
            max_rise_from_open_pct: 시가 대비 최대 상승률 (%) - 초과 시 제외 (스파이크 방지)
            
        Returns:
            Tuple of (filtered_leaders: List[Dict], full_log: List[Dict])
            - filtered_leaders: 최종 통과 종목 리스트
            - full_log: 전체 후보의 필터 결과 (상위 20개)
        """
        import logging
        _logger = logging.getLogger(__name__)
        
        if not self.client:
            raise ValueError("API client required for intraday leaders fetch")
        
        # 전체 로그 기록용
        full_log = []
        
        try:
            # 1. Primary Ranking 다중 타입 호출 병합 (대안 2)
            # 설정된 메인 랭킹 외에, 단타에 적합한 '거래대금(4)'을 추가로 병합하여 모수 확장
            primary_types = list(set([str(ranking_type), "4"]))
            
            ranking = []
            seen_symbols = set()
            for p_type in primary_types:
                res = await self.client.get_ranking(p_type, exchange_division)
                if res:
                    for item in res:
                        sym = str(item.get("Symbol"))
                        if sym and sym not in seen_symbols:
                            seen_symbols.add(sym)
                            ranking.append(item)
            
            if not ranking:
                _logger.warning(f"[Universe] Primary Ranking API returned empty response across types {primary_types}")
                return [], []
            
            _logger.info(f"[Universe] Primary Ranking API (Types={primary_types}) returned {len(ranking)} unique items")
            
            # 2. 보조 랭킹 다중 타입 교집합 (대안 2)
            secondary_excluded = set()
            if secondary_ranking_type and secondary_ranking_type != "none":
                # 설정된 보조 랭킹 외에, '거래량 급증(6)'을 추가로 병합하여 교집합 모수 확장
                secondary_types = list(set([str(secondary_ranking_type), "6"]))
                
                combined_sec_symbols = set()
                for s_type in secondary_types:
                    sec_ranking = await self.client.get_ranking(s_type, exchange_division)
                    if sec_ranking:
                        for item in sec_ranking:
                            if item.get("Symbol"):
                                combined_sec_symbols.add(str(item.get("Symbol")))
                
                if combined_sec_symbols:
                    _logger.info(f"[Universe] Secondary Ranking API (Types={secondary_types}) returned {len(combined_sec_symbols)} unique symbols")
                    # 교집합에서 제외되는 종목 기록
                    secondary_excluded = {str(item.get("Symbol")) for item in ranking} - combined_sec_symbols
                    # 메인 랭킹 묶음(primary_types)과 보조 랭킹 묶음(secondary_types)의 교집합 추출
                    ranking = [item for item in ranking if str(item.get("Symbol")) in combined_sec_symbols]
                    _logger.info(f"[Universe] Intersection of Primary & Secondary groups left {len(ranking)} items")
                else:
                    _logger.warning("[Universe] Secondary Ranking API returned empty response. Ignored.")
            
            # 3. 상위 N개 슬라이싱
            top_items = ranking[:count]
            
            # 4. 갭상승률 및 ETF 필터링 (로그 기록 포함)
            filtered = []
            ranking_pos = 0
            for item in top_items:
                symbol = str(item.get("Symbol", ""))
                name = item.get("SymbolName", "")
                current_price = item.get("CurrentPrice", 0)
                previous_close = item.get("PreviousClose", 0)
                trading_volume = item.get("TradingVolume", 0)
                
                # 랭킹 타입에 따라 등락률 키값이 다를 수 있음
                change_pct = item.get("ChangePreviousClosePer")
                if change_pct is None:
                    change_pct = item.get("ChangePercentage", 0)
                
                if not symbol or current_price <= 0:
                    continue
                
                ranking_pos += 1
                
                # 갭상승률 계산
                gap_pct = float(change_pct) if change_pct else (
                    ((current_price - previous_close) / previous_close * 100) if previous_close > 0 else 0.0
                )
                
                # 기본 로그 엔트리
                log_entry = {
                    "symbol": symbol,
                    "name": name,
                    "ranking_position": ranking_pos,
                    "gap_pct": round(gap_pct, 2),
                    "current_price": float(current_price),
                    "open_price": 0.0,  # 나중에 board 조회 시 업데이트
                    "previous_close": float(previous_close),
                    "volume": int(trading_volume or 0),
                    "filter_result": "PASS",
                    "filter_detail": "",
                }
                
                # [ETF 제외 필터]
                is_etf = False
                symbol_str = symbol.strip()
                if symbol_str.isdigit():
                    val = int(symbol_str)
                    # 일본 ETF/REIT 주요 대역
                    if (1300 <= val <= 1499) or (1500 <= val <= 1699) or (2000 <= val <= 2099) or (2500 <= val <= 2699) or (2800 <= val <= 2899):
                        is_etf = True
                
                name_lower = name.lower() if name else ""
                if "etf" in name_lower or "上場" in name_lower or "インデックス" in name_lower or "レバレッジ" in name_lower:
                    is_etf = True
                
                if is_etf:
                    _logger.info(f"[Universe] ⏭️ ETF/REIT 제외: {symbol} ({name})")
                    log_entry["filter_result"] = "ETF제외"
                    log_entry["filter_detail"] = f"ETF/REIT 종목 제외"
                    full_log.append(log_entry)
                    continue
                
                # [가격 상한 필터] - 갭 필터 전에 적용하여 고가 종목 조기 제거
                if max_buy_price > 0 and current_price >= max_buy_price:
                    _logger.info(f"[Universe] ⏭️ 가격 초과 제외: {symbol} ({name}) 현재가 ¥{current_price:,.0f} >= 상한 ¥{max_buy_price:,.0f}")
                    log_entry["filter_result"] = "가격초과"
                    log_entry["filter_detail"] = f"현재가 ¥{current_price:,.0f} >= 상한 ¥{max_buy_price:,.0f}"
                    full_log.append(log_entry)
                    continue
                
                # 필터: gap_min% <= gap_pct <= gap_max%
                if gap_pct < gap_min:
                    log_entry["filter_result"] = "갭범위미달"
                    log_entry["filter_detail"] = f"gap {gap_pct:+.2f}% < 하한 {gap_min}%"
                    full_log.append(log_entry)
                    _logger.debug(f"[Universe] ❌ 갭 필터 제외: {symbol}: gap={gap_pct:+.2f}% (범위 {gap_min}~{gap_max}% 밖)")
                    continue
                elif gap_pct > gap_max:
                    log_entry["filter_result"] = "갭범위초과"
                    log_entry["filter_detail"] = f"gap {gap_pct:+.2f}% > 상한 {gap_max}%"
                    full_log.append(log_entry)
                    _logger.debug(f"[Universe] ❌ 갭 필터 제외: {symbol}: gap={gap_pct:+.2f}% (범위 {gap_min}~{gap_max}% 밖)")
                    continue
                
                _logger.debug(f"[Universe] ✅ 갭 필터 통과: {symbol} ({name}): gap={gap_pct:+.2f}%")
                filtered.append({
                    "symbol": symbol,
                    "name": name,
                    "current_price": float(current_price),
                    "previous_close": float(previous_close),
                    "gap_pct": round(gap_pct, 2),
                    "volume": int(trading_volume or 0),
                    "_log_entry": log_entry,  # 임시: 시가 검증 후 최종 로그에 추가
                })
            
            # 5. 시가 대비 약세 종목 필터링 (갭 채움 방지)
            if filtered:
                _logger.info(f"[Universe] 갭/ETF 필터 통과 {len(filtered)}개 종목의 시가 검증을 시작합니다.")
                
                import asyncio
                tasks = [self.client.get_board(f_item["symbol"]) for f_item in filtered]
                boards = []
                try:
                    boards = await asyncio.gather(*tasks, return_exceptions=True)
                except Exception as ex:
                    _logger.error(f"[Universe] 시가 조회 병렬 처리 중 실패: {ex}")
                
                final_filtered = []
                for f_item, board in zip(filtered, boards):
                    log_entry = f_item.pop("_log_entry")
                    
                    if isinstance(board, Exception):
                        _logger.warning(f"[Universe] {f_item['symbol']} 시가 조회 중 예외 발생: {board}. 리스트에 유지합니다.")
                        log_entry["filter_result"] = "PASS"
                        log_entry["filter_detail"] = "시가 조회 실패 (유지)"
                        full_log.append(log_entry)
                        final_filtered.append(f_item)
                        continue
                    
                    if not board:
                        log_entry["filter_result"] = "PASS"
                        full_log.append(log_entry)
                        final_filtered.append(f_item)
                        continue
                    
                    open_price = board.open_price
                    curr_price = board.current_price if board.current_price > 0 else f_item["current_price"]
                    log_entry["open_price"] = float(open_price) if open_price else 0.0
                    log_entry["current_price"] = float(curr_price)
                    
                    # 시가 정보가 있고 시장이 열려 있는 경우
                    if open_price > 0:
                        # 시가 대비 약세 필터: 현재가가 시가보다 낮으면(음봉) 제외
                        if curr_price < open_price:
                            _logger.info(
                                f"[Universe] ❌ 시가 대비 약세 종목 제외: {f_item['symbol']} ({f_item['name']}) "
                                f"시가=¥{open_price:,.1f}, 현재가=¥{curr_price:,.1f} (음봉/갭락세)"
                            )
                            log_entry["filter_result"] = "시가약세"
                            log_entry["filter_detail"] = f"현재가 ¥{curr_price:,.0f} < 시가 ¥{open_price:,.0f} (음봉)"
                            full_log.append(log_entry)
                            continue
                        
                        # [NEW] 시가 대비 과도한 상승 필터: 아침 스파이크 꼭대기 매수 방지
                        rise_from_open = ((curr_price - open_price) / open_price) * 100 if open_price > 0 else 0
                        if rise_from_open > max_rise_from_open_pct:
                            _logger.info(
                                f"[Universe] ❌ 시가 대비 과도 상승 종목 제외: {f_item['symbol']} ({f_item['name']}) "
                                f"시가=¥{open_price:,.1f}, 현재가=¥{curr_price:,.1f} "
                                f"(시가 대비 +{rise_from_open:.2f}% > 한도 +{max_rise_from_open_pct}%)"
                            )
                            log_entry["filter_result"] = "시가과열"
                            log_entry["filter_detail"] = f"시가 대비 +{rise_from_open:.2f}% > 한도 +{max_rise_from_open_pct}%"
                            full_log.append(log_entry)
                            continue
                        
                        # [NEW] 시가 기준 갭 검증: 과도한 갭업 종목 이중 체크
                        prev_close = f_item.get("previous_close", 0)
                        if prev_close > 0:
                            open_gap_pct = ((open_price - prev_close) / prev_close) * 100
                            if open_gap_pct > gap_max:
                                _logger.info(
                                    f"[Universe] ❌ 시가 기준 갭 초과 종목 제외: {f_item['symbol']} ({f_item['name']}) "
                                    f"전일종가=¥{prev_close:,.1f}, 시가=¥{open_price:,.1f} "
                                    f"(시가 갭 +{open_gap_pct:.2f}% > 상한 +{gap_max}%)"
                                )
                                log_entry["filter_result"] = "시가갭초과"
                                log_entry["filter_detail"] = f"시가 갭 +{open_gap_pct:.2f}% > 상한 +{gap_max}%"
                                full_log.append(log_entry)
                                continue
                    
                    # 실시간 현재가로 업데이트 후 리스트 추가
                    f_item["current_price"] = curr_price
                    log_entry["filter_result"] = "PASS"
                    full_log.append(log_entry)
                    final_filtered.append(f_item)
                
                filtered = final_filtered
            
            _logger.info(
                f"[Universe] 최종 Intraday leaders: {len(filtered)} / {len(top_items)} "
                f"(gap filter: +{gap_min}% ~ +{gap_max}%)"
            )
            
            # 상위 20개만 로그에 유지
            full_log = full_log[:20]
            
            return filtered, full_log
            
        except Exception as e:
            _logger.error(f"[Universe] fetch_intraday_leaders failed: {e}")
            return [], []

    async def fetch_stock_name(self, symbol: str) -> str:
        """
        Fetch stock name from local map or external source (Yahoo Finance).
        
        Args:
            symbol: Stock symbol (e.g., "7203")
            
        Returns:
            Stock name (e.g., "Toyota Motor Corp.") or "Unknown Stock"
        """
        # 1. Check local map
        stock_map = self.load_stock_map()
        if symbol in stock_map:
            return stock_map[symbol]
            
        # 2. Check external source (Yahoo Finance)
        try:
            import yfinance as yf
            # Japanese stocks usually need .T suffix
            ticker_symbol = f"{symbol}.T" if not symbol.endswith(".T") else symbol
            ticker = yf.Ticker(ticker_symbol)
            
            # Fetch info (this is blocking, ideally should be run in executor)
            # But for this use case (single manual add), it's acceptable
            info = ticker.info
            name = info.get("shortName") or info.get("longName")
            
            if name:
                return name
        except Exception as e:
            print(f"Error fetching name for {symbol}: {e}")
            
        return "Unknown Stock"
