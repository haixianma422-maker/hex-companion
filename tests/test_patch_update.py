"""New game versions: version-aware hero snapshots, the unrated title catalog and placeholder rows."""
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from aram_demo import opgg, qq101
from aram_demo.cache import DataStore, is_current, patch_key
from aram_demo.companion_state import PanelState
from aram_demo.lcu import ClientState
from aram_demo.models import Augment, Champion, is_placeholder_name
from aram_demo.recognition import match_slots, with_catalog
from tests.qt_support import close_companion, new_companion

SEED = Path(__file__).resolve().parents[1] / 'data'


def flight(value):
    chunk = '5a:' + json.dumps(value, ensure_ascii=False) + '\n'
    return '<script>self.__next_f.push(' + json.dumps([1, chunk]) + ')</script>'


def now(days=0):
    return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()


class PatchFreshnessTests(unittest.TestCase):
    def test_patch_key_compares_major_minor_across_source_formats(self):
        self.assertEqual(patch_key('16.21.1'), (16, 21))
        self.assertEqual(patch_key('16.21'), (16, 21))
        self.assertGreater(patch_key('16.21'), patch_key('16.20.1'))
        self.assertIsNone(patch_key(None))
        self.assertIsNone(patch_key('unknown'))

    def test_recent_snapshot_from_older_patch_is_not_current(self):
        hero = {'patch': '16.20.1', 'fetched_at': now()}
        self.assertTrue(is_current(hero, '16.20.1'))
        self.assertTrue(is_current(hero, '16.20'))
        self.assertFalse(is_current(hero, '16.21.1'))
        self.assertFalse(is_current(dict(hero, fetched_at=now(2)), '16.20.1'))
        self.assertFalse(is_current(None, '16.21.1'))

    def test_unknown_versions_fall_back_to_age(self):
        self.assertTrue(is_current({'fetched_at': now()}, '16.21.1'))
        self.assertTrue(is_current({'patch': '16.20.1', 'fetched_at': now()}, None))


class PlaceholderTests(unittest.TestCase):
    def test_internal_keys_are_placeholders_but_titles_are_not(self):
        self.assertTrue(is_placeholder_name('GoH_PentakillAug_Generic_BlankName'))
        for title in ('力量', '？？？', '小蜜蜂！！！', 'ADAPt', '鼓声暴起 低音轰鸣'):
            self.assertFalse(is_placeholder_name(title), title)

    def test_opgg_skips_placeholder_rows(self):
        page = flight(['$', 'component', None, {'data': [
            {'id': 3001, 'name': '死之舞', 'tier': 0, 'rarity': 8, 'performance': 60},
            {'id': 3002, 'name': 'GoH_PentakillAug_Generic_BlankName', 'tier': 2, 'rarity': 4, 'performance': 50},
        ]}])
        self.assertEqual([a.id for a in opgg.parse_augments(page)], [3001])


class CatalogTests(unittest.TestCase):
    ROWS = [
        {'augmentID': 1001, 'name_cn': '泰坦的坚决', 'mode': 'KIWI, KIWI_JADE', 'level': 'kPrismatic', 'isPBE': 0},
        {'augmentID': 3001, 'name_cn': '死之舞', 'mode': 'KIWI', 'level': 'kPrismatic', 'isPBE': 0},
        {'augmentID': 3002, 'name_cn': '单曲红人', 'mode': 'KIWI', 'level': 'kGold', 'isPBE': 1},
        {'augmentID': 3003, 'name_cn': '慢炖', 'mode': '', 'level': 'kPrismatic', 'isPBE': 0},
        {'augmentID': 3004, 'name_cn': '竞技场专属', 'mode': 'CHERRY', 'level': 'kGold', 'isPBE': 0},
        {'augmentID': 3005, 'name_cn': 'GoH_PentakillAug_Generic_BlankName', 'mode': 'KIWI', 'level': 'kGold', 'isPBE': 0},
        {'augmentID': 3006, 'name_cn': '力量', 'mode': 'KIWI', 'level': 'kGold', 'isPBE': 0},
        {'augmentID': 3007, 'name_cn': '', 'mode': 'KIWI', 'level': 'kGold', 'isPBE': 0},
    ]

    def test_catalog_keeps_live_mayhem_titles_without_ratings(self):
        rows = qq101.catalog_augments(self.ROWS)
        self.assertEqual([(a.id, a.tier, a.rarity) for a in rows], [(1001, None, 8), (3001, None, 8), (3006, None, 4)])

    def test_store_never_reads_ratings_from_catalog(self):
        with tempfile.TemporaryDirectory() as directory:
            store = DataStore(Path(directory), source='opgg')
            store._write('augment_catalog.json', {'augments': [{'id': 3001, 'name': '死之舞', 'tier': 0, 'rarity': 8}]})
            self.assertEqual(store.augment_catalog(), [Augment(3001, '死之舞', None, 8)])
            with patch.object(qq101, 'fetch_json', return_value=self.ROWS):
                data = store.refresh_augment_catalog()
            self.assertEqual(len(data['augments']), 3)
            self.assertEqual(store.read('augment_catalog.json')['source'], qq101.AUGMENTS)

    def test_rated_source_wins_and_duplicate_titles_stay_unambiguous(self):
        rated = [Augment(1001, '泰坦的坚决', 2, 8)]
        catalog = [Augment(1001, '泰坦的坚决', None, 8), Augment(9001, '泰坦的 坚决', None, 8),
                   Augment(3001, '死之舞', None, 8)]
        merged = with_catalog(rated, catalog)
        self.assertEqual([(a.id, a.tier) for a in merged], [(1001, 2), (3001, None)])
        rows = match_slots(['泰坦的坚决', '死之舞', ''], merged)
        self.assertEqual([(r.augment_id, r.status) for r in rows[:2]], [(1001, 'matched'), (3001, 'matched')])

    def test_new_titles_with_spaces_or_short_names_match_safely(self):
        augments = [Augment(3010, '鼓声暴起 低音轰鸣', None, 4), Augment(3006, '力量', None, 4),
                    Augment(3011, '厄运', None, 4)]
        rows = match_slots(['鼓声暴起\n低音轰鸣', '力量\n伤害', '力最'], augments)
        self.assertEqual([r.augment_id for r in rows], [3010, 3006, None])
        self.assertNotEqual(rows[2].status, 'matched')

    def test_titles_differing_only_by_punctuation_are_told_apart(self):
        # 26.21 added 罪恶快感！ (Get Jinxed) beside 罪恶快感 (Get Excited); both are offered to one hero.
        augments = [Augment(1322, '罪恶快感', 3, 4), Augment(3004, '罪恶快感！', 1, 4)]
        rows = match_slots(['罪恶快感！\n功能', '罪恶快感', '罪恶快感!'], augments)
        self.assertEqual([(r.augment_id, r.status) for r in rows],
                         [(3004, 'matched'), (1322, 'matched'), (3004, 'matched')])
        unclear = match_slots(['罪恶快感？'], augments)[0]
        self.assertEqual((unclear.augment_id, unclear.status, sorted(unclear.candidates)), (None, 'ambiguous', [1322, 3004]))
        self.assertEqual([a.id for a in with_catalog([augments[0]], [augments[1]])], [1322, 3004])


class CompanionPatchTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.app = new_companion(DataStore(Path(self.tmp.name), SEED, source='opgg'))

    def tearDown(self):
        close_companion(self.app)
        self.tmp.cleanup()

    def online(self):
        self.app.services, self.app.preview = True, False
        self.app.state = PanelState('select', 'ChampSelect', 222, queue_id=2400)
        self.addCleanup(setattr, self.app, 'services', False)
        self.addCleanup(setattr, self.app, 'preview', True)

    def test_recent_snapshot_from_previous_patch_is_refetched(self):
        self.online()
        hero = dict(self.app.store.hero(222), patch='16.20.1', fetched_at=now())
        with patch.object(self.app, 'fetch_hero') as fetch, patch.object(self.app.store, 'hero', return_value=hero), \
             patch.object(self.app, 'refresh_icons'), patch.object(self.app, 'refresh_visual_assets'):
            with patch.object(self.app.store, 'index_patch', return_value='16.20.1'):
                self.app.load_data()
            fetch.assert_not_called()
            with patch.object(self.app.store, 'index_patch', return_value='16.21.1'):
                self.app.load_data()
            fetch.assert_called_once_with(222)

    def test_index_from_new_patch_retires_loaded_hero(self):
        self.online()
        self.app.data = dict(self.app.store.hero(222), patch='16.20.1', fetched_at=now())
        jobs = []
        self.app.background = lambda job, callback, **kw: jobs.append((job, callback))
        jinx = Champion(222, '暴走萝莉', 'jinx', 1, 1)
        with patch.object(self.app, 'refresh_catalog'), patch.object(self.app, 'fetch_hero') as fetch, \
             patch.object(self.app.store, 'champions', return_value=[jinx]):
            self.app.refresh_index()
            jobs[0][1]({'patch': '16.20.1'})
            fetch.assert_not_called()
            jobs[0][1]({'patch': '16.21.1'})
            fetch.assert_called_once_with(222)

    def test_unrated_new_augment_is_named_instead_of_pending(self):
        # A title the source cannot have rated, whatever the shipped snapshot holds.
        self.app.catalog = [Augment(99001, '尚无评级的新海克斯', None, 8)]
        self.app.panel.catalog = {99001: self.app.catalog[0]}
        self.app.on_client_state(ClientState('InProgress', 222, queue_id=2400, match_id=1))
        self.assertNotIn(99001, {a['id'] for a in self.app.data['augments']})
        self.app.accept_matches(match_slots(['尚无评级的新海克斯', '暴击飞弹', ''], self.app.augments))
        self.assertEqual([m.augment_id for m in self.app.matches[:2]], [99001, 1356])
        text = self.app.panel.content_text()
        self.assertIn('尚无评级的新海克斯', text)
        self.assertIn('暂无评级', text)
        self.assertIn('已识别 2 / 3', text)

    def test_catalog_refresh_updates_titles_and_failure_is_silent(self):
        jobs = []
        self.app.background = lambda job, callback, **kw: jobs.append((job, callback, kw.get('done')))
        self.app.status = '保持不变'
        rows = [{'augmentID': 3001, 'name_cn': '死之舞', 'mode': 'KIWI', 'level': 'kPrismatic', 'isPBE': 0}]
        with patch.object(self.app.store, 'read', return_value={'fetched_at': now(2)}):
            self.app.refresh_catalog()
            self.app.refresh_catalog()
        self.assertEqual(len(jobs), 1)
        job, callback, done = jobs.pop()
        with patch.object(qq101, 'fetch_json', return_value=rows):
            callback(job())
        done()
        self.assertEqual(self.app.catalog, [Augment(3001, '死之舞', None, 8)])
        self.assertIn(3001, self.app.panel.catalog)
        self.assertIn(3001, {a.id for a in self.app.augments})
        with patch.object(self.app.store, 'read', return_value=None):
            self.app.refresh_catalog()
        job, callback, done = jobs.pop()
        with patch.object(qq101, 'fetch_json', side_effect=OSError('offline')):
            callback(job())
        self.assertEqual(self.app.status, '保持不变')
        self.assertEqual(len(self.app.catalog), 1)

    def test_fresh_catalog_is_not_refetched(self):
        with patch.object(self.app, 'background') as background, \
             patch.object(self.app.store, 'read', return_value={'fetched_at': now()}):
            self.app.refresh_catalog()
        background.assert_not_called()


if __name__ == '__main__':
    unittest.main()
