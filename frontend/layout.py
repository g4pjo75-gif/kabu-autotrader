# -*- coding: utf-8 -*-
"""
Frontend Layout Module

Sidebar, Header, Theme settings for NiceGUI dashboard.
Dark Mode dashboard layout reference: Program Garden style.
"""
from nicegui import ui
from typing import Callable, Dict, Any


# Theme configuration
theme_config = {
    "primary": "#6366f1",  # Indigo
    "secondary": "#8b5cf6",  # Purple
    "accent": "#06b6d4",  # Cyan
    "dark": "#1e1b4b",  # Dark indigo
    "background": "#0f0e17",
    "surface": "#1a1a2e",
    "text": "#fffffe",
    "text_secondary": "#a7a9be",
    "success": "#22c55e",
    "warning": "#f59e0b",
    "error": "#ef4444",
}


def create_layout(app_state: Dict[str, Any] = None) -> None:
    """
    Create the main dashboard layout with sidebar navigation.
    
    Args:
        app_state: Shared application state dictionary
    """
    # Apply dark theme
    ui.dark_mode().enable()
    
    # Custom CSS for styling
    ui.add_head_html("""
    <style>
        :root {
            --primary: #6366f1;
            --secondary: #8b5cf6;
            --accent: #06b6d4;
            --dark: #1e1b4b;
            --background: #0f0e17;
            --surface: #1a1a2e;
        }
        
        body {
            background-color: var(--background) !important;
        }
        
        .q-drawer {
            background-color: var(--surface) !important;
        }
        
        .nav-item {
            border-radius: 8px;
            margin: 4px 8px;
            transition: all 0.2s;
        }
        
        .nav-item:hover {
            background-color: rgba(99, 102, 241, 0.2);
        }
        
        .nav-item.active {
            background-color: rgba(99, 102, 241, 0.3);
            border-left: 3px solid var(--primary);
        }
        
        .card-gradient {
            background: linear-gradient(135deg, var(--surface) 0%, var(--dark) 100%);
            border: 1px solid rgba(255, 255, 255, 0.1);
        }
        
        .status-badge {
            padding: 4px 12px;
            border-radius: 20px;
            font-size: 12px;
            font-weight: 500;
        }
        
        .status-running {
            background-color: rgba(34, 197, 94, 0.2);
            color: #22c55e;
        }
        
        .status-stopped {
            background-color: rgba(239, 68, 68, 0.2);
            color: #ef4444;
        }
    </style>
    """)


def create_sidebar(app_state: Dict[str, Any] = None) -> ui.left_drawer:
    """Create the navigation sidebar"""
    with ui.left_drawer(value=True).classes("bg-gray-900") as drawer:
        # Logo/Title
        with ui.column().classes("p-4 items-center"):
            ui.label("🚀 Antigravity").classes(
                "text-2xl font-bold text-white"
            )
            ui.label("자동 주식 트레이딩").classes(
                "text-xs text-gray-400"
            )
        
        ui.separator().classes("my-2")
        
        # Navigation items
        nav_items = [
            {"icon": "settings", "label": "설정 및 연결", "path": "/"},
            {"icon": "search", "label": "종목 발굴", "path": "/extraction"},
            {"icon": "trending_up", "label": "자동 매매", "path": "/trading"},
            {"icon": "dashboard", "label": "대시보드", "path": "/dashboard"},
        ]
        
        for item in nav_items:
            with ui.row().classes("nav-item cursor-pointer p-3 w-full items-center"):
                ui.icon(item["icon"]).classes("text-gray-400 mr-3")
                ui.link(item["label"], item["path"]).classes(
                    "text-gray-300 no-underline hover:text-white"
                )
        
        # Spacer
        ui.space()
        
        # Connection status at bottom
        with ui.column().classes("p-4"):
            ui.separator().classes("my-2")
            with ui.row().classes("items-center"):
                icon = ui.icon("circle").classes("text-xs mr-2")
                label = ui.label("미연결").classes("text-sm")
                
                def update_status():
                    if not app_state:
                         # Default state if no app_state provided
                        icon.classes(remove="text-green-500 text-orange-500", add="text-red-500")
                        label.text = "미연결 (State X)"
                        label.classes(remove="text-green-400 text-orange-400", add="text-gray-400")
                        return

                    connected = app_state.get("connected", False)
                    sim_mode = app_state.get("simulation_mode", False)
                    
                    if not connected:
                        # Red / Disconnected
                        icon.classes(remove="text-green-500 text-orange-500", add="text-red-500")
                        label.text = "미연결"
                        label.classes(remove="text-green-400 text-orange-400", add="text-gray-400")
                    elif sim_mode:
                        # Orange / Simulation
                        icon.classes(remove="text-red-500 text-green-500", add="text-orange-500")
                        label.text = "시뮬레이션 모드"
                        label.classes(remove="text-gray-400 text-green-400", add="text-orange-400")
                    else:
                        # Green / Connected
                        icon.classes(remove="text-red-500 text-orange-500", add="text-green-500")
                        label.text = "API 연결됨"
                        label.classes(remove="text-gray-400 text-orange-400", add="text-green-400")
                
                # Check status every 1s
                ui.timer(1.0, update_status)
    
    return drawer


def create_header(drawer: ui.left_drawer, title: str = "Antigravity") -> ui.header:
    """Create the top header bar"""
    with ui.header().classes("bg-gray-900 border-b border-gray-800") as header:
        with ui.row().classes("w-full items-center justify-between px-4"):
            # Left: Menu toggle and title
            with ui.row().classes("items-center"):
                ui.button(icon="menu", on_click=lambda: drawer.toggle()).props(
                    "flat round"
                ).classes("text-white")
                ui.label(title).classes("text-lg font-semibold text-white ml-4")
            
            # Right: Status and time
            with ui.row().classes("items-center gap-4"):
                ui.label().classes("text-gray-400 text-sm").bind_text_from(
                    globals(), "current_time", lambda: ""
                )
    
    return header


def create_page_container() -> ui.element:
    """Create the main content container"""
    with ui.column().classes(
        "w-full max-w-6xl mx-auto p-6"
    ) as container:
        pass
    return container


def create_card(title: str = "", icon: str = None) -> ui.card:
    """Create a styled card component"""
    with ui.card().classes(
        "card-gradient rounded-lg p-4 w-full"
    ) as card:
        if title or icon:
            with ui.row().classes("items-center mb-4"):
                if icon:
                    ui.icon(icon).classes("text-indigo-400 mr-2")
                if title:
                    ui.label(title).classes("text-lg font-semibold text-white")
    return card


def create_status_badge(status: str, is_running: bool = False) -> ui.element:
    """Create a status indicator badge"""
    css_class = "status-badge status-running" if is_running else "status-badge status-stopped"
    with ui.element("span").classes(css_class) as badge:
        ui.label(status)
    return badge


def create_data_table(columns: list, rows: list) -> ui.table:
    """Create a styled data table"""
    table = ui.table(
        columns=columns,
        rows=rows,
        row_key="id" if rows and "id" in rows[0] else None,
    ).classes("w-full")
    
    table.add_slot("body", """
        <q-tr :props="props">
            <q-td v-for="col in props.cols" :key="col.name" :props="props">
                {{ col.value }}
            </q-td>
        </q-tr>
    """)
    
    return table
