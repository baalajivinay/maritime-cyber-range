"""
Testbed Theme & Styling.
Clean, professional desktop workstation palette designed for clarity and usability.
"""

# Professional Dark Palette
BG_WINDOW = "#1e1e24"        # Main window background
BG_PANEL = "#26262e"         # Card / container background
BG_PANEL_HEADER = "#2f2f38"  # Header / toolbar background
BG_INPUT = "#1a1a20"         # Input fields, text areas, dropdowns
BORDER_COLOR = "#3a3a46"     # Clean 1px card borders
BORDER_FOCUS = "#2f80ed"     # Focus border blue

# Typography Colors
TEXT_PRIMARY = "#f0f0f5"     # Primary high-contrast text
TEXT_SECONDARY = "#b0b0c0"   # Secondary descriptive text
TEXT_MUTED = "#757588"       # Disabled / hint text

# Functional Status Colors
COLOR_BLUE = "#2f80ed"       # Primary action blue
COLOR_BLUE_HOVER = "#1b6cd4"
COLOR_GREEN = "#27ae60"      # Safe / Connected / Running green
COLOR_GREEN_HOVER = "#219653"
COLOR_RED = "#eb5757"        # Alert / Attack Active / Stop red
COLOR_RED_HOVER = "#d84343"
COLOR_AMBER = "#f2994a"      # Warning / High Innovation orange

# Nautical Map Palette
MAP_WATER = "#1a2634"        # Calm deep water
MAP_FAIRWAY = "#223244"      # Navigable fairway channel
MAP_LAND = "#2a3744"         # Coastline / harbor land
MAP_GRID = "#253546"         # Coordinate grid lines
MAP_OWN_SHIP = "#38bdf8"     # Own vessel icon
MAP_GHOST_SHIP = "#f87171"   # AIS Ghost vessel icon
MAP_PATH = "#22c55e"         # Planned navigation track
MAP_SPOOF_LINE = "#ef4444"   # Red divergence vector line
MAP_WAYPOINT = "#fbbf24"     # Active waypoint marker

CLEAN_QSS = f"""
QMainWindow, QDialog {{
    background-color: {BG_WINDOW};
    color: {TEXT_PRIMARY};
}}

QWidget {{
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Ubuntu", "Cantarell", sans-serif;
    font-size: 13px;
    color: {TEXT_PRIMARY};
}}

/* Cards and Panels */
QFrame.card {{
    background-color: {BG_PANEL};
    border: 1px solid {BORDER_COLOR};
    border-radius: 6px;
}}

QGroupBox {{
    background-color: {BG_PANEL};
    border: 1px solid {BORDER_COLOR};
    border-radius: 6px;
    margin-top: 24px;
    font-size: 13px;
    font-weight: 600;
    color: {TEXT_PRIMARY};
    padding-top: 14px;
}}

QGroupBox::title {{
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 12px;
    top: 6px;
    padding: 0 4px;
    color: {TEXT_PRIMARY};
}}

/* Tab Widget */
QTabWidget::pane {{
    border: 1px solid {BORDER_COLOR};
    border-radius: 6px;
    background-color: {BG_PANEL};
    top: -1px;
}}

QTabBar::tab {{
    background-color: {BG_PANEL_HEADER};
    color: {TEXT_SECONDARY};
    padding: 8px 18px;
    margin-right: 2px;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
    border: 1px solid {BORDER_COLOR};
    border-bottom: none;
    font-weight: 500;
}}

QTabBar::tab:selected {{
    background-color: {BG_PANEL};
    color: {COLOR_BLUE};
    font-weight: 600;
    border-bottom: 2px solid {COLOR_BLUE};
}}

QTabBar::tab:hover:!selected {{
    background-color: #383844;
    color: {TEXT_PRIMARY};
}}

/* Buttons */
QPushButton {{
    background-color: #32323c;
    border: 1px solid {BORDER_COLOR};
    border-radius: 5px;
    color: {TEXT_PRIMARY};
    padding: 7px 16px;
    font-weight: 500;
}}

QPushButton:hover {{
    background-color: #3e3e4a;
    border-color: #4e4e5c;
}}

QPushButton:pressed {{
    background-color: #282830;
}}

QPushButton.primary {{
    background-color: {COLOR_BLUE};
    border: 1px solid {COLOR_BLUE_HOVER};
    color: #ffffff;
    font-weight: 600;
}}

QPushButton.primary:hover {{
    background-color: {COLOR_BLUE_HOVER};
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
    border: 1px solid {BORDER_COLOR};
    border-radius: 5px;
    padding: 6px 12px;
    color: {TEXT_PRIMARY};
    min-height: 20px;
}}

QComboBox:focus {{
    border-color: {BORDER_FOCUS};
}}

QComboBox::drop-down {{
    border: none;
    width: 20px;
}}

QComboBox QAbstractItemView {{
    background-color: {BG_PANEL};
    border: 1px solid {BORDER_COLOR};
    selection-background-color: {COLOR_BLUE};
    selection-color: #ffffff;
    color: {TEXT_PRIMARY};
    padding: 4px;
}}

QLineEdit, QSpinBox, QDoubleSpinBox {{
    background-color: {BG_INPUT};
    border: 1px solid {BORDER_COLOR};
    border-radius: 5px;
    padding: 6px 10px;
    color: {TEXT_PRIMARY};
}}

QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus {{
    border-color: {BORDER_FOCUS};
}}

QSlider::groove:horizontal {{
    height: 6px;
    background-color: #32323c;
    border-radius: 3px;
}}

QSlider::sub-page:horizontal {{
    background-color: {COLOR_BLUE};
    border-radius: 3px;
}}

QSlider::handle:horizontal {{
    background-color: #ffffff;
    border: 1px solid #c0c0c0;
    width: 16px;
    margin-top: -5px;
    margin-bottom: -5px;
    border-radius: 8px;
}}

QSlider::handle:horizontal:hover {{
    background-color: {COLOR_BLUE};
}}

/* Scrollbars */
QScrollBar:vertical {{
    background-color: {BG_WINDOW};
    width: 10px;
    margin: 0px;
}}

QScrollBar::handle:vertical {{
    background-color: #3e3e4a;
    min-height: 20px;
    border-radius: 5px;
}}

QScrollBar::handle:vertical:hover {{
    background-color: #505060;
}}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0px;
}}

/* Tables */
QTableWidget {{
    background-color: {BG_INPUT};
    border: 1px solid {BORDER_COLOR};
    border-radius: 5px;
    gridline-color: #2c2c36;
    color: {TEXT_PRIMARY};
}}

QHeaderView::section {{
    background-color: {BG_PANEL_HEADER};
    color: {TEXT_SECONDARY};
    padding: 6px;
    border: none;
    border-right: 1px solid {BORDER_COLOR};
    border-bottom: 1px solid {BORDER_COLOR};
    font-weight: 600;
}}

QTableWidget::item:selected {{
    background-color: #2b3a4a;
    color: #ffffff;
}}
"""
