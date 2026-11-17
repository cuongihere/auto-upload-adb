"""Shared desktop styling and scrollable settings pages."""
from PySide6.QtGui import QFont, QPalette, QColor
from PySide6.QtWidgets import QScrollArea
from pathlib import Path


def scroll_page(widget):
    area = QScrollArea()
    area.setWidgetResizable(True)
    area.setFrameShape(QScrollArea.NoFrame)
    area.setWidget(widget)
    return area


def apply_theme(app):
    app.setStyle('Fusion')
    app.setFont(QFont('Segoe UI', 10))
    palette = app.palette()
    palette.setColor(QPalette.Window, QColor('#ffffff'))
    palette.setColor(QPalette.Base, QColor('#ffffff'))
    palette.setColor(QPalette.WindowText, QColor('#243449'))
    palette.setColor(QPalette.Text, QColor('#243449'))
    app.setPalette(palette)
    arrow = (Path(__file__).resolve().parent / 'assets' / 'chevron-down.svg').as_posix()
    app.setStyleSheet('''
        QWidget { color: #243449; font-family: "Segoe UI"; font-size: 13px; }
        QMainWindow, QDialog, QScrollArea, QTabWidget::pane { background: #ffffff; }
        QLabel { background: transparent; }
        QLabel[role="title"] { font-size: 22px; font-weight: 700; color: #142d4e; }
        QLabel[role="muted"] { color: #62738a; font-size: 12px; }
        QLabel[role="status"] { background: #e5eefb; color: #214a82; border: 1px solid #c8d9ef;
            border-radius: 6px; padding: 8px 12px; }
        QGroupBox { background: #ffffff; border: 1px solid #d5deea; border-radius: 9px;
            margin-top: 14px; padding: 16px 10px 10px; font-weight: 600; }
        QGroupBox::title { subcontrol-origin: margin; left: 14px; padding: 0 6px; color: #243e60; }
        QPushButton { background: #e4ecf8; color: #244770; border: 1px solid #9db4d2;
            border-radius: 6px; padding: 7px 12px; min-height: 18px; font-weight: 600; }
        QPushButton:hover { background: #d0dff3; border-color: #4779b8; }
        QPushButton:pressed { background: #b9cfee; }
        QPushButton:focus { border: 2px solid #3677c7; }
        QPushButton[role="primary"] { background: #245caa; border-color: #245caa; color: white; }
        QPushButton[role="primary"]:hover { background: #194983; }
        QPushButton[role="success"] { background: #14765a; border-color: #14765a; color: white; }
        QPushButton[role="success"]:hover { background: #0d5d46; }
        QPushButton[role="danger"] { background: #fff0ee; color: #a13232; border-color: #dfa8a5; }
        QPushButton[role="danger"]:hover { background: #ffdbd7; }
        QPushButton:disabled { background: #edf0f4; color: #8b97a7; border-color: #d5dce5; }
        QLineEdit, QPlainTextEdit, QListWidget, QTableWidget, QComboBox, QSpinBox {
            background: #ffffff; color: #243449; border: 1px solid #c6d2e1; border-radius: 5px;
            selection-background-color: #c7dcf7; selection-color: #12375f; }
        QLineEdit, QComboBox, QSpinBox { padding: 5px 8px; min-height: 21px; }
        QComboBox::drop-down { border: none; width: 22px; }
        QComboBox::down-arrow { image: url("ARROW_PATH"); width: 12px; height: 8px; }
        QPlainTextEdit { padding: 6px; }
        QLineEdit:focus, QPlainTextEdit:focus, QListWidget:focus { border-color: #3677c7; }
        QListWidget::item { padding: 8px 6px; border-bottom: 1px solid #edf1f6; }
        QTableWidget { gridline-color: #e4eaf2; alternate-background-color: #f5f8fc; }
        QTableWidget::item { padding: 5px; }
        QHeaderView::section { background: #e8eef6; color: #405675; border: none;
            border-bottom: 1px solid #c7d4e4; padding: 8px 7px; font-weight: 600; }
        QTabWidget::pane { border: 1px solid #d5deea; border-radius: 7px; }
        QTabBar::tab { background: #e4ebf4; color: #566b85; border: 1px solid #d5deea;
            padding: 9px 15px; margin-right: 3px; border-top-left-radius: 6px; border-top-right-radius: 6px; }
        QTabBar::tab:selected { background: #ffffff; color: #174d91; border-bottom: 3px solid #245caa; }
        QCheckBox { spacing: 7px; padding: 3px 0; }
        QCheckBox::indicator { width: 17px; height: 17px; }
        QSplitter::handle { background: #d6e0ec; }
        QSplitter::handle:hover { background: #8aaedb; }
        QDockWidget { font-weight: 600; }
        QDockWidget::title { background: #f5f7fa; padding: 9px; }
        QMenuBar { background: #f7f9fc; border-bottom: 1px solid #d5deea; }
        QMenu { background: #ffffff; border: 1px solid #c6d2e1; padding: 5px; }
        QMenu::item { padding: 7px 24px; }
        QMenu::item:selected { background: #dce8f8; }
        QToolTip { background: #ffffff; color: #243449; border: 1px solid #c6d2e1; padding: 7px; }
    '''.replace('ARROW_PATH', arrow))
