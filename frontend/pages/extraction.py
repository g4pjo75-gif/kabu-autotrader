# -*- coding: utf-8 -*-
"""
Stock Extraction Page

Universe & Strategy Selector UI.
"""
from nicegui import ui
import asyncio
from typing import Any, Dict, List

from strategies import (
    SMAGoldenDeadCross,
    StockSMAEMACross,
    StockMACDShift,
    StockRSIStochastic,
    TurtleBreakoutFilter,
    TurtleLiquidityFilter,
    TurtleVolatilityFilter,
    BollingerBands,
    CandlePatterns,
    TripleConfirmScorer,
)


# Available extraction strategies
EXTRACTION_STRATEGIES = [
    SMAGoldenDeadCross,
    StockSMAEMACross,
    StockMACDShift,
    StockRSIStochastic,
    TurtleBreakoutFilter,
    TurtleLiquidityFilter,
    TurtleVolatilityFilter,
    BollingerBands,
    CandlePatterns,
    TripleConfirmScorer,
]


async def extraction_page(app_state: Dict[str, Any]) -> None:
    """
    Stock Extraction Page
    
    - Target Universe Selector (Nikkei 225, Ranking, CSV)
    - Strategy Selector with dynamic parameters
    - Analysis results table
    """
    
    ui.label("종목 발굴").classes("text-2xl font-bold text-white mb-6")
    
    with ui.row().classes("w-full gap-6"):
        # === Left Panel: Configuration ===
        with ui.card().classes("w-80 bg-gray-800 rounded-lg p-6"):
            # Universe Selector
            with ui.row().classes("items-center mb-4"):
                ui.icon("public").classes("text-indigo-400 mr-2")
                ui.label("대상 종목 군").classes("text-lg font-semibold text-white")
            
            universe_options = {
                "nikkei225": "닛케이 225",
                "nikkei400": "JPX-Nikkei 400 (225 제외)",
                "ranking": "실시간 랭킹 (거래량)",
                "csv": "CSV 파일 업로드",
            }
            
            universe_select = ui.radio(
                list(universe_options.values()),
                value="닛케이 225",
            ).classes("text-white mb-4")
            
            # CSV file input (shown conditionally)
            csv_upload = ui.upload(
                label="CSV 파일 선택",
                auto_upload=True,
            ).classes("w-full mb-4").props("dark")
            csv_upload.visible = False
            
            def on_universe_change():
                csv_upload.visible = universe_select.value == "CSV 파일 업로드"
            
            universe_select.on_value_change(on_universe_change)
            
            ui.separator().classes("my-4")
            
            # Strategy Selector
            with ui.row().classes("items-center justify-between w-full mb-4"):
                with ui.row().classes("items-center"):
                    ui.icon("psychology").classes("text-purple-400 mr-2")
                    ui.label("추출 전략").classes("text-lg font-semibold text-white")
                
                # Guide Dialog
                with ui.dialog() as guide_dialog, ui.card().classes("w-[500px] bg-gray-800 border border-gray-700 p-6"):
                    with ui.row().classes("w-full items-center justify-between mb-4"):
                        ui.label("전략 가이드").classes("text-xl font-bold text-white")
                        ui.button(icon="close", on_click=guide_dialog.close).props("flat round dense").classes("text-gray-400")
                    
                    with ui.scroll_area().classes("h-[400px] w-full p-2"):
                        for cls in EXTRACTION_STRATEGIES:
                            with ui.column().classes("w-full mb-4"):
                                ui.label(cls.display_name).classes("text-indigo-400 font-bold text-base")
                                ui.label(cls.description).classes("text-gray-300 text-sm mb-1")
                                # Show parameter descriptions if possible, simplistic for now
                                ui.separator().classes("bg-gray-700 mt-2")
                    
                    ui.button("닫기", on_click=guide_dialog.close).classes("w-full mt-4 bg-gray-700 text-white")

                ui.button("가이드", icon="help", on_click=guide_dialog.open).props("flat dense").classes(
                    "text-gray-400 hover:text-white text-sm"
                )
            
            strategy_options = {
                cls.name: cls.display_name for cls in EXTRACTION_STRATEGIES
            }
            
            strategy_select = ui.select(
                options=strategy_options,
                value=list(strategy_options.keys())[0],
                label="전략 선택",
            ).classes("w-full mb-4").props("filled dark")
            
            # Dynamic Parameters Container
            params_container = ui.column().classes("w-full")
            current_params = {}
            
            def render_params():
                params_container.clear()
                selected_name = strategy_select.value
                
                # Find the strategy class
                strategy_cls = next(
                    (cls for cls in EXTRACTION_STRATEGIES if cls.name == selected_name),
                    None
                )
                
                if not strategy_cls:
                    return
                
                with params_container:
                    for param in strategy_cls.get_parameters():
                        if param.param_type == "int":
                            inp = ui.number(
                                label=param.display_name,
                                value=param.default,
                                min=param.min_value,
                                max=param.max_value,
                            ).classes("w-full mb-2").props("filled dark dense")
                            current_params[param.name] = inp
                        
                        elif param.param_type == "float":
                            inp = ui.number(
                                label=param.display_name,
                                value=param.default,
                                min=param.min_value,
                                max=param.max_value,
                                step=0.1,
                            ).classes("w-full mb-2").props("filled dark dense")
                            current_params[param.name] = inp
                        
                        elif param.param_type == "select":
                            inp = ui.select(
                                options=param.options,
                                value=param.default,
                                label=param.display_name,
                            ).classes("w-full mb-2").props("filled dark dense")
                            current_params[param.name] = inp
                        
                        elif param.param_type == "bool":
                            inp = ui.switch(
                                param.display_name,
                                value=param.default,
                            ).classes("mb-2")
                            current_params[param.name] = inp
            
            strategy_select.on_value_change(render_params)
            render_params()  # Initial render
            
            ui.separator().classes("my-4")
            
            # Run Analysis Button
            progress = ui.linear_progress(value=0).classes("w-full mb-2")
            progress.visible = False
            progress_label = ui.label("").classes("text-gray-400 text-sm mb-4")
            
            async def run_analysis():
                # 1. Setup
                progress.visible = True
                progress.value = 0
                results_container.clear()
                
                # Get Strategy
                selected_name = strategy_select.value
                strategy_cls = next(
                    (cls for cls in EXTRACTION_STRATEGIES if cls.name == selected_name),
                    None
                )
                if not strategy_cls:
                    ui.notify("전략을 선택해주세요", type="warning")
                    return

                # Instantiate Strategy with params
                strategy_params = {
                    name: inp.value for name, inp in current_params.items()
                }
                strategy = strategy_cls(**strategy_params)
                
                # Get Client & Universe
                client = app_state.get("kabu_client")
                if not client:
                    from backend.kabu_client import MockKabuClient
                    client = MockKabuClient()
                    
                from backend.universe import Universe
                universe = Universe(client)
                
                target_symbols = universe.load_nikkei_225()
                stock_map = universe.load_stock_map()
                
                total = len(target_symbols)
                progress_label.text = f"분석 시작: 총 {total}개 종목 (병렬 처리 중...)"
                
                extracted_results = []
                
                # 2. Parallel Analysis
                sem = asyncio.Semaphore(10)  # Limit concurrent requests to 10
                completed_count = 0
                
                async def analyze_symbol(symbol: str):
                    nonlocal completed_count
                    async with sem:
                        try:
                            # Fetch Data
                            days_needed = 300
                            df = await client.get_stock_history(symbol, days=days_needed)
                            
                            if df.empty or len(df) < 50:
                                return None
                                
                            # Execute Strategy
                            result = await strategy.evaluate(symbol, df)
                            
                            if result.signal:
                                stock_name = stock_map.get(symbol, symbol)
                                if stock_name == symbol:
                                    stock_name = await universe.fetch_stock_name(symbol)
                                
                                idx_price = df["close"].iloc[-1]
                                
                                return {
                                    "symbol": symbol,
                                    "name": stock_name,
                                    "price": idx_price,
                                    "score": result.score,
                                    "details": result.details
                                }
                        except Exception as e:
                            print(f"Error analyzing {symbol}: {e}")
                            return None
                        finally:
                            completed_count += 1
                            # Update progress periodically to avoid UI flooding
                            if completed_count % 5 == 0 or completed_count == total:
                                progress.value = completed_count / total
                                progress_label.text = f"분석 중... ({completed_count}/{total}) 병렬 처리"

                # Run all tasks
                tasks = [analyze_symbol(sym) for sym in target_symbols]
                results = await asyncio.gather(*tasks)
                
                # Filter None results
                extracted_results = [r for r in results if r is not None]

                # 3. Finish
                app_state["extraction_results"] = extracted_results
                progress_label.text = f"완료: {len(extracted_results)}종목 검출됨"
                ui.notify(f"분석 완료: {len(extracted_results)}건 검출", type="positive")
                
                # Refresh results table
                await refresh_results()
            
            ui.button(
                "분석 실행 (병렬)",
                on_click=run_analysis,
                icon="rocket_launch",
            ).classes("w-full bg-indigo-600 text-white")
        
        # === Right Panel: Results ===
        with ui.card().classes("flex-1 bg-gray-800 rounded-lg p-6"):
            with ui.row().classes("items-center justify-between mb-4"):
                with ui.row().classes("items-center"):
                    ui.icon("list").classes("text-green-400 mr-2")
                    ui.label("추출 결과").classes("text-lg font-semibold text-white")
                
                ui.button(
                    "선택 종목을 매매 화면으로 전송",
                    icon="send",
                ).classes("bg-green-600 text-white")
            
            ui.separator().classes("mb-4")
            
            # Results Table
            results_container = ui.column().classes("w-full")
            
            async def refresh_results():
                results_container.clear()
                results = app_state.get("extraction_results", [])
                
                if not results:
                    with results_container:
                        ui.label("분석을 실행해주세요").classes("text-gray-400")
                    return
                
                columns = [
                    {"name": "select", "label": "선택", "field": "select", "align": "center"},
                    {"name": "symbol", "label": "코드", "field": "symbol"},
                    {"name": "name", "label": "종목명", "field": "name"},
                    {"name": "price", "label": "현재가", "field": "price", "align": "right"},
                    {"name": "score", "label": "점수", "field": "score", "align": "right"},
                ]
                
                rows = []
                for r in results:
                    score = r.get("score")
                    if score is None:
                        score = 0.0
                    
                    rows.append({
                        "id": r["symbol"],
                        "symbol": r["symbol"],
                        "name": r["name"],
                        "price": f"¥{r['price']:,.0f}",
                        "score": f"{score:.1f}",
                    })
                
                with results_container:
                    table = ui.table(
                        columns=columns,
                        rows=rows,
                        selection="multiple",
                        row_key="id",
                    ).classes("w-full")
            
            await refresh_results()
