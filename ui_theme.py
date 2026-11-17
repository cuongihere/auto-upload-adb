"""Shared compact desktop theme and scrollable settings pages."""
from pathlib import Path

from PySide6.QtGui import QColor, QFont, QPalette
from PySide6.QtWidgets import QScrollArea


def scroll_page(widget):
    area = QScrollArea()
    area.setWidgetResizable(True)
    area.setFrameShape(QScrollArea.NoFrame)
    area.setWidget(widget)
    return area


def apply_theme(app):
    app.setStyle("Fusion")
    app.setFont(QFont("Segoe UI", 9))
    palette = app.palette()
    palette.setColor(QPalette.Window, QColor("#f5f7fb"))
    palette.setColor(QPalette.Base, QColor("#ffffff"))
    palette.setColor(QPalette.WindowText, QColor("#243449"))
    palette.setColor(QPalette.Text, QColor("#243449"))
    app.setPalette(palette)
    arrow = (Path(__file__).resolve().parent / "assets" / "chevron-down.svg").as_posix()
    app.setStyleSheet("""
        QWidget { color: #243449; font-family: "Segoe UI"; font-size: 12px; }
        QMainWindow, QDialog, QScrollArea { background: #f5f7fb; }
        QLabel { background: transparent; }
        QLabel[role="title"] { font-size: 20px; font-weight: 700; color: #152b49; }
        QLabel[role="muted"] { color: #61748c; font-size: 11px; }
        QLabel[role="metric"] { background: #ffffff; color: #254261; border: 1px solid #d9e3ee;
            border-radius: 7px; padding: 8px 11px; font-size: 12px; font-weight: 600; }
        QLabel[role="summary"] { background: #e6f1ff; color: #1c589e; border: 1px solid #c8dff8;
            border-radius: 7px; padding: 7px 12px; font-weight: 600; }
        QLabel[role="status"] { background: #eaf2fc; color: #234b79; border: 1px solid #d2e0f3;
            border-radius: 7px; padding: 9px 12px; font-weight: 600; }
        QGroupBox { background: #ffffff; border: 1px solid #d9e3ed; border-radius: 8px;
            margin-top: 12px; padding: 12px 9px 9px; font-weight: 600; }
        QGroupBox::title { subcontrol-origin: margin; left: 12px; padding: 0 6px; color: #334b69; }
        QPushButton { background: #f0f4fb; color: #254261; border: 1px solid #c8d7e8;
            border-radius: 6px; padding: 6px 10px; min-height: 20px; font-weight: 600; }
        QPushButton:hover { background: #e0ebf9; border-color: #719ac8; }
        QPushButton:pressed { background: #c8dcf3; }
        QPushButton:focus { border: 2px solid #3677c7; }
        QPushButton[role="primary"] { background: #2563b7; border-color: #2563b7; color: #ffffff; }
        QPushButton[role="primary"]:hover { background: #184f98; }
        QPushButton[role="success"] { background: #137c60; border-color: #137c60; color: white; }
        QPushButton[role="success"]:hover { background: #0c634b; }
        QPushButton[role="danger"] { background: #fff1f0; color: #ad3535; border-color: #e6b0ac; }
        QPushButton[role="danger"]:hover { background: #ffdfdc; }
        QPushButton:checked { background: #dfebfb; border-color: #5c87be; }
        QPushButton:disabled { background: #eef1f5; color: #8a97a9; border-color: #d9e0e9; }
        QLineEdit, QPlainTextEdit, QListWidget, QTableWidget, QComboBox, QSpinBox {
            background: #ffffff; color: #243449; border: 1px solid #ccd7e4; border-radius: 5px;
            selection-background-color: #c7dcf7; selection-color: #12375f; }
        QLineEdit, QComboBox, QSpinBox { padding: 5px 8px; min-height: 19px; }
        QComboBox::drop-down { border: none; width: 20px; }
        QComboBox::down-arrow { image: url("ARROW_PATH"); width: 12px; height: 8px; }
        QPlainTextEdit { padding: 6px; }
        QLineEdit:focus, QPlainTextEdit:focus, QListWidget:focus { border-color: #3677c7; }
        QListWidget::item { padding: 6px; border-bottom: 1px solid #edf1f6; }
        QTableWidget { gridline-color: #e5eaf1; alternate-background-color: #f7faff; }
        QTableWidget::item { padding: 4px; }
        QHeaderView::section { background: #eaf0f8; color: #415b7a; border: none;
            border-bottom: 1px solid #d4dfec; padding: 7px 7px; font-weight: 600; }
        QTabWidget::pane { background: #ffffff; border: 1px solid #d9e3ed; border-radius: 7px; }
        QTabBar::tab { background: #e8eef6; color: #526b87; border: 1px solid #d8e1ed;
            padding: 7px 12px; margin-right: 3px; border-top-left-radius: 6px; border-top-right-radius: 6px; }
        QTabBar::tab:selected { background: #ffffff; color: #1c579d; border-bottom: 2px solid #2563b7; }
        QCheckBox { spacing: 6px; padding: 2px 0; }
        QCheckBox::indicator { width: 16px; height: 16px; }
        QSplitter::handle { background: #dce5ee; }
        QSplitter::handle:hover { background: #a4bfdc; }
        QDockWidget { font-weight: 600; }
        QDockWidget::title { background: #eaf0f7; padding: 8px; color: #33506f; }
        QMenuBar { background: #f5f7fb; border-bottom: 1px solid #d9e3ed; }
        QMenu { background: #ffffff; border: 1px solid #ccd7e4; padding: 5px; }
        QMenu::item { padding: 7px 24px; }
        QMenu::item:selected { background: #e1ebf8; }
        QToolTip { background: #ffffff; color: #243449; border: 1px solid #c6d2e1; padding: 7px; }
        QProgressBar { background: #e6edf7; border: none; border-radius: 5px;
            text-align: center; min-height: 14px; color: #244263; }
        QProgressBar::chunk { background: #3078c8; border-radius: 5px; }
    """.replace("ARROW_PATH", arrow))
