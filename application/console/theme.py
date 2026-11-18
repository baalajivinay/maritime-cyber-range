"""
Tactical Marine Theme & Styling (IEC 62288 Conformance).
High-contrast dusk/night color palette for marine consoles and classification testbeds.
"""

# Palette Constants
BG_DARK = "#080B10"         # Deep night marine background
PANEL_BG = "#0F141D"        # Tactical slate panel background
PANEL_BORDER = "#1E2736"    # Panel border
PANEL_HEADER = "#151C28"    # Sub-header background
ACCENT_CYAN = "#00D2FF"     # Marine telemetry cyan
ACCENT_BLUE = "#3B82F6"     # Guidance / planned track blue
COLOR_PASS = "#10B981"      # Emerald green (Normal / Safe / Resilient)
COLOR_WARN = "#F59E0B"      # Marine amber (Warning / Innovation High)
COLOR_ALARM = "#EF4444"     # Signal red (Attack / Breach / Uncontained)
TEXT_WHITE = "#F1F5F9"      # Primary reading text
TEXT_MUTED = "#64748B"      # Secondary labels / units
TEXT_DIM = "#475569"        # Minor grid text

# Chart & ECDIS Palette
CHART_WATER_DEEP = "#071018"
CHART_WATER_SHALLOW = "#0B1824"
CHART_WATER_FAIRWAY = "#0E2133"
CHART_LAND = "#18222D"
CHART_GRID = "#152232"
CHART_BUOY_PORT = "#EF4444"
CHART_BUOY_STBD = "#10B981"
CHART_BUOY_CARDINAL = "#F59E0B"
CHART_TRUE_VESSEL = "#00E5FF"
CHART_SPOOFED_GHOST = "#F87171"
CHART_WAYPOINT = "#34D399"

TACTICAL_QSS = f"""
QMainWindow, QDialog {{
    background-color: {BG_DARK};
    color: {TEXT_WHITE};
}}

QWidget {{
    font-family: 'Inter', 'Segoe UI', 'DejaVu Sans', sans-serif;
    font-size: 12px;
    color: {TEXT_WHITE};
}}

/* Panels and GroupBoxes */
QFrame.panel {{
    background-color: {PANEL_BG};
    border: 1px solid {PANEL_BORDER};
    border-radius: 4px;
}}

QGroupBox {{
    background-color: {PANEL_BG};
    border: 1px solid {PANEL_BORDER};
    border-radius: 4px;
    margin-top: 18px;
    font-weight: bold;
    font-size: 11px;
    color: {ACCENT_CYAN};
}}

QGroupBox::title {{
    subcontrol-origin: margin;
    subcontrol-position: top left;
    padding: 2px 8px;
    background-color: {PANEL_HEADER};
    border: 1px solid {PANEL_BORDER};
    border-radius: 2px;
}}

/* Push Buttons */
QPushButton {{
    background-color: #1A2332;
    border: 1px solid #2A384C;
    border-radius: 3px;
    color: {TEXT_WHITE};
    padding: 6px 12px;
    font-weight: 600;
}}

QPushButton:hover {{
    background-color: #243144;
    border-color: {ACCENT_CYAN};
}}

QPushButton:pressed {{
    background-color: #0E1622;
}}

QPushButton:disabled {{
    background-color: #11161F;
    border-color: #1A222E;
    color: #475569;
}}

QPushButton.btn-primary {{
    background-color: #0284C7;
    border-color: #38BDF8;
    color: #FFFFFF;
}}
QPushButton.btn-primary:hover {{
    background-color: #0369A1;
}}

QPushButton.btn-attack {{
    background-color: #991B1B;
    border: 1px solid #EF4444;
    color: #FEE2E2;
    font-weight: bold;
}}
QPushButton.btn-attack:hover {{
    background-color: #B91C1C;
    border-color: #F87171;
}}

QPushButton.btn-safe {{
    background-color: #065F46;
    border: 1px solid #10B981;
    color: #D1FAE5;
    font-weight: bold;
}}
QPushButton.btn-safe:hover {{
    background-color: #047857;
}}

/* ComboBox */
QComboBox {{
    background-color: #151D2A;
    border: 1px solid #2B3A4E;
    border-radius: 3px;
    padding: 4px 8px;
    color: {TEXT_WHITE};
    font-weight: 500;
}}
QComboBox:hover {{
    border-color: {ACCENT_CYAN};
}}
QComboBox::drop-down {{
    border: none;
    width: 20px;
}}
QComboBox QAbstractItemView {{
    background-color: #151D2A;
    border: 1px solid #2B3A4E;
    selection-background-color: #1E293B;
    selection-color: {ACCENT_CYAN};
    color: {TEXT_WHITE};
}}

/* Sliders */
QSlider::groove:horizontal {{
    height: 4px;
    background: #1E293B;
    border-radius: 2px;
}}
QSlider::sub-page:horizontal {{
    background: {ACCENT_CYAN};
    border-radius: 2px;
}}
QSlider::handle:horizontal {{
    background: #FFFFFF;
    border: 1px solid {ACCENT_CYAN};
    width: 14px;
    margin-top: -5px;
    margin-bottom: -5px;
    border-radius: 7px;
}}

/* Table & List View */
QTableWidget, QTreeWidget, QListWidget {{
    background-color: {PANEL_BG};
    border: 1px solid {PANEL_BORDER};
    gridline-color: #17202E;
    color: {TEXT_WHITE};
    font-family: 'JetBrains Mono', 'Fira Code', 'DejaVu Sans Mono', monospace;
    font-size: 11px;
}}
QHeaderView::section {{
    background-color: {PANEL_HEADER};
    border: 1px solid {PANEL_BORDER};
    color: {TEXT_MUTED};
    padding: 4px 6px;
    font-weight: 600;
}}

/* ScrollBars */
QScrollBar:vertical {{
    background: {BG_DARK};
    width: 8px;
    margin: 0;
}}
QScrollBar::handle:vertical {{
    background: #253346;
    min-height: 20px;
    border-radius: 4px;
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0px;
}}

/* Tab Widget */
QTabWidget::pane {{
    border: 1px solid {PANEL_BORDER};
    background-color: {PANEL_BG};
}}
QTabBar::tab {{
    background-color: #121824;
    border: 1px solid {PANEL_BORDER};
    padding: 6px 14px;
    margin-right: 2px;
    color: {TEXT_MUTED};
    font-weight: 600;
}}
QTabBar::tab:selected {{
    background-color: {PANEL_BG};
    border-bottom-color: {PANEL_BG};
    color: {ACCENT_CYAN};
}}
"""
