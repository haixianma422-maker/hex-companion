import json
import os
import threading
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from .models import Champion
from .opgg import BASE, fetch_html, page_patch, parse_augments, parse_builds, parse_champions, parse_item_options, verify_mayhem_page


class DataStore:
    def __init__(self, root: Path, seed_root: Path | None = None):
        self.root = Path(root)
        self.seed_root = Path(seed_root) if seed_root is not None else None
        self.root.mkdir(parents=True, exist_ok=True)
        self.last_error = ''
        self._lock = threading.RLock()

    def read(self, filename):
        roots = [self.root]
        if self.seed_root is not None and filename != 'settings.json':
            roots.append(self.seed_root)
        for root in roots:
            try:
                return json.loads((root / filename).read_text(encoding='utf-8'))
            except FileNotFoundError:
                continue
            except (OSError, ValueError) as exc:
                self.last_error = f'缓存无法读取：{filename}（{type(exc).__name__}）'
        return None

    def _write(self, filename, data):
        with self._lock:
            path = self.root / filename
            path.parent.mkdir(parents=True, exist_ok=True)
            temporary = path.with_suffix('.json.tmp')
            temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
            os.replace(temporary, path)

    def champions(self):
        raw = self.read('champions.json') or {}
        try:
            return [Champion(**row) for row in raw.get('champions', [])]
        except (TypeError, KeyError):
            self.last_error = '英雄缓存格式不兼容，请刷新英雄榜'
            return []

    def hero(self, champion_id):
        return self.read(f'heroes/{int(champion_id)}.json')

    def refresh(self, champion=None):
        if champion is None:
            html = fetch_html(BASE)
            data = {'champions': [asdict(x) for x in parse_champions(html)], 'source': BASE,
                    'patch': page_patch(html), 'fetched_at': datetime.now(timezone.utc).isoformat()}
            self._write('champions.json', data)
        else:
            augment_url = f'{BASE}/{champion.slug}/augments'
            build_url = f'{BASE}/{champion.slug}/build'
            aug_html = fetch_html(augment_url)
            augments = parse_augments(aug_html)
            build_html = fetch_html(build_url)
            if not verify_mayhem_page(build_html, build_url):
                raise ValueError('出装页面未通过海克斯大乱斗模式校验，保留原有缓存')
            builds = parse_builds(build_html)
            items_url = f'{BASE}/{champion.slug}/items'
            items_note = ''
            try:
                items_html = fetch_html(items_url)
                if not verify_mayhem_page(items_html, items_url):
                    raise ValueError('装备详情页未通过海克斯大乱斗模式校验')
                options = parse_item_options(items_html)
                # Keep the primary Mayhem build order. The item page supplies
                # only later choices, never a replacement core or boots.
                builds += [row for row in options if row.category == '后续装备']
            except (OSError, ValueError) as exc:
                items_note = f'后续装备暂未更新：{type(exc).__name__}'
            data = {'champion_id': champion.id, 'name': champion.name,
                    'augments': [asdict(x) for x in augments], 'builds': [asdict(x) for x in builds],
                    'source': augment_url, 'build_source': build_url,
                    'build_mode_verified': True, 'build_mode': 'aram-mayhem', 'tier_labels': {},
                    'build_verification': 'OP.GG Mayhem URL, page title and isAramMayhem=true; core from build page',
                    'items_source': items_url, 'items_note': items_note,
                    'patch': page_patch(aug_html), 'fetched_at': datetime.now(timezone.utc).isoformat()}
            self._write(f'heroes/{champion.id}.json', data)
        self.last_error = ''
        return data
