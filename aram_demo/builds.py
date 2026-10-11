"""A transparent six-slot reference assembled from OP.GG item choices."""
import json
from pathlib import Path

CATALOG = json.loads((Path(__file__).resolve().parents[1] / 'data/item_catalog.json').read_text(encoding='utf-8'))['items']


def six_item_reference(data, catalog=None):
    catalog = CATALOG if catalog is None else catalog
    builds = (data or {}).get('builds', [])
    core = next((row['items'] for row in builds if row['category'] == '核心装备'), [])
    boots = next((row['items'] for row in builds if row['category'] == '鞋子'), [])
    chosen, seen, groups = [], set(), set()
    crit = 0

    def add(item, role, filtered=False):
        nonlocal crit
        iid = item.get('id')
        meta = catalog.get(str(iid), {})
        item_groups = set(meta.get('groups', []))
        item_crit = meta.get('crit', 0)
        if not iid or iid in seen or len(chosen) >= 6:
            return
        if filtered and (not meta.get('complete') or groups & item_groups or crit + item_crit > 1.001):
            return
        chosen.append({**item, 'role': role})
        seen.add(iid)
        groups.update(item_groups)
        crit += item_crit

    final_core = [item for item in core if catalog.get(str(item.get('id')), {}).get('complete', True)]
    for item in final_core[:3]:
        meta = catalog.get(str(item.get('id')), {})
        if item.get('name', '').startswith('装备 ') and meta.get('name'):
            item = {**item, 'name': meta['name']}
        add(item, '核心')
    if core and boots:
        add(boots[0], '鞋子')
    if core:
        for row in builds:
            if row['category'] == '后续装备':
                for item in row['items']:
                    add(item, '后续参考', filtered=True)
    return chosen
