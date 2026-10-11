import ctypes
import json
import os
import sys
import time
import tkinter as tk
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from PIL import ImageGrab
from aram_demo.cache import DataStore
from aram_demo.ui import DemoApp

if os.name == 'nt':
    ctypes.windll.shcore.SetProcessDpiAwareness(1)
out = ROOT / 'artifacts'
out.mkdir(exist_ok=True)
root = tk.Tk()
app = DemoApp(root, DataStore(ROOT / 'data'))

def settle():
    for _ in range(8):
        root.update()
        time.sleep(0.06)

def screenshot(window, path):
    window.lift()
    settle()
    x, y = window.winfo_rootx(), window.winfo_rooty()
    ImageGrab.grab(bbox=(x, y, x + window.winfo_width(), y + window.winfo_height())).save(path)

try:
    settle()
    def widgets(widget):
        yield widget
        for child in widget.winfo_children():
            yield from widgets(child)
    scan_button = next(w for w in widgets(root) if 'text' in w.keys() and w.cget('text') == '识别屏幕  F6')
    assert scan_button.winfo_ismapped() and scan_button.winfo_height() > 10, 'Scan action not visible'
    assert scan_button.winfo_rooty() + scan_button.winfo_height() <= min(root.winfo_rooty() + root.winfo_height(), root.winfo_screenheight()), 'Scan action clipped below window'
    assert app.selected_id == 222
    assert len(app.candidates.get_children()) == 3
    app.candidates.selection_set('99')
    app.candidates.event_generate('<<TreeviewSelect>>')
    settle()
    assert app.selected_id == 99
    assert '拉克丝' in app.hero_title.get() or '光辉女郎' in app.hero_title.get()
    app.select_hero(222, False)
    assert len(app.augments) == 159
    assert '卢安娜的飓风' in app.build_text.get('1.0', 'end')
    app.card_vars[0].set('暴击飞弹')
    app.card_vars[1].set(next(a.name for a in app.augments if a.tier == 2))
    app.card_vars[2].set(next(a.name for a in app.augments if a.tier == 5))
    screenshot(root, out / 'demo_main.png')
    app.show_manual()
    settle()
    assert app.overlay.window is not None
    screenshot(app.overlay.window, out / 'demo_overlay.png')
    app.hide_overlay()
    assert app.overlay.window is None
    app.tabs.select(1)
    screenshot(root, out / 'demo_augments.png')
    report = {'status': 'passed', 'candidate_count': 3, 'jinx_augments': 159,
              'flows': ['select_candidate', 'switch_hero', 'builds', 'manual_three_cards', 'overlay_show_hide', 'augment_list'],
              'game_tested': False}
    (out / 'ui_result.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report))
finally:
    app.close()
