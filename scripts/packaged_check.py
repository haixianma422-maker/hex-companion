"""Controlled offline acceptance for the distributed executable, not a game test."""
import ctypes
import json
import os
import sys
import tempfile
import time
import traceback
import hashlib
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
    errors = []
    try:
        from PIL import Image, ImageDraw, ImageFont
        from PySide6 import __version__ as pyside_version
        from PySide6.QtCore import QObject, qVersion
        from PySide6.QtGui import QGuiApplication
        from PySide6.QtQuick import QQuickWindow
        from aram_demo.cache import DataStore
        from aram_demo.companion import CompanionApp
        from aram_demo.lcu import ClientState
        from aram_demo.models import Augment
        from aram_demo.recognition import Recognizer
        from aram_demo.recognition import match_slots
        from aram_demo.builds import recommended_items
        seed = Path(__file__).resolve().parents[1] / 'data'
        qt = QGuiApplication.instance() or QGuiApplication(sys.argv[:1])
        qt.setQuitOnLastWindowClosed(False)
        sys.excepthook = lambda kind, value, tb: errors.append(''.join(traceback.format_exception(kind, value, tb)))

        def wait(condition, seconds=5):
            deadline = time.monotonic() + seconds
            while time.monotonic() < deadline:
                qt.processEvents()
                if condition():
                    return True
                time.sleep(.01)
            return condition()

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
            # Windows OCR answered above; the bundled model must reread on its own as well.
            from aram_demo.recognition import TITLE_OCR
            report['ocr_engines'] = {'windows': TITLE_OCR._windows is not None, 'model': TITLE_OCR._model is not None}
            assert all(report['ocr_engines'].values()), f'OCR engine missing: {report["ocr_engines"]}'
            crop = image.crop((550, 180, 950, 300))
            report['model_reread'] = TITLE_OCR._model.read(crop, Recognizer(regions).title_mask(crop))
            assert report['model_reread'] == '魔法飞弹', f'Model reread mismatch: {report["model_reread"]}'
            app = CompanionApp(store, preview=True)
            assert wait(lambda: app.tray.icon.visible)
            panel_window = app.overlay.window('panelWindow')
            candidates=[hero.id for hero in store.champions()][:16]
            app.on_client_state(ClientState('ChampSelect', 101, candidates, queue_id=3270))
            assert wait(lambda: panel_window.isVisible() and not app.panel.assets.busy())
            app.present()
            selection = app.panel.content_text()
            assert '技能优先级' not in selection
            assert '召唤师技能' in selection
            spells=app.data['summoner_spells']
            assert len(spells)==2 and all(app.panel.assets_shown.get(('spell',spell['id'])) for spell in spells)
            assert app.panel.assets_shown.get(('splash',101))
            assert app.panel.view['source'] == store.source
            grid = panel_window.findChild(QObject, 'candidateGrid')
            assert wait(lambda: grid.property('count') == len(candidates))
            grid.setProperty('contentY', 64)
            assert wait(lambda: grid.property('contentY') == 64)
            report['candidate_grid_scrolls']=True
            report['graphics_api']=QQuickWindow.graphicsApi().name
            app.on_client_state(ClientState('InProgress', 101, queue_id=3270))
            app.accept_matches(match_slots(['虚幻武器','巫师式思考','有始有终'],app.augments))
            assert wait(lambda: not app.panel.assets.busy())
            app.present()
            assert app.panel.visible
            gameplay = app.panel.content_text()
            priority=app.data['skill_priority']
            assert f'主 {priority[0]} › 副 {priority[1]}' in gameplay and '召唤师技能' not in gameplay
            assert all(app.panel.assets_shown.get(('skill',key)) for key in priority)
            items=recommended_items(app.data)
            assert len(items)==4 and all(app.panel.assets_shown.get(('item',item['id'])) for item in items), 'Bundled item icons missing'
            for source in ('qq101','opgg','qq101'):
                app.change_source(source)
                assert app.data and app.data.get('source_id')==source
                assert app.data.get('champion_id')==101
                app.accept_matches(match_slots(['虚幻武器','巫师式思考','有始有终'],app.augments))
                assert wait(lambda: not app.panel.assets.busy())
                app.present()
                assert all(app.panel.assets_shown.get(('augment',aid)) for aid in (1029,1097,1038))
            report['offline_source_switch']=True
            report['reported_images_visible']=True
            app.panel.set_motion(True)
            app.bubble.set_motion(True)
            app.panel.set_zoom(1.1)
            assert app.panel.width==round(360*app.panel.ratio*1.1)
            assert wait(lambda: abs(panel_window.width() - app.panel.place['width']) < 1)
            app.panel.on_resize(app.panel.zoom)
            assert store.read('settings.json')['panel_zoom']==app.panel.zoom
            report['native_resize_and_persistence']=True
            surface = panel_window.findChild(QObject, 'panelSurface')
            app.hide()
            bubble_window = app.overlay.window('bubbleWindow')
            assert app.bubble.visible and not app.panel.visible
            assert wait(lambda: bubble_window.isVisible() and not panel_window.isVisible())
            app.expand()
            assert wait(lambda: panel_window.isVisible() and not bubble_window.isVisible()
                        and surface.property('opacity') == 1 and surface.property('scale') == 1)
            report['native_visibility_cleanup']=True
            app.panel.set_motion(False);app.bubble.set_motion(False)
            app.show_settings()
            assert wait(lambda: app.dialog.window.isVisible())
            assert app.dialog.save()
            assert app.dialog.form['applied'] and app.dialog is not None
            app.dialog.close()
            report['native_save_feedback']=True
            app.hotkeys.configure(custom)
            assert app.hotkeys.bindings == custom and len(app.hotkeys.registered) == 3
            ctypes.windll.user32.PostThreadMessageW(app.hotkeys.thread.native_id, 0x0312, 3, 0)
            assert wait(lambda: app.collapsed and app.bubble.visible, 2)
            ctypes.windll.user32.PostThreadMessageW(app.hotkeys.thread.native_id, 0x0312, 3, 0)
            assert wait(lambda: not app.collapsed and app.panel.visible and not app.bubble.visible, 2)
            store._write('settings.json', {'auto_recognize': False, 'hotkeys': custom})
            assert store.read('settings.json')['hotkeys'] == custom
            assert not errors, '\n'.join(errors)
            report.update(champions=len(store.champions()),
                          ocr=[{'text': m.text, 'augment_id': m.augment_id} for m in matches],
                          mayhem_build_verified=True, tray_visible=True,
                          hotkeys=app.hotkeys.status, native_hotkey_toggle=True, item_icons=4, source_build_slots=4, panel_bubble_toggle=True,
                          writable_cache_and_settings=True, qt_version=qVersion(), pyside_version=pyside_version)
            report['skill_priority_visible'] = True
            report['skill_priority_game_only'] = True
            report['summoner_spells_select_only'] = True
            app.close()
            qt.processEvents()
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
        if errors:
            report['callback_errors'] = errors
    finally:
        if app is not None:
            app.close()
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    return 0 if report['status'] == 'passed' else 1
