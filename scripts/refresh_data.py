import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from aram_demo.cache import DataStore

parser = argparse.ArgumentParser(description='按需刷新 OP.GG 数据')
parser.add_argument('--heroes', nargs='*', type=int, default=[])
args = parser.parse_args()
store = DataStore(ROOT / 'data')
store.refresh(None)
heroes = {c.id: c for c in store.champions()}
print(json.dumps({'champions': len(heroes)}, ensure_ascii=False))
for cid in args.heroes:
    if cid not in heroes:
        raise SystemExit(f'未知英雄 ID：{cid}')
    data = store.refresh(heroes[cid])
    print(json.dumps({'champion': cid, 'augments': len(data['augments']), 'builds': len(data['builds']),
                      'patch': data['patch']}, ensure_ascii=False))
