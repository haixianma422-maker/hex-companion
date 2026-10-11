"""Background controls; callbacks are queued onto the Tk thread by the caller."""
import threading
from .theme import GOLD, ACCENT, SURFACE


class Tray:
    def __init__(self, dispatch, toggle, settings, refresh, close, on_error=None):
        import pystray
        from PIL import Image, ImageDraw
        image = Image.new('RGBA', (64, 64), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)
        draw.polygon([(32, 2), (58, 17), (58, 47), (32, 62), (6, 47), (6, 17)], fill=SURFACE, outline=GOLD, width=4)
        draw.line([(23, 20), (23, 44)], fill=ACCENT, width=5)
        draw.line([(41, 20), (41, 44)], fill=ACCENT, width=5)
        draw.line([(23, 32), (41, 32)], fill=ACCENT, width=5)
        def item(label, callback, default=False):
            return pystray.MenuItem(label, lambda icon, menu_item: dispatch(callback), default=default)
        menu = pystray.Menu(item('展开 / 收起伴随浮窗', toggle, True),
                            item('设置 / 手动修正', settings), item('刷新数据与客户端', refresh),
                            pystray.Menu.SEPARATOR, item('退出海克斯随行', close))
        self.icon = pystray.Icon('hex-companion', image, '海克斯随行 · 等待海克斯大乱斗', menu)
        self.dispatch, self.on_error = dispatch, on_error
        self.stopping = threading.Event()
        self.thread = None

    def start(self):
        def setup(icon):
            if self.stopping.is_set():
                icon.stop()
            else:
                icon.visible = True
        def run():
            try:
                self.icon.run(setup=setup)
            except Exception as exc:
                if self.on_error and not self.stopping.is_set():
                    detail = str(exc)
                    self.dispatch(lambda: self.on_error(detail))
        self.thread = threading.Thread(target=run, daemon=True)
        self.thread.start()

    def stop(self):
        self.stopping.set()
        if self.icon.visible:
            self.icon.visible = False
        self.icon.stop()
        if self.thread and self.thread is not threading.current_thread():
            self.thread.join(timeout=2)
