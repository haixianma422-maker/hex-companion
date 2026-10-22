"""101's official payloads and small adversarial inputs, without network access."""
import copy
import importlib.util
import json
from datetime import datetime, timezone
from pathlib import Path

import unittest
from unittest.mock import patch

from aram_demo.models import Champion

FIXTURES = Path(__file__).parent / 'fixtures' / 'qq101'


def load(name):
    return json.loads((FIXTURES / f'{name}.json').read_text(encoding='utf-8'))


def hero_fields(payloads):
    return json.loads(next(iter(payloads['fuwen_hero_rank']['data']['_fieldValues'].values())))


def replace_fields(payloads, fields):
    payloads['fuwen_hero_rank']['data']['_fieldValues'] = {'fixture': json.dumps(fields)}


GAREN = Champion(86, '盖伦', 'garen', None, None)


class ProviderTests(unittest.TestCase):
    def test_verified_ratings_arrive_before_optional_metadata_finishes(self):
        import threading
        ready, release = threading.Event(), threading.Event()
        errors, early = [], []
        def fetch(url):
            if url.endswith('items.js'):
                release.wait(3)
            return self.fetch(url)
        def receive(data):
            early.append(data)
            ready.set()
        def work():
            try:
                self.qq.fetch_hero(GAREN, on_ready=receive)
            except Exception as error:
                errors.append(error)
        with patch.object(self.qq, 'fetch_json', side_effect=fetch):
            worker = threading.Thread(target=work); worker.start()
            try:
                self.assertTrue(ready.wait(1), str(errors))
                self.assertTrue(worker.is_alive())
                self.assertEqual(len(early[0]['augments']), 138)
                self.assertEqual(early[0]['skill_priority'], ['Q', 'E'])
            finally:
                release.set(); worker.join(4)
        self.assertEqual(errors, [])

    def test_independent_hero_requests_overlap(self):
        import threading
        barrier = threading.Barrier(4)
        def fetch(url):
            barrier.wait(timeout=2)
            return self.fetch(url)
        with patch.object(self.qq, 'fetch_json', side_effect=fetch):
            result = self.qq.fetch_hero(GAREN)
        self.assertEqual(len(result['augments']), 138)

    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec('aram_demo.qq101'), '101 provider is missing')
        from aram_demo import qq101
        self.qq = qq101
        qq101._metadata_text.cache_clear()
        self.payloads = {'hero_list.js': load('hero_list'), 'kiwi_augments.json': load('augments'),
                         '86.js': load('hero86'), 'items.js': load('items'), 'fuwen_hero_rank': load('garen')}
        self.fetch_patch = patch.object(qq101, 'fetch_json', side_effect=self.fetch)
        self.fetch_patch.start()
        self.addCleanup(self.fetch_patch.stop)
        self.addCleanup(qq101._metadata_text.cache_clear)

    def fetch(self, url):
        key = url.split('?')[0].rsplit('/', 1)[-1]
        if key not in self.payloads:
            raise ValueError('No data for this statistics date')
        return copy.deepcopy(self.payloads[key])

    def test_garen_preserves_source_sabc_and_frontend_default_recommendations(self):
        qq = self.qq
        result = qq.fetch_hero(GAREN)
        assert result['champion_id'] == 86
        assert result['source_id'] == 'qq101'
        assert result['source_name'] == '101 数据站'
        assert result['tier_labels'] == {'0': 'S', '1': 'A', '2': 'B', '3': 'C'}
        assert result['augments'][0] == {'id': 1214, 'name': '旋转至胜', 'tier': 0, 'rarity': 1}
        rarity = {a['id']: a['rarity'] for a in result['augments']}
        assert rarity[1401] == 4
        assert rarity[1041] == 8
        assert {a['tier'] for a in result['augments']} == {0, 1, 2, 3}
        assert len(result['augments']) == 138
        assert result['skill_priority'] == ['Q', 'E']
        assert result['skill_icons']['Q'] == 'https://game.gtimg.cn/images/lol/act/img/spell/GarenQ.png'
        assert [[i['id'] for i in b['items']] for b in result['builds']] == [[6631, 3046, 3036], [3006]]
        assert [b['category'] for b in result['builds']] == ['核心装备', '鞋子']
        assert result['summoner_spells'] == []
        assert result['build_mode_verified'] is True
        assert result['build_mode'] == 'aram-mayhem'
        assert 'fuwen_hero_rank' in result['build_source']
        assert result['patch'] == '16.20'
        assert result['stat_date'] == '20261013'


    def test_invalid_required_augments_fail_without_fabricating_grades(self):
        for bad in ['', 'kGold:1|86|1214|255|0.1|S', '255:1|22|1214|255|0.1|S',
                    '255:1|86|1214|255|0.1', '255:1|86|1214|255|0.1|D',
                    '255:1|86|999999|255|0.1|S', '255:bad']:
            with self.subTest(payload=bad):
                fields = hero_fields(self.payloads)
                fields['augment_json_irank'] = bad
                replace_fields(self.payloads, fields)
                with self.assertRaises(ValueError):
                    self.qq.fetch_hero(GAREN)

    def test_augments_retired_after_the_statistics_day_are_skipped(self):
        # 26.21: 101's 10-21 statistics still rated augments its dictionary had dropped.
        fields = hero_fields(self.payloads)
        fields['augment_json_irank'] = '255:1|86|1214|255|0.1|S#2|86|999999|255|0.1|A'
        replace_fields(self.payloads, fields)
        assert [a['id'] for a in self.qq.fetch_hero(GAREN)['augments']] == [1214]
        for bad in ['255:1|86|1214|255|0.1|S#2|86|1214|255|0.1|A', '255:1|86|999999|255|0.1|S#2|86|999999|255|0.1|A']:
            with self.subTest(duplicate=bad):
                fields['augment_json_irank'] = bad
                replace_fields(self.payloads, fields)
                with self.assertRaises(ValueError):
                    self.qq.fetch_hero(GAREN)

    def test_business_errors_are_not_successful_empty_heroes(self):
        for payload in [{'code': 0, 'data': None}, {'code': 1, 'data': {'_fieldValues': {'x': '{}'}}},
                        {'code': 0, 'data': {'_fieldValues': {'x': 'not json'}}}]:
            with self.subTest(payload=payload):
                self.payloads['fuwen_hero_rank'] = payload
                with self.assertRaises(ValueError):
                    self.qq.fetch_hero(GAREN)

    def test_optional_missing_recommendations_still_return_real_augments(self):
        qq, payloads = self.qq, self.payloads
        fields = hero_fields(payloads)
        for key in ('skill_json', 'itemcore_json', 'itemshoes'):
            fields.pop(key, None)
        replace_fields(payloads, fields)
        payloads['86.js'] = {}
        payloads['items.js'] = {}
        result = qq.fetch_hero(GAREN)
        assert result['augments']
        assert result['skill_priority'] == []
        assert result['skill_icons'] == {}
        assert result['builds'] == []


    def test_all_group_uses_supplied_letter_and_ignores_alternative_groups(self):
        qq, payloads = self.qq, self.payloads
        fields = hero_fields(payloads)
        fields['augment_json_irank'] = '255:1|86|1214|255|0.9|C&kGold:1|86|1214|kGold|0.99|S'
        replace_fields(payloads, fields)
        assert qq.fetch_hero(GAREN)['augments'][0]['tier'] == 3


    def test_malformed_optional_metadata_does_not_hide_valid_augments(self):
        self.payloads['86.js'] = {'spells': None}
        self.payloads['items.js'] = {'items': None}
        result = self.qq.fetch_hero(GAREN)
        assert len(result['augments']) == 138
        assert result['skill_icons'] == {}


    def test_core_equal_win_rates_retain_source_order(self):
        fields = hero_fields(self.payloads)
        fields['itemcore_json'] = json.dumps({'1': {'itemcore': '3031&3046&6631', 'winrate': 5100},
                                              '2': {'itemcore': '3036&3046&6631', 'winrate': 5100}})
        replace_fields(self.payloads, fields)
        assert [i['id'] for i in self.qq.fetch_hero(GAREN)['builds'][0]['items']] == [3031, 3046, 6631]


    def test_role_specific_tiers_follow_frontend_percentage_boundaries_and_best_role(self):
        qq, payloads = self.qq, self.payloads
        # 10 fighters: 1=>T0, 2=>T1, 3=>T2, 4=>T3, rest=>T4.
        # Mage index 1 promotes hero 8 to T0, preserving API rank within role buckets.
        payloads['hero_list.js'] = {'version': '16.20', 'hero': [
            {'heroId': str(i), 'title': f'英雄{i}', 'alias': f'Hero{i}', 'roles': ['fighter'] + (['mage'] if i == 8 else [])}
            for i in range(1, 11)]}
        payloads['fuwen_aram_hero_rank_v2'] = {'code': 0, 'data': {'_fieldValues': {'x': json.dumps({
            'dtstatdate': '20261013', 'listcollect': '#'.join(f'{i}_{i}_0_0.5_0.1' for i in range(1, 11))})}}}
        result = qq.fetch_champions()
        rows = {c['id']: c for c in result['champions']}
        assert [rows[i]['tier'] for i in (1, 2, 3, 4, 5, 8)] == [0, 1, 2, 3, 4, 0]
        assert [rows[i]['rank'] for i in (1, 8, 2)] == [1, 2, 3]
        assert rows[8]['name'] == '英雄8'
        assert rows[8]['slug'] == 'hero8'
        assert result['stat_date'] == '20261013'


    def test_statistics_dates_use_china_yesterday_and_bounded_fallback(self):
        from aram_demo import qq101
        now = datetime(2026, 10, 14, 16, 30, tzinfo=timezone.utc)
        dates = qq101.statistics_dates(now)
        assert dates == ['20261014', '20261013', '20261012', '20261011', '20261010', '20261009', '20261008']


    def test_rank_tries_an_older_statistics_date_when_latest_has_no_data(self):
        qq, payloads = self.qq, self.payloads
        valid = {'code': 0, 'data': {'_fieldValues': {'x': json.dumps({'listcollect': '86_1_0_0.5_0.1', 'dtstatdate': '20261012'})}}}
        def fetch(url):
            if 'fuwen_aram_hero_rank_v2' in url:
                return valid if 'dtstatdate=20261012' in url else {'code': 0, 'data': None}
            return self.fetch(url)
        with patch.object(qq, 'statistics_dates', return_value=['20261013', '20261012']), \
                patch.object(qq, 'fetch_json', side_effect=fetch):
            result = qq.fetch_champions()
        assert result['stat_date'] == '20261012'
        assert result['champions'][0]['id'] == 86
