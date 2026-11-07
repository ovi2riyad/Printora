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
    assert WEBSITE=='https://enthugo.vom' and EMAIL=='ovi2riyad@gmail.com'
    settings.close();settings.deleteLater();db.conn.close();app.processEvents()


def test_payload_contains_current_guides_and_credits(tmp_path,monkeypatch):
    from scripts import build_release
    payload=tmp_path/'StudioPhotoMaker';(payload/'_internal/models').mkdir(parents=True)
    (payload/'StudioPhotoMaker.exe').write_bytes(b'fixture executable')
    (payload/'_internal/models/u2net_human_seg.onnx').write_bytes(b'fixture model')
    monkeypatch.setattr(build_release,'make_icon',lambda path:path.write_bytes(b'fixture icon'))
    build_release.prepare_payload(payload)
    for name in ('README.md','CREDITS.md','THIRD_PARTY.md','docs/DEVELOPMENT.md','docs/VALIDATION.md'):
        assert (payload/name).read_bytes()==(build_release.ROOT/name).read_bytes()
    assert AUTHOR in (payload/'CREDITS.md').read_text(encoding='utf-8')


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
