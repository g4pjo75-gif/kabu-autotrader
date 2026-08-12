# -*- coding: utf-8 -*-
"""
Dashboard Page

Monitoring UI with portfolio summary, positions, and real-time logs.
"""
from nicegui import ui
from typing import Any, Dict
from datetime import datetime


async def dashboard_page(app_state: Dict[str, Any]) -> None:
    """
    Dashboard Page
    
    - Summary Cards (Total Assets, Cash, Daily P&L)
    - Positions Table
    - Active Orders
    - Real-time Log Console
    """
    
    ui.label("대시보드").classes("text-2xl font-bold text-white mb-6")
    
    # === Containers ===
    
    # Global Refresh Button
    with ui.row().classes("w-full justify-end mb-4"):
        async def on_refresh_all():
            ui.notify("데이터를 갱신합니다...", type="info")
            await update_dashboard()
            ui.notify("갱신 완료", type="positive")
            
        ui.button("전체 데이터 갱신", icon="refresh", on_click=on_refresh_all).classes("bg-indigo-600 text-white")

    # 1. Summary Rows
    summary_container = ui.row().classes("w-full gap-4 mb-6")
    
    with ui.row().classes("w-full gap-6"):
        # Left Column
        left_col = ui.column().classes("flex-1 gap-6")
        # Right Column
        right_col = ui.column().classes("flex-1 gap-6")

    # 2. Positions (Left)
    with left_col:
        with ui.card().classes("bg-gray-800 rounded-lg p-6 w-full"):
            with ui.row().classes("items-center justify-between mb-4"):
                with ui.row().classes("items-center"):
                    ui.icon("account_balance_wallet").classes("text-indigo-400 mr-2")
                    ui.label("보유 포지션").classes("text-lg font-semibold text-white")
                
                with ui.row().classes("gap-2 items-center"):
                    position_badge = ui.badge("0종목").classes("bg-indigo-600")
                    ui.button(icon="refresh", on_click=lambda: update_positions()).props("flat round dense").classes("text-gray-400")
            
            ui.separator().classes("mb-4")
            positions_container = ui.column().classes("w-full")

    # 3. History & Orders & Logs (Right)
    with right_col:
        # Trade History (Recent 50)
        with ui.card().classes("bg-gray-800 rounded-lg p-6 w-full"):
            with ui.row().classes("items-center justify-between mb-4 w-full"):
                with ui.row().classes("items-center"):
                    ui.icon("history").classes("text-green-400 mr-2")
                    ui.label("최근 체결 내역 (Last 50)").classes("text-lg font-semibold text-white")
                
                ui.button(icon="refresh", on_click=lambda: update_history()).props("flat round dense").classes("text-gray-400")

            ui.separator().classes("mb-4")
            history_container = ui.column().classes("w-full max-h-60 overflow-y-auto")

        # Active Orders (미체결 주문 - 사용자 요청으로 숨김 처리)
        if False:
            with ui.card().classes("bg-gray-800 rounded-lg p-6 w-full"):
                with ui.row().classes("items-center justify-between mb-4"):
                    with ui.row().classes("items-center"):
                        ui.icon("pending_actions").classes("text-yellow-400 mr-2")
                        ui.label("미체결 주문").classes("text-lg font-semibold text-white")
                    
                    with ui.row().classes("gap-2 items-center"):
                        orders_badge = ui.badge("0건").classes("bg-yellow-600")
                        ui.button(icon="refresh", on_click=lambda: update_orders()).props("flat round dense").classes("text-gray-400")
                
                ui.separator().classes("mb-4")
                orders_container = ui.column().classes("w-full")

        # Live Logs (Auto-refresh)
        with ui.card().classes("bg-gray-800 rounded-lg p-6 w-full"):
            with ui.row().classes("items-center justify-between mb-4"):
                with ui.row().classes("items-center"):
                    ui.icon("terminal").classes("text-green-400 mr-2")
                    ui.label("실시간 로그 (자동 갱신)").classes("text-lg font-semibold text-white")
                
                # Turn off log toggle? Or keep it always on?
                # ui.switch("Auto").props("dense") 
            
            ui.separator().classes("mb-4")
            log_container = ui.column().classes("w-full h-96 overflow-y-auto bg-gray-900 rounded p-3 font-mono text-xs")

    # 4. Daily Summary (New)
    with ui.row().classes("w-full mt-6 mb-6"):
        with ui.column().classes("w-full gap-4"):
            # Summary Table
            with ui.card().classes("w-full bg-gray-800 rounded-lg p-6"):
                with ui.row().classes("items-center justify-between mb-4"):
                    with ui.row().classes("items-center"):
                        ui.icon("calendar_month").classes("text-purple-400 mr-2")
                        ui.label("일자별 매매 요약").classes("text-lg font-semibold text-white")
                    
                    ui.button(icon="refresh", on_click=lambda: update_daily_summary()).props("flat round dense").classes("text-gray-400")
                
                ui.separator().classes("mb-4")
                daily_summary_container = ui.column().classes("w-full")

            # Detailed Trade List with Date Picker
            with ui.card().classes("w-full bg-gray-800 rounded-lg p-6"):
                with ui.row().classes("items-center justify-between mb-4"):
                    with ui.row().classes("items-center"):
                        ui.icon("list").classes("text-cyan-400 mr-2")
                        ui.label("상세 매매 리스트").classes("text-lg font-semibold text-white")
                    
                    with ui.row().classes("items-center gap-2"):
                        today_str = datetime.now().strftime("%Y-%m-%d")
                        selected_date = {"value": today_str}
                        
                        with ui.input("날짜 선택", value=today_str).props('filled dark dense').classes('w-40') as date_input:
                            with ui.menu().props('no-parent-event') as date_menu:
                                with ui.date(value=today_str).bind_value(date_input) as date_picker:
                                    pass
                            with date_input.add_slot('append'):
                                ui.icon('edit_calendar').on('click', date_menu.open).classes('cursor-pointer')
                        
                        def on_date_change():
                            selected_date["value"] = date_input.value
                            update_date_details(date_input.value)
                        
                        date_input.on('change', on_date_change)
                        
                        ui.button(icon="refresh", on_click=lambda: update_date_details(date_input.value)).props("flat round dense").classes("text-gray-400")

                ui.separator().classes("mb-4")
                today_details_container = ui.column().classes("w-full")

    # === Update Functions ===

    async def update_summary():
        summary_container.clear()
        
        # Default values
        total_assets = 0
        cash = 0
        pnl = 0
        pnl_pct = 0.0
        
        client = app_state.get("client")
        is_live = getattr(client, 'live_trading', False) if client else False
        
        if client:
            try:
                cash = await client.get_wallet_cash()
                
                # Calculate position value
                pos_value = 0
                positions = app_state.get("positions", [])
                for p in positions:
                    qty = p.get("qty", 0)
                    price = p.get("current_price", p.get("avg_price", 0))
                    pos_value += qty * price
                
                total_assets = cash + pos_value
                
                # P&L calculation
                if is_live:
                    # 실매매: 당일 실현 손익 (DB 기반)
                    db = app_state.get("database")
                    if db:
                        today_str = datetime.now().strftime("%Y-%m-%d")
                        trades = db.get_trades_by_date(today_str)
                        pnl = sum(t.realized_pnl or 0 for t in trades if t.realized_pnl)
                else:
                    # 시뮬레이션: 초기 자산 대비
                    initial_assets = 500_000
                    pnl = total_assets - initial_assets
                    pnl_pct = (pnl / initial_assets) * 100 if initial_assets > 0 else 0
                
            except Exception as e:
                print(f"Error loading dashboard summary: {e}")
        
        with summary_container:
            # Total Assets
            with ui.card().classes("flex-1 bg-gradient-to-br from-indigo-600 to-purple-600 rounded-lg p-4"):
                asset_label = "총 자산 (실계좌)" if is_live else "총 자산 (시뮬레이션)"
                ui.label(asset_label).classes("text-indigo-200 text-sm")
                ui.label(f"¥{total_assets:,.0f}").classes("text-2xl font-bold text-white")
                with ui.row().classes("items-center mt-2"):
                    if is_live:
                        ui.badge("LIVE", color="red").classes("text-xs")
                    else:
                        ui.badge("SIM", color="orange").classes("text-xs")
                        color = "text-green-300" if pnl >= 0 else "text-red-300"
                        ui.label(f"{pnl_pct:+.2f}%").classes(f"{color} text-sm font-bold ml-2")

            # Cash
            with ui.card().classes("flex-1 bg-gradient-to-br from-cyan-600 to-blue-600 rounded-lg p-4"):
                cash_label = "현금 잔고 (실계좌)" if is_live else "현금 잔고 (시뮬레이션)"
                ui.label(cash_label).classes("text-cyan-200 text-sm")
                ui.label(f"¥{cash:,.0f}").classes("text-2xl font-bold text-white")

            # P&L
            with ui.card().classes("flex-1 bg-gradient-to-br from-green-600 to-emerald-600 rounded-lg p-4"):
                pnl_label = "당일 실현 손익" if is_live else "누적 총 손익 (평가손 포함)"
                ui.label(pnl_label).classes("text-green-200 text-sm")
                pnl_color = "text-white" if pnl == 0 else ("text-green-300" if pnl > 0 else "text-red-300")
                ui.label(f"¥{pnl:+,.0f}").classes(f"text-2xl font-bold {pnl_color}")
                sub_label = "실제 체결 손익" if is_live else "실현 수익 + 평가 손익"
                ui.label(sub_label).classes("text-xs text-green-100 opacity-70")

            # Status
            with ui.card().classes("flex-1 bg-gradient-to-br from-gray-700 to-gray-800 rounded-lg p-4"):
                ui.label("자동 매매").classes("text-gray-400 text-sm")
                is_running = app_state.get("trading_active", False)
                status_text = "가동 중" if is_running else "중지됨"
                status_color = "text-green-400" if is_running else "text-red-400"
                ui.label(status_text).classes(f"text-2xl font-bold {status_color}")
                if is_live:
                    ui.badge("LIVE TRADING", color="red").classes("mt-2")

    async def update_positions():
        positions_container.clear()
        
        # Fetch fresh positions from client (not just cached app_state)
        client = app_state.get("client")
        if client:
            try:
                raw_positions = await client.get_positions()
                normalized = []
                for p in raw_positions:
                    symbol = p.get("Symbol", "")
                    qty = p.get("Qty", p.get("LeavesQty", 0))
                    qty = int(float(qty)) if qty else 0
                    
                    # Skip zero-qty positions (already sold)
                    if qty <= 0:
                        continue
                    
                    avg_price = p.get("Price", p.get("AveragePrice", 0))
                    
                    # Fetch real-time price for each position
                    current_price = 0
                    try:
                        board = await client.get_board(symbol)
                        current_price = board.current_price
                    except Exception:
                        current_price = avg_price
                    
                    normalized.append({
                        "symbol": symbol,
                        "name": p.get("SymbolName", p.get("symbol_name", "")),
                        "qty": qty,
                        "avg_price": avg_price,
                        "current_price": current_price,
                    })
                app_state["positions"] = normalized
            except Exception as e:
                print(f"Error fetching positions: {e}")
        
        positions = app_state.get("positions", [])
        position_badge.text = f"{len(positions)}종목"
        
        columns = [
            {"name": "name", "label": "종목명 (코드)", "field": "name", "align": "left"},
            {"name": "qty", "label": "수량", "field": "qty", "align": "right"},
            {"name": "avg", "label": "평단가", "field": "avg", "align": "right"},
            {"name": "cur", "label": "현재가", "field": "cur", "align": "right"},
            {"name": "pnl", "label": "평가손익", "field": "pnl", "align": "right"},
        ]
        
        rows = []
        for p in positions:
            qty = float(p.get("qty", 0))
            avg = float(p.get("avg_price", 0))
            cur = float(p.get("current_price", 0))
            if cur == 0: cur = avg # Fallback
            
            val = qty * cur
            cost = qty * avg
            pnl_val = val - cost
            pnl_pct = (pnl_val / cost * 100) if cost > 0 else 0.0
            
            pnl_color = "text-red-400" if pnl_val < 0 else "text-green-400"
            rows.append({
                "name": f"{p.get('name', 'Unknown')} ({p.get('symbol', '')})",
                "qty": f"{qty:,.0f}",
                "avg": f"¥{avg:,.0f}",
                "cur": f"¥{cur:,.0f}",
                "pnl": f"¥{pnl_val:,.0f}",
                "pnl_pct": f"{pnl_pct:+.2f}%",
                "pnl_color": pnl_color
            })

        with positions_container:
            if not rows:
                ui.label("보유 포지션이 없습니다").classes("text-gray-500 italic")
            else:
                table = ui.table(columns=columns, rows=rows, pagination=10).classes("w-full")
                table.add_slot("body-cell-pnl", '''
                    <q-td :props="props">
                        <div :class="props.row.pnl_color">
                            {{ props.value }}<br>
                            <span class="text-xs">{{ props.row.pnl_pct }}</span>
                        </div>
                    </q-td>
                ''')

    def update_history():
        history_container.clear()
        db = app_state.get("database")
        trades = []
        if db:
            trades = db.get_trades(limit=50) # Show last 50
        
        if not trades:
            with history_container:
                ui.label("체결 내역이 없습니다").classes("text-gray-500 italic")
            return

        with history_container:
            for t in trades:
                color = "text-red-400" if t.side == "BUY" else "text-blue-400"
                side_str = "매수" if t.side == "BUY" else "매도"
                with ui.row().classes("w-full justify-between items-center text-sm p-1 border-b border-gray-700"):
                    ui.label(t.timestamp.strftime("%m-%d %H:%M")).classes("text-gray-500 w-24")
                    with ui.row().classes("flex-1 gap-2"):
                        ui.label(t.symbol).classes("font-bold text-white")
                        ui.label(side_str).classes(f"{color} font-bold")
                        ui.label(f"{t.qty}주").classes("text-white")
                    ui.label(f"¥{t.price:,.0f}").classes("text-gray-300")

    def update_orders():
        orders_container.clear()
        orders = app_state.get("orders", [])
        orders_badge.text = f"{len(orders)}건"
        
        with orders_container:
            if not orders:
                ui.label("진행 중인 주문이 없습니다").classes("text-gray-500 italic")
            else:
                for order in orders:
                    with ui.row().classes("w-full justify-between items-center p-2 bg-gray-700 rounded"):
                        with ui.column().classes("gap-0"):
                            symbol = order.get('Symbol', order.get('symbol', ''))
                            ui.label(f"{symbol}").classes("font-bold text-white")
                            side = order.get('Side', order.get('side', ''))
                            qty = order.get('Qty', order.get('qty', ''))
                            price = order.get('Price', order.get('price', ''))
                            ui.label(f"{side} {qty} @ {price}").classes("text-xs text-gray-400")
                        ui.spinner(size="xs")

    def update_logs():
        log_container.clear()
        logs = app_state.get("logs", [])[-100:] # Last 100 logs
        
        with log_container:
            if not logs:
                ui.label("로그가 없습니다").classes("text-gray-600")
            else:
                # Show newest at top
                for log in reversed(logs):
                    level = log.get("type", "INFO")
                    color = {
                        "INFO": "text-gray-300",
                        "WARN": "text-yellow-400", 
                        "ERROR": "text-red-400",
                        "TRADE": "text-green-400"
                    }.get(level, "text-gray-400")
                    
                    with ui.row().classes("gap-2 items-start"):
                        time_str = log.get("time", "")
                        display_time = time_str.split(" ")[1] if " " in time_str else time_str
                        ui.label(display_time).classes("text-gray-600 w-16 text-xs mt-1")
                        ui.label(f"[{level}]").classes(f"{color} w-12 text-xs font-bold mt-1")
                        ui.label(log.get("msg")).classes("text-gray-200 text-sm flex-1 break-all")

    def update_daily_summary():
        daily_summary_container.clear()
        db = app_state.get("database")
        if not db: return

        # Get all trades
        all_trades = db.get_trades(limit=1000)
        
        # Aggregate by date
        from collections import defaultdict
        daily_stats = defaultdict(lambda: {"pnl": 0, "wins": 0, "losses": 0, "trades": 0, "strategies": defaultdict(float)})
        
        for t in all_trades:
            if hasattr(t, 'realized_pnl') and t.realized_pnl: 
                date_str = t.timestamp.strftime("%Y-%m-%d")
                pnl = t.realized_pnl
                daily_stats[date_str]["pnl"] += pnl
                daily_stats[date_str]["trades"] += 1
                if pnl > 0: daily_stats[date_str]["wins"] += 1
                elif pnl < 0: daily_stats[date_str]["losses"] += 1
                
                str_name = t.extraction_strategy or t.strategy_name or "Manual"
                daily_stats[date_str]["strategies"][str_name] += pnl

        # Convert to list and sort
        sorted_dates = sorted(daily_stats.keys(), reverse=True)
        
        rows = []
        for d in sorted_dates:
            stats = daily_stats[d]
            total_trades = stats["trades"]
            win_rate = (stats["wins"] / total_trades * 100) if total_trades > 0 else 0
            
            strat_details = ", ".join([f"{k}: ¥{v:,.0f}" for k, v in stats["strategies"].items()])
            pnl_color = "text-green-400" if stats["pnl"] >= 0 else "text-red-400"
            
            rows.append({
                "date": d,
                "pnl": f"¥{stats['pnl']:,.0f}",
                "trades": f"{total_trades}회 (승률 {win_rate:.0f}%)",
                "strategies": strat_details,
                "pnl_color": pnl_color
            })

        columns = [
            {"name": "date", "label": "날짜", "field": "date", "align": "left"},
            {"name": "pnl", "label": "실현 손익", "field": "pnl", "align": "right"},
            {"name": "trades", "label": "매매 횟수", "field": "trades", "align": "center"},
            {"name": "strategies", "label": "전략별 손익", "field": "strategies", "align": "left"},
        ]
        
        with daily_summary_container:
            if not rows:
                 ui.label("매매 기록이 없습니다").classes("text-gray-500 italic")
            else:
                table = ui.table(columns=columns, rows=rows, pagination=5).classes("w-full")
                table.add_slot("body-cell-pnl", '''
                    <q-td :props="props">
                        <span :class="props.row.pnl_color">{{ props.value }}</span>
                    </q-td>
                ''')

    def update_date_details(target_date: str = None):
        """Update trade details for a specific date. Defaults to today."""
        today_details_container.clear()
        db = app_state.get("database")
        if not db: return

        if not target_date:
            target_date = datetime.now().strftime("%Y-%m-%d")

        # Get trades for the selected date
        trades = db.get_trades_by_date(target_date)
        
        if not trades:
            with today_details_container:
                ui.label(f"{target_date} 매매 기록이 없습니다").classes("text-gray-500 italic")
            return
        
        # Calculate summary stats
        total_pnl = sum(t.realized_pnl or 0 for t in trades)
        sell_trades = [t for t in trades if t.side == "SELL" and t.realized_pnl]
        wins = sum(1 for t in sell_trades if (t.realized_pnl or 0) > 0)
        losses = sum(1 for t in sell_trades if (t.realized_pnl or 0) < 0)
        win_rate = (wins / len(sell_trades) * 100) if sell_trades else 0
            
        columns = [
            {"name": "time", "label": "시간", "field": "time", "sortable": True, "align": "left"},
            {"name": "symbol", "label": "종목", "field": "symbol", "sortable": True, "align": "left"},
            {"name": "side", "label": "매매", "field": "side", "sortable": True, "align": "center"},
            {"name": "price", "label": "가격", "field": "price", "sortable": True, "align": "right"},
            {"name": "qty", "label": "수량", "field": "qty", "sortable": True, "align": "right"},
            {"name": "strategy", "label": "전략", "field": "strategy", "sortable": True, "align": "left"},
            {"name": "pnl", "label": "손익", "field": "pnl", "sortable": True, "align": "right"},
        ]
        
        rows = []
        for t in trades:
            time_str = t.timestamp.strftime("%H:%M:%S")
            side_kr = "매수" if t.side == "BUY" else "매도"
            side_color = "text-red-400" if t.side == "BUY" else "text-blue-400"
            
            pnl_val = t.realized_pnl or 0
            pnl_str = f"¥{pnl_val:,.0f}" if pnl_val != 0 else "-"
            pnl_color = "text-green-400" if pnl_val > 0 else "text-red-400" if pnl_val < 0 else "text-gray-400"
            
            rows.append({
                "time": time_str,
                "symbol": f"{t.symbol_name} ({t.symbol})",
                "symbol_code": t.symbol,
                "side": side_kr,
                "price": f"¥{t.price:,.0f}",
                "qty": f"{t.qty:,}",
                "strategy": t.extraction_strategy or t.strategy_name or "-",
                "pnl": pnl_str,
                "side_color": side_color,
                "pnl_color": pnl_color
            })
            
        with today_details_container:
            # Summary row
            pnl_total_color = "text-green-400" if total_pnl >= 0 else "text-red-400"
            with ui.row().classes("w-full items-center gap-4 mb-3 p-2 bg-gray-700 rounded"):
                ui.label(f"📅 {target_date}").classes("text-white font-semibold")
                ui.label(f"총 {len(trades)}건").classes("text-gray-300")
                ui.label(f"실현 손익: ¥{total_pnl:,.0f}").classes(f"{pnl_total_color} font-bold")
                ui.label(f"승률: {win_rate:.0f}% ({wins}승/{losses}패)").classes("text-gray-300")
            
            table = ui.table(columns=columns, rows=rows, pagination=20).classes("w-full")
            
            # Custom slots for color and links
            table.add_slot("body-cell-symbol", '''
                <q-td :props="props">
                    <a :href="'https://finance.yahoo.co.jp/quote/' + props.row.symbol_code + '.T'"
                       target="_blank"
                       class="text-cyan-400 hover:text-cyan-300 underline cursor-pointer">
                        {{ props.value }}
                    </a>
                </q-td>
            ''')
            table.add_slot("body-cell-side", '''
                <q-td :props="props">
                    <span :class="props.row.side_color">{{ props.value }}</span>
                </q-td>
            ''')
            table.add_slot("body-cell-pnl", '''
                <q-td :props="props">
                    <span :class="props.row.pnl_color">{{ props.value }}</span>
                </q-td>
            ''')


    # Master Update - Only called manually now
    async def update_dashboard():
        await update_summary()
        await update_positions()
        update_history()
        # update_orders() # Disabled since UI is hidden
        update_daily_summary()
        update_date_details()
        # Logs updated separately

    # Initial Load
    await update_dashboard()
    update_logs()
    
    # Auto-refresh ONLY for logs (1 second interval)
    ui.timer(1.0, update_logs)
