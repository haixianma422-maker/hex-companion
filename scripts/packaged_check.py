"""Controlled offline acceptance for the distributed executable, not a game test."""
import ctypes
import json
import os
import sys
import tempfile
import time
import traceback
import hashlib
from types import SimpleNamespace
from pathlib import Path
from unittest.mock import patch


def run(report_path):
    report_path = Path(report_path).resolve()
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report = {'status': 'failed', 'frozen': bool(getattr(sys, 'frozen', False)),
              'live_game_tested': False, 'network_allowed': False}
    if report['frozen']:
        report['executable']=str(Path(sys.executable).resolve())
        with Path(sys.executable).open('rb') as stream:
            report['exe_sha256']=hashlib.file_digest(stream,'sha256').hexdigest()
    app = None
    try:
        import tkinter as tk
        from PIL import Image, ImageDraw, ImageFont
        from aram_demo.cache import DataStore
        from aram_demo.companion import CompanionApp
        from aram_demo.lcu import ClientState
        from aram_demo.models import Augment
        from aram_demo.recognition import Recognizer
        from aram_demo.recognition import match_slots
        from aram_demo.builds import recommended_items
        seed = Path(__file__).resolve().parents[1] / 'data'
        if os.name == 'nt':
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        with tempfile.TemporaryDirectory(dir=report_path.parent) as directory, \
             patch('socket.socket.connect', side_effect=AssertionError('Offline check attempted network')):
            store = DataStore(Path(directory) / 'data', seed_root=seed)
            assert store.read('settings.json') is None
            assert len(store.champions()) > 100
            inventory=json.loads((seed/'visual-assets/resource-cache-manifest.json').read_text(encoding='utf-8'))
            for asset in inventory['assets']:
                assert asset['cached'], f'Missing cached resource: {asset["key"]}'
                path=(seed/asset['path']).resolve()
                path.relative_to(seed.resolve())
                assert hashlib.sha256(path.read_bytes()).hexdigest()==asset['sha256'], f'Resource hash mismatch: {asset["key"]}'
            report['verified_cached_resources']=len(inventory['assets'])
            custom = {'scan': 'Ctrl+Alt+F10', 'refresh': 'Ctrl+Alt+F11', 'toggle': 'Ctrl+Alt+F12'}
            store._write('settings.json',{'hotkeys':custom,'animations':False})
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
            callback_errors=[]
            root.report_callback_exception=lambda kind,value,tb:callback_errors.append(''.join(traceback.format_exception(kind,value,tb)))
            app = CompanionApp(root, store, preview=True)
            deadline = time.monotonic() + 5
            while not app.tray.icon.visible and time.monotonic() < deadline:
                root.update()
                time.sleep(.05)
            assert app.tray.icon.visible
            candidates=[hero.id for hero in store.champions()][:16]
            app.on_client_state(ClientState('ChampSelect', 101, candidates, queue_id=3270))
            root.update()
            selection = app.panel.content_text()
            assert '技能优先级' not in selection
            assert '召唤师技能' in selection
            spells=app.data['summoner_spells']
            assert len(spells)==2 and all(app.panel.assets_shown.get(('spell',spell['id'])) for spell in spells)
            assert app.panel.assets_shown.get(('splash',101))
            assert app.panel.source_picker.winfo_ismapped()
            app.panel.motion.enabled=True
            app.panel._wheel(SimpleNamespace(x=100*app.panel.scale,y=340*app.panel.scale,delta=-120))
            deadline=time.monotonic()+2
            while 'candidate-scroll' in app.panel.motion.jobs and time.monotonic()<deadline:
                root.update();time.sleep(.01)
            assert app.panel.candidate_scroll==32
            app.panel.set_motion(False)
            report['smooth_candidate_scroll']=True
            app.on_client_state(ClientState('InProgress', 101, queue_id=3270))
            app.accept_matches(match_slots(['虚幻武器','巫师式思考','有始有终'],app.augments))
            root.update()
            assert app.panel.visible and root.state() == 'withdrawn'
            gameplay = app.panel.content_text()
            priority=app.data['skill_priority']
            assert f'主 {priority[0]} › 副 {priority[1]}' in gameplay and '召唤师技能' not in gameplay
            assert all(app.panel.assets_shown.get(('skill',key)) for key in priority)
            assert app.panel.source_picker.winfo_ismapped()
            items=recommended_items(app.data)
            assert len(items)==4 and all(app.panel.assets_shown.get(('item',item['id'])) for item in items), 'Bundled item icons missing'
            for source in ('qq101','opgg','qq101'):
                app.change_source(source);root.update()
                assert app.data and app.data.get('source_id')==source
                assert app.data.get('champion_id')==101
                app.accept_matches(match_slots(['虚幻武器','巫师式思考','有始有终'],app.augments))
                assert all(app.panel.assets_shown.get(('augment',aid)) for aid in (1029,1097,1038))
            report['offline_source_switch']=True
            report['reported_images_visible']=True
            app.panel.set_motion(True)
            app.bubble.set_motion(True)
            app.panel.set_zoom(1.1)
            root.update()
            assert app.panel.window.winfo_width()==round(360*app.panel.scale)
            assert app.panel.scan_button.scale==app.panel.scale
            app.panel.on_resize(app.panel.zoom)
            assert store.read('settings.json')['panel_zoom']==app.panel.zoom
            report['native_resize_and_persistence']=True
            app.hide()
            root.update()
            assert app.bubble.visible and not app.panel.visible
            app.expand()
            deadline=time.monotonic()+3
            while (app.panel.motion.jobs or app.bubble.motion.jobs) and time.monotonic()<deadline:
                root.update();time.sleep(.01)
            assert app.panel.visible and not app.bubble.visible
            assert not app.panel.motion.jobs and not app.bubble.motion.jobs
            assert float(app.panel.window.attributes('-alpha'))==1.
            report['native_visibility_cleanup']=True
            app.panel.set_motion(False);app.bubble.set_motion(False)
            app.show_settings();root.update()
            from aram_demo.ui_widgets import PixelButton
            apply=next(w for w in app.dialog.winfo_children() if isinstance(w,PixelButton) and w.text=='保存并应用')
            apply.invoke()
            assert apply.text=='已应用' and app.dialog.winfo_exists()
            app.dialog.destroy();root.update()
            report['native_save_feedback']=True
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
            assert not callback_errors, '\n'.join(callback_errors)
            report.update(champions=len(store.champions()),
                          ocr=[{'text': m.text, 'augment_id': m.augment_id} for m in matches],
                          mayhem_build_verified=True, tray_visible=True,
                          hotkeys=app.hotkeys.status, native_hotkey_toggle=True, item_icons=4, source_build_slots=4, panel_bubble_toggle=True,
                          writable_cache_and_settings=True, tcl_version=root.tk.call('info', 'patchlevel'))
            report['skill_priority_visible'] = True
            report['skill_priority_game_only'] = True
            report['summoner_spells_select_only'] = True
            app.close()
            # pystray's Win32 backend removes the native icon/window at loop
            # shutdown without resetting its cached `visible` property.
            assert not app.tray.thread.is_alive(), 'Tray message loop still running'
            assert not ctypes.windll.user32.IsWindow(app.tray.icon._hwnd), 'Tray window still exists'
            report['clean_exit'] = True
            app = None
            report['status'] = 'passed'
    except Exception:
        report['status'] = 'failed'
        report['error'] = traceback.format_exc()
    finally:
        if app is not None:
            app.close()
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    return 0 if report['status'] == 'passed' else 1
