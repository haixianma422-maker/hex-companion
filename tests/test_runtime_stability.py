"""Production lifecycle checks with controlled client inputs, not live acceptance."""
import copy
import ctypes
import gc
import tempfile
import unittest
from ctypes import wintypes
from pathlib import Path
from unittest.mock import Mock, patch

from PySide6.QtCore import QObject
from PySide6.QtGui import QGuiApplication

from aram_demo.cache import DataStore
from aram_demo.lcu import ClientState
from aram_demo.recognition import match_slots
from aram_demo.windows import LeagueWindow
from tests.qt_support import close_companion, new_companion, pump, settle_assets


class RuntimeStabilityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.app = new_companion(DataStore(Path(self.tmp.name), seed_root=Path(__file__).resolve().parents[1] / 'data'),
                                 preview=False)
        self.app.locate = lambda: LeagueWindow(0, (100, 100, 1300, 900), (0, 0, 1920, 1040), True)

    def tearDown(self):
        close_companion(self.app)
        self.tmp.cleanup()

    def game(self):
        self.app.on_client_state(ClientState('InProgress', 222, queue_id=3270, match_id=1))
        self.app.accept_matches(match_slots(['暴击飞弹', '魔法飞弹', '纯粹主义者 - 术师'], self.app.augments))

    def grid(self):
        window = self.app.overlay.window('panelWindow')
        pump(until=window.isVisible)
        return window.findChild(QObject, 'candidateGrid')

    def test_candidate_scroll_survives_repaint_and_shrinking_list_is_clamped(self):
        ids = list(self.app.champions)[:16]
        self.app.on_client_state(ClientState('ChampSelect', 222, ids, queue_id=3270))
        grid = self.grid()
        pump(.05)
        grid.setProperty('contentY', 64)
        with patch.object(self.app.visual_assets, 'path', wraps=self.app.visual_assets.path) as paths:
            self.app.status = '重绘'
            self.app.panel.signature = None
            self.app.present()
            pump(.05)
            # Scrolling and repainting reuse the rows; nothing is validated again.
            paths.assert_not_called()
        self.assertEqual(grid.property('contentY'), 64)
        self.app.on_client_state(ClientState('ChampSelect', 222, ids[:2], queue_id=3270))
        pump(.05)
        self.assertLessEqual(grid.property('contentY'), max(0, grid.property('contentHeight') - grid.property('height')))

    def test_verified_skill_priority_uses_local_icons_before_remote_metadata_arrives(self):
        import io
        from PIL import Image
        self.game()
        urls = {'Q': 'https://ddragon.leagueoflegends.com/cdn/16.20.1/img/spell/JinxQ.png',
                'E': 'https://ddragon.leagueoflegends.com/cdn/16.20.1/img/spell/JinxE.png'}
        self.app.visual_assets._catalog['champions']['222']['skill_icons'] = urls
        image = io.BytesIO(); Image.new('RGB', (64, 64), 'blue').save(image, 'PNG')
        with patch.object(self.app.advice_icons, '_download', return_value=image.getvalue()):
            self.app.advice_icons.ensure(urls.values())
        self.app.data = dict(self.app.data, skill_priority=['Q', 'E'], skill_icons={})
        with patch.object(self.app.advice_icons, '_download', side_effect=AssertionError('must stay offline')):
            self.app.present()
            settle_assets(self.app)
        self.assertTrue(self.app.panel.assets_shown[('skill', 'Q')])
        self.assertTrue(self.app.panel.assets_shown[('skill', 'E')])

    def test_failed_advice_images_are_requested_again_after_backoff(self):
        self.game()
        self.app.data['skill_icons'] = {'Q': 'https://game.gtimg.cn/images/lol/act/img/spell/XerathArcanopulseChargeUp.png'}
        pending = []
        self.app.services = True; self.app.auto = False
        self.app.background = lambda job, callback, **kw: pending.append((callback, kw.get('done')))
        self.app.refresh_advice_icons()
        callback, done = pending.pop(0)
        done()
        with patch.object(self.app.advice_icons, 'path', return_value=None):
            callback([])
        with patch('aram_demo.companion.time.monotonic', return_value=10**10):
            self.app._tick()
        self.assertTrue(pending)

    def test_source_switch_masks_content_until_data_and_keeps_window_visible(self):
        self.game()
        self.app.change_source('qq101')
        # This fixture has no 101 hero cache; keep the mask until real data arrives.
        self.assertTrue(self.app.panel.view['sourcePending'])
        self.assertTrue(self.app.panel.visible)
        self.app.change_source('opgg')
        self.assertFalse(self.app.panel.view['sourcePending'])
        self.assertTrue(self.app.panel.visible)

    def test_hero_change_during_reveal_finishes_visibility(self):
        self.app.panel.set_motion(True)
        self.app.on_client_state(ClientState('ChampSelect', 222, queue_id=3270))
        self.app.on_client_state(ClientState('ChampSelect', 99, queue_id=3270))
        window = self.app.overlay.window('panelWindow')
        surface = window.findChild(QObject, 'panelSurface')
        pump(until=lambda: window.isVisible() and surface.property('opacity') == 1 and surface.property('scale') == 1)
        self.assertTrue(self.app.panel.visible)

    def test_deferred_visual_entries_are_requested_again(self):
        self.game()
        pending = []
        self.app.services = True
        self.app.background = lambda job, callback, **kw: pending.append((callback, kw['done']))
        self.app.refresh_visual_assets()
        callback, done = pending.pop(0)
        done()
        callback({'updated': 1, 'failed': 0, 'missing': 0, 'deferred': 1})
        self.assertEqual(len(pending), 1)

    def test_same_timestamp_in_place_recommendation_change_repaints(self):
        self.game()
        self.app.data = copy.deepcopy(self.app.data)
        self.app.present()
        stamp = self.app.data.get('fetched_at')
        self.app.data['skill_priority'] = ['E', 'Q']
        core = next(row for row in self.app.data['builds'] if row['category'] == '核心装备')
        core['items'][0]['name'] = '实际更新装备'
        self.app.present()
        self.assertEqual(self.app.data.get('fetched_at'), stamp)
        self.assertIn('主 E › 副 Q', self.app.panel.content_text())
        self.assertIn('实际更新装备', self.app.panel.content_text())

    def test_fatal_tray_error_hides_surfaces_before_reporting_and_cannot_remap(self):
        self.game(); self.app.show_settings()
        def report(*args, **kwargs):
            self.assertFalse(self.app.panel.visible)
            self.assertFalse(self.app.bubble.visible)
            self.assertIsNone(self.app.dialog)
            self.app.present()
            self.assertFalse(self.app.panel.visible)
        with patch('aram_demo.companion.message_box', side_effect=report) as error:
            self.app.tray_failed('injected tray failure')
        error.assert_called_once()
        self.assertTrue(self.app.closed)

    def test_background_cleanup_failure_still_destroys_native_window(self):
        self.game()
        window = self.app.overlay.window('panelWindow')
        pump(until=window.isVisible)
        hwnd = int(window.winId())
        self.app.tray = Mock(); self.app.tray.stop.side_effect = RuntimeError('injected shutdown failure')
        with self.assertLogs('aram_demo.companion', level='ERROR'):
            self.app.close()
        user = ctypes.WinDLL('user32', use_last_error=True); user.IsWindow.argtypes = [wintypes.HWND]
        pump(until=lambda: not user.IsWindow(hwnd))
        self.assertTrue(self.app.closed)

    def test_repeated_modes_collapse_and_expand_do_not_accumulate_gui_resources(self):
        self.game(); pump(.1); gc.collect()
        windows = len(QGuiApplication.topLevelWindows())
        threads = len(__import__('threading').enumerate())
        for _ in range(25):
            self.app.on_client_state(ClientState('ChampSelect', 222, [90, 99, 222, 201, 86, 17], queue_id=3270))
            self.game()
            self.app.hide(); pump(.01)
            self.assertTrue(self.app.bubble.visible)
            self.app.expand(); pump(.01)
        settle_assets(self.app); gc.collect()
        self.assertEqual(len(QGuiApplication.topLevelWindows()), windows)
        self.assertLessEqual(len(__import__('threading').enumerate()), threads)
        self.assertTrue(self.app.panel.visible)
        self.assertFalse(self.app.bubble.visible)


if __name__ == '__main__':
    unittest.main()
