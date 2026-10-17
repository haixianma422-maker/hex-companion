"""Native window checks for the Qt overlay, run against the preview (source or EXE).

Never moves the real cursor or takes focus: clicks are posted window messages.
Writes artifacts/overlay/verification.json and panel screenshots at three scale factors.
python scripts/verify_overlay.py [--exe dist/HexCompanion/HexCompanion.exe]
"""
import argparse
import ctypes
import json
import os
import re
import subprocess
import sys
import threading
import time
from ctypes import wintypes
from pathlib import Path

import psutil
from PIL import ImageGrab

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'artifacts' / 'overlay'
PANEL, BUBBLE = '海克斯随行 · 伴随浮窗', '海克斯随行 · 浮标'
WS_EX = {'TOPMOST': 0x8, 'TOOLWINDOW': 0x80, 'NOACTIVATE': 0x08000000, 'TRANSPARENT': 0x20}
user = ctypes.WinDLL('user32', use_last_error=True)
user.GetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int]; user.GetWindowLongPtrW.restype = ctypes.c_ssize_t
user.SendMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]; user.SendMessageW.restype = ctypes.c_ssize_t
user.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
user.GetForegroundWindow.restype = wintypes.HWND
user.WindowFromPoint.argtypes = [wintypes.POINT]; user.WindowFromPoint.restype = wintypes.HWND
user.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
user.GetDpiForWindow.argtypes = [wintypes.HWND]; user.GetDpiForWindow.restype = wintypes.UINT


def windows_of(pid):
    try:   # a venv python.exe is a launcher; the interpreter is its child
        pids = {pid, *(child.pid for child in psutil.Process(pid).children(recursive=True))}
    except psutil.Error:
        pids = {pid}
    found = {}
    proto = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    @proto
    def collect(hwnd, _):
        owner = wintypes.DWORD(); user.GetWindowThreadProcessId(hwnd, ctypes.byref(owner))
        if owner.value in pids and user.IsWindowVisible(hwnd):
            buffer = ctypes.create_unicode_buffer(128); user.GetWindowTextW(hwnd, buffer, 128)
            found[buffer.value] = hwnd
        return True
    user.EnumWindows(collect, 0)
    return found


def wait_for(pid, title, timeout=40):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        hwnd = windows_of(pid).get(title)
        if hwnd:
            return hwnd
        time.sleep(.05)
    raise TimeoutError(f'{title} did not appear')


def rect(hwnd):
    r = wintypes.RECT(); user.GetWindowRect(hwnd, ctypes.byref(r))
    return r.left, r.top, r.right, r.bottom


def launch(command, env=None, frames=None):
    environment = {**os.environ, **(env or {})}
    if frames is not None:
        # Qt times frames on its render thread; the log costs the app no Python work.
        environment.update(QSG_RENDER_TIMING='1', QT_FORCE_STDERR_LOGGING='1', QT_MESSAGE_PATTERN='%{time process}|%{message}')
    child = subprocess.Popen([*command, '--preview'], cwd=ROOT, env=environment,
                             stderr=subprocess.PIPE if frames is not None else None)
    if frames is not None:
        def read():
            for line in iter(child.stderr.readline, b''):
                text = line.decode('utf-8', 'replace')
                if 'frame rendered in' in text:
                    frames.append(float(text.split('|', 1)[0]))
        threading.Thread(target=read, daemon=True).start()
    return child


def stop(child):
    try:
        for process in psutil.Process(child.pid).children(recursive=True):
            process.kill()
    except psutil.Error:
        pass
    child.kill(); child.wait(10)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--exe', help='packaged HexCompanion.exe; defaults to app.py from this checkout')
    args = parser.parse_args()
    command = [str(Path(args.exe).resolve())] if args.exe else [sys.executable, str(ROOT / 'app.py')]
    OUT.mkdir(parents=True, exist_ok=True)
    report = {'target': args.exe or 'source', 'checked_at': time.strftime('%Y-%m-%d %H:%M:%S')}

    foreground = user.GetForegroundWindow()
    frames = [] if not args.exe else None     # a windowed EXE has no stderr to read
    started = time.perf_counter()
    child = launch(command, frames=frames)
    try:
        panel = wait_for(child.pid, PANEL)
        report['panel_visible_s'] = round(time.perf_counter() - started, 2)
        time.sleep(1.5)
        style = user.GetWindowLongPtrW(panel, -20)
        report['ex_style'] = {name: bool(style & bit) for name, bit in WS_EX.items()}
        report['mouse_activate'] = {3: 'MA_NOACTIVATE', 1: 'MA_ACTIVATE'}.get(
            user.SendMessageW(panel, 0x0021, panel, (0x0201 << 16) | 1), 'other')
        report['foreground_unchanged'] = user.GetForegroundWindow() == foreground
        scale = user.GetDpiForWindow(panel) / 96
        left, top, right, bottom = rect(panel)
        mid_x, mid_y = (left + right) // 2, (top + bottom) // 2
        probes = {'shadow_left': (left - round(6 * scale), mid_y), 'shadow_below': (mid_x, bottom + round(6 * scale)),
                  'panel_center': (mid_x, mid_y)}
        report['click_target'] = {name: 'panel' if user.WindowFromPoint(wintypes.POINT(*point)) == panel else 'below'
                                  for name, point in probes.items()}
        if frames is not None:
            mark = len(frames); time.sleep(10)
            report['idle_frames_10s'] = len(frames) - mark
        # Post a click on the collapse button (panel units 301, 18): the bubble should replace the panel.
        # The saved zoom scales the panel, so derive units from the window's actual width.
        unit = (right - left) / 360
        position = (round(18 * unit) << 16) | round(301 * unit)
        for message, wparam in ((0x0200, 0), (0x0201, 1), (0x0202, 0)):
            user.PostMessageW(panel, message, wparam, position)
        report['posted_click_collapses'] = bool(wait_for(child.pid, BUBBLE, 5))
        report['foreground_after_click'] = user.GetForegroundWindow() == foreground
    finally:
        stop(child)

    grabs = {}
    for factor in ('1', '1.5', '2'):
        child = launch(command, env={'QT_SCALE_FACTOR': factor})
        try:
            panel = wait_for(child.pid, PANEL)
            time.sleep(2)
            box = rect(panel)
            image = ImageGrab.grab(box, all_screens=True)
            image.save(OUT / f'panel-{factor}x.png')
            grabs[factor] = list(image.size)
        finally:
            stop(child)
    report['grabs'] = grabs
    path = OUT / ('verification-exe.json' if args.exe else 'verification.json')
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False, indent=2))
    ok = (report['ex_style']['NOACTIVATE'] and report['mouse_activate'] == 'MA_NOACTIVATE' and report['foreground_unchanged']
          and report['click_target'] == {'shadow_left': 'below', 'shadow_below': 'below', 'panel_center': 'panel'}
          and report['posted_click_collapses'] and report['foreground_after_click'] and report.get('idle_frames_10s', 0) == 0)
    sys.exit(0 if ok else 1)


if __name__ == '__main__':
    main()
