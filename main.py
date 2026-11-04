import sys
import os
from pathlib import Path
if '--smoke-test' in sys.argv:
    os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QTimer
from app.ui.studio_window import StudioWindow as MainWindow

def main():
    if '--verify-studio' in sys.argv:
        from app.services.studio_diagnostics import verify_studio
        position=sys.argv.index('--verify-studio')
        return verify_studio(sys.argv[position+1],sys.argv[position+2])
    if '--verify-cropper' in sys.argv:
        from app.services.cropper_diagnostics import verify_cropper
        position=sys.argv.index('--verify-cropper')
        return verify_cropper(sys.argv[position+1],sys.argv[position+2])
    if '--verify-runtime' in sys.argv:
        from app.services.diagnostics import verify_runtime
        position=sys.argv.index('--verify-runtime')
        return verify_runtime(sys.argv[position+1],sys.argv[position+2])
    app = QApplication(sys.argv)
    app.setApplicationName('Studio Photo Maker')
    app.setOrganizationName('StudioPhotoMaker')
    window = MainWindow()
    window.show()
    if '--smoke-test' in sys.argv:
        position=sys.argv.index('--smoke-test')
        destination=Path(sys.argv[position+1]) if position+1<len(sys.argv) else Path('smoke-test.png')
        def finish():
            window.grab().save(str(destination));window.dirty=False;window.close()
        QTimer.singleShot(1500,finish)
    return app.exec()

if __name__ == '__main__':
    sys.exit(main())
