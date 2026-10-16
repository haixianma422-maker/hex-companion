"""Local checks for the QML spike. Writes artifacts/qml-spike/verification.json.

Runs the preview in child processes; never moves the real cursor or takes focus.
python -m qml_spike.verify [--exe dist/HexCompanionQml/HexCompanionQml.exe]
"""
import argparse
import ctypes
import json
import os
import subprocess
import sys
import time
from ctypes import wintypes
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / 'artifacts' / 'qml-spike'
user = ctypes.WinDLL('user32', use_last_error=True)
user.GetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int]; user.GetWindowLongPtrW.restype = ctypes.c_ssize_t
user.SendMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]; user.SendMessageW.restype = ctypes.c_ssize_t
user.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
user.GetForegroundWindow.restype = wintypes.HWND
user.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
user.WindowFromPoint.argtypes = [wintypes.POINT]; user.WindowFromPoint.restype = wintypes.HWND
user.GetDpiForWindow.argtypes = [wintypes.HWND]; user.GetDpiForWindow.restype = wintypes.UINT
WS_EX = {'TOPMOST': 0x8, 'TOOLWINDOW': 0x80, 'LAYERED': 0x80000, 'NOREDIRECTIONBITMAP': 0x200000, 'NOACTIVATE': 0x08000000}


def windows_of(pid):
    import psutil   # a venv python.exe is a launcher; the interpreter is its child
    try:
        pids = {pid, *(c.pid for c in psutil.Process(pid).children(recursive=True))}
    except psutil.Error:
        pids = {pid}
    found = {}
    proto = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    @proto
    def collect(hwnd, _):
        owner = wintypes.DWORD(); user.GetWindowThreadProcessId(hwnd, ctypes.byref(owner))
        if owner.value in pids:
            buffer = ctypes.create_unicode_buffer(128); user.GetWindowTextW(hwnd, buffer, 128)
            if buffer.value:
                found[buffer.value] = hwnd
        return True
    user.EnumWindows(collect, 0)
    return found


def launch(command, metrics=None, extra=(), env=None):
    args = [*command, '--preview', *extra]
    if metrics:
        metrics.unlink(missing_ok=True); args += ['--metrics', str(metrics)]
    return subprocess.Popen(args, cwd=ROOT, env={**os.environ, **(env or {})})


def wait_window(pid, title='海克斯随行 · QML 样例', timeout=30):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        hwnd = windows_of(pid).get(title)
        if hwnd and user.IsWindowVisible(hwnd):
            return hwnd
        time.sleep(.05)
    raise TimeoutError('panel window did not appear')


def rows(path):
    return [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines()] if path.is_file() else []


def click(hwnd, lx, ly, scale):
    """Post a left click at logical panel coordinates."""
    x, y = round(lx * scale), round(ly * scale)
    pos = (y << 16) | x
    user.PostMessageW(hwnd, 0x0200, 0, pos)        # WM_MOUSEMOVE
    user.PostMessageW(hwnd, 0x0201, 1, pos)        # WM_LBUTTONDOWN
    user.PostMessageW(hwnd, 0x0202, 0, pos)        # WM_LBUTTONUP


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--exe', help='packaged spike to test instead of the source')
    args = parser.parse_args()
    command = [str(ROOT / args.exe)] if args.exe else [sys.executable, '-m', 'qml_spike.main']
    OUT.mkdir(parents=True, exist_ok=True)
    # A packaged preview has no .build-cache and logs beside its bundled seed data.
    log_path = (ROOT / args.exe).parent / '_internal/data/logs/runtime.log' if args.exe else ROOT / '.build-cache/strict-ui-preview/logs/runtime.log'
    report = {'target': args.exe or 'source', 'checked_at': time.strftime('%Y-%m-%d %H:%M:%S')}

    # 1. Window behaviour, focus, clicks, idle cost.
    foreground = user.GetForegroundWindow()
    metrics = OUT / 'metrics-idle.jsonl'
    log_mark = log_path.stat().st_size if log_path.is_file() else 0
    started = time.perf_counter()
    child = launch(command, metrics)
    try:
        hwnd = wait_window(child.pid)
        report['window_visible_s'] = round(time.perf_counter() - started, 3)
        time.sleep(1.0)
        style = user.GetWindowLongPtrW(hwnd, -20)
        report['ex_style'] = {name: bool(style & bit) for name, bit in WS_EX.items()}
        report['mouse_activate'] = {3: 'MA_NOACTIVATE', 1: 'MA_ACTIVATE'}.get(
            user.SendMessageW(hwnd, 0x0021, hwnd, (0x0201 << 16) | 1), 'other')
        report['foreground_unchanged'] = user.GetForegroundWindow() == foreground
        scale = user.GetDpiForWindow(hwnd) / 96
        rect = wintypes.RECT(); user.GetWindowRect(hwnd, ctypes.byref(rect))
        report['window_px'] = [rect.right - rect.left, rect.bottom - rect.top]
        report['dpi_scale'] = scale
        # System hit testing on the layered window: transparent pixels should fall through.
        mid_x, mid_y = (rect.left + rect.right) // 2, (rect.top + rect.bottom) // 2
        probes = {'shadow_left': (rect.left - round(6 * scale), mid_y), 'shadow_below': (mid_x, rect.bottom + round(6 * scale)),
                  'rounded_corner': (rect.left, rect.top), 'panel_edge': (rect.left + 2, mid_y), 'panel_center': (mid_x, mid_y)}
        report['click_target'] = {name: ('panel' if user.WindowFromPoint(wintypes.POINT(*point)) == hwnd else 'below')
                                  for name, point in probes.items()}
        time.sleep(23)                          # idle: nothing should be drawn
        idle = rows(metrics)
        click(hwnd, 12 + 168 + 80, 284 + 30, scale)   # second candidate card
        time.sleep(1.5)
        report['foreground_after_click'] = user.GetForegroundWindow() == foreground
        # log_mark is a byte offset; the log holds Chinese text, so slice bytes before decoding.
        text = log_path.read_bytes()[log_mark:].decode('utf-8', 'replace') if log_path.is_file() else ''
        report['posted_click_reached_card'] = 'candidate clicked' in text
        first = [line for line in text.splitlines() if 'first frame' in line]
        report['first_frame_log'] = first[-1].split('INFO aram_demo.qml_spike ')[-1] if first else None
        report['idle_rows'] = idle
    finally:
        child.terminate(); child.wait(10)

    # 2. Continuous hero switching: frame pacing and cost while animating.
    metrics = OUT / 'metrics-cycle.jsonl'
    child = launch(command, metrics, ['--cycle', '0.6'])
    try:
        wait_window(child.pid)
        time.sleep(21)
    finally:
        child.terminate(); child.wait(10)
    report['cycle_rows'] = rows(metrics)

    # 3. Logical DPI renders.
    shots = {}
    for factor in ('1', '1.25', '1.5', '2'):
        png = OUT / f'panel-{factor}x.png'
        png.unlink(missing_ok=True)
        subprocess.run([*command, '--preview', '--grab', str(png)], cwd=ROOT, timeout=60,
                       env={**os.environ, 'QT_SCALE_FACTOR': factor})
        if png.is_file():
            from PySide6.QtGui import QImage
            image = QImage(str(png)); shots[factor] = [image.width(), image.height()]
    report['grabs'] = shots

    path = OUT / ('verification-exe.json' if args.exe else 'verification.json')
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({k: v for k, v in report.items() if not k.endswith('_rows')}, ensure_ascii=False, indent=2))
    for name in ('idle_rows', 'cycle_rows'):
        print(name, json.dumps(report[name], ensure_ascii=False))


if __name__ == '__main__':
    main()
