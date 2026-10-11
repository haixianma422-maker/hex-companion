import ctypes
import argparse
import os
import sys
import subprocess
from pathlib import Path
import tkinter as tk

from aram_demo.cache import DataStore
from aram_demo.companion import CompanionApp
from aram_demo.windows import single_instance


def main():
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
            # The elevated onefile process must own its extraction directory;
            # the original launcher exits immediately after this request.
            os.environ['PYINSTALLER_RESET_ENVIRONMENT'] = '1'
            result = ctypes.windll.shell32.ShellExecuteW(
                None, 'runas', sys.executable, subprocess.list2cmdline(sys.argv[1:]), None, 0)
            if result <= 32:
                ctypes.windll.user32.MessageBoxW(None, '启动需要确认 Windows 权限提示，以读取管理员运行的联盟客户端。', '海克斯随行', 0x10)
            return
    instance_handle = single_instance() if not args.preview and not args.inspector else True
    if not instance_handle:
        return
    if os.name == 'nt':
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except OSError:
            pass
    root = tk.Tk()
    seed = Path(__file__).resolve().parent / 'data'
    if getattr(sys, 'frozen', False):
        local = Path(os.environ.get('LOCALAPPDATA', Path.home() / 'AppData' / 'Local'))
        store = DataStore(local / 'HexCompanion' / 'data', seed_root=seed)
    else:
        store = DataStore(seed)
    if args.inspector:
        from aram_demo.ui import DemoApp
        DemoApp(root, store)
    else:
        app = CompanionApp(root, store, preview=args.preview)
        if args.preview:
            app.preview_next()
    root.mainloop()


if __name__ == '__main__':
    sys.exit(main())
