"""Render native windows and exercise overflow, settings and pointer scrolling."""
import ctypes
import json
import os
import sys
import tempfile
import time
import tkinter as tk
from pathlib import Path
from tkinter import ttk

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from PIL import ImageGrab
from aram_demo.cache import DataStore
from aram_demo.companion import CompanionApp
from aram_demo.lcu import ClientState
from aram_demo.models import Champion
from aram_demo.theme import BG, MUTED, SURFACE, TEXT, GRADES, GRADE_BACKGROUNDS
from aram_demo.windows import LeagueWindow

if os.name == 'nt':
    ctypes.windll.shcore.SetProcessDpiAwareness(1)


def settle(root):
    for _ in range(6):
        root.update()
        time.sleep(.04)


def descendants(widget):
    for child in widget.winfo_children():
        yield child
        yield from descendants(child)


def contrast(first, second):
    def luminance(color):
        channels = [int(color[i:i + 2], 16) / 255 for i in (1, 3, 5)]
        channels = [c / 12.92 if c <= .04045 else ((c + .055) / 1.055) ** 2.4 for c in channels]
        return sum(c * weight for c, weight in zip(channels, (.2126, .7152, .0722)))
    light, dark = sorted((luminance(first), luminance(second)), reverse=True)
    return (light + .05) / (dark + .05)


def capture(widget, name):
    widget.lift()
    widget.focus_force()
    settle(widget)
    x, y = widget.winfo_rootx(), widget.winfo_rooty()
    picture = ImageGrab.grab(bbox=(x, y, x + widget.winfo_width(), y + widget.winfo_height()))
    expected = tuple(int(BG[i:i + 2], 16) for i in (1, 3, 5))
    assert picture.getpixel((10, 10))[:3] == expected, 'Screenshot must show our foreground window'
    picture.save(ROOT / 'artifacts' / name)


with tempfile.TemporaryDirectory(dir=ROOT / 'tests') as temporary:
    root = tk.Tk()
    app = CompanionApp(root, DataStore(ROOT / 'data'), preview=True, services=False)
    # Reads real snapshots; all settings writes stay in a temporary store.
    try:
        app.preview_next()
        app.preview_next()
        app.store = DataStore(Path(temporary))
        app.show_settings()
        settle(root)
        capture(app.dialog, 'companion_settings.png')
        notebook = next(w for w in descendants(app.dialog) if isinstance(w, ttk.Notebook))
        notebook.select(1)
        settle(root)
        capture(app.dialog, 'companion_settings_advanced.png')
        buttons = [w for w in descendants(app.dialog) if isinstance(w, tk.Button)]
        for control in buttons:
            if control.cget('text') in ('取消', '保存并应用'):
                assert control.winfo_ismapped()
                assert control.winfo_rooty() + control.winfo_height() <= app.dialog.winfo_rooty() + app.dialog.winfo_height()
        next(w for w in buttons if w.cget('text') == '保存并应用').invoke()
        assert app.store.read('settings.json')['auto_recognize'] is True
        assert not app.dialog.winfo_exists()

        app.locate = lambda: LeagueWindow(0, (200, 40, 1000, 540), (0, 0, 1400, 580), True)
        app.panel.signature = None
        app.present()
        settle(root)
        assert app.panel.window.winfo_height() <= 556
        assert app.panel.content.scroll.winfo_ismapped()
        app.panel.content.canvas.yview_moveto(1)
        settle(root)
        assert app.panel.content.canvas.yview()[1] >= .999
        capture(app.panel.window, 'companion_game_small.png')

        long_name = '这是用于检查长名称完整换行的候选英雄'
        app.champions[99998] = Champion(99998, long_name, 'test', 1, 1)
        app.champions[99997] = Champion(99997, '档位暂缺的英雄', 'test-unknown', None, None)
        app.on_client_state(ClientState('ChampSelect', 222, [99998, 99997] + list(app.champions)[:18] + [99999], queue_id=2400))
        settle(root)
        assert long_name in app.panel.content_text() and '未知档位' in app.panel.content_text()
        assert '暂无档位' in app.panel.content_text()
        text = next(w for w in descendants(app.panel.content.body) if isinstance(w, tk.Label) and w.cget('text') == long_name)
        before = app.panel.content.canvas.yview()
        text.event_generate('<MouseWheel>', delta=-120)
        settle(root)
        assert app.panel.content.canvas.yview()[0] > before[0], 'Wheel over row text must scroll the list'
        assert text.winfo_reqwidth() <= text.winfo_width() + 2, 'Long name must wrap inside actual allocated width'

        pairs = [(TEXT, BG), (MUTED, BG), (TEXT, SURFACE), (MUTED, SURFACE)] + list(zip(GRADES, GRADE_BACKGROUNDS))
        ratios = [round(contrast(a, b), 2) for a, b in pairs]
        assert min(ratios) >= 4.5, ratios
        report = {'status': 'passed', 'contrast_min': min(ratios),
                  'checks': ['settings_save', 'two_settings_tabs', 'small_work_area_scroll',
                             'long_name_wrap', 'wheel_over_row', 'unknown_candidate', 'text_contrast'],
                  'real_game_tested': False}
        (ROOT / 'artifacts' / 'ui_polish_result.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
        print(json.dumps(report))
    finally:
        app.close()
