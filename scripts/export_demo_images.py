"""Capture real app widgets with simulated match state and no personal settings."""
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
from aram_demo.theme import BG

if os.name == 'nt':
    ctypes.windll.shcore.SetProcessDpiAwareness(1)
out = ROOT / 'docs/images'
out.mkdir(parents=True, exist_ok=True)

def settle(root):
    for _ in range(8):
        root.update()
        time.sleep(.04)

with tempfile.TemporaryDirectory(dir=ROOT / '.build-cache') as folder:
    root = tk.Tk()
    backdrop = tk.Toplevel(root)
    backdrop.overrideredirect(True)
    backdrop.configure(bg=BG)
    backdrop.attributes('-topmost', True)
    backdrop.geometry('600x900+20+20')
    app = CompanionApp(root, DataStore(Path(folder), seed_root=ROOT / 'data'), preview=True, services=False)
    def capture(widget, name):
        settle(root)
        x, y = widget.winfo_rootx(), widget.winfo_rooty()
        w, h = widget.winfo_width(), widget.winfo_height()
        backdrop.geometry(f'{w+24}x{h+24}{x-12:+d}{y-12:+d}')
        backdrop.lift()
        widget.lift()
        widget.focus_force()
        settle(root)
        ImageGrab.grab(bbox=(x, y, x+w, y+h)).save(out / name)
    try:
        app.preview_next()
        capture(app.panel.window, 'champion-select.png')
        app.preview_next()
        assert len(app.panel.build_views) == 4
        assert all(getattr(icon, 'picture', None) is not icon.placeholder for icon in app.panel.icon_views)
        capture(app.panel.window, 'in-game.png')
        app.hide()
        capture(app.bubble.window, 'collapsed-bubble.png')
        app.expand()
        app.show_settings()
        def descendants(widget):
            for child in widget.winfo_children():
                yield child
                yield from descendants(child)
        notebook = next(widget for widget in descendants(app.dialog) if isinstance(widget, ttk.Notebook))
        notebook.select(2)
        capture(app.dialog, 'hotkey-settings.png')
        print(json.dumps({'status': 'passed', 'simulated_match': True, 'source': 'native_app_widgets',
                          'equipment_icons': 4, 'images': sorted(path.name for path in out.glob('*.png'))}))
    finally:
        backdrop.destroy()
        app.close()
