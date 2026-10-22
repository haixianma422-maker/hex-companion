import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PySide6.QtCore import QObject

from aram_demo.cache import DataStore
from aram_demo.lcu import ClientState
from aram_demo.recognition import match_slots
from aram_demo.models import Champion, augment_label
from aram_demo.windows import LeagueWindow
from tests.qt_support import close_companion, new_companion, pump


class CompanionAppTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.app = new_companion(DataStore(Path(self.tmp.name), Path(__file__).resolve().parents[1] / 'data', source='opgg'))

    def tearDown(self):
        close_companion(self.app)
        self.tmp.cleanup()

    def window(self, name='panelWindow'):
        return self.app.overlay.window(name)

    def test_small_panel_follows_mode_lifecycle(self):
        self.assertFalse(self.app.panel.visible)
        self.app.on_client_state(ClientState('ChampSelect', 222, [99, 86], queue_id=2400))
        pump(until=lambda: self.window().isVisible())
        self.assertTrue(self.app.panel.visible)
        self.assertEqual(self.app.panel.width, round(360 * self.app.panel.ratio))
        self.app.on_client_state(ClientState('ChampSelect', 222, [99], queue_id=450))
        pump(until=lambda: not self.window().isVisible())
        self.assertFalse(self.app.panel.visible)

    def test_update_restart_waits_until_lobby_select_and_game_are_over(self):
        from unittest.mock import Mock
        self.app.updater = Mock(ready=('manager', 'info'))
        notes = []
        self.app.notify = notes.append
        for phase in ('Lobby', 'ChampSelect', 'InProgress'):
            self.app.on_client_state(ClientState(phase, 222, queue_id=2400))
            self.app.restart_update()
        self.app.updater.restart.assert_not_called()
        self.assertFalse(self.app.closed)
        self.assertEqual(len(notes), 3)
        self.app.on_client_state(ClientState('None', queue_id=None))
        self.app.restart_update()
        self.app.updater.restart.assert_called_once()
        self.assertTrue(self.app.closed)

    def test_tencent_custom_mayhem_select_shows_real_hero_panel(self):
        self.app.on_client_state(ClientState('ChampSelect', 222, queue_id=3270))
        self.assertTrue(self.app.panel.visible)
        self.assertIn('暴走萝莉', self.app.panel.content_text())
        self.assertIn('3270', self.app.connection_text)
        self.assertNotIn('模式未匹配', self.app.connection_text)

    def test_game_transition_shows_builds_and_letter_ratings_in_same_panel(self):
        self.app.on_client_state(ClientState('ChampSelect', 222, [99, 86], queue_id=2400))
        self.app.on_client_state(ClientState('InProgress', 222, queue_id=2400, match_id=1))
        names = ['暴击飞弹', '魔法飞弹', '纯粹主义者 - 术师']
        self.app.accept_matches(match_slots(names, self.app.augments))
        labels = self.app.panel.content_text()
        self.assertIn('核心出装', labels)
        self.assertIn('卢安娜飓风', labels)
        # Grades come from the shipped snapshot, which changes with every patch.
        grades = {a['name']: augment_label(a['tier']) for a in self.app.data['augments']}
        for name in names:
            self.assertIn(grades[name], tuple('SABCDE'))
            self.assertIn(name + '\n已识别', labels)
            self.assertIn(grades[name] + '\n' + name, labels)

    def test_partial_recognition_reports_count_instead_of_complete_success(self):
        self.app.on_client_state(ClientState('InProgress', 222, queue_id=3270))
        self.app.accept_matches(match_slots(['暴击飞弹', '', '未知选项'], self.app.augments))
        self.assertIn('1/3', self.app.status)
        self.assertIn('待确认', self.app.status)

    def test_late_ocr_result_cannot_reappear_after_leaving_mode(self):
        self.app.on_client_state(ClientState('InProgress', 222, queue_id=2400, match_id=1))
        ticket = self.app.ocr_ticket()
        matches = match_slots(['暴击飞弹'], self.app.augments)
        self.app.on_client_state(ClientState('Lobby', queue_id=450))
        self.app.deliver(ticket, self.app.accept_matches, matches, None)
        self.assertFalse(self.app.panel.visible)
        self.assertFalse(self.app.matches)

    def test_manual_correction_survives_auto_scan_until_f6_resumes_it(self):
        self.app.on_client_state(ClientState('InProgress', 222, queue_id=2400))
        self.app.apply_manual(['暴击飞弹', '', ''])
        self.app.scan(force=False)
        self.assertEqual(self.app.matches[0].augment_id, 1356)
        self.assertIsNone(self.app.matches[1].augment_id)
        self.assertTrue(self.app.manual_override)
        self.app.scan()
        self.assertFalse(self.app.manual_override)
        self.assertIsNotNone(self.app.matches[1].augment_id)

    def test_slow_ocr_completion_leaves_results_visible_before_next_scan(self):
        self.app.on_client_state(ClientState('InProgress', 222, queue_id=3270))
        self.app.preview = False
        anchor = LeagueWindow(0, (100, 100, 1300, 900), (0, 0, 1920, 1040), True)
        self.app.locate = lambda: anchor
        self.app.last_scan = 0
        with patch('aram_demo.companion.time.monotonic', return_value=20):
            self.app.accept_matches(match_slots(['暴击飞弹', '', ''], self.app.augments))
        with patch('aram_demo.companion.time.monotonic', return_value=20.1), \
             patch('aram_demo.companion.find_league_window', return_value=anchor):
            self.app._tick()
        self.assertFalse(self.app.scanning)
        self.assertIn('1/3', self.app.status)

    def test_refresh_reloads_tier_index_and_repaints_candidates(self):
        self.app.on_client_state(ClientState('ChampSelect', 222, [86], queue_id=2400))
        jobs = []
        self.app.background = lambda job, callback, **kw: jobs.append((job, callback))
        self.app.refresh()
        with patch.object(self.app.store, 'refresh', return_value={}) as refresh:
            result = jobs[0][0]()
            refresh.assert_called_once_with(None)
        updated = Champion(86, '德玛西亚之力', 'garen', 1, 1)
        with patch.object(self.app.store, 'champions', return_value=[updated]):
            jobs[0][1](result)
        self.assertEqual(self.app.champions[86].tier_label, 'T1')
        self.assertIn('T1', self.app.panel.content_text())

    def test_unknown_candidate_id_remains_visible(self):
        self.app.on_client_state(ClientState('ChampSelect', 222, [99999], queue_id=2400))
        self.assertIn('99999', self.app.panel.content_text())
        self.assertIn('—', self.app.panel.content_text())

    def test_invalid_install_folder_cannot_be_saved(self):
        with tempfile.TemporaryDirectory() as directory:
            self.app.store = DataStore(Path(directory) / 'cache')
            original = self.app.settings.get('install_path')
            self.app.show_settings()
            self.app.dialog.set_value('path', directory)
            with patch.object(self.app.store, '_write') as write:
                self.assertFalse(self.app.dialog.save())
            self.assertEqual(self.app.settings.get('install_path'), original)
            write.assert_not_called()
            self.assertIsNone(self.app.store.read('settings.json'))
            self.assertIsNotNone(self.app.dialog)
            self.assertIn('path', self.app.dialog.field_errors)
            self.assertEqual(self.app.dialog.tab, 2)

    def test_open_settings_updates_connection_error_and_mode_filter_reason(self):
        self.app.show_settings()
        self.app.on_client_state(ClientState(message='客户端已运行，但无法读取连接凭据；请检查管理员权限'))
        self.assertIn('管理员', self.app.connection_text)
        self.app.on_client_state(ClientState('ChampSelect', 222, queue_id=450))
        self.assertIn('450', self.app.connection_text)
        self.assertIn('隐藏', self.app.connection_text)
        self.app.on_client_state(ClientState('ChampSelect', 222, queue_id=2400))
        self.assertIn('2400', self.app.connection_text)
        self.assertNotIn('模式未匹配', self.app.connection_text)
        self.assertIn('2400', self.app.dialog.form['connection'])

    def test_saving_unchanged_cards_does_not_pause_automatic_recognition(self):
        self.app.preview_next()
        self.app.preview_next()
        with tempfile.TemporaryDirectory() as directory:
            self.app.store = DataStore(Path(directory))
            self.app.show_settings()
            self.assertTrue(self.app.dialog.save())
            self.assertFalse(self.app.manual_override)

    def test_deliberately_clearing_all_three_choices_applies_manual_correction(self):
        self.app.preview_next()
        self.app.preview_next()
        with tempfile.TemporaryDirectory() as directory:
            self.app.store = DataStore(Path(directory))
            self.app.show_settings()
            for slot in range(3):
                self.app.dialog.set_value(f'choice.{slot}', '请选择')
            self.assertTrue(self.app.dialog.save())
            self.assertTrue(self.app.manual_override)
            self.assertTrue(all(m.augment_id is None for m in self.app.matches))

    def test_recognition_refresh_keeps_build_scroll_position_in_same_game(self):
        self.app.locate = lambda: LeagueWindow(0, (200, 40, 1000, 540), (0, 0, 1400, 500), True)
        self.app.preview_next()
        self.app.preview_next()
        pump(until=lambda: self.window().isVisible())
        body = self.window().findChild(QObject, 'panelBody')
        self.assertTrue(body.property('interactive'))
        body.setProperty('contentY', 60)
        self.app.scanning = True
        self.app.present()
        pump(.05)
        self.assertEqual(body.property('contentY'), 60)

    def test_cancel_discards_selected_install_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            self.app.store = DataStore(Path(directory))
            original = self.app.settings.get('install_path')
            self.app.show_settings()
            self.app.dialog.set_value('path', 'D:/Fake-League')
            self.app.dialog.close()
            self.assertIsNone(self.app.dialog)
            self.assertEqual(self.app.settings.get('install_path'), original)
            self.assertIsNone(self.app.store.read('settings.json'))

    def changes(self, model):
        events = []
        model.rowsInserted.connect(lambda *_: events.append('insert'))
        model.rowsRemoved.connect(lambda *_: events.append('remove'))
        model.modelReset.connect(lambda *_: events.append('reset'))
        return events

    def test_scan_keeps_panel_mapped_and_cards_in_place(self):
        from PIL import Image
        self.app.on_client_state(ClientState('InProgress', 222, queue_id=3270))
        self.app.preview = False
        anchor = LeagueWindow(0, (100, 100, 1300, 900), (0, 0, 1920, 1040), True)
        self.app.locate = lambda: anchor
        self.app.present()
        pump(until=lambda: self.window().isVisible())
        events = self.changes(self.app.panel.cards)
        pending = []
        self.app.background = lambda *args, **kwargs: pending.append(args)
        with patch('aram_demo.companion.find_league_window', return_value=anchor), \
             patch('PIL.ImageGrab.grab', return_value=Image.new('RGB', (1200, 800))):
            self.app.scan()
            self.assertTrue(self.app.panel.visible)
            pump(.05)
            self.assertTrue(self.window().isVisible())
        self.assertTrue(pending)
        self.app.scanning = False
        self.app.accept_matches([])
        self.assertEqual(events, [])

    def test_collapse_leaves_clickable_bubble_and_drag_does_not_expand(self):
        self.app.on_client_state(ClientState('InProgress', 222, queue_id=3270))
        self.app.hide()
        bubble = self.app.bubble
        self.assertFalse(self.app.panel.visible)
        self.assertTrue(bubble.visible)
        original = bubble.position
        from aram_demo.qt_overlay import to_logical
        x, y = to_logical(original[0] - 100, original[1] + 60)
        bubble.moved(round(x), round(y))
        self.assertTrue(bubble.visible)
        self.assertNotEqual(bubble.position, original)
        dragged = bubble.position
        self.app.present()
        self.assertEqual(bubble.position, dragged)
        bubble.expand()
        self.assertTrue(self.app.panel.visible)
        self.assertFalse(bubble.visible)

    def test_bubble_hint_names_the_toggle_key_and_hides_with_the_bubble(self):
        from PySide6.QtCore import QMetaObject
        self.app.bubble.set_hotkeys({'toggle': 'Ctrl+Alt+H'})
        self.app.on_client_state(ClientState('InProgress', 222, queue_id=3270))
        self.app.hide()
        pump(until=lambda: self.window('bubbleWindow').isVisible())
        root, tip = self.app.overlay.engine.rootObjects()[0], self.window('bubbleTipWindow')
        QMetaObject.invokeMethod(root, 'showTip')
        pump(until=tip.isVisible)
        self.assertIn('Ctrl+Alt+H', self.app.bubble.state['tip'])
        self.app.expand()
        pump(until=lambda: not tip.isVisible())

    def test_collapsed_mode_hides_on_alt_tab_and_exit_and_preserves_choice(self):
        self.app.on_client_state(ClientState('InProgress', 222, queue_id=3270))
        self.app.hide()
        self.app.preview = False
        anchor = LeagueWindow(0, (100, 100, 1300, 900), (0, 0, 1920, 1040), False)
        self.app.locate = lambda: anchor
        with patch('aram_demo.companion.foreground_is_ours', return_value=False):
            self.app.present()
        self.assertFalse(self.app.bubble.visible)
        self.assertFalse(self.app.panel.visible)
        self.app.preview = True
        self.app.present()
        self.assertTrue(self.app.bubble.visible)
        self.app.on_client_state(ClientState('Lobby', queue_id=450))
        self.assertFalse(self.app.bubble.visible)
        self.app.on_client_state(ClientState('ChampSelect', 222, queue_id=3270))
        self.assertTrue(self.app.panel.visible)

    def test_occluded_titles_pause_capture_without_hiding_panel(self):
        self.app.on_client_state(ClientState('InProgress', 222, queue_id=3270))
        self.app.preview = False
        anchor = LeagueWindow(0, (100, 100, 1300, 900), (0, 0, 1920, 1040), True)
        self.app.locate = lambda: anchor
        self.app.present()
        self.app.panel.offset = (-1000, 250)
        self.app.present()
        with patch('aram_demo.companion.find_league_window', return_value=anchor), \
             patch('PIL.ImageGrab.grab') as capture:
            self.app.scan()
            capture.assert_not_called()
        self.assertTrue(self.app.panel.visible)
        self.assertFalse(self.app.scanning)
        self.assertIn('遮挡', self.app.status)

    def test_collapsed_bubble_pauses_auto_scan_and_results_do_not_expand_it(self):
        self.app.on_client_state(ClientState('InProgress', 222, queue_id=3270))
        self.app.hide()
        self.app.preview = False
        self.app.locate = lambda: LeagueWindow(0, (100, 100, 1300, 900), (0, 0, 1920, 1040), True)
        with patch.object(self.app, 'scan') as scan:
            self.app._tick()
            scan.assert_not_called()
        self.app.accept_matches(match_slots(['暴击飞弹'], self.app.augments))
        self.assertFalse(self.app.panel.visible)
        self.assertTrue(self.app.bubble.visible)
        self.app.bubble._place(-5000, 5000)
        self.assertEqual(self.app.bubble.position, (0, 1040 - self.app.bubble.size))
        self.app.expand()
        self.assertTrue(self.app.panel.visible)

    def test_new_choices_and_data_update_existing_cards_in_place(self):
        import copy
        self.app.on_client_state(ClientState('InProgress', 222, queue_id=3270))
        events = self.changes(self.app.panel.cards)
        items = self.changes(self.app.panel.items)
        place = dict(self.app.panel.place)
        self.app.accept_matches(match_slots(['暴击飞弹', '魔法飞弹', '纯粹主义者 - 术师'], self.app.augments))
        data = copy.deepcopy(self.app.data)
        next(a for a in data['augments'] if a['id'] == 1356)['tier'] = 1
        core = next(row for row in data['builds'] if row['category'] == '核心装备')
        core['items'][0]['name'] = '更新后的装备'
        self.app.data = data
        self.app.present()
        self.assertEqual(events, [])
        self.assertEqual(items, [])
        self.assertEqual(self.app.panel.place, place)
        self.assertIn('更新后的装备', self.app.panel.content_text())
        self.assertIn('A', self.app.panel.content_text())

    def test_detection_keeps_scan_button_and_last_results_stable(self):
        from PIL import Image
        self.app.on_client_state(ClientState('InProgress', 222, queue_id=3270))
        self.app.preview = False
        anchor = LeagueWindow(0, (100, 100, 1300, 900), (0, 0, 1920, 1040), True)
        self.app.locate = lambda: anchor
        self.app.accept_matches(match_slots(['暴击飞弹', '', ''], self.app.augments))
        status = self.app.status
        self.app.background = lambda *a, **k: None
        with patch('aram_demo.companion.find_league_window', return_value=anchor), \
             patch('PIL.ImageGrab.grab', return_value=Image.new('RGB', (1200, 800))):
            self.app.scan(force=False)
        self.assertEqual(self.app.panel.view['scanText'], '重新识别 F6')
        self.assertFalse(self.app.panel.view['scanning'])
        self.assertEqual(self.app.status, status)
        self.assertIn('暴击飞弹', self.app.panel.content_text())
        # A manual click can adopt the pending automatic scan and gets explicit feedback.
        self.app.scan(force=True)
        self.assertEqual(self.app.panel.view['scanText'], '识别中…')
        self.assertTrue(self.app.panel.view['scanning'])

    def test_candidate_refresh_preserves_existing_rows(self):
        self.app.on_client_state(ClientState('ChampSelect', 222, [86], queue_id=3270))
        events = self.changes(self.app.panel.candidates)
        self.app.champions[86] = Champion(86, '德玛西亚之力', 'garen', 1, 1)
        self.app.on_client_state(ClientState('ChampSelect', 222, [86, 99], queue_id=3270))
        self.assertNotIn('remove', events)
        self.assertNotIn('reset', events)
        self.assertIn('T1', self.app.panel.content_text())

    def test_persistent_game_panel_recovers_height_after_small_work_area(self):
        self.app.on_client_state(ClientState('InProgress', 222, queue_id=3270))
        ratio = self.app.panel.ratio
        self.app.locate = lambda: LeagueWindow(0, (100, 40, 1000, 540), (0, 0, 1400, 580), True)
        self.app.present()
        self.assertEqual(self.app.panel.height, 568)
        self.app.locate = lambda: LeagueWindow(0, (100, 40, 1000, 900), (0, 0, 1920, 1040), True)
        self.app.present()
        self.assertEqual(self.app.panel.height, round(580 * ratio))

    def test_four_build_slots_stay_when_data_becomes_incomplete(self):
        import copy
        from tests.qt_support import settle_assets
        self.app.on_client_state(ClientState('InProgress', 222, queue_id=3270))
        settle_assets(self.app)
        self.assertEqual(len([k for k in self.app.panel.assets_shown if k[0] == 'item']), 4)
        self.assertNotIn('饮血剑', self.app.panel.content_text())
        events = self.changes(self.app.panel.items)
        data = copy.deepcopy(self.app.data); data['builds'] = []
        self.app.data = data; self.app.present()
        self.assertEqual(events, [])
        self.assertEqual(self.app.panel.content_text().count('暂无资料'), 4)
        self.assertEqual(len([k for k in self.app.panel.assets_shown if k[0] == 'item']), 0)

    def test_hotkey_toggle_can_restore_panel_after_collapse(self):
        self.app.on_client_state(ClientState('InProgress', 222, queue_id=2400))
        self.app.hotkeys.callbacks[3]()
        self.app.events.get_nowait()[1]()
        self.assertTrue(self.app.bubble.visible)
        self.assertFalse(self.app.panel.visible)
        self.app.hotkeys.callbacks[3]()
        self.app.events.get_nowait()[1]()
        self.assertTrue(self.app.panel.visible)
        self.assertFalse(self.app.bubble.visible)

    def test_custom_hotkeys_save_and_reload_with_matching_button_caption(self):
        with tempfile.TemporaryDirectory() as directory:
            self.app.store = DataStore(Path(directory))
            self.app.panel.on_preview = None
            self.app.on_client_state(ClientState('InProgress', 222, queue_id=2400))
            self.app.show_settings()
            self.app.dialog.set_value('hotkey.scan', 'Ctrl+Alt+J')
            self.app.dialog.set_value('hotkey.toggle', 'Ctrl+Alt+H')
            self.assertTrue(self.app.dialog.save())
            self.assertTrue(self.app.dialog.form['applied'])
            saved = self.app.store.read('settings.json')['hotkeys']
            self.assertEqual(saved['toggle'], 'Ctrl+Alt+H')
            self.assertIn('Ctrl+Alt+J', self.app.panel.view['scanText'])
            from aram_demo.hotkeys import Hotkeys
            reloaded = Hotkeys(lambda: None, lambda: None, lambda: None, bindings=saved)
            self.assertEqual(reloaded.bindings, saved)

    def test_duplicate_hotkey_keeps_settings_open_and_does_not_save(self):
        with tempfile.TemporaryDirectory() as directory:
            self.app.store = DataStore(Path(directory))
            self.app.show_settings()
            self.app.dialog.set_value('hotkey.toggle', 'F6')
            self.assertFalse(self.app.dialog.save())
            self.assertIsNotNone(self.app.dialog)
            self.assertIsNone(self.app.store.read('settings.json'))
            self.assertEqual(self.app.hotkeys.bindings['toggle'], 'F8')
            self.assertEqual(set(self.app.dialog.field_errors), {'hotkey.scan', 'hotkey.toggle'})

    def test_auto_detection_resumes_within_half_second_after_previous_result(self):
        self.app.on_client_state(ClientState('InProgress', 222, queue_id=3270))
        self.app.preview = False
        anchor = LeagueWindow(0, (100, 100, 1300, 900), (0, 0, 1920, 1040), True)
        self.app.locate = lambda: anchor
        self.app.accept_matches(match_slots(['暴击飞弹'], self.app.augments))
        self.app.last_scan = 20
        with patch('aram_demo.companion.time.monotonic', return_value=20.4), \
             patch.object(self.app, 'scan') as scan:
            self.app._tick()
            scan.assert_called_once_with(force=False)

    def test_ordinary_game_frames_use_slow_checks_then_selection_switches_to_fast(self):
        self.app.on_client_state(ClientState('InProgress', 222, queue_id=3270))
        self.app.preview = False
        self.app.locate = lambda: LeagueWindow(0, (100, 100, 1300, 900), (0, 0, 1920, 1040), True)
        self.app.last_scan = 20
        with patch('aram_demo.companion.time.monotonic', return_value=20.4), \
             patch.object(self.app, 'scan') as scan:
            self.app._tick()
            scan.assert_not_called()
        self.app.accept_matches(match_slots(['暴击飞弹'], self.app.augments))
        self.assertEqual(self.app.scan_interval, .25)
        # A single animation frame must preserve the visible results.
        self.app.accept_matches(None)
        self.assertIsNotNone(self.app.matches[0].augment_id)
        self.app.accept_matches(None)
        self.assertFalse(self.app.matches)
        self.assertEqual(self.app.scan_interval, 1.5)

    def test_fresh_hero_cache_skips_automatic_fetch_but_refresh_forces_it(self):
        from datetime import datetime, timedelta, timezone
        from aram_demo.companion_state import PanelState
        self.app.services, self.app.preview = True, False
        self.app.state = PanelState('select', 'ChampSelect', 222, queue_id=2400)
        # Same version as the index: a refreshed local data/champions.json must not decide this test.
        hero = dict(self.app.store.hero(222), patch=self.app.store.index_patch(),
                    fetched_at=datetime.now(timezone.utc).isoformat())
        with patch.object(self.app, 'fetch_hero') as fetch, \
             patch.object(self.app, 'refresh_icons'), patch.object(self.app, 'refresh_visual_assets'), \
             patch.object(self.app, 'refresh_index'), patch.object(self.app, 'background'):
            with patch.object(self.app.store, 'hero', return_value=hero):
                self.app.load_data()
                fetch.assert_not_called()
                self.app.refresh()
                fetch.assert_called_once_with(222)
            fetch.reset_mock()
            stale = dict(hero, fetched_at=(datetime.now(timezone.utc) - timedelta(days=2)).isoformat())
            with patch.object(self.app.store, 'hero', return_value=stale):
                self.app.load_data()
            fetch.assert_called_once_with(222)
        self.app.services, self.app.preview = False, True

    def test_new_game_resets_fast_scan_policy_and_window_checks_are_throttled(self):
        self.app.on_client_state(ClientState('InProgress', 222, queue_id=3270, match_id=1))
        self.app.accept_matches(match_slots(['暴击飞弹'], self.app.augments))
        self.app.on_client_state(ClientState('InProgress', 222, queue_id=3270, match_id=2))
        self.assertEqual(self.app.scan_interval, 1.5)
        self.app.auto = False
        with patch('aram_demo.companion.time.monotonic', side_effect=[20, 20.15, 20.3]), \
             patch.object(self.app, 'present') as present:
            self.app._tick()
            self.app._tick()
            self.app._tick()
            self.assertEqual(present.call_count, 1)
