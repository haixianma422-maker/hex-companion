import json
import tempfile
import tkinter as tk
import unittest
from pathlib import Path
from unittest.mock import patch

from aram_demo import opgg
from aram_demo.cache import DataStore
from aram_demo.companion_state import PanelState
from aram_demo.models import Champion
from aram_demo.panel import CompanionPanel


FIXTURES = Path(__file__).parent / 'fixtures/recommendations'


def flight(value):
    return '<script>self.__next_f.push(' + json.dumps(
        [1, '5a:' + json.dumps(value, ensure_ascii=False) + '\n']) + ')</script>'


def page(slug):
    return flight(json.loads((FIXTURES / (slug + '.json')).read_text(encoding='utf-8'))['rows'])


class RecommendationDataTests(unittest.TestCase):
    def parse(self, html):
        function = getattr(opgg, 'parse_recommendations', None)
        self.assertTrue(callable(function), 'Missing recommendation parser')
        return function(html)

    def test_live_page_rows_keep_skill_priority_and_first_spell_pair(self):
        for slug, priority, spells in [
            ('garen', ['E', 'Q'], [{'id': 4, 'name': '闪现'}, {'id': 32, 'name': '标记'}]),
            ('yuumi', ['Q', 'E'], [{'id': 7, 'name': '治疗术'}, {'id': 14, 'name': '引燃'}]),
            ('jayce', ['Q', 'E'], [{'id': 4, 'name': '闪现'}, {'id': 32, 'name': '标记'}]),
        ]:
            with self.subTest(hero=slug):
                self.assertEqual(self.parse(page(slug)), {
                    'skill_priority': priority, 'summoner_spells': spells})

    def test_absent_rows_do_not_invent_recommendations_from_hero_skill_header(self):
        self.assertEqual(self.parse(flight({'metaType': 'skill', 'extraData': 'Q'})), {
            'skill_priority': [], 'summoner_spells': []})

    def test_invalid_or_duplicate_skills_and_incomplete_spells_are_not_shown(self):
        for order in [('Q', 'Q', 'E'), ('R', 'E', 'W'), ('Q',), ('Q', {}, 'E')]:
            with self.subTest(order=order):
                row = ['$', 'tr', None, {'children': [
                    {'metaType': 'skill', 'extraData': key} for key in order]}]
                self.assertEqual(self.parse(flight(row))['skill_priority'], [])
        for spells in [
            [{'metaType': 'spell', 'metaId': 4, 'children': {'alt': '闪现'}}],
            [{'metaType': 'spell', 'metaId': 4, 'children': {'alt': '闪现'}}] * 2,
            [{'metaType': 'spell', 'metaId': 4, 'children': {'alt': '闪现'}},
             {'metaType': 'spell', 'metaId': 32, 'children': {}}],
        ]:
            self.assertEqual(self.parse(flight(['$', 'tr', None, {'children': spells}]))['summoner_spells'], [])

    def test_refresh_persists_recommendations_with_verified_hero_data(self):
        augment = flight({'id': 1, 'name': '魔法飞弹', 'tier': 0, 'rarity': 4, 'performance': 95})
        build = '<title>海克斯大乱斗</title>' + flight({'isAramMayhem': True}) + page('garen') + flight(
            ['$', 'tr', 'core_items_0', {'children': {'metaType': 'item', 'metaId': 6631, 'children': {'alt': '挺进破坏者'}}}])
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as tmp:
            store = DataStore(Path(tmp))
            with patch('aram_demo.cache.fetch_html', side_effect=[augment, build]):
                store.refresh(Champion(86, '德玛西亚之力', 'garen', 1, 1))
            cached = store.hero(86)
            self.assertEqual(cached.get('skill_priority'), ['E', 'Q'])
            self.assertEqual([(s['id'], s['name']) for s in cached['summoner_spells']], [(4, '闪现'), (32, '标记')])


class RecommendationPanelTests(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tk()
        self.root.withdraw()
        self.panel = CompanionPanel(self.root, lambda: None, lambda: None, lambda: None)
        self.heroes = {86: Champion(86, '德玛西亚之力', 'garen', 1, 1)}
        self.data = {'champion_id': 86, 'build_mode_verified': True, 'build_mode': 'aram-mayhem',
                     'skill_priority': ['E', 'Q'],
                     'summoner_spells': [{'id': 4, 'name': '闪现'}, {'id': 32, 'name': '标记'}]}

    def tearDown(self):
        self.root.destroy()

    def render(self, stage, data=None, cid=86):
        self.panel.render(PanelState(stage=stage, champion_id=cid), self.heroes,
                          self.data if data is None else data, [], '')
        return self.panel.content_text()

    def test_priority_is_game_only_and_spells_are_selection_only(self):
        text = self.render('select')
        self.assertNotIn('主 E › 副 Q', text)
        self.assertEqual([k for k in self.panel.assets_shown if k[0]=='skill'],[])
        self.assertIn('闪现', text)
        self.assertIn('标记', text)
        game = self.render('game')
        self.assertIn('主 E › 副 Q', game)
        self.assertNotIn('召唤师技能', game)
        self.assertNotIn('闪现', game)
        lobby = self.render('lobby')
        self.assertNotIn('召唤师技能', lobby)
        self.assertNotIn('主 E › 副 Q', lobby)

    def test_async_refresh_updates_text_without_rebuilding_panel(self):
        self.render('select', {})
        content = self.panel.canvas
        text = self.render('select')
        self.assertIs(self.panel.canvas, content)
        self.assertNotIn('主 E › 副 Q', text)
        self.assertIn('闪现', text)
        self.assertIn('标记', text)

    def test_missing_unverified_or_other_hero_data_cannot_leave_stale_advice(self):
        for data, cid in [({}, 86), (dict(self.data, build_mode_verified=False), 86),
                          (self.data, 99), (dict(self.data, skill_priority=['Q', 'Q'], summoner_spells=[]), 86)]:
            with self.subTest(data=data, cid=cid):
                self.render('game')
                text = self.render('game', data, cid)
                self.assertNotIn('主 E › 副 Q', text)
                self.assertNotIn('主 Q › 副 Q', text)
                self.assertNotIn('闪现', self.render('select', data, cid))

    def test_skill_tiles_have_key_badges_and_spell_tiles_disappear_in_game(self):
        self.render('select')
        self.assertFalse(any(k[0]=='skill' for k in self.panel.assets_shown))
        self.assertEqual(len([k for k in self.panel.assets_shown if k[0]=='spell']),2)
        self.render('game')
        self.assertEqual([k[1] for k in self.panel.assets_shown if k[0]=='skill'],['E','Q'])
        self.assertFalse(any(k[0]=='spell' for k in self.panel.assets_shown))

    def test_101_source_and_opgg_spell_supplement_are_labeled_separately(self):
        self.panel.source_name = '101 数据站'
        data = dict(self.data, source_id='qq101', summoner_source='opgg',
                    tier_labels={'0': 'S', '1': 'A', '2': 'B', '3': 'C'})
        text = self.render('select', data)
        self.assertIn('101 数据站', text)
        self.assertIn('OP.GG 补充', text)

    def test_icon_cache_is_rendered_without_network_in_render_path(self):
        import io
        from PIL import Image
        from aram_demo.advice_icons import AdviceIconCache
        stream = io.BytesIO()
        Image.new('RGB', (64, 64), '#9911ee').save(stream, format='PNG')
        url = 'https://game.gtimg.cn/images/lol/act/img/spell/GarenE.png'
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as tmp:
            cache = AdviceIconCache(tmp)
            with patch.object(cache, '_download', return_value=stream.getvalue()):
                cache.ensure([url])
            self.panel.advice_icons = cache
            with patch('urllib.request.urlopen', side_effect=AssertionError('GUI attempted network')):
                self.render('game', dict(self.data, skill_icons={'E': url}))
            self.assertTrue(self.panel.assets_shown[('skill','E')])
            self.render('game', dict(self.data, skill_priority=['Q', 'E']))
            self.render('game', self.data)
            self.assertEqual([k[1] for k in self.panel.assets_shown if k[0]=='skill'],['E','Q'])


if __name__ == '__main__':
    unittest.main()
