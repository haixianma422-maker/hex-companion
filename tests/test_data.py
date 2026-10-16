import importlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


def flight(value):
    chunk = '5a:' + json.dumps(value, ensure_ascii=False) + '\n'
    return '<script>self.__next_f.push(' + json.dumps([1, chunk]) + ')</script>'


class DataTests(unittest.TestCase):
    def recommended_items(self, *args):
        function = getattr(self.module('builds'), 'recommended_items', None)
        self.assertTrue(callable(function), 'Source-only core plus boots recommendation is not implemented')
        return function(*args)

    def module(self, name):
        try:
            return importlib.import_module('aram_demo.' + name)
        except ImportError:
            self.fail('Missing implementation: ' + name)

    def test_candidates_sort_by_tier_then_rank_and_unknown_last(self):
        m = self.module('models')
        heroes = [m.Champion(1, '未知', 'unknown', None, None),
                  m.Champion(2, '乙', 'b', 2, 10),
                  m.Champion(3, '甲', 'a', 1, 20),
                  m.Champion(4, '丙', 'c', 2, 5)]
        self.assertEqual([x.id for x in m.sort_champions(heroes)], [3, 4, 2, 1])

    def test_champion_ids_and_slugs_are_taken_from_source(self):
        op = self.module('opgg')
        page = flight(['$', 'component', None, {'champions': [
            {'champion_id': 62, 'id': 62, 'name': '齐天大圣', 'key': 'monkeyking', 'tier': 2, 'rank': 23}
        ]}])
        result = op.parse_champions(page)
        self.assertEqual((result[0].id, result[0].slug, result[0].tier), (62, 'monkeyking', 2))

    def test_empty_augment_names_are_excluded_without_changing_tier(self):
        op = self.module('opgg')
        page = flight(['$', 'component', None, {'data': [
            {'id': 10, 'name': '暴击飞弹', 'tier': 0, 'rarity': 4, 'performance': 95.71, 'popular': 7.43},
            {'id': 11, 'name': None, 'tier': 5, 'rarity': 1, 'performance': 60, 'popular': 0}
        ]}])
        rows = op.parse_augments(page)
        self.assertEqual([(r.id, r.name, r.tier, r.rarity) for r in rows], [(10, '暴击飞弹', 0, 4)])

    def test_missing_payload_is_not_treated_as_empty_success(self):
        op = self.module('opgg')
        with self.assertRaises(ValueError):
            op.parse_champions('<html>maintenance</html>')
        with self.assertRaises(ValueError):
            op.parse_augments('<html>maintenance</html>')

    def test_core_items_preserve_source_order(self):
        op = self.module('opgg')
        def item(i, name):
            return ['$', 'item', None, {'metaType': 'item', 'metaId': i,
                    'children': ['$', 'img', None, {'alt': name}]}]
        page = flight(['$', 'tr', 'core_items_0', {'children': [item(3032, '育恩塔尔荒野箭'), item(3085, '卢安娜的飓风')]}])
        build = op.parse_builds(page)[0]
        self.assertEqual([x['id'] for x in build.items], [3032, 3085])
        self.assertEqual(build.category, '核心装备')

    def test_mayhem_build_verification_rejects_normal_aram_or_missing_mode_marker(self):
        op = self.module('opgg')
        marker = flight(['$', 'component', None, {'type': 'aram', 'isAramMayhem': True}])
        good = '<title>暴走萝莉「海克斯大乱斗」模式的出装 | OP.GG</title>' + marker
        self.assertTrue(op.verify_mayhem_page(good, op.BASE + '/jinx/build'))
        self.assertFalse(op.verify_mayhem_page(good, 'https://op.gg/zh-cn/lol/modes/aram/jinx/build'))
        self.assertFalse(op.verify_mayhem_page('<title>普通大乱斗</title>' + marker, op.BASE + '/jinx/build'))
        self.assertFalse(op.verify_mayhem_page('<title>海克斯大乱斗</title>', op.BASE + '/jinx/build'))

    def test_refresh_keeps_verified_mayhem_core_instead_of_item_page_override(self):
        cache, op, models = self.module('cache'), self.module('opgg'), self.module('models')
        def item(i, name):
            return ['$', 'component', None, {'metaType': 'item', 'metaId': i, 'children': {'alt': name}}]
        mode = '<title>海克斯大乱斗</title>' + flight({'isAramMayhem': True})
        augment = flight({'id': 1, 'name': '魔法飞弹', 'tier': 0, 'rarity': 4, 'performance': 95})
        build = mode + flight(['$', 'tr', 'core_items_0', {'children': [item(1, '模式核心')]}])
        items = mode + flight([
            ['$', 'section', None, {'children': [{'children': '核心装备'}, {'metaBuildItems': [{'id': 2, 'name': '另一组合'}]}]}],
            ['$', 'section', None, {'children': [{'children': '装备'}, {'metaItem': {'id': 3, 'name': '后续装备'}}]}]])
        with tempfile.TemporaryDirectory() as tmp:
            store = cache.DataStore(Path(tmp))
            with patch('aram_demo.cache.fetch_html', side_effect=[augment, build, items]) as fetch:
                result = store.refresh(models.Champion(222, '暴走萝莉', 'jinx', 1, 1))
            self.assertTrue(result['build_mode_verified'])
            self.assertEqual(result['build_mode'], 'aram-mayhem')
            core = next(r for r in result['builds'] if r['category'] == '核心装备')
            self.assertEqual(core['items'][0]['id'], 1)
            self.assertEqual(fetch.call_count, 2)
            self.assertFalse(any(row['category'] == '后续装备' for row in result['builds']))

    def test_failed_refresh_preserves_cache_bytes(self):
        cache = self.module('cache')
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            old = {'fetched_at': '2026-10-10T00:00:00Z', 'source': 'https://op.gg', 'champions': [
                {'id': 222, 'name': '暴走萝莉', 'slug': 'jinx', 'tier': 1, 'rank': 8}]}
            p = root / 'champions.json'
            p.write_text(json.dumps(old), encoding='utf-8')
            before = p.read_bytes()
            store = cache.DataStore(root)
            with patch('aram_demo.cache.fetch_html', side_effect=OSError('offline')):
                with self.assertRaises(OSError):
                    store.refresh(None)
            self.assertEqual(p.read_bytes(), before)
            self.assertEqual(store.champions()[0].id, 222)
            self.assertIsNone(store.hero(999))

    def test_failed_serialization_leaves_no_temporary_file(self):
        cache = self.module('cache')
        with tempfile.TemporaryDirectory() as tmp:
            store = cache.DataStore(Path(tmp))
            with self.assertRaises(TypeError):
                store._write('champions.json', {'bad': object()})
            self.assertEqual(list(Path(tmp).iterdir()), [])

    def test_snapshot_freshness_requires_recent_aware_timestamp(self):
        from datetime import datetime, timedelta, timezone
        is_fresh = self.module('cache').is_fresh
        now = datetime.now(timezone.utc)
        self.assertTrue(is_fresh({'fetched_at': now.isoformat()}))
        self.assertTrue(is_fresh({'fetched_at': now.isoformat().replace('+00:00', 'Z')}))
        self.assertFalse(is_fresh({'fetched_at': (now - timedelta(days=2)).isoformat()}))
        self.assertFalse(is_fresh({'fetched_at': '2026-10-16T00:00:00'}))
        self.assertFalse(is_fresh({}))
        self.assertFalse(is_fresh(None))

    def test_oversized_page_is_rejected_instead_of_truncated(self):
        opgg = self.module('opgg')
        response = unittest.mock.MagicMock()
        response.__enter__.return_value.read.return_value = b'a' * 6_000_001
        with patch('aram_demo.opgg.urllib.request.urlopen', return_value=response) as urlopen:
            with self.assertRaises(ValueError):
                opgg.fetch_html(opgg.BASE)
        self.assertEqual(urlopen.call_args[0][0].get_header('User-agent'), 'HexCompanion/1.0')

    def test_corrupt_cache_does_not_crash_startup(self):
        cache = self.module('cache')
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / 'champions.json').write_text('{broken', encoding='utf-8')
            store = cache.DataStore(Path(tmp))
            self.assertEqual(store.champions(), [])
            self.assertTrue(store.last_error)

    def test_item_page_sections_keep_core_boots_and_popular_items_distinct(self):
        op = self.module('opgg')
        def section(title, rows):
            return ['$', 'section', None, {'children': [
                ['$', 'div', None, {'children': title}],
                ['$', 'component', None, {'data': rows}]]}]
        page = flight([section('核心装备', [{'metaBuildItems': [{'id': 1, 'name': '核心'}]}]),
                       section('鞋子', [{'metaItem': {'id': 2, 'name': '鞋子'}}]),
                       section('装备', [{'metaItem': {'id': 3, 'name': '后续'}, 'pick_rate': 20}])])
        rows = op.parse_item_options(page)
        self.assertEqual([r.category for r in rows], ['核心装备', '鞋子', '后续装备'])
        self.assertEqual(rows[2].items[0]['id'], 3)

    def test_mode_build_preserves_three_source_core_items_and_one_boot_only(self):
        recommended_items = self.recommended_items
        data = {'builds': [{'category': '核心装备', 'items': [{'id': i, 'name': str(i)} for i in (1, 2, 3)]},
                           {'category': '鞋子', 'items': [{'id': 4, 'name': '鞋子'}]},
                           {'category': '后续装备', 'items': [{'id': i, 'name': str(i)} for i in (1, 9, 5, 6)]}]}
        catalog = {str(i): {'complete': i != 9, 'crit': 0, 'groups': []} for i in range(1, 10)}
        items = recommended_items(data, catalog)
        self.assertEqual([i['id'] for i in items], [1, 2, 3, 4])
        self.assertEqual([i['role'] for i in items], ['核心', '核心', '核心', '鞋子'])
        self.assertEqual(len(recommended_items({'builds': data['builds'][:1]}, catalog)), 3)

    def test_missing_core_slots_are_not_filled_from_popular_items(self):
        recommended_items = self.recommended_items
        data = {'builds': [{'category': '核心装备', 'items': [{'id': 1, 'name': '核心'}]},
                           {'category': '鞋子', 'items': [{'id': 4, 'name': '鞋'}]},
                           {'category': '后续装备', 'items': [{'id': i, 'name': str(i)} for i in (2, 3, 5)]}]}
        catalog = {'1': {'complete': True, 'crit': 1, 'groups': ['last_whisper']},
                   '2': {'complete': True, 'crit': 0, 'groups': ['last_whisper']},
                   '3': {'complete': True, 'crit': .25, 'groups': []},
                   '5': {'complete': True, 'crit': 0, 'groups': []}}
        self.assertEqual([i['id'] for i in recommended_items(data, catalog)], [1, 4])

    def test_boots_can_be_shown_even_when_source_core_is_unavailable(self):
        recommended_items = self.recommended_items
        self.assertEqual(recommended_items({'builds': [{'category': '鞋子', 'items': [{'id': 4, 'name': '鞋'}]}]}, {})[0]['id'], 4)


if __name__ == '__main__':
    unittest.main()
