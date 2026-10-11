import ctypes
import os
import threading
from ctypes import wintypes


class Hotkeys:
    def __init__(self, on_scan, on_refresh, on_close):
        self.callbacks = {1: on_scan, 2: on_refresh}
        self.on_close = on_close
        self.status = '快捷键未启动'
        self._stop = threading.Event()
        self._overlay_visible = False

    def set_overlay_visible(self, visible):
        self._overlay_visible = visible

    def start(self):
        if os.name != 'nt':
            self.status = '当前平台请使用界面按钮'
            return
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def _run(self):
        user32 = ctypes.windll.user32
        registered = []
        try:
            for ident, vk in ((1, 0x75), (2, 0x76)):
                if user32.RegisterHotKey(None, ident, 0x4000, vk):
                    registered.append(ident)
            self.status = 'F6 识别 · F7 刷新 · Esc 收起为浮标' if len(registered) == 2 else '部分快捷键被占用，请使用界面按钮'
            message = wintypes.MSG()
            esc_down = False
            while not self._stop.wait(0.035):
                while user32.PeekMessageW(ctypes.byref(message), None, 0, 0, 1):
                    if message.message == 0x0312 and message.wParam in self.callbacks:
                        self.callbacks[message.wParam]()
                down = bool(user32.GetAsyncKeyState(0x1B) & 0x8000)
                if down and not esc_down and self._overlay_visible:
                    self.on_close()
                esc_down = down
        finally:
            for ident in registered:
                user32.UnregisterHotKey(None, ident)

    def stop(self):
        self._stop.set()
