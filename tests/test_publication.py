"""Public credits remain visible and travel with the installer payload."""
from PySide6.QtWidgets import QApplication,QLabel
from app.credits import AUTHOR,WEBSITE,EMAIL,DEVELOPMENT_CREDIT


def test_settings_about_includes_requested_public_credits(tmp_path,monkeypatch):
    from app.core.database import Database
    from app.ui.studio_settings import StudioSettings
    monkeypatch.setenv('LOCALAPPDATA',str(tmp_path/'data'))
    app=QApplication.instance() or QApplication([]);db=Database()
    settings=StudioSettings(db,lambda work,done:done(work()),lambda text:None,lambda:None)
    about=settings.findChild(QLabel,'appCredits')
    assert any(settings.tabs.tabText(i)=='About' for i in range(settings.tabs.count()))
    assert about.openExternalLinks() and all(value in about.text() for value in (AUTHOR,WEBSITE,EMAIL,DEVELOPMENT_CREDIT))
    assert WEBSITE=='https://enthugo.com' and EMAIL=='ovi2riyad@gmail.com'
    legal=settings.findChild(QLabel,'appLicense')
    assert 'MIT License' in legal.text() and '/LICENSE' in legal.text()
    assert 'without warranty' in legal.text() and 'Component notices' in legal.text()
    settings.close();settings.deleteLater();db.conn.close();app.processEvents()


def test_payload_contains_current_guides_and_credits(tmp_path,monkeypatch):
    from scripts import build_release
    payload=tmp_path/'StudioPhotoMaker';(payload/'_internal/models').mkdir(parents=True)
    (payload/'StudioPhotoMaker.exe').write_bytes(b'fixture executable')
    (payload/'_internal/models/u2net_human_seg.onnx').write_bytes(b'fixture model')
    monkeypatch.setattr(build_release,'make_icon',lambda path:path.write_bytes(b'fixture icon'))
    build_release.prepare_payload(payload)
    for name in ('README.md','CREDITS.md','THIRD_PARTY.md','LICENSE','assets/creator-card.svg','docs/DEVELOPMENT.md','docs/VALIDATION.md','licenses/LGPL-3.0.txt','licenses/GPL-3.0.txt'):
        assert (payload/name).read_bytes()==(build_release.ROOT/name).read_bytes()
    assert AUTHOR in (payload/'CREDITS.md').read_text(encoding='utf-8')
    assert (payload/'licenses/packages/pyside6_essentials/METADATA').is_file()
    assert (payload/'licenses/packages/Python/LICENSE.txt').is_file()


def test_about_license_link_displays_complete_license_offline(monkeypatch):
    from pathlib import Path
    from PySide6.QtCore import QUrl
    from PySide6.QtWidgets import QDialog,QTextBrowser
    from app.ui.about import creator_card
    app=QApplication.instance() or QApplication([])
    shown=[]
    def inspect_dialog(dialog):
        shown.append(dialog.findChild(QTextBrowser,'licenseText').toPlainText())
        return 0
    monkeypatch.setattr(QDialog,'exec',inspect_dialog)
    card=creator_card();legal=card.findChild(QLabel,'appLicense')
    license_path=Path(__file__).resolve().parents[1]/'LICENSE'
    legal.linkActivated.emit(QUrl.fromLocalFile(str(license_path)).toString())
    assert len(shown)==1 and shown[0].strip()==license_path.read_text(encoding='utf-8').strip()
    assert 'Copyright (c) 2026 Riyad Ahmed Ovi' in shown[0]
    card.deleteLater();app.processEvents()


def test_main_window_fits_a_sub640_logical_desktop(tmp_path,monkeypatch):
    from PySide6.QtCore import QRect
    from app.ui.studio_window import StudioWindow
    monkeypatch.setenv('LOCALAPPDATA',str(tmp_path/'data'))
    app=QApplication.instance() or QApplication([])
    class SmallDesktop:
        def availableGeometry(self):return QRect(0,0,512,384)
    monkeypatch.setattr(QApplication,'primaryScreen',lambda:SmallDesktop())
    window=StudioWindow();window.show()
    try:
        for theme in ('Light','Dark'):
            window.shell.set_theme(theme)
            for _ in range(8):app.processEvents()
            assert window.minimumSize().width()<=512 and window.size().width()<=512
            assert window.minimumSize().height()<=384 and window.size().height()<=384
    finally:
        window.timer.stop();window.invalidate_autosave();window.dirty=False;window.close();app.processEvents()
