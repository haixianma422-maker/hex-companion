import json
import tempfile
import tkinter as tk
import unittest
from pathlib import Path
from unittest.mock import patch

from aram_demo.cache import DataStore
from aram_demo.companion import CompanionApp
from aram_demo.ui_widgets import PixelButton
from aram_demo.lcu import ClientState
from aram_demo.models import Champion


class SourceCacheTests(unittest.TestCase):
    def test_recent_verified_spells_do_not_wait_for_another_opgg_request(self):
        from datetime import datetime, timezone
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as folder:
            op = DataStore(Path(folder), source='opgg')
            op._write('heroes/86.json', {'champion_id': 86, 'build_mode': 'aram-mayhem',
                      'build_mode_verified': True, 'fetched_at': datetime.now(timezone.utc).isoformat(),
                      'summoner_spells': [{'id': 4, 'name': '闪现'}, {'id': 32, 'name': '标记'}]})
            qq = DataStore(Path(folder), source='qq101')
            with patch('aram_demo.cache.fetch_html', side_effect=AssertionError('unexpected network request')) as network:
                data = {}
                qq._supplement_spells(Champion(86, '盖伦', 'garen', 1, 1), data)
                network.assert_not_called()
            self.assertEqual(data['summoner_spells'][1]['id'], 32)
            self.assertEqual(data['summoner_source'], 'opgg')

    def test_retired_store_cannot_overwrite_current_generation_cache(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as folder:
            old = DataStore(Path(folder))
            old.retire()
            current = DataStore(Path(folder))
            current._write('heroes/86.json', {'generation': 'new'})
            old._write('heroes/86.json', {'generation': 'old'})
            self.assertEqual(current.hero(86), {'generation': 'new'})

    def test_independent_stores_can_write_the_same_cache_concurrently_on_windows(self):
        import threading
        from concurrent.futures import ThreadPoolExecutor
        barrier = threading.Barrier(2)
        def write(store, value):
            barrier.wait(timeout=5)
            for _ in range(5):
                store._write('heroes/86.json', {'value': value})
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as folder:
            stores = [DataStore(Path(folder)), DataStore(Path(folder))]
            with ThreadPoolExecutor(2) as pool:
                futures = [pool.submit(write, store, value)
                           for value, store in enumerate(stores)]
                for future in futures:
                    future.result()
            self.assertIn(stores[0].hero(86), [{'value': 0}, {'value': 1}])

    def test_sources_have_separate_snapshots_and_shared_settings(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as folder:
            op = DataStore(Path(folder), source='opgg')
            qq = DataStore(Path(folder), source='qq101')
            op._write('heroes/86.json', {'source_id': 'opgg', 'skill_priority': ['E', 'Q']})
            qq._write('heroes/86.json', {'source_id': 'qq101', 'skill_priority': ['Q', 'E']})
            qq._write('settings.json', {'data_source': 'qq101'})
            self.assertEqual(op.hero(86)['skill_priority'], ['E', 'Q'])
            self.assertEqual(qq.hero(86)['skill_priority'], ['Q', 'E'])
            self.assertEqual(DataStore(Path(folder)).source, 'qq101')
            self.assertEqual(op.read('settings.json')['data_source'], 'qq101')

    def test_101_cannot_fall_back_to_opgg_seed_under_101_label(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as folder:
            root = Path(folder)
            seed = DataStore(root / 'seed', source='opgg')
            seed._write('heroes/86.json', {'source_id': 'opgg'})
            qq = DataStore(root / 'user', root / 'seed', source='qq101')
            self.assertIsNone(qq.hero(86))

    def test_failed_source_refresh_preserves_previous_cache(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as folder:
            qq = DataStore(Path(folder), source='qq101')
            qq._write('heroes/86.json', {'source_id': 'qq101', 'stat_date': '20261013'})
            before = qq.hero(86)
            with patch('aram_demo.qq101.fetch_hero', side_effect=ValueError('invalid response')):
                with self.assertRaises(ValueError):
                    qq.refresh(Champion(86, '德玛西亚之力', 'garen', 1, 1))
            self.assertEqual(qq.hero(86), before)

    def test_101_missing_spells_use_labeled_verified_opgg_cache_when_offline(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as folder:
            root = Path(folder)
            op = DataStore(root, source='opgg')
            op._write('heroes/86.json', {'champion_id': 86, 'build_mode': 'aram-mayhem',
                      'build_mode_verified': True, 'fetched_at': '2026-10-12T00:00:00Z',
                      'summoner_spells': [{'id': 4, 'name': '闪现'}, {'id': 32, 'name': '标记'}]})
            qq = DataStore(root, source='qq101')
            data = {'source_id': 'qq101', 'champion_id': 86, 'augments': [], 'builds': [],
                    'skill_priority': ['Q', 'E'], 'summoner_spells': []}
            with patch('aram_demo.qq101.fetch_hero', return_value=data), \
                 patch('aram_demo.cache.fetch_html', side_effect=OSError('offline')):
                result = qq.refresh(Champion(86, '德玛西亚之力', 'garen', 1, 1))
            self.assertEqual(result['source_id'], 'qq101')
            self.assertEqual(result['summoner_source'], 'opgg')
            self.assertEqual(result['summoner_spells'][1]['id'], 32)
            self.assertEqual(result['skill_priority'], ['Q', 'E'])


class SourceSwitchTests(unittest.TestCase):
    def test_first_switch_requests_current_hero_without_waiting_for_rank(self):
        jobs = []
        self.app.services = True
        self.app.preview = False
        self.app.background = lambda job, callback, **kw: jobs.append(kw.get('ticket'))
        self.app.change_source('qq101')
        self.assertTrue(any(ticket and ticket[0] == 'hero' and ticket[2] == 86 for ticket in jobs))
        self.assertIsNone(self.app.champions[86].tier)
        self.assertIsNone(self.app.data)

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir=Path(__file__).parent)
        self.root = tk.Tk()
        self.root.design_scale = 1
        self.store = DataStore(Path(self.tmp.name))
        self.store._write('champions.json', {'champions': [
            {'id': 86, 'name': '德玛西亚之力', 'slug': 'garen', 'tier': 1, 'rank': 1}]})
        self.app = CompanionApp(self.root, self.store, preview=True, services=False)
        self.app.on_client_state(ClientState('ChampSelect', 86, queue_id=3270))

    def tearDown(self):
        self.app.close()
        self.tmp.cleanup()

    def test_old_source_hero_response_cannot_replace_new_source(self):
        pending = []
        self.app.background = lambda job, callback, **kwargs: pending.append((callback, kwargs))
        self.app.fetch_hero(86)
        callback, kwargs = pending[0]
        self.app.change_source('qq101')
        self.app.deliver(kwargs.get('ticket'), callback, {'source_id': 'opgg', 'augments': []}, None)
        self.assertEqual(self.app.store.source, 'qq101')
        self.assertIsNone(self.app.data)

    def test_failed_settings_write_does_not_apply_source_selection(self):
        self.app.show_settings()
        self.app.source_var.set('101 数据站')
        with patch.object(self.store, '_write', side_effect=OSError('read-only')):
            def visit(parent):
                for child in parent.winfo_children():
                    yield child
                    yield from visit(child)
            next(w for w in visit(self.app.dialog) if isinstance(w, PixelButton)
                 and w.text == '保存并应用').invoke()
        self.assertEqual(self.app.store.source, 'opgg')
        self.assertTrue(self.app.dialog.winfo_exists())

    def test_settings_save_switches_source_and_persists_it_for_restart(self):
        self.app.show_settings()
        self.app.source_var.set('101 数据站')
        def visit(parent):
            for child in parent.winfo_children():
                yield child
                yield from visit(child)
        next(w for w in visit(self.app.dialog) if isinstance(w, PixelButton)
             and w.text == '保存并应用').invoke()
        self.assertEqual(self.app.store.source, 'qq101')
        self.assertEqual(DataStore(Path(self.tmp.name)).source, 'qq101')

    def test_quick_source_selector_works_and_persists_in_selection_and_game(self):
        for phase, name, source in [('ChampSelect', '101 数据站', 'qq101'), ('InProgress', 'OP.GG', 'opgg')]:
            with self.subTest(phase=phase):
                self.app.on_client_state(ClientState(phase, 86, queue_id=3270))
                self.app.panel.source_picker._choose(0 if source=='opgg' else 1)
                self.root.update()
                self.assertEqual(self.app.store.source, source)
                self.assertEqual(DataStore(Path(self.tmp.name)).source, source)
                self.assertEqual(self.app.panel.quick_source_var.get(), name)

    def test_quick_source_save_failure_keeps_active_source_and_picker(self):
        with patch.object(self.store, '_write', side_effect=OSError('read-only')):
            self.app.panel.source_picker._choose(1)
            self.root.update()
        self.assertEqual(self.app.store.source, 'opgg')
        self.assertEqual(self.app.panel.quick_source_var.get(), 'OP.GG')

    def test_repeated_failed_source_save_restores_the_active_picker_each_time(self):
        with patch.object(self.store, '_write', side_effect=OSError('read-only')):
            for _ in range(2):
                self.app.panel.source_picker._choose(1)
                self.root.update()
                self.assertEqual(self.app.store.source, 'opgg')
                self.assertEqual(self.app.panel.quick_source_var.get(), 'OP.GG')

    def test_source_can_be_switched_while_old_source_worker_is_pending(self):
        pending = []
        self.app.background = lambda job, callback, **kwargs: pending.append((callback, kwargs))
        self.app.fetch_hero(86)
        self.app.panel.source_picker._choose(1)
        self.root.update()
        callback, kwargs = pending[0]
        self.app.deliver(kwargs.get('ticket'), callback, {'source_id': 'opgg', 'augments': []}, None)
        self.assertEqual(self.app.store.source, 'qq101')
        self.assertIsNone(self.app.data)


if __name__ == '__main__':
    unittest.main()
