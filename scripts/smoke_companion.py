"""Actual small-window lifecycle check, using simulated LCU states."""
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
from aram_demo.companion import CompanionApp
from aram_demo.lcu import ClientState
from aram_demo.windows import _user32, find_league_window

if os.name == 'nt':
    ctypes.windll.shcore.SetProcessDpiAwareness(1)
out = ROOT / 'artifacts'
root = tk.Tk()
app = CompanionApp(root, DataStore(ROOT / 'data'), preview=True, services=False)

def settle():
    for _ in range(8):
        root.update()
        time.sleep(.06)

def screenshot(name):
    win = app.panel.window
    settle()
    assert win.winfo_width() == 304
    x, y = win.winfo_rootx(), win.winfo_rooty()
    ImageGrab.grab(bbox=(x, y, x + win.winfo_width(), y + win.winfo_height())).save(out / name)

def check_labels(widget):
    for child in widget.winfo_children():
        if isinstance(child, tk.Label) and str(child.cget('text')) in core_names:
            assert child.winfo_ismapped(), 'Build label not visible'
            assert child.winfo_height() >= child.winfo_reqheight(), 'Build text squeezed inside label'
            assert child.winfo_rooty() + child.winfo_height() <= app.panel.window.winfo_rooty() + app.panel.window.winfo_height(), 'Build label clipped'
            viewport = app.panel.content.canvas
            assert child.winfo_rooty() + child.winfo_height() <= viewport.winfo_rooty() + viewport.winfo_height(), 'Build label outside visible content area'
        check_labels(child)

try:
    settle()
    assert root.state() == 'withdrawn' and not app.panel.visible
    app.on_client_state(ClientState('Lobby', queue_id=450))
    assert not app.panel.visible
    before = _user32().GetForegroundWindow() if os.name == 'nt' else None
    app.preview_next()
    screenshot('companion_select.png')
    assert '查看局内预览' in app.panel.content_text(), 'Preview action should name its destination'
    if os.name == 'nt':
        assert _user32().GetForegroundWindow() == before, 'Automatic popup stole foreground focus'
    assert '德玛西亚之力' in app.panel.content_text()
    app.preview_next()
    screenshot('companion_game.png')
    assert '查看选人预览' in app.panel.content_text(), 'Game preview should offer a clear route back'
    core_names = {item['name'] for build in app.data['builds'] if build['category'] == '核心装备'
                  for item in build['items']}
    check_labels(app.panel.inner)
    assert all(letter in app.panel.content_text() for letter in ('S', 'B', 'E'))
    app.on_client_state(ClientState('EndOfGame'))
    settle()
    assert not app.panel.visible and root.state() == 'withdrawn'
    report = {'status': 'passed', 'root_hidden': True, 'width': 304,
              'flows': ['normal_mode_hidden', 'mayhem_select', 'game_builds_and_letters', 'exit_hidden', 'no_focus_steal'],
              'actual_league_window_found': find_league_window('select') is not None, 'real_game_tested': False}
    (out / 'companion_result.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report))
finally:
    app.close()
