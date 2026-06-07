# -*- coding: utf-8 -*-
"""
Report Service Module

Generates daily trading reports with per-strategy performance analysis.
Reports are saved as markdown files and optionally sent via Telegram.
"""
import logging
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

from backend.market_index_service import MarketIndexService

from backend.database import Database, TradeRecord, AnalysisCandidate, ExtractionLogEntry

logger = logging.getLogger(__name__)

REPORTS_DIR = Path(__file__).parent.parent / "reports"
REPORTS_DIR.mkdir(exist_ok=True)


def _format_price(price: float) -> str:
    """Format price for report display.
    
    Prices under 1000 JPY show 1 decimal place (e.g. ¥156.4)
    to prevent confusing cases like NTT where ¥156/¥156 shows ¥+40 profit.
    Prices 1000+ display as integers (e.g. ¥5,490).
    """
    if price < 1000:
        return f"¥{price:,.1f}"
    return f"¥{price:,.0f}"


class ReportService:
    """
    Daily Trading Report Generator.
    
    Generates per-strategy performance reports for strategy comparison.
    Designed for 2-week simulation period to select best strategy for live trading.
    """

    def __init__(self, app_state: Dict[str, Any]):
        self.app_state = app_state
        self.db: Database = app_state.get("database") or Database()

    async def generate_daily_report(self, target_date: str = None) -> str:
        """
        Generate a daily trading report.
        
        Args:
            target_date: Date string (YYYY-MM-DD). Defaults to today.
            
        Returns:
            Markdown report string.
        """
        if not target_date:
            target_date = datetime.now().strftime("%Y-%m-%d")

        trades = self.db.get_trades_by_date(target_date)
        all_trades = self.db.get_trades(limit=10000)
        
        # 전략별 누적 성과 랭킹을 위해 정확히 최근 2주(14일) 전까지의 데이터만 필터링하여 사용
        target_dt = datetime.strptime(target_date, "%Y-%m-%d").date()
        cutoff_date = target_dt - timedelta(days=14)
        all_trades = [t for t in all_trades if t.timestamp.date() >= cutoff_date]

        report = self._build_report(target_date, trades, all_trades)

        # Save to file
        report_path = REPORTS_DIR / f"{target_date}.md"
        report_path.write_text(report, encoding="utf-8")
        logger.info(f"[Report] Saved daily report to {report_path}")

        # Send via Telegram
        await self._send_telegram(target_date, trades, all_trades)

        return report

    def _build_report(
        self, 
        target_date: str, 
        today_trades: List[TradeRecord], 
        all_trades: List[TradeRecord]
    ) -> str:
        """Build markdown report content."""
        lines = []
        lines.append(f"# 일일 매매 보고서 - {target_date}")
        lines.append("")

        # === 1. Today Summary ===
        buy_trades = [t for t in today_trades if t.side == "BUY"]
        sell_trades = [t for t in today_trades if t.side == "SELL"]
        total_pnl = sum(t.realized_pnl or 0 for t in today_trades)
        wins = sum(1 for t in sell_trades if (t.realized_pnl or 0) > 0)
        losses = sum(1 for t in sell_trades if (t.realized_pnl or 0) < 0)
        win_rate = (wins / len(sell_trades) * 100) if sell_trades else 0

        lines.append("## 📊 당일 요약")
        lines.append("")
        lines.append(f"| 항목 | 수치 |")
        lines.append(f"|------|------|")
        lines.append(f"| 총 거래 | {len(today_trades)}건 (매수 {len(buy_trades)} / 매도 {len(sell_trades)}) |")
        lines.append(f"| 실현 손익 | ¥{total_pnl:+,.0f} |")
        lines.append(f"| 승률 | {win_rate:.0f}% ({wins}승 / {losses}패) |")
        lines.append("")

        # === 1.5 Market Index Sections ===
        market_index_service: MarketIndexService = self.app_state.get("market_index_service")
        if not market_index_service:
            market_index_service = MarketIndexService()
        
        market_data = market_index_service.get_market_data(target_date)

        # --- US Market ---
        us_data = market_data.get("us_market", {})
        if us_data:
            lines.append("## 🇺🇸 미국 시장 동향 (전일)")
            lines.append("")
            lines.append("| 지수 | 종가 | 변동 | 변동률 | 상태 |")
            lines.append("|------|------|------|--------|------|")

            up_count = 0
            down_count = 0
            for ticker, info in us_data.items():
                name = info["name"]
                close = info["close"]
                change = info["change"]
                change_pct = info["change_pct"]
                if info["direction"] == "up":
                    arrow = "📈 상승"
                    up_count += 1
                else:
                    arrow = "📉 하락"
                    down_count += 1
                lines.append(
                    f"| {name} | {close:,.2f} | {change:+,.2f} | {change_pct:+.2f}% | {arrow} |"
                )

            # Summary line
            if up_count > down_count:
                summary = "미국 시장 전반적 상승 → 일본 시장 긍정적 영향 예상"
            elif down_count > up_count:
                summary = "미국 시장 전반적 하락 → 일본 시장 부정적 영향 주의"
            else:
                summary = "미국 시장 혼조세 → 일본 시장 방향성 불확실"
            lines.append("")
            lines.append(f"> 💡 {summary}")
            lines.append("")

        # --- JP Market Index Snapshots ---
        jp_snapshots = market_data.get("jp_snapshots", {})
        if jp_snapshots:
            lines.append("## 🇯🇵 일본 시장 지수 추이")
            lines.append("")
            
            # Collect all tickers across snapshots
            all_tickers = {}
            for label, snap_info in jp_snapshots.items():
                for ticker, data in snap_info.get("data", {}).items():
                    all_tickers[ticker] = data["name"]

            # Build header
            header = "| 시점 |"
            separator = "|------|"
            for ticker, name in all_tickers.items():
                header += f" {name} | 변동률 |"
                separator += "--------|--------|"
            lines.append(header)
            lines.append(separator)

            # Get first snapshot prices for change calculation
            first_label = None
            first_prices = {}
            snapshot_order = ["09:05", "09:10", "15:30"]
            sorted_labels = sorted(
                jp_snapshots.keys(),
                key=lambda x: snapshot_order.index(x) if x in snapshot_order else 99
            )
            
            label_display = {
                "09:05": "09:05 (개장)",
                "09:10": "09:10 (5분후)",
                "15:30": "15:30 (종가)",
            }

            for label in sorted_labels:
                snap_info = jp_snapshots[label]
                display_label = label_display.get(label, label)
                row = f"| {display_label} |"

                for ticker in all_tickers:
                    data = snap_info.get("data", {}).get(ticker, {})
                    price = data.get("price", 0)

                    if first_label is None:
                        first_prices[ticker] = price
                        row += f" {price:,.2f} | - |"
                    else:
                        base = first_prices.get(ticker, 0)
                        if base > 0 and price > 0:
                            pct = ((price - base) / base) * 100
                            pct_str = f"{pct:+.2f}%"
                        else:
                            pct_str = "-"
                        row += f" {price:,.2f} | {pct_str} |"

                lines.append(row)
                if first_label is None:
                    first_label = label

            # Summary for JP indices
            if len(sorted_labels) >= 2:
                last_label = sorted_labels[-1]
                last_snap = jp_snapshots[last_label].get("data", {})
                summaries = []
                for ticker in all_tickers:
                    base = first_prices.get(ticker, 0)
                    last_price = last_snap.get(ticker, {}).get("price", 0)
                    if base > 0 and last_price > 0:
                        pct = ((last_price - base) / base) * 100
                        direction = "상승" if pct >= 0 else "하락"
                        summaries.append(f"{all_tickers[ticker]} {pct:+.2f}% {direction}")
                
                if summaries:
                    lines.append("")
                    lines.append(f"> 💡 장중 추이: {', '.join(summaries)}")
            lines.append("")

        # === Pre-load: Analysis candidates and trade lookups ===
        # (Needed by both strategy performance and candidate detail sections)
        candidates = self.db.get_analysis_candidates(target_date)
        from collections import OrderedDict
        grouped = OrderedDict()
        for c in candidates:
            universe_label = "N225" if c.target_universe == "nikkei225" else "JPX400" if c.target_universe == "nikkei400" else c.target_universe
            key = f"{c.extraction_strategy} ({universe_label})"
            if key not in grouped:
                grouped[key] = []
            grouped[key].append(c)

        # Build sell/buy trade lookups
        sell_lookup = {}
        for t in today_trades:
            if t.side == "SELL":
                ext = t.extraction_strategy or t.strategy_name or "Unknown"
                sell_lookup[(ext, t.target_universe, t.symbol)] = t
                universe_label = ""
                if t.target_universe:
                    universe_label = "N225" if t.target_universe == "nikkei225" else "JPX400" if t.target_universe == "nikkei400" else t.target_universe
                sell_lookup[(ext, universe_label, t.symbol)] = t

        sell_by_symbol = {}
        buy_by_symbol = {}
        for t in today_trades:
            if t.side == "SELL":
                sell_by_symbol[t.symbol] = t
            elif t.side == "BUY":
                buy_by_symbol[t.symbol] = t

        # === 2. Per-Strategy Performance (Today) ===
        lines.append("## 🏆 전략별 성과 (당일)")
        lines.append("")

        # All 18 registered strategies (9 extraction × 2 universes)
        ALL_EXTRACTION_STRATEGIES = [
            "SMAGoldenDeadCross", "StockSMAEMACross", "StockMACDShift",
            "StockRSIStochastic", "TurtleBreakoutFilter", "TurtleLiquidityFilter",
            "TurtleVolatilityFilter", "BollingerBands", "CandlePatterns",
            "TripleConfirmScorer",
        ]
        ALL_UNIVERSES = [("nikkei225", "N225"), ("nikkei400", "JPX400")]
        all_strategy_names = set()
        for ext in ALL_EXTRACTION_STRATEGIES:
            for _, ulabel in ALL_UNIVERSES:
                all_strategy_names.add(f"{ext} ({ulabel})")

        strategy_stats = defaultdict(lambda: {
            "buys": 0, "sells": 0, "pnl": 0.0, "wins": 0, "losses": 0, "symbols": []
        })

        # Track symbols already counted per strategy to avoid double-counting
        strategy_counted_symbols = defaultdict(set)

        # 1) Count actual trades (BOUGHT stocks)
        for t in today_trades:
            ext = t.extraction_strategy or t.strategy_name or "Unknown"
            universe_label = ""
            if t.target_universe:
                universe_label = "N225" if t.target_universe == "nikkei225" else "JPX400" if t.target_universe == "nikkei400" else t.target_universe
            name = f"{ext} ({universe_label})" if universe_label else ext
            strategy_stats[name]["symbols"].append(t.symbol)
            strategy_counted_symbols[name].add(t.symbol)
            if t.side == "BUY":
                strategy_stats[name]["buys"] += 1
            else:
                strategy_stats[name]["sells"] += 1
                pnl = t.realized_pnl or 0
                strategy_stats[name]["pnl"] += pnl
                if pnl > 0:
                    strategy_stats[name]["wins"] += 1
                elif pnl < 0:
                    strategy_stats[name]["losses"] += 1

        # 2) Include SKIPPED candidates using their actual trade data from other strategies
        for strat_key, cands in grouped.items():
            for c in cands:
                if c.status != "SKIPPED" or c.symbol == "-":
                    continue
                # Skip if already counted in this strategy
                if c.symbol in strategy_counted_symbols[strat_key]:
                    continue
                # Look up actual buy/sell from another strategy
                skip_buy_t = buy_by_symbol.get(c.symbol)
                skip_sell_t = sell_by_symbol.get(c.symbol)
                if skip_buy_t:
                    strategy_stats[strat_key]["buys"] += 1
                    strategy_stats[strat_key]["symbols"].append(c.symbol)
                    strategy_counted_symbols[strat_key].add(c.symbol)
                if skip_sell_t:
                    strategy_stats[strat_key]["sells"] += 1
                    pnl = skip_sell_t.realized_pnl or 0
                    strategy_stats[strat_key]["pnl"] += pnl
                    if pnl > 0:
                        strategy_stats[strat_key]["wins"] += 1
                    elif pnl < 0:
                        strategy_stats[strat_key]["losses"] += 1

        if strategy_stats:
            lines.append("| 전략 | 매수 | 매도 | 실현손익 | 승률 |")
            lines.append("|------|------|------|----------|------|")
            
            # Sort by PnL descending
            sorted_strats = sorted(strategy_stats.items(), key=lambda x: x[1]["pnl"], reverse=True)
            for name, stats in sorted_strats:
                total = stats["wins"] + stats["losses"]
                wr = (stats["wins"] / total * 100) if total > 0 else 0
                pnl_str = f"¥{stats['pnl']:+,.0f}"
                lines.append(f"| {name} | {stats['buys']} | {stats['sells']} | {pnl_str} | {wr:.0f}% |")
            lines.append("")
        else:
            lines.append("_당일 거래 없음_")
            lines.append("")

        # === 2.5 Strategy Execution Status (Safety Halts & No Candidates) ===
        traded_strategies = set(strategy_stats.keys())
        # (candidates and grouped already loaded above)
            
        safety_halt_strategies = []
        no_candidate_strategies = []
        
        # Identify all active configurations
        registered_names = set()
        active_configs = self.db.get_automation_configs(active_only=True)
        for c in active_configs:
            ext = c.name
            uni = c.config_json.get("target_universe", "unknown")
            uni_label = "N225" if uni == "nikkei225" else "JPX400" if uni == "nikkei400" else uni
            registered_names.add(f"{ext} ({uni_label})")
        
        # Identify strategies that were actually run today + active
        active_today = registered_names.union(grouped.keys()).union(traded_strategies)
        
        for s in sorted(active_today):
            if s in traded_strategies:
                continue
            
            cands = grouped.get(s, [])
            if not cands:
                if s in registered_names:
                    no_candidate_strategies.append((s, "필터 조건 미충족 (매수 후보 0건)"))
                else:
                    no_candidate_strategies.append((s, "데이터 누락 (시스템 미실행 또는 PC 재시작 등)"))
                continue

            if len(cands) == 1 and cands[0].symbol == "-":
                reason = cands[0].skip_reason
                if "안전 장치" in reason:
                    safety_halt_strategies.append((s, reason))
                else:
                    no_candidate_strategies.append((s, reason))
            else:
                # aggregate skip reasons from candidates
                reasons = [c.skip_reason for c in cands if c.skip_reason]
                if reasons:
                    from collections import Counter
                    r_counts = Counter(reasons)
                    r_strs = [f"{r}({cnt}건)" for r, cnt in r_counts.items()]
                    combined = ", ".join(r_strs)
                    no_candidate_strategies.append((s, f"후보발견됨 (매수 SKIP: {combined})"))
                else:
                    no_candidate_strategies.append((s, "분석 후보 미발견 또는 매수 대기"))

        if safety_halt_strategies:
            lines.append("### 🚨 매매 중단 전략 (안전 장치 가동)")
            lines.append("")
            # Group by reason
            reason_map = defaultdict(list)
            for s, r in safety_halt_strategies:
                reason_map[r].append(s)
                
            for r, strats in reason_map.items():
                reason_text = r.replace("매매 중단 (안전 장치 작동: ", "").replace(")", "")
                lines.append(f"> 아래 전략들은 시장 안전 장치 가동으로 인해 당일 매매가 중단되었습니다. (사유: {reason_text})")
                lines.append("")
                for s in strats:
                    lines.append(f"- {s}")
                lines.append("")

        if no_candidate_strategies:
            lines.append("### ⚠️ 매수 후보 미발견 전략")
            lines.append("")
            lines.append("> 아래 전략들은 당일 분석에서 매수 후보를 찾지 못했거나 매수가 발생하지 않았습니다.")
            lines.append("")
            for s, r in no_candidate_strategies:
                lines.append(f"- {s} - {r}")
            lines.append("")

        # === 2.7 Full Analysis Candidates + Trade Results ===
        # (sell_lookup, sell_by_symbol, buy_by_symbol already built above)
        
        if candidates:
            # Fetch close prices for all relevant symbols
            unique_symbols = {c.symbol for c in candidates if c.symbol != "-"}
            for t in today_trades:
                if t.symbol != "-":
                    unique_symbols.add(t.symbol)
    
            close_prices = {}
            open_prices = {}
            if unique_symbols:
                fetch_symbols = [f"{sym}.T" if not sym.endswith(".T") else sym for sym in unique_symbols]
                try:
                    import pandas as pd
                    import yfinance as yf
                    # Fetch recent day data to get final closing price
                    data = yf.download(fetch_symbols, period="1d", progress=False)
                    if not data.empty:
                        if "Close" in data:
                            closes = data["Close"]
                            for sym in fetch_symbols:
                                base_sym = sym.replace(".T", "")
                                if len(fetch_symbols) == 1:
                                    val = closes.iloc[-1]
                                else:
                                    val = closes[sym].iloc[-1] if hasattr(closes, 'columns') and sym in closes.columns else pd.NA
                                if not pd.isna(val) and float(val) > 0:
                                    close_prices[base_sym] = float(val)
                        if "Open" in data:
                            opens = data["Open"]
                            for sym in fetch_symbols:
                                base_sym = sym.replace(".T", "")
                                if len(fetch_symbols) == 1:
                                    val = opens.iloc[-1]
                                else:
                                    val = opens[sym].iloc[-1] if hasattr(opens, 'columns') and sym in opens.columns else pd.NA
                                if not pd.isna(val) and float(val) > 0:
                                    open_prices[base_sym] = float(val)
                except Exception as e:
                    logger.error(f"[Report] Failed to fetch prices: {e}")

            # NEW: Full candidate list with status and sell results
            lines.append("## 📊 전략별 분석 후보 전체")
            lines.append("")
            lines.append("> 각 전략 내 분석 후보 전체 리스트 (매수/SKIP 상태 및 매도 결과 포함)")
            lines.append("")
            
            # Aggregate rank stats (BOUGHT only)
            rank_aggregate = defaultdict(lambda: {"count": 0, "wins": 0, "losses": 0, "total_pnl": 0.0})
            
            for strat_key in sorted(grouped.keys()):
                cands = grouped[strat_key]
                if len(cands) == 1 and cands[0].symbol == "-":
                    continue
                    
                cands.sort(key=lambda c: c.rank)
                
                lines.append(f"### {strat_key}")
                lines.append("")
                lines.append("| 순위 | 종목 | 점수 | 상태 | 매수가 | 매도가 | 당일시가 | 당일종가 | 손익 | 결과 | 비고 |")
                lines.append("|------|------|------|------|--------|--------|----------|----------|------|------|------|")
                
                for c in cands:
                    # Determine status display
                    if c.status == "BOUGHT":
                        status_display = "✅ 매수"
                        # Find corresponding sell trade
                        sell_t = sell_lookup.get((c.extraction_strategy, c.target_universe, c.symbol))
                        if not sell_t:
                            sell_t = sell_by_symbol.get(c.symbol)
                        
                        if sell_t:
                            sell_price_str = _format_price(sell_t.price)
                            pnl = sell_t.realized_pnl or 0
                            pnl_str = f"¥{pnl:+,.0f}"
                            result_emoji = "✅" if pnl > 0 else "❌" if pnl < 0 else "➖"
                            
                            # Aggregate rank stats
                            rank_aggregate[c.rank]["count"] += 1
                            rank_aggregate[c.rank]["total_pnl"] += pnl
                            if pnl > 0:
                                rank_aggregate[c.rank]["wins"] += 1
                            elif pnl < 0:
                                rank_aggregate[c.rank]["losses"] += 1
                        else:
                            sell_price_str = "-"
                            pnl_str = "-"
                            result_emoji = "⏳"
                        
                        # Fix: Use actual buy trade price if available, otherwise candidate price
                        buy_t = buy_by_symbol.get(c.symbol)
                        if buy_t:
                            buy_price_str = _format_price(buy_t.price)
                        else:
                            buy_price_str = _format_price(c.price)
                        
                        note = ""
                        
                    elif c.status == "SKIPPED":
                        status_display = "⏭️ SKIP"
                        note = c.skip_reason
                        
                        # Look up actual trade data for this symbol (from any strategy)
                        skip_buy_t = buy_by_symbol.get(c.symbol)
                        skip_sell_t = sell_by_symbol.get(c.symbol)
                        
                        if skip_buy_t:
                            buy_price_str = _format_price(skip_buy_t.price)
                        else:
                            buy_price_str = "-"
                        
                        if skip_sell_t:
                            sell_price_str = _format_price(skip_sell_t.price)
                            pnl = skip_sell_t.realized_pnl or 0
                            pnl_str = f"¥{pnl:+,.0f}"
                            result_emoji = "✅" if pnl > 0 else "❌" if pnl < 0 else "➖"
                        elif skip_buy_t:
                            # Bought but not yet sold (still holding)
                            sell_price_str = "-"
                            pnl_str = "-"
                            result_emoji = "⏳"
                        else:
                            sell_price_str = "-"
                            pnl_str = "-"
                            result_emoji = "-"
                        
                    else:  # PENDING
                        status_display = "⏳ 대기"
                        note = ""
                        
                        # Look up actual trade data for this symbol
                        pending_buy_t = buy_by_symbol.get(c.symbol)
                        pending_sell_t = sell_by_symbol.get(c.symbol)
                        
                        if pending_buy_t:
                            buy_price_str = _format_price(pending_buy_t.price)
                        else:
                            buy_price_str = "-"
                        
                        if pending_sell_t:
                            sell_price_str = _format_price(pending_sell_t.price)
                            pnl = pending_sell_t.realized_pnl or 0
                            pnl_str = f"¥{pnl:+,.0f}"
                            result_emoji = "✅" if pnl > 0 else "❌" if pnl < 0 else "➖"
                        elif pending_buy_t:
                            sell_price_str = "-"
                            pnl_str = "-"
                            result_emoji = "⏳"
                        else:
                            sell_price_str = "-"
                            pnl_str = "-"
                            result_emoji = "-"
                    
                    score_str = f"{c.score:.1f}" if c.score else "-"
                    name_display = f"{c.symbol_name} ({c.symbol})" if c.symbol_name else c.symbol
                    
                    close_price = close_prices.get(c.symbol)
                    close_price_str = _format_price(close_price) if close_price else "-"
                    
                    open_price = open_prices.get(c.symbol)
                    open_price_str = _format_price(open_price) if open_price else "-"
                    
                    lines.append(
                        f"| {c.rank} | {name_display} | {score_str} | {status_display} | {buy_price_str} | {sell_price_str} | {open_price_str} | {close_price_str} | {pnl_str} | {result_emoji} | {note} |"
                    )
                
                lines.append("")
            
            # Rank aggregate summary (BOUGHT only)
            if rank_aggregate:
                lines.append("### 📈 순위별 집계 요약 (매수된 종목 기준)")
                lines.append("")
                lines.append("| 순위 | 거래수 | 승 | 패 | 승률 | 총손익 | 평균손익 |")
                lines.append("|------|--------|-----|-----|------|--------|----------|")
                
                for rank in sorted(rank_aggregate.keys()):
                    stats = rank_aggregate[rank]
                    total = stats["wins"] + stats["losses"]
                    wr = (stats["wins"] / total * 100) if total > 0 else 0
                    avg_pnl = stats["total_pnl"] / stats["count"] if stats["count"] > 0 else 0
                    lines.append(
                        f"| {rank} | {stats['count']} | {stats['wins']} | {stats['losses']} | {wr:.0f}% | ¥{stats['total_pnl']:+,.0f} | ¥{avg_pnl:+,.0f} |"
                    )
                lines.append("")
        
        else:
            # FALLBACK: Legacy rank-based view (no candidate data available)
            buy_trades_by_strategy = defaultdict(list)
            sell_trades_by_strategy = defaultdict(dict)

            for t in today_trades:
                ext = t.extraction_strategy or t.strategy_name or "Unknown"
                universe_label = ""
                if t.target_universe:
                    universe_label = "N225" if t.target_universe == "nikkei225" else "JPX400" if t.target_universe == "nikkei400" else t.target_universe
                strat_name = f"{ext} ({universe_label})" if universe_label else ext
                
                if t.side == "BUY":
                    buy_trades_by_strategy[strat_name].append(t)
                elif t.side == "SELL":
                    sell_trades_by_strategy[strat_name][t.symbol] = t

            if buy_trades_by_strategy:
                lines.append("## 📊 전략별 순위별 매매 상세")
                lines.append("")
                lines.append("> 각 전략 내 매수 순위별 거래 결과 (순위 1 = 분석 점수 최상위)")
                lines.append("")

                rank_aggregate = defaultdict(lambda: {"count": 0, "wins": 0, "losses": 0, "total_pnl": 0.0})

                for strat_name in sorted(buy_trades_by_strategy.keys()):
                    buys = buy_trades_by_strategy[strat_name]
                    sells = sell_trades_by_strategy.get(strat_name, {})
                    
                    buys_sorted = sorted(buys, key=lambda t: t.timestamp)
                    
                    lines.append(f"### {strat_name}")
                    lines.append("")
                    lines.append("| 순위 | 종목 | 매수가 | 매도가 | 당일시가 | 당일종가 | 손익 | 결과 |")
                    lines.append("|------|------|--------|--------|----------|----------|------|------|")
                    
                    for idx, buy_t in enumerate(buys_sorted):
                        rank = buy_t.buy_rank if buy_t.buy_rank > 0 else (idx + 1)
                        sell_t = sells.get(buy_t.symbol)
                        
                        if sell_t:
                            sell_price = sell_t.price
                            pnl = sell_t.realized_pnl or 0
                            result_emoji = "✅" if pnl > 0 else "❌" if pnl < 0 else "➖"
                            pnl_str = f"¥{pnl:+,.0f}"
                            
                            rank_aggregate[rank]["count"] += 1
                            rank_aggregate[rank]["total_pnl"] += pnl
                            if pnl > 0:
                                rank_aggregate[rank]["wins"] += 1
                            elif pnl < 0:
                                rank_aggregate[rank]["losses"] += 1
                        else:
                            sell_price = "-"
                            pnl_str = "-"
                            result_emoji = "⏳"
                        
                        sell_price_str = _format_price(sell_price) if isinstance(sell_price, (int, float)) else sell_price
                        close_price = close_prices.get(buy_t.symbol, None) if 'close_prices' in locals() else None
                        close_price_str = _format_price(close_price) if close_price else "-"
                        
                        open_price = open_prices.get(buy_t.symbol, None) if 'open_prices' in locals() else None
                        open_price_str = _format_price(open_price) if open_price else "-"
                        
                        lines.append(
                            f"| {rank} | {buy_t.symbol_name} ({buy_t.symbol}) | {_format_price(buy_t.price)} | {sell_price_str} | {open_price_str} | {close_price_str} | {pnl_str} | {result_emoji} |"
                        )
                    
                    lines.append("")

                if rank_aggregate:
                    lines.append("### 📈 순위별 집계 요약")
                    lines.append("")
                    lines.append("| 순위 | 거래수 | 승 | 패 | 승률 | 총손익 | 평균손익 |")
                    lines.append("|------|--------|-----|-----|------|--------|----------|")
                    
                    for rank in sorted(rank_aggregate.keys()):
                        stats = rank_aggregate[rank]
                        total = stats["wins"] + stats["losses"]
                        wr = (stats["wins"] / total * 100) if total > 0 else 0
                        avg_pnl = stats["total_pnl"] / stats["count"] if stats["count"] > 0 else 0
                        lines.append(
                            f"| {rank} | {stats['count']} | {stats['wins']} | {stats['losses']} | {wr:.0f}% | ¥{stats['total_pnl']:+,.0f} | ¥{avg_pnl:+,.0f} |"
                        )
                    lines.append("")

        # === 2.9 Full Extraction Log (상위 20개 + 탈락 요약) ===
        extraction_log = self.db.get_extraction_log(target_date)
        if extraction_log:
            lines.append("## 🔍 당일 종목 검색 전체 로그")
            lines.append("")
            lines.append("> Ranking API 원본 리스트에서 각 종목의 필터 통과/탈락 사유 (상위 20개 + 탈락 요약)")
            lines.append("")
            
            # Group by strategy
            from collections import OrderedDict
            log_by_strategy = OrderedDict()
            for entry in extraction_log:
                universe_label = "N225" if entry.target_universe == "nikkei225" else "JPX400" if entry.target_universe == "nikkei400" else entry.target_universe
                key = f"{entry.extraction_strategy} ({universe_label})"
                if key not in log_by_strategy:
                    log_by_strategy[key] = []
                log_by_strategy[key].append(entry)
            
            for strat_key, entries in log_by_strategy.items():
                # Find the cycle time for display
                cycle_time = entries[0].cycle_time if entries else ""
                lines.append(f"### {strat_key} - {cycle_time} 추출")
                lines.append("")
                
                # Separate PASS and filtered entries
                passed = [e for e in entries if e.filter_result == "PASS"]
                filtered_out = [e for e in entries if e.filter_result != "PASS"]
                
                # Table: Show PASS entries (with final rank and score)
                lines.append("#### ✅ 필터 통과 종목")
                lines.append("")
                if passed:
                    lines.append("| # | 종목 | 갭% | 현재가 | 시가 | 거래량 | 점수 | 최종순위 | 점수근거 |")
                    lines.append("|---|------|-----|--------|------|--------|------|----------|----------|")
                    for e in passed:
                        name_display = f"{e.symbol_name} ({e.symbol})" if e.symbol_name else e.symbol
                        price_str = _format_price(e.current_price) if e.current_price > 0 else "-"
                        open_str = _format_price(e.open_price) if e.open_price > 0 else "-"
                        vol_str = f"{e.volume:,}" if e.volume > 0 else "-"
                        score_str = f"{e.score:.1f}" if e.score > 0 else "-"
                        rank_str = f"{e.final_rank}위" if e.final_rank > 0 else "-"
                        
                        # Find score reason from candidates
                        reason = ""
                        for c in candidates:
                            if c.symbol == e.symbol:
                                # Look for reason in the targets
                                break
                        
                        lines.append(
                            f"| {e.ranking_position} | {name_display} | {e.gap_pct:+.2f}% | {price_str} | {open_str} | {vol_str} | {score_str} | {rank_str} | |"
                        )
                    lines.append("")
                else:
                    lines.append("_필터 통과 종목 없음_")
                    lines.append("")
                
                # Rejection summary: Group by filter_result, show each stock
                if filtered_out:
                    lines.append("#### ❌ 탈락 종목 전체")
                    lines.append("")
                    
                    from collections import Counter
                    reason_counts = Counter(e.filter_result for e in filtered_out)
                    
                    lines.append("| # | 종목 | 탈락 사유 | 상세 |")
                    lines.append("|---|------|-----------|------|")
                    
                    idx = 1
                    for reason, count in reason_counts.most_common():
                        reason_entries = [e for e in filtered_out if e.filter_result == reason]
                        for ex in reason_entries:
                            name_disp = f"{ex.symbol_name}({ex.symbol})" if ex.symbol_name else ex.symbol
                            detail = ex.filter_detail if ex.filter_detail else ""
                            lines.append(f"| {idx} | {name_disp} | {reason} | {detail} |")
                            idx += 1
                    
                    lines.append("")
                
                lines.append("")

        # === 3. Cumulative Strategy Ranking ===
        lines.append("## 📈 전략별 누적 성과 랭킹 (시뮬레이션 전체)")
        lines.append("")
        lines.append("> 2주 시뮬레이션 후 실전 전환 시 최적 전략 선정 참고용")
        lines.append("")

        cumulative = defaultdict(lambda: {
            "total_trades": 0, "sells": 0, "pnl": 0.0, "wins": 0, "losses": 0, "days": set()
        })

        for t in all_trades:
            # Build strategy display name with universe
            ext = t.extraction_strategy or t.strategy_name or "Unknown"
            universe_label = ""
            if t.target_universe:
                universe_label = "N225" if t.target_universe == "nikkei225" else "JPX400" if t.target_universe == "nikkei400" else t.target_universe
            name = f"{ext} ({universe_label})" if universe_label else ext
            cumulative[name]["total_trades"] += 1
            cumulative[name]["days"].add(t.timestamp.strftime("%Y-%m-%d"))
            if t.side == "SELL":
                cumulative[name]["sells"] += 1
                pnl = t.realized_pnl or 0
                cumulative[name]["pnl"] += pnl
                if pnl > 0:
                    cumulative[name]["wins"] += 1
                elif pnl < 0:
                    cumulative[name]["losses"] += 1

        if cumulative:
            lines.append("| 순위 | 전략 | 총거래 | 실현손익 | 승률 | 활동일수 |")
            lines.append("|------|------|--------|----------|------|----------|")

            sorted_cum = sorted(cumulative.items(), key=lambda x: x[1]["pnl"], reverse=True)
            for rank, (name, stats) in enumerate(sorted_cum, 1):
                total_sell = stats["wins"] + stats["losses"]
                wr = (stats["wins"] / total_sell * 100) if total_sell > 0 else 0
                pnl_str = f"¥{stats['pnl']:+,.0f}"
                emoji = "🥇" if rank == 1 else "🥈" if rank == 2 else "🥉" if rank == 3 else f"{rank:2d}"
                lines.append(
                    f"| {emoji} | {name} | {stats['total_trades']} | {pnl_str} | {wr:.0f}% | {len(stats['days'])}일 |"
                )
            lines.append("")
        else:
            lines.append("_누적 데이터 없음_")
            lines.append("")

        # === 4. Trade Details ===
        lines.append("## 📋 당일 거래 상세")
        lines.append("")

        if today_trades:
            lines.append("| 시간 | 종목 | 매매 | 가격 | 수량 | 전략 | 손익 |")
            lines.append("|------|------|------|------|------|------|------|")
            for t in today_trades:
                time_str = t.timestamp.strftime("%H:%M:%S")
                side_kr = "매수" if t.side == "BUY" else "매도"
                pnl = t.realized_pnl or 0
                pnl_str = f"¥{pnl:+,.0f}" if pnl != 0 else "-"
                # Build strategy display with universe
                ext = t.extraction_strategy or t.strategy_name or '-'
                universe_label = ""
                if t.target_universe:
                    universe_label = "N225" if t.target_universe == "nikkei225" else "JPX400" if t.target_universe == "nikkei400" else t.target_universe
                strategy_display = f"{ext} ({universe_label})" if universe_label else ext
                lines.append(
                    f"| {time_str} | {t.symbol_name} ({t.symbol}) | {side_kr} | {_format_price(t.price)} | {t.qty} | {strategy_display} | {pnl_str} |"
                )
            lines.append("")
        else:
            lines.append("_당일 거래 없음_")
            lines.append("")

        # === Footer ===
        lines.append("---")
        lines.append(f"_생성: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | Antigravity Auto-Trading System_")

        return "\n".join(lines)

    async def _send_telegram(
        self,
        target_date: str,
        today_trades: List[TradeRecord],
        all_trades: List[TradeRecord]
    ):
        """Send summary via Telegram."""
        notifier = self.app_state.get("notifier")
        if not notifier or not notifier.is_configured:
            logger.info("[Report] Telegram not configured, skipping notification")
            return

        # Build compact Telegram message
        buy_count = sum(1 for t in today_trades if t.side == "BUY")
        sell_count = sum(1 for t in today_trades if t.side == "SELL")
        total_pnl = sum(t.realized_pnl or 0 for t in today_trades)
        sell_trades = [t for t in today_trades if t.side == "SELL"]
        wins = sum(1 for t in sell_trades if (t.realized_pnl or 0) > 0)
        losses = sum(1 for t in sell_trades if (t.realized_pnl or 0) < 0)
        win_rate = (wins / len(sell_trades) * 100) if sell_trades else 0

        # Cumulative top 3
        cumulative = defaultdict(float)
        for t in all_trades:
            if t.side == "SELL" and t.realized_pnl:
                name = t.extraction_strategy or t.strategy_name or "Unknown"
                universe_label = ""
                if t.target_universe:
                    universe_label = "N225" if t.target_universe == "nikkei225" else "JPX400" if t.target_universe == "nikkei400" else t.target_universe
                full_name = f"{name} ({universe_label})" if universe_label else name
                cumulative[full_name] += t.realized_pnl

        top3 = sorted(cumulative.items(), key=lambda x: x[1], reverse=True)[:3]
        top3_str = "\n".join(
            f"  {'🥇🥈🥉'[i] if i < 3 else str(i+1)} {name}: ¥{pnl:+,.0f}"
            for i, (name, pnl) in enumerate(top3)
        )

        msg = f"""
📊 <b>일일 매매 보고서 ({target_date})</b>
━━━━━━━━━━━━━━━━
📈 거래: {len(today_trades)}건 (매수 {buy_count} / 매도 {sell_count})
💰 실현손익: ¥{total_pnl:+,.0f}
🎯 승률: {win_rate:.0f}% ({wins}승/{losses}패)

🏆 <b>누적 TOP 3 전략</b>
{top3_str if top3_str else '  데이터 없음'}
"""
        try:
            await notifier._send_message(msg.strip())
            logger.info("[Report] Telegram report sent")
        except Exception as e:
            logger.error(f"[Report] Telegram send failed: {e}")
