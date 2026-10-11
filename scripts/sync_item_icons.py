"""Download the small set of icons used by verified cached hero builds."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from aram_demo.builds import recommended_items
from aram_demo.item_icons import ITEM_PATCH, ItemIconCache

cache = ItemIconCache(ROOT / 'data')
ids = set()
for path in (ROOT / 'data/heroes').glob('*.json'):
    hero = json.loads(path.read_text(encoding='utf-8'))
    if hero.get('build_mode_verified') and hero.get('build_mode') == 'aram-mayhem':
        ids.update(item['id'] for item in recommended_items(hero))
updated = cache.ensure(sorted(ids))
missing = [iid for iid in sorted(ids) if cache.path(iid) is None]
manifest = {'patch': ITEM_PATCH, 'source': f'https://ddragon.leagueoflegends.com/cdn/{ITEM_PATCH}/img/item/',
            'items': [iid for iid in sorted(ids) if cache.path(iid)], 'missing': missing}
(ROOT / 'data/item-icons').mkdir(exist_ok=True)
(ROOT / 'data/item-icons/manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
print(json.dumps({'updated': len(updated), 'available': len(ids) - len(missing), 'missing': missing}))
raise SystemExit(1 if missing else 0)
