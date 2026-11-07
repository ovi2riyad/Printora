"""Shared adaptive palette for the existing native-widget application."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

def apply_theme(window):
    selected=window.db.get('theme','Dark')
    if hasattr(window,'shell'):window.shell.theme_picker.setCurrentText(selected)
    dark=selected=='Dark' or selected=='System' and QApplication.styleHints().colorScheme()==Qt.ColorScheme.Dark
    bg,panel,text,muted,border,accent=('#10182c','#1b2946','#f2f5ff','#b8c6e5','#53698f','#2464f5') if dark else ('#eef3fb','#ffffff','#17243b','#5e718b','#b7c9e0','#2463eb')
    window.setProperty('themeMode','Dark' if dark else 'Light')
    window.setStyleSheet(f'''
        QWidget {{background:{bg};color:{text};font-family:"Segoe UI";font-size:13px;}}
        QLabel {{background:transparent;}} QLabel#title {{font-size:24px;font-weight:650;}}
        QLabel#brand {{font-size:26px;font-weight:750;color:{text};}}
        QFrame#hero {{background:#101a35;border:1px solid {border};border-radius:12px;}}
        QFrame#hero QLabel {{color:#f4f5ff;}} QFrame#hero QLabel#title {{font-size:25px;font-weight:700;}}
        QLabel#muted,QLabel#section {{color:{muted};}} QLabel#section {{font-size:17px;font-weight:650;}}
        QFrame#card,QGroupBox {{background:qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 {panel},stop:1 {bg});border:1px solid {border};border-radius:11px;padding:6px;}}
        QPushButton {{background:qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 {panel},stop:1 {bg});border:1px solid {border};border-radius:7px;padding:6px 10px;min-height:21px;font-weight:550;}}
        QPushButton:hover {{border-color:#75b8ff;background:{panel};}} QPushButton#primary,QPushButton:checked {{background:qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 #258dff,stop:1 #2342e9);color:white;border:1px solid #60baff;font-weight:650;}}
        QFrame#workflow {{border:2px solid #49bbff;border-radius:12px;background:qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 #398efb,stop:.6 #1955dd,stop:1 #218bfa);padding:0;}}
        QFrame#workflow[accent="green"] {{border-color:#69e2c2;background:qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 #38b68c,stop:.5 #13795f,stop:1 #167a82);}}
        QFrame#workflow[accent="purple"] {{border-color:#bb8cff;background:qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 #9d52eb,stop:.6 #5926c8,stop:1 #8240e8);}}
        QFrame#workflow[accent="amber"] {{border-color:#ffce78;background:qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 #f4a244,stop:.5 #bf6247,stop:1 #de9560);}}
        QFrame#workflow:hover {{border:3px solid #c8edff;}}
        QFrame#workflow QLabel {{color:white;background:transparent;border:0;}}
        QLabel#tileTitle {{font-size:18px;font-weight:700;}} QLabel#tileDetail {{font-size:12px;font-weight:450;}}
        QPushButton:disabled {{color:{muted};}} QPushButton:focus,QLineEdit:focus,QComboBox:focus {{border:2px solid {accent};}}
        QLineEdit,QComboBox,QSpinBox,QDoubleSpinBox,QTextEdit {{background:{panel};border:1px solid {border};border-radius:4px;padding:4px;min-height:19px;selection-background-color:{accent};}}
        QComboBox QAbstractItemView {{background:{panel};color:{text};selection-background-color:{accent};}}
        QListWidget,QTableWidget,QGraphicsView {{background:{panel};border:1px solid {border};border-radius:6px;}}
        QListWidget::item {{padding:5px;}} QListWidget::item:selected {{background:{accent};color:white;}}
        QListWidget#navigation {{border:0;border-right:1px solid {border};border-radius:0;background:{bg};}} QListWidget#navigation::item {{padding:7px 8px;margin:2px 4px;border-radius:7px;font-size:14px;}}
        QListWidget#navigation::item:selected {{background:qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 #278dff,stop:1 #2545de);color:white;border:1px solid #598cfa;}}
        QHeaderView::section {{background:{panel};padding:5px;border:1px solid {border};}}
        QTabWidget::pane {{border:1px solid {border};}} QTabBar::tab {{background:{panel};padding:7px 10px;}}
        QTabBar::tab:selected {{color:{accent};border-bottom:2px solid {accent};}}
        QScrollArea {{border:0;}} QScrollBar:vertical {{width:10px;background:{bg};}}
        QScrollBar::handle:vertical {{background:{border};min-height:30px;border-radius:4px;}}
        QSplitter::handle {{background:{border};width:7px;}}
        QSplitter::handle:hover {{background:{accent};}}
        QToolBar {{background:{panel};border:1px solid {border};border-radius:7px;padding:3px;spacing:4px;}}
        QToolButton {{background:transparent;border:1px solid transparent;border-radius:5px;padding:5px;min-width:22px;min-height:22px;}}
        QToolButton:hover,QToolButton:checked {{background:{bg};border-color:{accent};}}
        QToolButton:disabled {{color:{muted};}}
        QMenu {{background:{panel};border:1px solid {border};padding:5px;}}
        QMenu::item {{padding:7px 18px;}} QMenu::item:selected {{background:{accent};color:white;}}
        QProgressBar {{border:0;background:{border};max-height:6px;}} QProgressBar::chunk {{background:{accent};}}
        QCheckBox {{spacing:6px;}} QToolTip {{background:{panel};color:{text};border:1px solid {border};padding:5px;}}
    ''')
    if hasattr(window,'shell'):
        window.shell.refresh_icons()
