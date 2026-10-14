"""Production lifecycle checks with controlled client inputs, not live acceptance."""
import copy
import ctypes
import gc
import tempfile
import tkinter as tk
import unittest
from ctypes import wintypes
from pathlib import Path
from unittest.mock import Mock, patch
from aram_demo.cache import DataStore
from aram_demo.companion import CompanionApp
from aram_demo.lcu import ClientState
from aram_demo.recognition import match_slots
from aram_demo.windows import LeagueWindow

class RuntimeStabilityTests(unittest.TestCase):
    def candidates(self):
        ids=list(self.app.champions)[:16]
        self.app.on_client_state(ClientState('ChampSelect',222,ids,queue_id=3270))
        self.root.update()
        return ids

    def test_candidate_scroll_accumulates_wheel_input_and_reuses_drawn_rows(self):
        from types import SimpleNamespace
        self.candidates();panel=self.app.panel
        panel.motion.enabled=True
        with patch('aram_demo.motion.time.monotonic',return_value=100), \
             patch.object(self.app.visual_assets,'path',wraps=self.app.visual_assets.path) as paths:
            panel._wheel(SimpleNamespace(x=100,y=340,delta=-120))
            self.assertLess(panel.candidate_scroll,32)
            panel._wheel(SimpleNamespace(x=100,y=340,delta=-120))
            panel._wheel(SimpleNamespace(x=100,y=340,delta=-30))
            self.assertIn('candidate-scroll',panel.motion.jobs)
            panel.motion.cancel('candidate-scroll',finish=True)
            self.assertEqual(panel.candidate_scroll,72)
            paths.assert_not_called()
        for _ in range(20):panel._wheel(SimpleNamespace(x=100,y=340,delta=-120))
        panel.motion.cancel('candidate-scroll',finish=True)
        self.assertEqual(panel.candidate_scroll,panel.candidate_content_height-188)
        self.assertNotIn('candidate-scroll',panel.motion.jobs)

    def test_candidate_scroll_motion_can_be_disabled_and_list_shrink_clamps_offset(self):
        from types import SimpleNamespace
        ids=self.candidates();panel=self.app.panel
        panel.motion.enabled=True
        with patch('aram_demo.motion.time.monotonic',return_value=100):
            panel._wheel(SimpleNamespace(x=100,y=340,delta=-120))
            panel.set_motion(False)
        self.assertEqual(panel.candidate_scroll,32)
        self.assertNotIn('candidate-scroll',panel.motion.jobs)
        panel._wheel(SimpleNamespace(x=100,y=340,delta=0))
        self.assertEqual(panel.candidate_scroll,32)
        self.app.on_client_state(ClientState('ChampSelect',222,ids[:2],queue_id=3270))
        self.assertEqual(panel.candidate_scroll,0)
        self.assertNotIn('candidate-scroll',panel.motion.jobs)

    def test_candidate_scroll_survives_repaint_and_reverses_without_old_momentum(self):
        from types import SimpleNamespace
        self.candidates();panel=self.app.panel;panel.motion.enabled=True
        with patch('aram_demo.motion.time.monotonic',return_value=100):
            for _ in range(3):panel._wheel(SimpleNamespace(x=100,y=340,delta=-120))
            panel._move_candidates(12)
            panel.signature=None;self.app.present()
            self.assertIn('candidate-scroll',panel.motion.jobs)
            self.assertAlmostEqual(panel.candidate_scroll,12,places=4)
            panel._wheel(SimpleNamespace(x=100,y=340,delta=120))
            panel.motion.cancel('candidate-scroll',finish=True)
        self.assertEqual(panel.candidate_scroll,0)

    def test_destroyed_widget_images_never_call_tk_from_worker_cleanup(self):
        import threading
        from PIL import ImageTk
        self.game();self.app.show_settings();self.root.update()
        images=[obj for obj in gc.get_objects() if isinstance(obj,ImageTk.PhotoImage) and obj.tk is self.root.tk]
        self.assertTrue(images)
        owners={}
        def visit(widget):
            for image in getattr(widget,'_owned_tk_images',[]):owners[id(image)]=(str(widget),widget.winfo_ismapped())
            for child in widget.winfo_children():visit(child)
        visit(self.root)
        self.app.close()
        self.assertTrue(all(getattr(image,'released',False) for image in images),
                        [(type(image).__name__,owners.get(id(image))) for image in images if not getattr(image,'released',False)])
        errors=[]
        def cleanup():
            try:
                for image in images:image.__del__()
            except Exception as error:errors.append(error)
        with patch.object(ImageTk.PhotoImage,'__del__',side_effect=AssertionError('worker touched Tk')) as native_delete:
            worker=threading.Thread(target=cleanup);worker.start();worker.join(2)
            self.assertFalse(worker.is_alive())
            native_delete.assert_not_called()
        self.assertFalse(errors)

    def test_verified_skill_priority_uses_local_icons_before_remote_metadata_arrives(self):
        import io
        from PIL import Image
        self.game()
        urls={'Q':'https://ddragon.leagueoflegends.com/cdn/16.20.1/img/spell/JinxQ.png',
              'E':'https://ddragon.leagueoflegends.com/cdn/16.20.1/img/spell/JinxE.png'}
        self.app.visual_assets._catalog['champions']['222']['skill_icons']=urls
        image=io.BytesIO();Image.new('RGB',(64,64),'blue').save(image,'PNG')
        with patch.object(self.app.advice_icons,'_download',return_value=image.getvalue()):
            self.app.advice_icons.ensure(urls.values())
        self.app.data=dict(self.app.data,skill_priority=['Q','E'],skill_icons={})
        with patch.object(self.app.advice_icons,'_download',side_effect=AssertionError('must stay offline')):
            self.app.present();self.root.update()
        self.assertTrue(self.app.panel.assets_shown[('skill','Q')])
        self.assertTrue(self.app.panel.assets_shown[('skill','E')])

    def test_failed_advice_images_are_requested_again_after_backoff(self):
        self.game()
        self.app.data['skill_icons']={'Q':'https://game.gtimg.cn/images/lol/act/img/spell/XerathArcanopulseChargeUp.png'}
        pending = []
        self.app.services = True; self.app.auto = False
        self.app.background=lambda job,callback,**kw:pending.append((callback,kw.get('done')))
        self.app.refresh_advice_icons()
        callback,done=pending.pop(0)
        done()
        with patch.object(self.app.advice_icons,'path',return_value=None):
            callback([])
        with patch('aram_demo.companion.time.monotonic', return_value=10**10):
            self.app._tick()
        self.assertTrue(pending)

    def test_source_transition_is_finite_keeps_window_visible_and_can_be_disabled(self):
        self.game()
        self.app.panel.motion.enabled=True
        with patch('aram_demo.motion.time.monotonic', return_value=100):
            self.app.change_source('qq101')
            self.assertIn('source',self.app.panel.motion.jobs)
            self.assertTrue(self.app.panel.visible)
            self.assertEqual(float(self.app.panel.window.attributes('-alpha')),1.)
            self.app.change_source('opgg')
            self.assertIn('source',self.app.panel.motion.jobs)
            self.app.panel.set_motion(False)
            self.assertNotIn('source',self.app.panel.motion.jobs)
            self.assertEqual(float(self.app.panel.window.attributes('-alpha')),1.)

    def test_hero_change_during_reveal_finishes_visibility(self):
        self.app.panel.motion.enabled = True
        with patch('aram_demo.motion.time.monotonic', return_value=100):
            self.app.on_client_state(ClientState('ChampSelect', 222, queue_id=3270))
            self.root.update()
            self.assertIn('visibility', self.app.panel.motion.jobs)
            self.app.on_client_state(ClientState('ChampSelect', 99, queue_id=3270))
            self.root.update()
            self.assertTrue(self.app.panel.visible)
            self.assertAlmostEqual(float(self.app.panel.window.attributes('-alpha')), 1.)

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

    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(dir=Path(__file__).parent)
        self.root=tk.Tk();self.root.design_scale=1
        self.app=CompanionApp(self.root,DataStore(Path(self.tmp.name),seed_root=Path(__file__).resolve().parents[1]/'data'),preview=False,services=False)
        self.app.locate=lambda:LeagueWindow(0,(100,100,1300,900),(0,0,1920,1040),True)
        self.app.panel.set_motion(False);self.app.bubble.set_motion(False)

    def tearDown(self):
        if not self.app.closed:
            for timer in self.root.tk.call('after','info'):
                self.root.after_cancel(timer)
        self.app.close();self.tmp.cleanup()

    def game(self):
        self.app.on_client_state(ClientState('InProgress',222,queue_id=3270,match_id=1))
        self.app.accept_matches(match_slots(['暴击飞弹','魔法飞弹','纯粹主义者 - 术师'],self.app.augments))
        self.root.update()

    def test_same_timestamp_in_place_recommendation_change_repaints(self):
        self.game()
        self.app.data=copy.deepcopy(self.app.data)
        self.app.present()
        stamp=self.app.data.get('fetched_at')
        self.app.data['skill_priority']=['E','Q']
        core=next(row for row in self.app.data['builds'] if row['category']=='核心装备')
        core['items'][0]['name']='实际更新装备'
        self.app.present();self.root.update()
        self.assertEqual(self.app.data.get('fetched_at'),stamp)
        self.assertIn('主 E › 副 Q',self.app.panel.content_text())
        self.assertIn('实际更新装备',self.app.panel.content_text())

    def test_fatal_tray_error_hides_surfaces_before_reporting_and_cannot_remap(self):
        self.game();self.app.show_settings();self.root.update()
        def report(*args,**kwargs):
            self.assertFalse(self.app.panel.visible)
            self.assertFalse(self.app.bubble.visible)
            self.assertFalse(self.app.dialog.winfo_exists())
            self.app.present()
            self.assertFalse(self.app.panel.visible)
        with patch('aram_demo.companion.messagebox.showerror',side_effect=report) as error:
            self.app.tray_failed('injected tray failure')
        error.assert_called_once()
        self.assertTrue(self.app.closed)

    def test_background_cleanup_failure_still_destroys_native_window(self):
        self.game();hwnd=self.app.panel.window.winfo_id()
        self.app.tray=Mock();self.app.tray.stop.side_effect=RuntimeError('injected shutdown failure')
        with self.assertLogs('aram_demo.companion',level='ERROR'):
            self.app.close()
        user=ctypes.WinDLL('user32',use_last_error=True);user.IsWindow.argtypes=[wintypes.HWND]
        self.assertFalse(user.IsWindow(hwnd))
        self.assertTrue(self.app.closed)

    def test_repeated_modes_collapse_and_expand_do_not_accumulate_gui_resources(self):
        self.game();gc.collect()
        images=len(self.root.tk.call('image','names'))
        timers=len(self.root.tk.call('after','info'))
        surfaces=len(self.root.winfo_children())
        for _ in range(25):
            self.app.on_client_state(ClientState('ChampSelect',222,[90,99,222,201,86,17],queue_id=3270))
            self.game()
            self.app.hide();self.root.update()
            self.assertTrue(self.app.bubble.visible)
            self.app.expand();self.root.update()
        gc.collect();self.root.update()
        self.assertEqual(len(self.root.winfo_children()),surfaces)
        self.assertEqual(len(self.root.tk.call('image','names')),images)
        self.assertLessEqual(len(self.root.tk.call('after','info')),timers)
        self.assertTrue(self.app.panel.visible)
        self.assertFalse(self.app.bubble.visible)

if __name__=='__main__':unittest.main()
