"""Motion contracts for the Qt overlay: finite, local, interruptible, and native resize."""
import tempfile
import unittest
from pathlib import Path

from PySide6.QtCore import QObject

from aram_demo.cache import DataStore
from aram_demo.lcu import ClientState
from aram_demo.qt_overlay import to_logical
from aram_demo.recognition import match_slots
from aram_demo.windows import LeagueWindow
from tests.qt_support import close_companion, new_companion, pump


class OverlayMotionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.app = new_companion(DataStore(Path(self.tmp.name), Path(__file__).resolve().parents[1] / 'data', source='opgg'))
        self.app.locate = lambda: LeagueWindow(0, (100, 100, 1300, 900), (0, 0, 1920, 1040), True)

    def tearDown(self):
        close_companion(self.app)
        self.tmp.cleanup()

    def game(self):
        self.app.on_client_state(ClientState('InProgress', 222, queue_id=3270))

    def item(self, name, window='panelWindow'):
        return self.app.overlay.window(window).findChild(QObject, name)

    def shown(self):
        return self.item('panelContent').property('shown').toVariant()

    def at_rest(self):
        surface = self.item('panelSurface')
        return surface.property('opacity') == 1 and surface.property('scale') == 1 and surface.property('y') == 0

    def test_hero_switch_is_finite_and_ends_on_the_new_hero(self):
        self.app.on_client_state(ClientState('ChampSelect', 101, [101, 222, 99, 17], queue_id=3270))
        pump(until=self.at_rest)
        self.app.panel.set_motion(True)
        self.app.on_client_state(ClientState('ChampSelect', 222, [101, 222, 99, 17], queue_id=3270))
        text = self.item('heroText')
        pump(until=lambda: self.shown().get('heroId') == 222
             and text.property('opacity') == 1 and text.property('x') == 0)

    def test_motion_off_still_ends_with_everything_opaque(self):
        # Zero-length Animators never wrote their end value back and left the panel invisible.
        self.app.on_client_state(ClientState('ChampSelect', 222, [101, 222, 99], queue_id=3270))
        grid = self.item('candidateGrid')
        pump(until=lambda: self.at_rest() and grid.property('count') == 3)
        # View delegates are visual children of the content item, not QObject children.
        cards = [c for c in grid.property('contentItem').childItems() if c.objectName() == 'candidateCard']
        self.assertEqual(len(cards), 3)
        pump(until=lambda: all(card.property('opacity') == 1 and card.property('scale') == 1 for card in cards))

    def test_card_reveal_only_touches_the_changed_card(self):
        self.game()
        self.app.accept_matches(match_slots(['暴击飞弹', '魔法飞弹', ''], self.app.augments))
        changed = []
        self.app.panel.cards.dataChanged.connect(lambda first, last, *_: changed.extend(range(first.row(), last.row() + 1)))
        self.app.accept_matches(match_slots(['暴击飞弹', '魔法飞弹', '纯粹主义者 - 术师'], self.app.augments))
        self.assertEqual(changed, [2])
        self.assertIn('已识别 3 / 3', self.app.panel.content_text())

    def test_pending_source_masks_content_and_waits_for_real_completion(self):
        self.game(); panel = self.app.panel
        old_data = dict(self.app.data)
        self.app.change_source('qq101')
        panel.data_loading = True
        self.app.present()
        self.assertTrue(panel.view['sourcePending'])
        self.assertIn('正在切换来源', panel.content_text())
        panel.data_loading = False
        self.app.data = dict(old_data, source_id='qq101')
        self.app.present()
        self.assertFalse(panel.view['sourcePending'])

    def test_reduced_motion_does_not_complete_a_running_scan(self):
        self.game(); panel = self.app.panel
        self.app.scanning = self.app.scan_feedback = True
        self.app.present()
        panel.set_motion(False)
        self.assertTrue(self.app.scanning)
        self.assertEqual(panel.view['scanText'], '识别中…')
        self.assertTrue(panel.view['scanning'])
        self.app.scan_finished()
        self.assertFalse(panel.view['scanning'])

    def test_source_failure_stops_loading_and_cannot_keep_old_source_cards(self):
        self.game(); panel = self.app.panel
        self.app.change_source('qq101')
        panel.network_error = 'controlled network failure'
        panel.data_loading = False
        self.app.present()
        self.assertFalse(panel.view['sourcePending'])
        self.assertNotIn('正在切换来源', panel.content_text())

    def test_motion_switch_reaches_qml_and_saved_dialog_shows_feedback(self):
        self.game()
        self.app.show_settings()
        self.app.dialog.select_tab(1)
        self.app.dialog.set_value('animations', False)
        self.assertTrue(self.app.dialog.save())
        self.assertTrue(self.app.dialog.form['applied'])
        self.assertIsNotNone(self.app.dialog)
        self.assertTrue((Path(self.tmp.name) / 'settings.json').is_file())
        self.assertFalse(self.app.panel.motion)

    def test_resize_scales_window_and_persists_zoom(self):
        self.game(); panel = self.app.panel
        panel.set_zoom(1.25)
        self.assertEqual(panel.width, round(360 * panel.ratio * 1.25))
        self.assertEqual(panel.height, round(580 * panel.ratio * 1.25))
        self.assertEqual(panel.place['zoom'], 1.25)
        panel.on_resize(panel.zoom)
        self.assertEqual(self.app.store.read('settings.json')['panel_zoom'], 1.25)

    def test_resize_clamps_to_work_area_and_stage_keeps_zoom(self):
        self.game(); panel = self.app.panel
        panel.set_zoom(10)
        x, y, w, h = panel.rect()
        self.assertLessEqual(x + w, 1920); self.assertLessEqual(y + h, 1040)
        zoom = panel.zoom
        self.app.on_client_state(ClientState('ChampSelect', 222, queue_id=3270))
        self.assertEqual(panel.zoom, zoom)

    def test_saved_zoom_and_monitor_change_both_fit_new_work_area(self):
        self.app.panel.set_zoom(2.5)
        self.app.locate = lambda: LeagueWindow(0, (0, 0, 700, 500), (0, 0, 700, 500), True)
        self.game()
        x, y, w, h = self.app.panel.rect()
        self.assertLessEqual(x + w, 700); self.assertLessEqual(y + h, 500)
        self.app.locate = lambda: LeagueWindow(0, (0, 0, 350, 500), (0, 0, 350, 500), True)
        self.app.present()
        x, y, w, h = self.app.panel.rect()
        self.assertLessEqual(x + w, 350); self.assertLessEqual(y + h, 500)

    def test_drag_then_resize_preserves_current_top_left(self):
        self.game(); panel = self.app.panel
        x, y, _, _ = panel.rect()
        lx, ly = to_logical(x + 50, y + 30)
        panel.moved(round(lx), round(ly))
        moved = panel.rect()[:2]
        panel.set_zoom(1.1)
        self.assertEqual(panel.rect()[:2], moved)
        self.app.present()
        self.assertEqual(panel.rect()[:2], moved)

    def test_hide_during_hero_transition_shows_the_current_hero_again(self):
        self.app.on_client_state(ClientState('ChampSelect', 101, [101, 222], queue_id=3270))
        pump(until=self.at_rest)
        self.app.panel.set_motion(True)
        self.app.on_client_state(ClientState('ChampSelect', 222, [101, 222], queue_id=3270))
        self.app.hide()
        self.app.expand()
        pump(until=lambda: self.shown().get('heroId') == 222 and self.at_rest())

    def test_collapse_shows_bubble_without_waiting_for_the_panel(self):
        self.game(); pump(until=self.at_rest)
        self.app.panel.set_motion(True); self.app.bubble.set_motion(True)
        self.app.hide()
        self.assertTrue(self.app.bubble.visible)
        self.assertFalse(self.app.panel.visible)
        bubble, panel = self.app.overlay.window('bubbleWindow'), self.app.overlay.window('panelWindow')
        pump(until=lambda: bubble.isVisible() and not panel.isVisible())
        self.app.expand()
        pump(until=lambda: panel.isVisible() and not bubble.isVisible() and self.at_rest())

    def test_repaint_during_a_hero_transition_ends_on_the_latest_view(self):
        self.app.on_client_state(ClientState('ChampSelect', 101, [101, 222], queue_id=3270))
        pump(until=self.at_rest)
        self.app.panel.set_motion(True)
        self.app.on_client_state(ClientState('ChampSelect', 222, [101, 222], queue_id=3270))
        self.app.panel.data_loading = True
        self.app.present()
        pump(until=lambda: self.shown().get('heroId') == 222)
        self.assertIn('加载中', self.app.panel.content_text())

    def test_bubble_ends_at_its_resting_position(self):
        self.game(); self.app.bubble.set_motion(True)
        self.app.hide()
        window = self.app.overlay.window('bubbleWindow')
        state = self.app.bubble.state
        pump(until=lambda: window.isVisible() and (window.x(), window.y()) == (state['x'], state['y']))


if __name__ == '__main__':
    unittest.main()
