"""Native popup interaction and capture lifecycle without connecting to League."""
import ctypes
import json
import os
import sys
import time
import tkinter as tk
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from PIL import ImageGrab
from aram_demo.cache import DataStore
from aram_demo.companion import CompanionApp
from aram_demo.lcu import ClientState
from aram_demo.recognition import match_slots
from aram_demo.windows import LeagueWindow, _user32

if os.name == 'nt':
    ctypes.windll.shcore.SetProcessDpiAwareness(1)
root = tk.Tk()
app = CompanionApp(root, DataStore(ROOT / 'data'), preview=True, services=False)
out = ROOT / 'artifacts'


def settle():
    for _ in range(4):
        root.update()
        time.sleep(.03)


try:
    width, height = root.winfo_screenwidth(), root.winfo_screenheight()
    anchor = LeagueWindow(0, (40, 80, width-350, height-100), (0, 0, width, height-48), True)
    app.locate = lambda: anchor
    app.panel.on_preview = None
    app.on_client_state(ClientState('InProgress', 222, queue_id=3270))
    matches = match_slots(['暴击飞弹', '魔法飞弹', '纯粹主义者 - 术师'], app.augments)
    app.accept_matches(matches)
    app.preview = False
    app.present()
    settle()
    content = app.panel.content
    def descendants(widget):
        return tuple(child for node in widget.winfo_children()
                     for child in (node, *descendants(node)))
    widgets = descendants(app.panel.inner)
    slots = tuple((card.winfo_y(), card.winfo_height()) for card, *_ in app.panel.augment_views)
    geometry = app.panel.window.geometry()
    button_appearance = tuple(app.panel.scan_button.cget(key) for key in ('text', 'bg', 'fg', 'state'))
    unmaps = []
    destroyed = []
    app.panel.window.bind('<Unmap>', lambda event: unmaps.append(event.widget)
                          if event.widget == app.panel.window else None, add='+')
    app.panel.window.bind('<Destroy>', lambda event: destroyed.append(str(event.widget)), add='+')

    # Use real screen capture and popup mapping; isolate OCR execution so this
    # verifies the visibility cycle separately from OCR accuracy.
    def background(job, callback, ticket=None, done=None):
        result = job()
        if done:
            done()
        app.deliver(ticket, callback, result, None)

    app.background = background
    before = _user32().GetForegroundWindow() if os.name == 'nt' else None
    alternatives = [matches,
                    match_slots(['穿针引线', '急急小子', '威能之追求'], app.augments),
                    match_slots(['科学狂人', '质变：混沌', '尊我为王'], app.augments),
                    match_slots(['未识别的长名称需要保留两行空间', '', '未知海克斯'], app.augments)]
    expected_names = set()
    with patch('aram_demo.companion.find_league_window', return_value=anchor), \
         patch.object(app.recognizer, 'read_screen') as ocr:
        for index in range(10):
            ocr.return_value = alternatives[index % len(alternatives)]
            app.scan()
            settle()
            assert app.panel.window.state() == 'normal'
            assert app.panel.content is content, 'New grades must preserve the content widgets'
            assert descendants(app.panel.inner) == widgets, 'Content widgets were replaced'
            assert app.panel.window.geometry() == geometry, 'Popup geometry changed'
            assert tuple(app.panel.scan_button.cget(key) for key in ('text', 'bg', 'fg', 'state')) == button_appearance
            assert tuple((card.winfo_y(), card.winfo_height()) for card, *_ in app.panel.augment_views) == slots
            expected_names.add(app.panel.augment_views[0][2].cget('text'))
        assert ocr.call_count == 10
    assert len(expected_names) >= 4, 'Recognition results did not actually change'
    assert not unmaps, 'Capture must not withdraw the popup'
    assert not destroyed, 'Capture must not destroy any widgets'
    capture_unmaps = len(unmaps)
    assert before == (_user32().GetForegroundWindow() if os.name == 'nt' else None), 'Scan stole focus'
    app.hide()
    settle()
    assert app.bubble.visible and not app.panel.visible
    bubble = app.bubble
    x, y = bubble.position
    ImageGrab.grab(bbox=(x-8, y-8, x+56, y+56)).save(out / 'companion_bubble.png')
    start = bubble.position
    canvas = bubble.canvas
    canvas.event_generate('<ButtonPress-1>', x=24, y=24, rootx=x+24, rooty=y+24)
    canvas.event_generate('<B1-Motion>', x=24, y=24, rootx=x-96, rooty=y+104)
    canvas.event_generate('<ButtonRelease-1>', x=24, y=24, rootx=x-96, rooty=y+104)
    settle()
    assert bubble.visible and bubble.position != start
    moved = bubble.position
    app.present()
    assert bubble.position == moved
    canvas.event_generate('<ButtonPress-1>', x=24, y=24)
    canvas.event_generate('<ButtonRelease-1>', x=24, y=24)
    settle()
    assert not bubble.visible and app.panel.visible
    app.on_client_state(ClientState('Lobby', queue_id=450))
    settle()
    assert not bubble.visible and not app.panel.visible
    report = {'status': 'passed', 'capture_cycles': 10, 'panel_unmaps_during_capture': capture_unmaps,
              'content_widgets_preserved': True, 'changed_result_sets': len(expected_names),
              'widgets_destroyed_during_capture': 0, 'geometry_and_slot_heights_preserved': True,
              'bubble_size': bubble.size,
              'checks': ['click_expand', 'drag_without_expand', 'position_retained', 'no_focus_steal', 'exit_hidden'],
              'ocr_accuracy_tested': False, 'live_game_tested': False}
    (out / 'companion_interaction_result.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report))
finally:
    app.close()
