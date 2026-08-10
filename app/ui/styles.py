APP_STYLESHEET = r"""
* {
    font-family: "Segoe UI";
    font-size: 14px;
    color: #e8edf7;
}
QMainWindow, QWidget#AppRoot {
    background: #0b0f17;
}
QWidget#Sidebar {
    background: #0e141f;
    border-right: 1px solid #202838;
}
QLabel#BrandMark {
    color: #74a7ff;
    font-size: 25px;
    font-weight: 700;
}
QLabel#BrandLogo {
    background: transparent;
}
QLabel#BrandName {
    color: #f5f7fb;
    font-size: 17px;
    font-weight: 650;
}
QLabel#BrandCaption, QLabel#MutedLabel, QLabel#CounterLabel {
    color: #8792a7;
}
QPushButton#NavButton {
    background: transparent;
    border: 0;
    border-radius: 9px;
    color: #99a5b9;
    font-size: 14px;
    font-weight: 550;
    padding: 12px 14px;
    text-align: left;
}
QPushButton#NavButton:hover {
    background: #161e2c;
    color: #edf2fb;
}
QPushButton#NavButton:checked {
    background: #172640;
    color: #8cb6ff;
    border-left: 3px solid #6d9eff;
    padding-left: 11px;
}
QLabel#PageTitle {
    color: #f7f9fc;
    font-size: 30px;
    font-weight: 700;
}
QLabel#PageSubtitle {
    color: #8995aa;
    font-size: 14px;
}
QFrame#Card {
    background: #111824;
    border: 1px solid #222c3d;
    border-radius: 14px;
}
QLabel#SectionTitle {
    color: #f0f3f8;
    font-size: 15px;
    font-weight: 650;
}
QTextEdit, QLineEdit, QComboBox, QSpinBox {
    background: #0c121c;
    border: 1px solid #2a3548;
    border-radius: 9px;
    padding: 9px 11px;
    selection-background-color: #3169c6;
}
QTextEdit:focus, QLineEdit:focus, QComboBox:focus, QSpinBox:focus {
    border: 1px solid #6d9eff;
}
QTextEdit { color: #dce4f1; }
QComboBox { min-height: 20px; }
QSpinBox { min-height: 20px; }
QComboBox::drop-down { border: 0; width: 26px; }
QComboBox QAbstractItemView {
    background: #151d29;
    border: 1px solid #2b374b;
    selection-background-color: #284f8d;
    outline: 0;
}
QPushButton {
    background: #1a2433;
    border: 1px solid #2a374a;
    border-radius: 9px;
    color: #d9e0ec;
    font-weight: 550;
    padding: 9px 14px;
}
QPushButton:hover { background: #222e40; border-color: #3a4a62; }
QPushButton:pressed { background: #151e2b; }
QPushButton:disabled { color: #5d687a; background: #151b25; border-color: #232b38; }
QPushButton#PrimaryButton {
    background: #5d91ed;
    border-color: #6ba0fb;
    color: #07111f;
    font-weight: 700;
}
QPushButton#PrimaryButton:hover { background: #76a7fa; }
QPushButton#PrimaryButton:pressed { background: #4e80d7; }
QPushButton#DownloadButton {
    background: #6d9eff;
    border: 0;
    color: #07111f;
    font-size: 15px;
    font-weight: 750;
    padding: 13px 22px;
}
QPushButton#DownloadButton:hover { background: #83adff; }
QPushButton#DangerGhost { color: #ff8b99; }
QPushButton#DangerGhost:hover { background: #321d27; border-color: #61303e; }
QCheckBox { spacing: 8px; color: #aeb8c8; }
QCheckBox::indicator {
    width: 18px;
    height: 18px;
    background: #0c121c;
    border: 1px solid #3b4658;
    border-radius: 5px;
}
QCheckBox::indicator:hover { border-color: #6d9eff; }
QCheckBox::indicator:checked {
    background: #6d9eff;
    border-color: #6d9eff;
}
QTableWidget#QueueTable {
    background: #0f1621;
    alternate-background-color: #111a27;
    border: 1px solid #222c3d;
    border-radius: 10px;
    outline: 0;
    selection-background-color: #192b49;
}
QTableWidget#QueueTable::item { border-bottom: 1px solid #1b2533; padding: 6px; }
QTableWidget#QueueTable::item:selected { background: #192b49; }
QHeaderView::section {
    background: #151e2b;
    color: #8995a9;
    border: 0;
    border-bottom: 1px solid #293447;
    padding: 10px 7px;
    font-size: 12px;
    font-weight: 650;
    text-transform: uppercase;
}
QScrollBar:vertical { background: transparent; width: 10px; margin: 2px; }
QScrollBar::handle:vertical { background: #334057; min-height: 28px; border-radius: 4px; }
QScrollBar::handle:vertical:hover { background: #465671; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QProgressBar {
    background: #171f2c;
    border: 0;
    border-radius: 4px;
    color: transparent;
    max-height: 8px;
}
QProgressBar::chunk { background: #6d9eff; border-radius: 4px; }
QProgressBar#ItemProgress {
    color: #dce6f5;
    max-height: 18px;
    min-height: 18px;
    text-align: center;
    font-size: 11px;
}
QStatusBar {
    background: #0d131d;
    border-top: 1px solid #202938;
    color: #8f9bad;
}
QStatusBar::item { border: 0; }
QScrollArea#SettingsScroll, QScrollArea#SettingsScroll > QWidget > QWidget {
    background: #0b0f17;
}
QToolTip {
    background: #202b3b;
    color: #f2f5fa;
    border: 1px solid #3a4b64;
    padding: 5px;
}
"""
