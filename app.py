import ctypes
import argparse
import os
import sys
import subprocess
import logging
from pathlib import Path

from aram_demo.cache import DataStore
from aram_demo.companion import CompanionApp
from aram_demo.windows import single_instance


def main():
    if getattr(sys, 'frozen', False):
        # Velopack runs install/update hooks by starting the EXE with its own arguments and
        # exits there; it must come before argument parsing, elevation and the instance lock.
        import velopack
        velopack.App().run()
    parser = argparse.ArgumentParser()
    parser.add_argument('--preview', action='store_true', help='预览小浮窗的选人 / 对局样式')
    parser.add_argument('--inspector', action='store_true', help='开发调试用资料查看器')
    parser.add_argument('--self-test', metavar='REPORT', help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.self_test:
        from scripts.packaged_check import run
        return run(Path(args.self_test))
    if getattr(sys, 'frozen', False) and os.name == 'nt' and not (args.preview or args.inspector):
        if not ctypes.windll.shell32.IsUserAnAdmin():
            # The elevated copy starts with a clean PyInstaller environment;
            # the original launcher exits immediately after this request.
            os.environ['PYINSTALLER_RESET_ENVIRONMENT'] = '1'
            result = ctypes.windll.shell32.ShellExecuteW(
                None, 'runas', sys.executable, subprocess.list2cmdline(sys.argv[1:]), None, 0)
            if result <= 32:
                ctypes.windll.user32.MessageBoxW(None, '启动需要确认 Windows 权限提示，以读取管理员运行的联盟客户端。', '海克斯随行', 0x10)
            return
    # Preview uses the same application lifecycle as the released companion.
    # Only the standalone developer inspector can run beside the companion.
    instance_handle = single_instance() if not args.inspector else True
    if not instance_handle:
        return
    seed = Path(__file__).resolve().parent / 'data'
    if args.preview and not getattr(sys, 'frozen', False):
        preview_root = seed.parent / '.build-cache/strict-ui-preview'
        cached = (preview_root / 'sources/qq101/heroes/222.json').is_file()
        if not cached:
            preview_root = seed.parent / '.build-cache/ui-preview'
        source = None if (preview_root / 'settings.json').is_file() else 'qq101' if cached else 'opgg'
        store = DataStore(preview_root, seed_root=seed, source=source)
    elif getattr(sys, 'frozen', False):
        local = Path(os.environ.get('LOCALAPPDATA', Path.home() / 'AppData' / 'Local'))
        store = DataStore(local / 'HexCompanion' / 'data', seed_root=seed)
    else:
        store = DataStore(seed)
    from aram_demo.runtime_log import configure
    configure(store.root)
    logger = logging.getLogger('aram_demo.app')
    logger.info('startup pid=%s preview=%s source=%s', os.getpid(), args.preview, store.source)
    if args.inspector:
        # The developer inspector is a separate Tk tool and is not part of the release.
        import tkinter as tk
        from aram_demo.ui import DemoApp
        if os.name == 'nt':
            try:
                ctypes.windll.shcore.SetProcessDpiAwareness(1)
            except OSError:
                pass
        root = tk.Tk()
        root.report_callback_exception = lambda kind, value, tb: logger.error('Tk callback failed', exc_info=(kind, value, tb))
        DemoApp(root, store)
        root.mainloop()
        return
    from PySide6.QtGui import QGuiApplication, QIcon
    # Python exceptions raised inside Qt slots reach sys.excepthook; a windowed EXE has no console.
    sys.excepthook = lambda kind, value, tb: logger.error('callback failed', exc_info=(kind, value, tb))
    qt = QGuiApplication(sys.argv)
    qt.setQuitOnLastWindowClosed(False)
    icon = Path(__file__).resolve().parent / 'packaging/hex-companion.ico'
    if icon.is_file():
        qt.setWindowIcon(QIcon(str(icon)))
    app = CompanionApp(store, preview=args.preview)
    if args.preview:
        # Double-click the panel title to step through the preview states.
        app.preview_next()
    return qt.exec()


if __name__ == '__main__':
    sys.exit(main())
