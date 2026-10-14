"""Background controls; callbacks are queued onto the Tk thread by the caller."""
import threading
import logging
from .theme import brand_image


class Tray:
    def __init__(self, dispatch, toggle, settings, refresh, close, on_error=None):
        import pystray
        image = brand_image()
        def item(label, callback, default=False):
            return pystray.MenuItem(label, lambda icon, menu_item: dispatch(callback), default=default)
        menu = pystray.Menu(item('展开 / 收起伴随浮窗', toggle, True),
                            item('设置 / 手动修正', settings), item('刷新数据与客户端', refresh),
                            pystray.Menu.SEPARATOR, item('退出海克斯随行', close))
        self.icon = pystray.Icon('hex-companion', image, '海克斯随行 · 等待海克斯大乱斗', menu)
        self.dispatch, self.on_error = dispatch, on_error
        self.stopping = threading.Event()
        self.failed = threading.Event()
        self.failure_lock = threading.Lock()
        self.thread = None

    def _failed(self, exc):
        with self.failure_lock:
            if self.stopping.is_set() or self.failed.is_set():
                return
            self.failed.set()
        logging.getLogger(__name__).exception('系统托盘启动失败')
        if self.on_error:
            detail = str(exc)
            self.dispatch(lambda: self.on_error(detail))

    def start(self):
        def setup(icon):
            try:
                if self.stopping.is_set():
                    icon.stop()
                else:
                    icon.visible = True
                    logging.getLogger(__name__).info('tray ready')
            except Exception as exc:
                self._failed(exc)
        def run():
            try:
                self.icon.run(setup=setup)
            except Exception as exc:
                self._failed(exc)
        self.thread = threading.Thread(target=run, daemon=True)
        self.thread.start()

    def stop(self):
        self.stopping.set()
        try:
            self.icon.stop()
        except Exception:
            logging.getLogger(__name__).exception('停止系统托盘失败')
        if self.thread and self.thread.is_alive() and self.thread is not threading.current_thread():
            self.thread.join(timeout=2)
