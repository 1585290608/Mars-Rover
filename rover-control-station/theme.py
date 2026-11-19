THEMES = {
    "Dark Blue": {
        "bg": "#081426",
        "panel": "#0d1d36",
        "panel_header": "#1b2b48",
        "border": "#2b4570",
        "text": "#eef4ff",
        "muted": "#9eb4d4",
        "accent": "#2aa8ff",
        "success": "#59e05d",
        "warning": "#ff7a1a",
        "danger": "#ff5252",
        "special": "#9d7bff",
        "plot_bg": "#0c182c",
        "input": "#213555",
        "bar_empty": "#d8dde6",
    },
    "Light Blue": {
        "bg": "#edf3fb",
        "panel": "#ffffff",
        "panel_header": "#d9e7f7",
        "border": "#9cb7d4",
        "text": "#11243d",
        "muted": "#526784",
        "accent": "#1576d6",
        "success": "#239f3e",
        "warning": "#df8719",
        "danger": "#cc3b3b",
        "special": "#7f63db",
        "plot_bg": "#f7fbff",
        "input": "#eef4fb",
        "bar_empty": "#cfd7e2",
    },
    "Matrix Dark": {
        "bg": "#03110a",
        "panel": "#071a11",
        "panel_header": "#10251a",
        "border": "#2b724b",
        "text": "#d8ffe5",
        "muted": "#83c59b",
        "accent": "#25ff6a",
        "success": "#67ff67",
        "warning": "#dfff3b",
        "danger": "#ff5f5f",
        "special": "#9d7bff",
        "plot_bg": "#06160d",
        "input": "#11261a",
        "bar_empty": "#b7c7b3",
    },
    "Amber Terminal": {
        "bg": "#130f08",
        "panel": "#1b140c",
        "panel_header": "#2a1d0f",
        "border": "#7d5826",
        "text": "#ffe8c3",
        "muted": "#c7af86",
        "accent": "#ffb347",
        "success": "#83ff7c",
        "warning": "#ff8c1a",
        "danger": "#ff4b4b",
        "special": "#a58aff",
        "plot_bg": "#140f08",
        "input": "#25190f",
        "bar_empty": "#d8c9b1",
    },
}


def get_theme(name: str) -> dict:
    return THEMES.get(name, THEMES["Dark Blue"])



def build_stylesheet(theme_name: str = "Dark Blue") -> str:
    t = get_theme(theme_name)
    return f"""
QWidget {{
    background-color: {t['bg']};
    color: {t['text']};
    font-family: 'Segoe UI', Arial, sans-serif;
    font-size: 14px;
}}
QMainWindow {{
    background-color: {t['bg']};
}}
QFrame#headerBar {{
    background-color: {t['panel']};
    border: 1px solid {t['border']};
    border-radius: 12px;
}}
QFrame#topStatusStrip {{
    background-color: {t['panel']};
    border: 1px solid {t['border']};
    border-radius: 10px;
}}
QLabel#mainTitle {{
    font-size: 26px;
    font-weight: 800;
    padding: 8px;
    color: {t['accent']};
}}
QFrame#tabsBadge {{
    background-color: qlineargradient(
        x1:0, y1:0, x2:1, y2:0,
        stop:0 {t['panel_header']},
        stop:1 {t['panel']}
    );
    border: 1px solid {t['border']};
    border-radius: 10px;
}}
QLabel#tabsBadgeTitle {{
    font-size: 20px;
    font-weight: 900;
    color: {t['accent']};
    padding: 3px 10px;
    letter-spacing: 0.5px;
}}
QFrame#dashboardPanel {{
    background-color: {t['panel']};
    border: 1px solid {t['border']};
    border-radius: 14px;
}}
QLabel#panelHeader {{
    background-color: {t['panel_header']};
    border: 1px solid {t['border']};
    border-radius: 10px;
    font-size: 16px;
    font-weight: 800;
    padding: 7px 9px;
}}
QLabel#panelHeaderCompact {{
    background-color: {t['panel_header']};
    border: 1px solid {t['border']};
    border-radius: 9px;
    font-size: 14px;
    font-weight: 750;
    padding: 3px 8px;
    min-height: 24px;
    max-height: 28px;
}}
QLabel#valueStrong {{
    font-size: 16px;
    font-weight: 800;
    min-height: 22px;
}}
QLabel#mutedText {{
    color: {t['muted']};
    min-height: 20px;
}}

QLabel#sensorCell, QLabel#sensorValueCell {{
    background-color: {t['plot_bg']};
    border: 1px solid transparent;
    border-radius: 6px;
    padding: 4px 8px;
}}
QLabel#sensorValueCell {{
    color: {t['text']};
}}
QLabel#okText {{
    color: {t['success']};
    font-weight: 800;
}}
QLabel#warnText {{
    color: {t['warning']};
    font-weight: 800;
}}
QLabel#dangerText {{
    color: {t['danger']};
    font-weight: 800;
}}
QPushButton, QToolButton {{
    background-color: {t['input']};
    border: 1px solid {t['border']};
    border-radius: 8px;
    padding: 8px 10px;
    min-height: 32px;
    font-weight: 700;
}}
QPushButton:hover, QToolButton:hover {{
    border: 1px solid {t['accent']};
}}
QPushButton:checked {{
    background-color: {t['accent']};
    color: white;
}}
QPushButton:disabled {{
    color: {t['muted']};
    background-color: {t['panel_header']};
    border-color: {t['border']};
}}
QPushButton#connectButton {{
    background-color: #0fa538;
    color: white;
}}
QPushButton#disconnectButton {{
    background-color: #ba382e;
    color: white;
}}
QPushButton#resetButton {{
    background-color: {t['panel_header']};
}}
QPushButton[activeDirection='true'] {{
    background-color: {t['accent']};
    color: white;
    border: 2px solid #ccecff;
}}
QComboBox, QSpinBox, QDoubleSpinBox, QLineEdit, QPlainTextEdit, QTextEdit {{
    background-color: {t['input']};
    border: 1px solid {t['border']};
    border-radius: 8px;
    padding: 6px;
    min-height: 30px;
}}
QSlider::groove:horizontal {{
    background: {t['input']};
    border: 1px solid {t['border']};
    height: 10px;
    border-radius: 5px;
}}
QSlider::sub-page:horizontal {{
    background: {t['accent']};
    border-radius: 5px;
}}
QSlider::handle:horizontal {{
    background: #f3f7ff;
    border: 1px solid {t['border']};
    width: 16px;
    margin: -4px 0;
    border-radius: 8px;
}}
QTabWidget::pane {{
    border: 1px solid {t['border']};
    border-radius: 10px;
    background: {t['bg']};
    top: -1px;
}}
QTabBar::tab {{
    background: {t['panel']};
    border: 1px solid {t['border']};
    padding: 8px 14px;
    margin-right: 4px;
    border-top-left-radius: 8px;
    border-top-right-radius: 8px;
}}
QTabBar::tab:selected {{
    background: {t['panel_header']};
    border-bottom-color: {t['panel_header']};
}}
QProgressBar {{
    border: 1px solid {t['border']};
    border-radius: 7px;
    background: {t['bar_empty']};
    min-height: 14px;
    max-height: 14px;
    text-align: center;
}}
QProgressBar::chunk {{
    border-radius: 6px;
}}
QScrollArea {{
    border: none;
}}
QScrollBar:vertical {{
    width: 12px;
    background: {t['bg']};
}}
QScrollBar::handle:vertical {{
    background: {t['panel_header']};
    border-radius: 6px;
    min-height: 30px;
}}
QFrame#lineDivider {{
    background: {t['border']};
    max-height: 1px;
    border: none;
}}
QLabel#obstacleBadge {{
    border-radius: 8px;
    padding: 4px 8px;
    font-size: 13px;
    font-weight: 800;
}}
QLabel#obstacleDistance {{
    background: transparent;
    border: none;
    font-size: 16px;
    font-weight: 800;
}}
QLabel#statusPill {{
    background-color: {t['panel_header']};
    color: {t['text']};
    border: 1px solid {t['border']};
    border-radius: 7px;
    padding: 2px 8px;
    min-height: 22px;
    font-weight: 700;
}}

"""
