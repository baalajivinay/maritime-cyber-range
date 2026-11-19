"""
Testbed Theme & Styling.
Clean, professional marine testbed palette (Kongsberg / Furuno / QGroundControl style).
High-contrast, legible typography with zero neon/sci-fi effects.
"""

# Professional Dark Marine Palette
BG_DARK = "#18191f"          # Main application background
PANEL_BG = "#22232b"         # Instrument panel & card background
PANEL_HEADER = "#2a2b35"     # Section headers & toolbars
PANEL_BORDER = "#353643"     # Subtle 1px borders
BG_INPUT = "#1a1b22"         # Input controls & lists

# Functional Colors
COLOR_BLUE = "#2f80ed"       # Primary action & own-ship guidance
COLOR_BLUE_HOVER = "#1b6cd4"
COLOR_GREEN = "#27ae60"      # Running / Safe / Resilient
COLOR_GREEN_HOVER = "#219653"
COLOR_RED = "#eb5757"        # Stop / Attack Active / Lubber line
COLOR_RED_HOVER = "#d84343"
COLOR_AMBER = "#f2994a"      # Warning / High Innovation
COLOR_CARDINAL_N = "#eb5757" # Compass North pointer

# Typography Colors
TEXT_WHITE = "#f0f1f5"       # Primary text
TEXT_MUTED = "#989aa8"       # Secondary labels & units
TEXT_DIM = "#5d5f70"         # Minor tick marks & grid

# Nautical Chart Palette
CHART_WATER_DEEP = "#16202c"
CHART_WATER_FAIRWAY = "#1c2a3a"
CHART_LAND = "#243242"
CHART_GRID = "#202d3e"
CHART_OWN_SHIP = "#38bdf8"
CHART_GHOST_SHIP = "#f87171"
CHART_WAYPOINT = "#fbbf24"
CHART_SPOOF_LINE = "#ef4444"

# Aliases for widgets
MAP_WATER = CHART_WATER_DEEP
MAP_FAIRWAY = CHART_WATER_FAIRWAY
MAP_LAND = CHART_LAND
MAP_GRID = CHART_GRID
MAP_OWN_SHIP = CHART_OWN_SHIP
MAP_GHOST_SHIP = CHART_GHOST_SHIP
MAP_PATH = COLOR_GREEN
MAP_SPOOF_LINE = CHART_SPOOF_LINE
MAP_WAYPOINT = CHART_WAYPOINT
TEXT_PRIMARY = TEXT_WHITE
TEXT_SECONDARY = TEXT_MUTED
BG_PANEL = PANEL_BG
BG_PANEL_HEADER = PANEL_HEADER
BORDER_COLOR = PANEL_BORDER



TESTBED_QSS = f"""
QMainWindow, QDialog {{
    background-color: {BG_DARK};
    color: {TEXT_WHITE};
}}

QWidget {{
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Ubuntu", "Cantarell", sans-serif;
    font-size: 12px;
    color: {TEXT_WHITE};
}}

/* Panels */
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
    font-size: 12px;
    font-weight: 600;
    color: {TEXT_WHITE};
    padding-top: 12px;
}}

QGroupBox::title {{
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 10px;
    top: 4px;
    padding: 0 4px;
    color: {TEXT_WHITE};
}}

/* Splitters */
QSplitter::handle {{
    background-color: {PANEL_BORDER};
}}

/* Buttons */
QPushButton {{
    background-color: #2e303b;
    border: 1px solid {PANEL_BORDER};
    border-radius: 4px;
    color: {TEXT_WHITE};
    padding: 5px 14px;
    font-weight: 500;
}}

QPushButton:hover {{
    background-color: #383a47;
    border-color: #4a4c5c;
}}

QPushButton:pressed {{
    background-color: #24252e;
}}

QPushButton.success {{
    background-color: {COLOR_GREEN};
    border: 1px solid {COLOR_GREEN_HOVER};
    color: #ffffff;
    font-weight: 600;
}}

QPushButton.success:hover {{
    background-color: {COLOR_GREEN_HOVER};
}}

QPushButton.danger {{
    background-color: {COLOR_RED};
    border: 1px solid {COLOR_RED_HOVER};
    color: #ffffff;
    font-weight: 600;
}}

QPushButton.danger:hover {{
    background-color: {COLOR_RED_HOVER};
}}

/* Form Controls */
QComboBox {{
    background-color: {BG_INPUT};
    border: 1px solid {PANEL_BORDER};
    border-radius: 4px;
    padding: 4px 10px;
    color: {TEXT_WHITE};
    min-height: 22px;
}}

QComboBox:focus {{
    border-color: {COLOR_BLUE};
}}

QComboBox QAbstractItemView {{
    background-color: {PANEL_BG};
    border: 1px solid {PANEL_BORDER};
    selection-background-color: {COLOR_BLUE};
    selection-color: #ffffff;
    color: {TEXT_WHITE};
    padding: 4px;
}}

QSlider::groove:horizontal {{
    height: 5px;
    background-color: #2e303b;
    border-radius: 2px;
}}

QSlider::sub-page:horizontal {{
    background-color: {COLOR_BLUE};
    border-radius: 2px;
}}

QSlider::handle:horizontal {{
    background-color: #ffffff;
    border: 1px solid #c0c0c0;
    width: 14px;
    margin-top: -5px;
    margin-bottom: -5px;
    border-radius: 7px;
}}

QSlider::handle:horizontal:hover {{
    background-color: {COLOR_BLUE};
}}

/* Scrollbars */
QScrollBar:vertical {{
    background-color: {BG_DARK};
    width: 8px;
    margin: 0px;
}}

QScrollBar::handle:vertical {{
    background-color: #383a47;
    min-height: 20px;
    border-radius: 4px;
}}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0px;
}}

/* Tables */
QTableWidget {{
    background-color: {BG_INPUT};
    border: 1px solid {PANEL_BORDER};
    border-radius: 4px;
    gridline-color: #2a2b35;
    color: {TEXT_WHITE};
}}

QHeaderView::section {{
    background-color: {PANEL_HEADER};
    color: {TEXT_MUTED};
    padding: 5px;
    border: none;
    border-right: 1px solid {PANEL_BORDER};
    border-bottom: 1px solid {PANEL_BORDER};
    font-weight: 600;
}}

/* Menu Bar & Menus */
QMenuBar {{
    background-color: {PANEL_BG};
    color: {TEXT_WHITE};
    border-bottom: 1px solid {PANEL_BORDER};
    padding: 2px 6px;
    font-size: 11px;
}}

QMenuBar::item {{
    background: transparent;
    padding: 4px 10px;
    border-radius: 3px;
}}

QMenuBar::item:selected {{
    background-color: #2f3240;
    color: #ffffff;
}}

QMenu {{
    background-color: {PANEL_BG};
    color: {TEXT_WHITE};
    border: 1px solid {PANEL_BORDER};
    padding: 4px;
    font-size: 11px;
}}

QMenu::item {{
    padding: 6px 24px 6px 16px;
    border-radius: 3px;
}}

QMenu::item:selected {{
    background-color: {COLOR_BLUE};
    color: #ffffff;
}}

QMenu::separator {{
    height: 1px;
    background-color: {PANEL_BORDER};
    margin: 4px 8px;
}}

/* Status Bar */
QStatusBar {{
    background-color: {PANEL_BG};
    color: {TEXT_MUTED};
    border-top: 1px solid {PANEL_BORDER};
    font-size: 11px;
    padding: 2px 8px;
}}

QStatusBar QLabel {{
    color: {TEXT_MUTED};
    font-size: 11px;
}}

/* Tab Widget */
QTabWidget::pane {{
    border: 1px solid {PANEL_BORDER};
    background-color: {PANEL_BG};
    border-radius: 4px;
}}

QTabBar::tab {{
    background-color: #1a1b22;
    color: {TEXT_MUTED};
    padding: 6px 14px;
    border-top-left-radius: 4px;
    border-top-right-radius: 4px;
    margin-right: 2px;
}}

QTabBar::tab:selected {{
    background-color: {PANEL_BG};
    color: {TEXT_WHITE};
    font-weight: 600;
}}
"""
