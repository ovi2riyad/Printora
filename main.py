import sys
import os
from pathlib import Path
if '--smoke-test' in sys.argv:
    os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QTimer
from app.ui.studio_window import StudioWindow as MainWindow

def main():
    # Diagnostic runs already require disposable app data. Their working folders
    # must be disposable too, including simulated scanner destination requests.
    if any(arg.startswith('--verify-') for arg in sys.argv) and os.environ.get('LOCALAPPDATA'):
        from app.services import user_folders
        user_folders.documents_directory=lambda:Path(os.environ['LOCALAPPDATA'])/'Documents'
    if '--verify-simple-workflows' in sys.argv:
        from app.services.simple_workflow_diagnostics import verify_simple_workflows
        return verify_simple_workflows(sys.argv[sys.argv.index('--verify-simple-workflows')+1])
    if '--verify-client' in sys.argv:
        from app.services.client_diagnostics import verify_client
        return verify_client(sys.argv[sys.argv.index('--verify-client')+1])
    if '--verify-visual-scan' in sys.argv:
        from app.services.visual_scan_diagnostics import verify_visual_scan
        position=sys.argv.index('--verify-visual-scan')
        return verify_visual_scan(sys.argv[position+1],sys.argv[position+2])
    if '--verify-ux' in sys.argv:
        from app.services.ux_diagnostics import verify_ux
        position=sys.argv.index('--verify-ux')
        return verify_ux(sys.argv[position+1],sys.argv[position+2])
    if '--hardware-worker' in sys.argv:
        from app.services.windows_printing import helper_main
        return helper_main()
    if '--verify-stabilization' in sys.argv:
        from app.services.stabilization_diagnostics import verify_stabilization
        return verify_stabilization(sys.argv[sys.argv.index('--verify-stabilization')+1])
    if '--verify-final-studio' in sys.argv:
        from app.services.final_diagnostics import verify_final
        return verify_final(sys.argv[sys.argv.index('--verify-final-studio')+1])
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
    from app.core.windows import configure_shell
    from app.version import VERSION
    configure_shell()
    app = QApplication(sys.argv)
    app.setApplicationVersion(VERSION)
    app.setApplicationName('Studio Photo Maker')
    app.setOrganizationName('StudioPhotoMaker')
    window = MainWindow()
    window.showMaximized()
    if '--smoke-test' not in sys.argv:
        QTimer.singleShot(300,window.hardware.refresh)
    if '--smoke-test' in sys.argv:
        position=sys.argv.index('--smoke-test')
        destination=Path(sys.argv[position+1]) if position+1<len(sys.argv) else Path('smoke-test.png')
        def finish():
            window.grab().save(str(destination));window.dirty=False;window.close()
        QTimer.singleShot(1500,finish)
    return app.exec()

if __name__ == '__main__':
    sys.exit(main())
