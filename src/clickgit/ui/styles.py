from __future__ import annotations


APP_STYLE = """
QMainWindow, QWidget {
    background: #f4f6f8;
    color: #17212b;
    font-family: "Microsoft YaHei UI", "Segoe UI";
    font-size: 13px;
}
QToolBar {
    background: #ffffff;
    border: 0;
    border-bottom: 1px solid #dce2e8;
    spacing: 4px;
    padding: 6px 8px;
}
QToolButton {
    min-height: 28px;
    padding: 3px 9px;
    border: 1px solid transparent;
    border-radius: 4px;
}
QToolButton:hover {
    background: #edf3f8;
    border-color: #c9d7e3;
}
QToolButton:pressed {
    background: #dfeaf2;
}
QToolButton:disabled {
    color: #98a4af;
}
#repositoryBar {
    background: #ffffff;
    border-bottom: 1px solid #dce2e8;
}
#repositoryName {
    font-size: 15px;
    font-weight: 600;
}
#branchBadge {
    background: #e7f3ea;
    color: #176b35;
    border: 1px solid #b9ddc4;
    border-radius: 4px;
    padding: 3px 7px;
}
QListWidget#navigation {
    background: #202a34;
    color: #d9e1e8;
    border: 0;
    outline: 0;
    padding-top: 8px;
}
QListWidget#navigation::item {
    min-height: 36px;
    padding: 2px 12px;
    border-left: 3px solid transparent;
}
QListWidget#navigation::item:hover {
    background: #2b3742;
}
QListWidget#navigation::item:selected {
    background: #34424f;
    color: #ffffff;
    border-left-color: #4da3d9;
}
QTreeWidget, QTableWidget, QListWidget#recentRepositories, QPlainTextEdit,
QLineEdit, QComboBox {
    background: #ffffff;
    border: 1px solid #ccd5dd;
    border-radius: 4px;
    selection-background-color: #d9ecf8;
    selection-color: #17212b;
}
QHeaderView::section {
    background: #edf1f4;
    border: 0;
    border-right: 1px solid #d8e0e6;
    border-bottom: 1px solid #ccd5dd;
    padding: 6px;
    font-weight: 600;
}
QTreeWidget::item:selected, QTableWidget::item:selected,
QListWidget::item:selected {
    background: #d9ecf8;
    color: #17212b;
}
QPushButton {
    background: #ffffff;
    border: 1px solid #b9c4ce;
    border-radius: 4px;
    min-height: 28px;
    padding: 2px 12px;
}
QPushButton:hover {
    background: #eef4f8;
    border-color: #8fa9ba;
}
QPushButton:pressed {
    background: #dce8ef;
}
QPushButton:disabled {
    color: #98a4af;
    background: #f3f5f6;
}
QPushButton#primaryButton, QPushButton#commitButton {
    background: #176b99;
    color: #ffffff;
    border-color: #176b99;
    font-weight: 600;
}
QPushButton#primaryButton:hover, QPushButton#commitButton:hover {
    background: #125a82;
}
QPushButton#dangerButton {
    color: #a32424;
    border-color: #d7abab;
}
QLabel#pageTitle {
    font-size: 18px;
    font-weight: 600;
}
QLabel#mutedLabel {
    color: #66737f;
}
QFrame#sectionLine {
    color: #dce2e8;
}
QStatusBar {
    background: #ffffff;
    border-top: 1px solid #dce2e8;
}
QProgressBar {
    border: 0;
    background: transparent;
}
"""
