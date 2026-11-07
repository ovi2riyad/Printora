"""Keep working-folder tests and simulated acquisitions out of real Documents."""
import pytest

@pytest.fixture(autouse=True)
def isolated_working_folders(tmp_path,monkeypatch):
    from app.services import user_folders
    documents=tmp_path/'Documents'
    monkeypatch.setattr(user_folders,'documents_directory',lambda:documents)
    yield
    # Each case owns its windows. Closed Qt windows can otherwise remain alive
    # through application style-hint signals for the whole regression process.
    from PySide6.QtWidgets import QApplication,QMainWindow
    from PySide6.QtCore import QCoreApplication,QEvent
    if QApplication.instance():
        for window in QApplication.topLevelWidgets():
            if isinstance(window,QMainWindow) and window.parentWidget() is None and not window.isVisible():window.deleteLater()
        QCoreApplication.sendPostedEvents(None,QEvent.DeferredDelete)
