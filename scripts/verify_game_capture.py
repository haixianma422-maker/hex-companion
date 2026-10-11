"""Replay a supplied game screenshot offline; never capture or control a live game."""
import argparse
from dataclasses import asdict
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from PIL import Image
from aram_demo.cache import DataStore
from aram_demo.models import Augment, augment_label
from aram_demo.recognition import Recognizer


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('image', type=Path)
    parser.add_argument('--champion-id', type=int, required=True)
    parser.add_argument('--expected-ids', help='Comma-separated IDs verified from the screenshot and source cache')
    args = parser.parse_args()
    store = DataStore(ROOT / 'data')
    data = store.hero(args.champion_id)
    if not data:
        raise ValueError('No cached augment data for this champion')
    augments = [Augment(**row) for row in data['augments']]
    regions = (store.read('settings.json') or {}).get('regions')
    started = time.monotonic()
    with Image.open(args.image) as image:
        size = image.size
        matches = Recognizer(regions).read_screen(image, augments)
    index = {a.id: a for a in augments}
    rows = []
    for match in matches:
        row = asdict(match)
        augment = index.get(match.augment_id)
        row.update(name=augment.name if augment else None,
                   grade=augment_label(augment.tier, data.get('tier_labels')) if augment else None)
        rows.append(row)
    report = {'champion_id': args.champion_id, 'image_size': size,
              'elapsed_seconds': round(time.monotonic() - started, 3),
              'source': data.get('source'), 'fetched_at': data.get('fetched_at'), 'matches': rows,
              'status': 'passed' if all(m.augment_id for m in matches) else 'unmatched',
              'verification': 'offline_replay_of_user_supplied_game_capture'}
    (ROOT / 'artifacts' / 'game_capture_ocr_result.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if args.expected_ids:
        expected = [int(value) for value in args.expected_ids.split(',')]
        assert [m.augment_id for m in matches] == expected, 'Screenshot augments did not match verified IDs'


if __name__ == '__main__':
    main()
