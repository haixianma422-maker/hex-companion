"""Audit the complete display-tag family against a versioned Chinese game resource."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT = ROOT / 'data/augment_display_tags.json'
PREFIX = 'cherry_augmentdisplaytag_'


def extract_tags(document):
    tags = {key: value for key, value in document['entries'].items() if key.startswith(PREFIX)}
    if not tags or any(not isinstance(value, str) or not value.strip() for value in tags.values()):
        raise ValueError('Resource has missing or invalid display-tag definitions')
    return dict(sorted(tags.items()))


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, help='Use a saved resource for an offline audit')
    parser.add_argument('--source-url', help='Use another fixed game version when updating')
    parser.add_argument('--update', action='store_true', help='Replace the bundled tag snapshot explicitly')
    args = parser.parse_args()
    snapshot = json.loads(SNAPSHOT.read_text(encoding='utf-8'))
    url = args.source_url or snapshot['source']
    if args.input:
        raw = args.input.read_bytes()
    else:
        request = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(request, timeout=25) as response:
            raw = response.read(40_000_001)
        if len(raw) > 40_000_000:
            raise ValueError('Resource exceeds the audit size limit')
    tags = extract_tags(json.loads(raw))
    missing = sorted(set(tags) - set(snapshot['tags']))
    obsolete = sorted(set(snapshot['tags']) - set(tags))
    changed = sorted(key for key in set(tags) & set(snapshot['tags']) if tags[key] != snapshot['tags'][key])
    same_hash = hashlib.sha256(raw).hexdigest() == snapshot['source_sha256']
    if args.update:
        snapshot.update(source=url, patch=url.split('/')[3], source_sha256=hashlib.sha256(raw).hexdigest(), tags=tags)
        SNAPSHOT.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    passed = args.update or (not missing and not obsolete and not changed and same_hash)
    report = {'status': 'passed' if passed else 'drift', 'source': url,
              'key_prefix': PREFIX, 'source_sha256': hashlib.sha256(raw).hexdigest(),
              'tag_count': len(tags), 'tags': tags, 'missing_keys': missing,
              'obsolete_keys': obsolete, 'changed_keys': changed, 'source_hash_matches_before_update': same_hash,
              'snapshot_updated': args.update, 'network_used': args.input is None}
    (ROOT / 'artifacts/augment_tags_audit_result.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if not passed:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
