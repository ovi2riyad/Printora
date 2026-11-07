"""Creator attribution and license access for the native About page."""
from pathlib import Path
import sys
from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QFrame, QLabel, QVBoxLayout, QDialog, QDialogButtonBox, QTextBrowser
from app.credits import AUTHOR, WEBSITE, EMAIL, DEVELOPMENT_CREDIT, COPYRIGHT, LICENSE, SOURCE_URL
from app.version import VERSION


def open_about_link(target, parent):
    url = QUrl(target)
    if not url.isLocalFile():
        QDesktopServices.openUrl(url)
        return
    path = Path(url.toLocalFile())
    dialog = QDialog(parent)
    dialog.setWindowTitle('Printora — '+('MIT License' if path.name=='LICENSE' else 'Component notices'))
    dialog.resize(700,540)
    screen = dialog.screen()
    if screen:
        available = screen.availableGeometry()
        dialog.resize(min(700,max(1,available.width()-24)),min(540,max(1,available.height()-50)))
    layout = QVBoxLayout(dialog)
    text = QTextBrowser()
    text.setObjectName('licenseText')
    text.setOpenExternalLinks(True)
    text.document().setBaseUrl(QUrl.fromLocalFile(str(path.parent)+'/'))
    try:
        content = path.read_text(encoding='utf-8')
        if path.suffix=='.md':text.setMarkdown(content)
        else:text.setPlainText(content)
    except OSError:
        text.setPlainText('This notice is missing from the application folder. Restore the complete '
            'Printora installation or find the license and notices at '+SOURCE_URL)
    layout.addWidget(text)
    close = QDialogButtonBox(QDialogButtonBox.Close)
    close.rejected.connect(dialog.reject)
    layout.addWidget(close)
    dialog.exec()


def creator_card():
    card = QFrame()
    card.setObjectName('creatorCard')
    card.setStyleSheet('''
        QFrame#creatorCard {background:qlineargradient(x1:0,y1:0,x2:1,y2:1,
            stop:0 #142546,stop:1 #0b1226);border:1px solid #39527b;border-radius:16px;}
        QFrame#creatorCard QLabel {background:transparent;border:0;color:#edf4ff;}
    ''')
    layout = QVBoxLayout(card)
    layout.setContentsMargins(24,24,24,24)
    layout.setSpacing(18)
    heading = QLabel(f'<span style="color:#53d9ee;font-size:13px;">THE CREATOR BEHIND</span>'
        f'<h1 style="margin-top:8px;">Printora <span style="font-size:16px;color:#aac1e2;">{VERSION}</span></h1>'
        '<span style="color:#b6c8e6;">Photography &amp; Document Studio</span>')
    heading.setWordWrap(True)
    layout.addWidget(heading)
    credits = QLabel(f'<h2>{AUTHOR}</h2><p style="color:#b6c8e6;">Creator &amp; project owner</p>'
        f'<p><a style="color:#69dff2;" href="{WEBSITE}">{WEBSITE}</a></p>'
        f'<p><a style="color:#69dff2;" href="mailto:{EMAIL}">{EMAIL}</a></p>'
        f'<p style="color:#b6c8e6;">{DEVELOPMENT_CREDIT}</p>')
    credits.setObjectName('appCredits')
    credits.setWordWrap(True)
    credits.setOpenExternalLinks(True)
    credits.setTextInteractionFlags(Qt.TextBrowserInteraction)
    layout.addWidget(credits)
    root = Path(sys.executable).parent if getattr(sys,'frozen',False) else Path(__file__).resolve().parents[2]
    license_url = QUrl.fromLocalFile(str(root/'LICENSE')).toString()
    notices_url = QUrl.fromLocalFile(str(root/'THIRD_PARTY.md')).toString()
    legal = QLabel(f'<p>{COPYRIGHT}</p>'
        f'<p><a style="color:#69dff2;" href="{license_url}">{LICENSE}</a> · '
        f'<a style="color:#69dff2;" href="{SOURCE_URL}">Source code</a> · '
        f'<a style="color:#69dff2;" href="{notices_url}">Component notices</a></p>'
        '<p style="color:#b6c8e6;">Free to use, modify and share. Retain the copyright and license notice.'
        '<br>Provided without warranty. Bundled components retain their own licenses.</p>')
    legal.setObjectName('appLicense')
    legal.setWordWrap(True)
    legal.setOpenExternalLinks(False)
    legal.setTextInteractionFlags(Qt.TextBrowserInteraction)
    legal.linkActivated.connect(lambda target:open_about_link(target,card))
    layout.addWidget(legal)
    return card
