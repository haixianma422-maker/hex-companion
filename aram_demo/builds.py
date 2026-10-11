"""Preserve OP.GG's first core build and first boots recommendation."""
import json
from pathlib import Path

CATALOG = json.loads((Path(__file__).resolve().parents[1] / 'data/item_catalog.json').read_text(encoding='utf-8'))['items']


def recommended_items(data, catalog=None):
    catalog = CATALOG if catalog is None else catalog
    builds = (data or {}).get('builds', [])
    core = next((row['items'] for row in builds if row['category'] == '核心装备'), [])
    boots = next((row['items'] for row in builds if row['category'] == '鞋子'), [])
    chosen, seen = [], set()

    def add(item, role):
        iid = item.get('id')
        if not iid or iid in seen or len(chosen) >= 4:
            return
        chosen.append({**item, 'role': role})
        seen.add(iid)

    final_core = [item for item in core if catalog.get(str(item.get('id')), {}).get('complete', True)]
    for item in final_core[:3]:
        meta = catalog.get(str(item.get('id')), {})
        if item.get('name', '').startswith('装备 ') and meta.get('name'):
            item = {**item, 'name': meta['name']}
        add(item, '核心')
    if boots:
        add(boots[0], '鞋子')
    return chosen
