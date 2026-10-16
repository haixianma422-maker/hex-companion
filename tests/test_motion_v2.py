"""Motion contracts: time samples, interruption, locality and native resize."""
import tempfile
import tkinter as tk
import unittest
from pathlib import Path
from unittest.mock import patch
from PIL import ImageChops, ImageTk

from aram_demo.motion import Motion
from aram_demo.cache import DataStore
from aram_demo.companion import CompanionApp
from aram_demo.lcu import ClientState
from aram_demo.recognition import match_slots
from aram_demo.windows import LeagueWindow


class SchedulerTests(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tk(); self.root.withdraw()
        self.motion = Motion(self.root)
        self.motion.enabled = True
        self.now = 100.
        self.clock = patch('aram_demo.motion.time.monotonic', lambda: self.now)
        self.clock.start()

    def tearDown(self):
        self.motion.cancel_all(); self.root.destroy(); self.clock.stop()

    def frame(self, elapsed):
        self.now = 100 + elapsed / 1000
        token = next(iter(self.motion.jobs.values()))
        command = self.root.tk.call('after', 'info', token)[0]
        self.root.tk.call('after', 'cancel', token)
        self.root.tk.call(command)

    def test_cubic_uses_elapsed_time_and_finishes_without_idle_jobs(self):
        values = []
        self.motion.animate('content', 0, 1, values.append, 180)
        self.frame(45)
        self.assertAlmostEqual(values[-1], .578125, places=6)
        self.frame(90)
        self.assertAlmostEqual(values[-1], .875, places=6)
        self.frame(200)
        self.assertEqual(values[-1], 1)
        self.assertFalse(self.motion.jobs)
        self.assertFalse(self.motion.ends)

    def test_replacement_finishes_old_target_before_new_frames(self):
        values = []
        self.motion.animate('content', 0, 1, values.append)
        self.motion.animate('content', 2, 3, values.append)
        self.assertEqual(values[:3], [0, 1, 2])

    def test_system_preference_changed_during_animation_cleans_up(self):
        values = []
        self.motion.animate('content', 0, 1, values.append)
        with patch('aram_demo.motion.system_motion_enabled', return_value=False):
            self.frame(45)
        self.assertEqual(values[-1], 1)
        self.assertFalse(self.motion.jobs)

    def test_real_task_activity_keeps_continuous_phase_beyond_demo_length(self):
        values=[]
        self.motion.activity('scan',values.append,period=1400)
        self.frame(1414)
        self.assertAlmostEqual(values[-1],1.01,places=6)
        self.motion.set_enabled(False)
        self.assertFalse(self.motion.jobs)


class NativeMotionTests(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tk(); self.root.design_scale = 1
        self.tmp = tempfile.TemporaryDirectory()
        self.app = CompanionApp(self.root, DataStore(Path(self.tmp.name),
            Path(__file__).resolve().parents[1] / 'data', source='opgg'), preview=True, services=False)
        self.app.locate = lambda: LeagueWindow(0, (100,100,1300,900), (0,0,1920,1040), True)
        self.app.panel.set_motion(False); self.app.bubble.set_motion(False)
        self.errors = []
        self.root.report_callback_exception = lambda *args: self.errors.append(args)

    def tearDown(self):
        self.app.close(); self.tmp.cleanup()
        self.assertFalse(self.errors)

    def game(self):
        self.app.on_client_state(ClientState('InProgress',222,queue_id=3270))
        self.root.update()

    def test_hero_switch_has_local_finite_transition(self):
        self.app.on_client_state(ClientState('ChampSelect',101,[101,222,99,17],queue_id=3270))
        self.root.update()
        panel = self.app.panel
        before = panel._full_image.copy()
        panel.motion.enabled = True
        with patch('aram_demo.motion.time.monotonic', return_value=100):
            self.app.on_client_state(ClientState('ChampSelect',222,[101,222,99,17],queue_id=3270))
            self.assertIn('hero', panel.motion.jobs)
            self.assertIsNone(ImageChops.difference(before.crop((0,0,360,68)).convert('RGB'),
                panel._full_image.crop((0,0,360,68)).convert('RGB')).getbbox())
        panel.set_motion(False)
        self.assertFalse(panel.motion.jobs)

    def test_card_reveal_keeps_count_old_until_last_frame(self):
        self.game()
        self.app.accept_matches(match_slots(['暴击飞弹','魔法飞弹',''],self.app.augments))
        panel = self.app.panel; before = panel._full_image.copy()
        panel.motion.enabled = True
        with patch('aram_demo.motion.time.monotonic', return_value=100):
            self.app.accept_matches(match_slots(['暴击飞弹','魔法飞弹','纯粹主义者 - 术师'],self.app.augments))
            self.assertIn('cards', panel.motion.jobs)
            self.assertIsNone(ImageChops.difference(before.crop((0,0,360,244)).convert('RGB'),
                panel._full_image.crop((0,0,360,244)).convert('RGB')).getbbox())

    def test_pending_source_masks_only_content_and_waits_for_real_completion(self):
        self.game(); panel = self.app.panel
        old_data = dict(self.app.data)
        panel.motion.enabled = True
        self.app.change_source('qq101')
        panel.data_loading = True
        self.app.present()
        panel.set_motion(False)
        self.assertTrue(panel._source_pending)
        panel.data_loading = False
        self.app.data = dict(old_data,source_id='qq101')
        self.app.present()
        self.assertFalse(panel._source_pending)

    def test_pointer_leave_and_reduced_motion_do_not_complete_scan(self):
        self.game(); panel = self.app.panel
        self.app.scanning = self.app.scan_feedback = True
        self.app.present()
        panel.scan_button.event_generate('<Leave>')
        panel.set_motion(False)
        self.assertTrue(self.app.scanning)
        self.assertIn('识别中', panel.scan_button.text)
        self.app.scan_finished()
        self.assertFalse(panel.scan_button.task_active)
        self.assertFalse(panel.scan_button.motion.jobs)

    def test_activity_frames_rotate_the_visible_icon(self):
        self.game(); button=self.app.panel.scan_button
        button.motion.enabled=True
        self.app.scanning=self.app.scan_feedback=True
        with patch('aram_demo.motion.time.monotonic',return_value=100):
            self.app.present()
        token=button.motion.jobs['activity']
        command=self.root.tk.call('after','info',token)[0]
        self.root.tk.call('after','cancel',token)
        with patch('aram_demo.motion.time.monotonic',return_value=100.14):
            self.root.tk.call(command)
        second=ImageTk.getimage(button._photo).convert('RGB')
        token=button.motion.jobs['activity']
        command=self.root.tk.call('after','info',token)[0]
        self.root.tk.call('after','cancel',token)
        with patch('aram_demo.motion.time.monotonic',return_value=100.28):
            self.root.tk.call(command)
        third=ImageTk.getimage(button._photo).convert('RGB')
        self.assertIsNotNone(ImageChops.difference(second,third).getbbox())

    def test_source_failure_stops_loading_and_cannot_keep_old_source_cards(self):
        self.game(); panel=self.app.panel
        self.app.change_source('qq101')
        panel.network_error='controlled network failure'
        panel.data_loading=False
        self.app.present()
        self.assertFalse(panel._source_pending)
        self.assertIsNone(panel._source_old)
        self.assertNotIn('正在切换来源',panel.content_text())

    def test_initial_reveal_captures_controls_and_has_transform_layer(self):
        self.app.panel.motion.enabled=True
        with patch('aram_demo.motion.time.monotonic',return_value=100):
            self.app.on_client_state(ClientState('InProgress',222,queue_id=3270))
            self.assertIsNotNone(self.app.panel._visibility_layer)
        self.app.panel.set_motion(False)
        self.assertEqual(self.app.panel._visibility_layer.winfo_manager(),'')

    def test_tabs_fade_content_and_saved_dialog_shows_real_write_feedback(self):
        self.game(); self.app.show_settings(); self.root.update()
        tabs = self.app._settings_notebook
        tabs.motion.enabled = True
        with patch('aram_demo.motion.time.monotonic', return_value=100):
            tabs.select(1)
            self.assertIn('content', tabs.motion.jobs)
        tabs.motion.set_enabled(False)
        tabs.select(0)
        for widget in self.app.dialog.winfo_children():
            if getattr(widget, 'text', '') == '保存并应用':
                widget.invoke()
                self.assertTrue(self.app.dialog.winfo_exists())
                self.assertEqual(widget.text, '已应用')
                self.assertTrue((Path(self.tmp.name)/'settings.json').is_file())
                break
        else:
            self.fail('save button missing')

    def test_resize_scales_controls_and_hits_and_persists_zoom(self):
        self.game(); panel = self.app.panel
        panel.set_zoom(1.25)
        self.root.update()
        self.assertEqual(panel.window.winfo_width(),450)
        self.assertEqual(panel.window.winfo_height(),725)
        self.assertEqual(panel.scan_button.scale,1.25)
        self.assertEqual(panel._logical(type('Event',(),{'x':375,'y':350})()),(300,280))
        panel.on_resize(panel.zoom)
        self.assertEqual(self.app.store.read('settings.json')['panel_zoom'],1.25)

    def test_resize_clamps_to_work_area_and_stage_keeps_zoom(self):
        self.game(); panel = self.app.panel
        panel.set_zoom(10)
        self.root.update()
        x,y,w,h = panel._geometry
        self.assertLessEqual(x+w,1920); self.assertLessEqual(y+h,1040)
        zoom = panel.zoom
        self.app.on_client_state(ClientState('ChampSelect',222,queue_id=3270))
        self.assertEqual(panel.zoom,zoom)

    def test_saved_zoom_and_monitor_change_both_fit_new_work_area(self):
        self.app.panel.set_zoom(2.5)
        self.app.locate=lambda:LeagueWindow(0,(0,0,700,500),(0,0,700,500),True)
        self.game()
        panel=self.app.panel
        x,y,w,h=panel._geometry
        self.assertLessEqual(x+w,700); self.assertLessEqual(y+h,500)
        self.app.locate=lambda:LeagueWindow(0,(0,0,350,500),(0,0,350,500),True)
        self.app.present(); self.root.update()
        x,y,w,h=panel._geometry
        self.assertLessEqual(x+w,350); self.assertLessEqual(y+h,500)

    def test_drag_then_resize_preserves_current_top_left(self):
        from types import SimpleNamespace
        self.game(); panel=self.app.panel
        x,y=panel.window.winfo_rootx(),panel.window.winfo_rooty()
        panel._press(SimpleNamespace(x=60,y=16,x_root=x+60,y_root=y+16))
        panel._drag(SimpleNamespace(x_root=x+110,y_root=y+46))
        panel._release(SimpleNamespace(x=60,y=16,x_root=x+110,y_root=y+46))
        self.root.update()
        moved=(panel.window.winfo_rootx(),panel.window.winfo_rooty())
        panel.set_zoom(1.1); self.root.update()
        self.assertEqual((panel.window.winfo_rootx(),panel.window.winfo_rooty()),moved)

    def test_hide_during_hero_transition_restores_current_target(self):
        self.app.on_client_state(ClientState('ChampSelect',101,[101,222],queue_id=3270))
        self.root.update(); panel=self.app.panel; panel.motion.enabled=True
        with patch('aram_demo.motion.time.monotonic',return_value=100):
            self.app.on_client_state(ClientState('ChampSelect',222,[101,222],queue_id=3270))
            panel.hide()
        hidden_target=panel._full_image.copy()
        panel.set_motion(False); self.app.present()
        panel.signature=None; self.app.present()
        self.assertIsNone(ImageChops.difference(hidden_target.convert('RGB'),panel._full_image.convert('RGB')).getbbox())

    def test_visibility_crossfades_bubble_without_waiting_for_collapse_end(self):
        self.game()
        self.app.panel.motion.enabled = self.app.bubble.motion.enabled = True
        with patch('aram_demo.motion.time.monotonic', return_value=100):
            self.app.hide()
            self.assertTrue(self.app.bubble.visible)
            self.assertIn('visibility',self.app.panel.motion.jobs)
            self.assertIn('visibility',self.app.bubble.motion.jobs)
        self.app.panel.set_motion(False); self.app.bubble.set_motion(False)
        self.assertEqual(float(self.app.bubble.window.attributes('-alpha')),1)
        self.app.expand(); self.root.update()
        self.assertFalse(self.app.bubble.visible)
        self.assertEqual(float(self.app.panel.window.attributes('-alpha')),1)
