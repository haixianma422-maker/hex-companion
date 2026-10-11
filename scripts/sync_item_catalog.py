"""Update the small local completion/compatibility catalog from Riot item data."""
import argparse
import json
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument('--patch', default='16.20.1')
parser.add_argument('--input', type=Path, help='Use a saved Riot item.json instead of downloading')
args = parser.parse_args()
url = f'https://ddragon.leagueoflegends.com/cdn/{args.patch}/data/zh_CN/item.json'
if args.input:
    source = json.loads(args.input.read_text(encoding='utf-8'))
else:
    with urllib.request.urlopen(url, timeout=20) as response:
        source = json.load(response)
raw = source['data']
conflicts = {'last_whisper': {'3033', '3036', '6694'},
             'lifeline': {'3053', '3156', '6673'},
             'tear': {'3003', '3040', '3004', '3042', '3119', '3121'},
             'hydra': {'3074', '3748', '6698'}}
items = {}
for iid, value in raw.items():
    upgrades = [raw[child] for child in value.get('into', []) if child in raw]
    complete = (value.get('gold', {}).get('total', 0) >= 1800
                and 'Boots' not in value.get('tags', []) and value.get('maps', {}).get('12')
                and not any(child.get('gold', {}).get('purchasable') and child.get('maps', {}).get('12')
                            for child in upgrades))
    items[iid] = {'name': value['name'], 'complete': bool(complete),
                  'crit': value.get('stats', {}).get('FlatCritChanceMod', .25 if iid == '3032' else 0),
                  'groups': [group for group, members in conflicts.items() if iid in members]}
payload = {'source': url, 'patch': source['version'],
           'notes': 'Completion uses ARAM availability and recipe metadata. Conflict groups are a partial local rule list.',
           'items': items}
(ROOT / 'data/item_catalog.json').write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps({'patch': payload['patch'], 'items': len(items), 'source': url}))
