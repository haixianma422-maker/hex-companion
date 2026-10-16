"""QML spike entry point: python -m qml_spike.main [--preview] [--hud] [--metrics FILE]."""
import argparse
import json
import logging
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

ROOT = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import QObject, Property, QTimer, QUrl, Qt, Signal
from PySide6.QtGui import QGuiApplication, QIcon
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuick import QQuickWindow

from aram_demo.cache import DataStore
from aram_demo.windows import single_instance
from qml_spike.bridge import Bridge


def gpu_percent(pid):
    """Sum this process's GPU engine utilisation (Windows performance counters)."""
    script = (f"(Get-Counter '\\GPU Engine(pid_{pid}_*)\\Utilization Percentage' -ErrorAction SilentlyContinue)"
              ".CounterSamples | Measure-Object -Property CookedValue -Sum | % Sum")
    try:
        out = subprocess.run(['powershell', '-NoProfile', '-Command', script], capture_output=True, text=True,
                             timeout=15, creationflags=0x08000000).stdout.strip()
        return round(float(out or 0), 2)
    except (OSError, ValueError, subprocess.SubprocessError):
        return None


FRAME_LOG_RULES = ('qt.scenegraph.time.renderer=false;qt.scenegraph.time.glyph=false;'
                   'qt.scenegraph.time.texture=false;qt.scenegraph.time.compilation=false')


def capture_frame_log(path):
    """Route Qt's render-thread timing log to a file. Must run before QGuiApplication exists.

    Frames are timed by Qt itself on the render thread. A Python slot on frameSwapped would run
    on the render thread too and has deadlocked against the GUI thread over the GIL.
    """
    os.environ.update(QSG_RENDER_TIMING='1', QT_FORCE_STDERR_LOGGING='1',
                      QT_MESSAGE_PATTERN='%{time process}|%{message}', QT_LOGGING_RULES=FRAME_LOG_RULES)
    stream = open(path, 'wb')
    os.dup2(stream.fileno(), 2)
    if os.name == 'nt':
        # A windowed (packaged) process has no standard error handle; point it at the file as well.
        import ctypes
        import msvcrt
        ctypes.windll.kernel32.SetStdHandle(-12, msvcrt.get_osfhandle(2))   # STD_ERROR_HANDLE
    return stream


class Metrics(QObject):
    """Reads presented frames from Qt's timing log; idle panels should present none."""
    changed = Signal()

    def __init__(self, path, bridge, frame_log, gpu=False):
        super().__init__()
        import psutil
        self.process, self.path, self.bridge, self.gpu = psutil.Process(), path, bridge, gpu
        self.process.cpu_percent(None)
        self.frame_log, self.offset, self.window = frame_log, 0, None
        self.last = None
        self.gaps = []
        self.frames = self.window_frames = 0
        self._text = ''
        self.gpu_value = None
        self.second = QTimer(self); self.second.timeout.connect(self.tick); self.second.start(1000)
        self.minute = QTimer(self); self.minute.timeout.connect(self.write); self.minute.start(10000)
        if gpu:
            threading.Thread(target=self._gpu_loop, daemon=True).start()

    def attach(self, window):
        import shiboken6
        self.window = f'[window {hex(shiboken6.getCppPointer(window)[0])}]'

    def read_frames(self):
        try:
            with open(self.frame_log, 'rb') as stream:
                stream.seek(self.offset)
                chunk = stream.read()
        except OSError:
            return
        complete = chunk.rfind(b'\n') + 1
        self.offset += complete
        for line in chunk[:complete].decode('utf-8', 'replace').splitlines():
            stamp, _, message = line.partition('|')
            if self.window not in message or 'frame rendered in' not in message:
                continue
            try:
                now = float(stamp)
            except ValueError:
                continue
            # Qt renders on demand: a pause between two animations is idle time, not a slow frame.
            if self.last is not None and now - self.last < .1:
                self.gaps.append((now - self.last) * 1000)
            self.last = now
            self.frames += 1; self.window_frames += 1

    def tick(self):
        self.read_frames()
        self._text = f'{self.frames} fps · rss {self.process.memory_info().rss / 2**20:.0f}MB'
        self.frames = 0
        self.changed.emit()

    def _gpu_loop(self):
        while True:
            self.gpu_value = gpu_percent(os.getpid())
            time.sleep(15)

    def snapshot(self):
        self.read_frames()
        gaps = sorted(self.gaps)
        median = gaps[len(gaps) // 2] if gaps else 0
        return {'time': time.strftime('%Y-%m-%d %H:%M:%S'), 'stage': self.bridge.state.stage,
                'visible': self.bridge.view.get('visible'), 'collapsed': self.bridge.collapsed,
                'rss_mb': round(self.process.memory_info().rss / 2**20, 1),
                'cpu_percent': round(self.process.cpu_percent(None), 2),
                'gpu_percent': self.gpu_value,
                'frames_10s': self.window_frames,
                'gap_ms_p50': round(gaps[len(gaps) // 2], 2) if gaps else None,
                'gap_ms_p99': round(gaps[int(len(gaps) * .99)], 2) if gaps else None,
                'gap_ms_max': round(gaps[-1], 2) if gaps else None,
                # A frame that took over 2.5x the median interval (and under the 100 ms idle cut-off).
                'slow_frames': sum(gap > max(2.5 * median, 12) for gap in gaps)}

    def write(self):
        row = self.snapshot()
        self.window_frames = 0; self.gaps = []
        if self.path:
            with open(self.path, 'a', encoding='utf-8') as stream:
                stream.write(json.dumps(row, ensure_ascii=False) + '\n')

    @Property(str, notify=changed)
    def text(self):
        return self._text


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--preview', action='store_true', help='模拟选人数据，不连接客户端')
    parser.add_argument('--cycle', type=float, default=0, help='预览时每隔 N 秒切换英雄')
    parser.add_argument('--hud', action='store_true', help='面板右下角显示帧数与内存')
    parser.add_argument('--metrics', metavar='FILE', help='每 10 秒写一行 JSON 指标')
    parser.add_argument('--gpu', action='store_true', help='指标中加入 GPU 占用（每 15 秒采样）')
    parser.add_argument('--grab', metavar='PNG', help='预览稳定后截取面板并退出')
    parser.add_argument('--quit-after', type=float, default=0)
    parser.add_argument('--stall-ms', type=float, default=0,
                        help='测试用：每 0.7 秒让 Python 占住主线程 N 毫秒，模拟同步的图片校验或数据处理')
    args = parser.parse_args()

    launched = time.perf_counter()
    frame_log = None
    if args.metrics or args.hud:
        import tempfile
        frame_log = Path(args.metrics).with_suffix('.frames.log') if args.metrics else Path(tempfile.gettempdir()) / 'hex-qml-frames.log'
        frame_log.parent.mkdir(parents=True, exist_ok=True)
        frame_stream = capture_frame_log(frame_log)
    if not args.preview and not single_instance():
        print('海克斯随行已在运行，请先退出 Tk 版本或另一个样例。')
        return 1
    seed = ROOT / 'data'
    if args.preview:
        preview_root = ROOT / '.build-cache/strict-ui-preview'
        store = DataStore(preview_root if preview_root.is_dir() else seed, seed_root=seed)
    elif getattr(sys, 'frozen', False):
        local = Path(os.environ.get('LOCALAPPDATA', Path.home() / 'AppData' / 'Local'))
        store = DataStore(local / 'HexCompanion' / 'data', seed_root=seed)
    else:
        store = DataStore(seed)
    from aram_demo.runtime_log import configure
    configure(store.root)
    log = logging.getLogger('aram_demo.qml_spike')

    app = QGuiApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    icon = ROOT / 'packaging/hex-companion.ico'
    if icon.is_file():
        app.setWindowIcon(QIcon(str(icon)))
    bridge = Bridge(store, preview=args.preview, services=not args.grab)
    metrics = Metrics(args.metrics, bridge, frame_log, gpu=args.gpu) if frame_log else None
    engine = QQmlApplicationEngine()
    engine.rootContext().setContextProperty('bridge', bridge)
    engine.rootContext().setContextProperty('hud', metrics if args.hud else None)
    engine.load(QUrl.fromLocalFile(str(ROOT / 'qml_spike' / 'qml' / 'Main.qml')))
    if not engine.rootObjects():
        log.error('QML failed to load')
        return 2
    panel = next(w for w in QGuiApplication.topLevelWindows() if w.objectName() == 'panelWindow')
    if metrics:
        metrics.attach(panel)
    first = {}
    def first_frame():
        if not first:
            first['s'] = time.perf_counter() - launched
            log.info('first frame %.3fs api=%s', first['s'], QQuickWindow.graphicsApi().name)
            panel.frameSwapped.disconnect(first_frame)
    panel.frameSwapped.connect(first_frame, Qt.QueuedConnection)
    bridge.start()
    if not args.preview and not args.grab:
        import ctypes
        admin = os.name == 'nt' and bool(ctypes.windll.shell32.IsUserAnAdmin())
        print('QML 样例已启动，等待海克斯大乱斗。关闭此终端或按 Ctrl+C 退出。', flush=True)
        if not admin:
            print('提示：当前不是管理员权限，可能读不到以管理员运行的联盟客户端。', flush=True)
    if args.preview and args.cycle:
        bridge.preview_timer.start(int(args.cycle * 1000))
    if args.stall_ms:
        def stall():
            end = time.perf_counter() + args.stall_ms / 1000
            while time.perf_counter() < end:   # busy work keeps the GIL, like PIL validation would
                pass
        staller = QTimer(); staller.timeout.connect(stall); staller.start(700)
    if args.grab:
        def grab():
            panel.grabWindow().save(args.grab)
            app.quit()
        QTimer.singleShot(1800, grab)
    if args.quit_after:
        QTimer.singleShot(int(args.quit_after * 1000), app.quit)
    app.aboutToQuit.connect(bridge.stop)
    # Qt's loop blocks Python signal handling; a short timer lets Ctrl+C reach the handler.
    import signal
    signal.signal(signal.SIGINT, lambda *_: app.quit())
    wake = QTimer(); wake.timeout.connect(lambda: None); wake.start(250)
    if metrics and args.metrics:
        app.aboutToQuit.connect(metrics.write)
    code = app.exec()
    del engine
    return code


if __name__ == '__main__':
    sys.exit(main())
