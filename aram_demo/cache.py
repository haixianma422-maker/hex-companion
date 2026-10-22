import json
import os
import re
import threading
import tempfile
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from weakref import WeakValueDictionary

from .models import Augment, Champion
from .opgg import (BASE, fetch_html, page_patch, parse_augments, parse_builds,
                   parse_champions, parse_recommendations, verify_mayhem_page)

SOURCE_NAMES = {'opgg': 'OP.GG', 'qq101': '101 数据站'}
FRESH_SECONDS = 86400
_ROOT_LOCKS = WeakValueDictionary()
_ROOT_LOCK_GUARD = threading.Lock()


def is_fresh(data, max_age=FRESH_SECONDS):
    """A snapshot fetched within max_age seconds needs no automatic refetch."""
    try:
        age = (datetime.now(timezone.utc) - datetime.fromisoformat(data.get('fetched_at', ''))).total_seconds()
    except (AttributeError, TypeError, ValueError):
        return False
    return 0 <= age < max_age


def patch_key(value):
    """Major.minor game version; OP.GG writes 16.21.1 and 101 writes 16.21."""
    match = re.match(r'(\d+)\.(\d+)', str(value or ''))
    return (int(match[1]), int(match[2])) if match else None


def is_current(data, index_patch=None, max_age=FRESH_SECONDS):
    """Fresh, and not from an older game version than the source's hero index."""
    if not is_fresh(data, max_age):
        return False
    current, cached = patch_key(index_patch), patch_key(data.get('patch'))
    return current is None or cached is None or cached >= current


def _root_lock(root):
    key = os.path.normcase(str(root.resolve()))
    with _ROOT_LOCK_GUARD:
        lock = _ROOT_LOCKS.get(key)
        if lock is None:
            lock = threading.RLock()
            _ROOT_LOCKS[key] = lock
        return lock


class DataStore:
    def __init__(self, root: Path, seed_root: Path | None = None, source=None):
        self.root = Path(root)
        self.seed_root = Path(seed_root) if seed_root is not None else None
        self.root.mkdir(parents=True, exist_ok=True)
        self.last_error = ''
        self._lock = _root_lock(self.root)
        self._retired = False
        if source is None:
            source = (self.read('settings.json') or {}).get('data_source', 'opgg')
            if source not in SOURCE_NAMES:
                source = 'opgg'
        if source not in SOURCE_NAMES:
            raise ValueError('未知数据来源')
        self.source = source

    @property
    def source_name(self):
        return SOURCE_NAMES[self.source]

    def _relative(self, filename):
        if (getattr(self, 'source', 'opgg') == 'qq101'
                and (filename == 'champions.json' or filename.startswith('heroes/'))):
            return Path('sources/qq101') / filename
        return Path(filename)

    def read(self, filename):
        roots = [self.root]
        if self.seed_root is not None and filename != 'settings.json':
            roots.append(self.seed_root)
        for root in roots:
            try:
                return json.loads((root / self._relative(filename)).read_text(encoding='utf-8'))
            except FileNotFoundError:
                continue
            except (OSError, ValueError) as exc:
                self.last_error = f'缓存无法读取：{filename}（{type(exc).__name__}）'
        return None

    def _write(self, filename, data):
        with self._lock:
            if self._retired:
                return
            path = self.root / self._relative(filename)
            path.parent.mkdir(parents=True, exist_ok=True)
            stream = tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent,
                                                 prefix=path.stem + '-', suffix='.tmp', delete=False)
            temporary = Path(stream.name)
            try:
                with stream:
                    json.dump(data, stream, ensure_ascii=False, indent=2)
                os.replace(temporary, path)
            finally:
                temporary.unlink(missing_ok=True)

    def retire(self):
        """Discard cache commits from workers started before a source switch."""
        with self._lock:
            self._retired = True

    def champions(self):
        raw = self.read('champions.json') or {}
        try:
            return [Champion(**row) for row in raw.get('champions', [])]
        except (TypeError, KeyError):
            self.last_error = '英雄缓存格式不兼容，请刷新英雄榜'
            return []

    def hero(self, champion_id):
        return self.read(f'heroes/{int(champion_id)}.json')

    def index_patch(self):
        return (self.read('champions.json') or {}).get('patch')

    def augment_catalog(self):
        """Every live title, shared by both sources; recognition only, never ratings."""
        raw = self.read('augment_catalog.json') or {}
        try:
            return [Augment(**dict(row, tier=None)) for row in raw.get('augments', [])]
        except (TypeError, KeyError):
            self.last_error = '海克斯名称表格式不兼容'
            return []

    def refresh_augment_catalog(self):
        from . import qq101
        data = qq101.fetch_augment_catalog()
        self._write('augment_catalog.json', data)
        return data

    def refresh(self, champion=None, on_ready=None):
        if self.source == 'qq101':
            from . import qq101
            def ready(partial):
                self._supplement_spells(champion, partial, cached_only=True)
                on_ready(partial)
            if champion is None:
                data = qq101.fetch_champions()
            elif on_ready:
                data = qq101.fetch_hero(champion, on_ready=ready)
            else:
                data = qq101.fetch_hero(champion)
            if champion is not None and not data.get('summoner_spells'):
                self._supplement_spells(champion, data)
            self._write('champions.json' if champion is None else f'heroes/{champion.id}.json', data)
            self.last_error = ''
            return data
        if champion is None:
            html = fetch_html(BASE)
            data = {'champions': [asdict(x) for x in parse_champions(html)], 'source': BASE,
                    'source_id': 'opgg', 'source_name': 'OP.GG',
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
            data = {'champion_id': champion.id, 'name': champion.name,
                    'source_id': 'opgg', 'source_name': 'OP.GG',
                    'augments': [asdict(x) for x in augments], 'builds': [asdict(x) for x in builds],
                    **parse_recommendations(build_html),
                    'source': augment_url, 'build_source': build_url,
                    'build_mode_verified': True, 'build_mode': 'aram-mayhem', 'tier_labels': {},
                    'build_verification': 'OP.GG Mayhem URL, page title and isAramMayhem=true; core from build page',
                    'patch': page_patch(aug_html), 'fetched_at': datetime.now(timezone.utc).isoformat()}
            self._recommendation_icons(build_html, data)
            self._write(f'heroes/{champion.id}.json', data)
        self.last_error = ''
        return data

    @staticmethod
    def _recommendation_icons(html, data):
        from .opgg import flight_nodes, walk
        skills, spells = {}, {}
        for node in flight_nodes(html):
            for value in walk(node):
                if not isinstance(value, dict) or value.get('metaType') not in ('skill', 'spell'):
                    continue
                url = next((child['src'] for child in walk(value)
                            if isinstance(child, dict) and isinstance(child.get('src'), str)
                            and child['src'].endswith('.png')), '')
                if value['metaType'] == 'skill' and value.get('extraData') in ('Q', 'W', 'E'):
                    skills.setdefault(value['extraData'], url)
                elif value['metaType'] == 'spell' and isinstance(value.get('metaId'), int):
                    spells.setdefault(value.get('metaId'), url)
        data['skill_icons'] = skills
        for spell in data.get('summoner_spells', []):
            if spells.get(spell['id']):
                spell['icon_url'] = spells[spell['id']]

    def _supplement_spells(self, champion, data, cached_only=False):
        cached = DataStore(self.root, self.seed_root, source='opgg').hero(champion.id) or {}
        cached_spells = cached.get('summoner_spells')
        valid_cache = (cached.get('champion_id') == champion.id
                       and cached.get('build_mode_verified') is True
                       and cached.get('build_mode') == 'aram-mayhem'
                       and isinstance(cached_spells, list) and len(cached_spells) == 2
                       and all(isinstance(spell, dict) and isinstance(spell.get('id'), int)
                               and not isinstance(spell['id'], bool) and spell['id'] > 0
                               for spell in cached_spells))
        recent = valid_cache and is_fresh(cached)
        url = f'{BASE}/{champion.slug}/build'
        if cached_only:
            data.update(summoner_spells=cached_spells if valid_cache else [],
                        summoner_source='opgg', summoner_source_name='OP.GG',
                        summoner_fetched_at=cached.get('fetched_at') if valid_cache else None)
            return
        try:
            if recent:
                data.update(summoner_spells=cached['summoner_spells'], summoner_source='opgg',
                            summoner_source_name='OP.GG', summoner_fetched_at=cached['fetched_at'])
                return
            html = fetch_html(url)
            if not verify_mayhem_page(html, url):
                raise ValueError('补充来源模式不匹配')
            supplement = parse_recommendations(html)
            self._recommendation_icons(html, supplement)
            stamp = datetime.now(timezone.utc).isoformat()
        except (OSError, ValueError):
            supplement = cached if valid_cache else {}
            stamp = supplement.get('fetched_at')
        data['summoner_spells'] = supplement.get('summoner_spells', [])
        data['summoner_source'] = 'opgg'
        data['summoner_source_name'] = 'OP.GG'
        data['summoner_fetched_at'] = stamp
