"""Controlled offline acceptance for the distributed executable, not a game test."""
import ctypes
import json
import os
import sys
import tempfile
import time
import traceback
from pathlib import Path
from unittest.mock import patch


def run(report_path):
    report_path = Path(report_path).resolve()
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report = {'status': 'failed', 'frozen': bool(getattr(sys, 'frozen', False)),
              'live_game_tested': False, 'network_allowed': False}
    app = None
    try:
        import tkinter as tk
        from PIL import Image, ImageDraw, ImageFont
        from aram_demo.cache import DataStore
        from aram_demo.companion import CompanionApp
        from aram_demo.lcu import ClientState
        from aram_demo.models import Augment
        from aram_demo.recognition import Recognizer
        seed = Path(__file__).resolve().parents[1] / 'data'
        if os.name == 'nt':
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        with tempfile.TemporaryDirectory(dir=report_path.parent) as directory, \
             patch('socket.socket.connect', side_effect=AssertionError('Offline check attempted network')):
            store = DataStore(Path(directory) / 'data', seed_root=seed)
            assert store.read('settings.json') is None
            assert len(store.champions()) > 100
            data = store.hero(222)
            assert data['build_mode_verified'] and data['build_mode'] == 'aram-mayhem'
            names = ['暴击飞弹', '魔法飞弹', '双刀流']
            image = Image.new('RGB', (1500, 600), '#0d1524')
            draw = ImageDraw.Draw(image)
            font = ImageFont.truetype(str(Path(os.environ.get('WINDIR', 'C:/Windows')) / 'Fonts/msyh.ttc'), 32)
            for index, name in enumerate(names):
                draw.text((index * 500 + 50, 205), name, font=font, fill='white')
            regions = [(.02, .3, .32, .5), (.35, .3, .65, .5), (.68, .3, .98, .5)]
            matches = Recognizer(regions).read_screen(image, [Augment(**row) for row in data['augments']])
            report['ocr'] = [{'text': m.text, 'augment_id': m.augment_id, 'status': m.status} for m in matches]
            assert [m.augment_id for m in matches] == [1356, 1133, 1225], f'OCR mismatch: {report["ocr"]}'
            assert all(m.status == 'matched' for m in matches)
            root = tk.Tk()
            app = CompanionApp(root, store, preview=True)
            deadline = time.monotonic() + 5
            while not app.tray.icon.visible and time.monotonic() < deadline:
                root.update()
                time.sleep(.05)
            assert app.tray.icon.visible
            app.on_client_state(ClientState('InProgress', 222, queue_id=3270))
            app.accept_matches(matches)
            root.update()
            assert app.panel.visible and root.state() == 'withdrawn'
            assert len(app.panel.build_views) == 4
            assert all(getattr(icon, 'picture', None) is not icon.placeholder for icon in app.panel.icon_views), 'Bundled item icons missing'
            app.hide()
            root.update()
            assert app.bubble.visible and not app.panel.visible
            app.expand()
            root.update()
            assert app.panel.visible and not app.bubble.visible
            custom = {'scan': 'Ctrl+Alt+F10', 'refresh': 'Ctrl+Alt+F11', 'toggle': 'Ctrl+Alt+F12'}
            app.hotkeys.configure(custom)
            assert app.hotkeys.bindings == custom and len(app.hotkeys.registered) == 3
            ctypes.windll.user32.PostThreadMessageW(app.hotkeys.thread.native_id, 0x0312, 3, 0)
            deadline = time.monotonic() + 2
            while not app.collapsed and time.monotonic() < deadline:
                root.update()
                time.sleep(.02)
            assert app.collapsed and app.bubble.visible
            ctypes.windll.user32.PostThreadMessageW(app.hotkeys.thread.native_id, 0x0312, 3, 0)
            deadline = time.monotonic() + 2
            while app.collapsed and time.monotonic() < deadline:
                root.update()
                time.sleep(.02)
            assert app.panel.visible and not app.bubble.visible
            store._write('settings.json', {'auto_recognize': False, 'hotkeys': custom})
            assert store.read('settings.json')['hotkeys'] == custom
            report.update(status='passed', champions=len(store.champions()),
                          ocr=[{'text': m.text, 'augment_id': m.augment_id} for m in matches],
                          mayhem_build_verified=True, tray_visible=True,
                          hotkeys=app.hotkeys.status, native_hotkey_toggle=True, item_icons=4, source_build_slots=4, panel_bubble_toggle=True,
                          writable_cache_and_settings=True, tcl_version=root.tk.call('info', 'patchlevel'))
            app.close()
            assert not app.tray.icon.visible
            report['clean_exit'] = True
            app = None
    except Exception:
        report['error'] = traceback.format_exc()
    finally:
        if app is not None:
            app.close()
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    return 0 if report['status'] == 'passed' else 1
