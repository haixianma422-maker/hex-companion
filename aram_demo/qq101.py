"""Public 101 Hextech ARAM statistics; no account or persistent cache needed.

Parsing follows 101's q0 (hero detail), A0 (hero rank), E0/Ya (role tiers).
Augment S/A/B/C letters come from the all-rarities group, never win rates.
"""
import json
import math
import re
import threading
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from functools import lru_cache

from .models import Augment, Build, Champion, is_placeholder_name

SOURCE_ID = 'qq101'
SOURCE_NAME = '101 数据站'
API = 'https://mlol.qt.qq.com/go/battle_info/odp_proxy/'
ASSETS = 'https://game.gtimg.cn/images/lol/act/img/js/'
HERO_LIST = ASSETS + 'heroList/hero_list.js'
AUGMENTS = ASSETS + 'kiwi/kiwi_augments.json'
ITEMS = ASSETS + 'items/items.js'
TIER_LABELS = dict(enumerate('SABC'))
RARITIES = {'kSilver': 1, 'kGold': 4, 'kPrismatic': 8}
ROLES = ('tank', 'fighter', 'mage', 'assassin', 'marksman', 'support')
_METADATA_LOCK = threading.Lock()
_METADATA_REQUESTS = {}


def fetch_json(url):
    """Read a bounded public JSON response with a finite network timeout."""
    request = urllib.request.Request(url, headers={'User-Agent': 'HexCompanion/1.0', 'Accept': 'application/json'})
    with urllib.request.urlopen(request, timeout=8) as response:
        raw = response.read(8_000_001)
    if len(raw) > 8_000_000:
        raise ValueError('101 数据响应过大')
    return json.loads(raw.decode('utf-8-sig'))


@lru_cache(maxsize=200)
def _metadata_text(url):
    # Immutable cache entries prevent a caller from poisoning another request.
    return json.dumps(fetch_json(url), ensure_ascii=False)


def _metadata(url, optional=False):
    try:
        # lru_cache alone can issue duplicate cold requests in concurrent workers.
        with _METADATA_LOCK:
            lock = _METADATA_REQUESTS.setdefault(url, threading.Lock())
        with lock:
            return json.loads(_metadata_text(url))
    except (OSError, ValueError):
        if not optional:
            raise
        return {}


def _decode_object(value):
    if isinstance(value, str):
        value = json.loads(value)
    if not isinstance(value, dict):
        raise ValueError('101 数据结构不完整')
    return value


def _fields(payload):
    if not isinstance(payload, dict) or payload.get('code') not in (0, '0'):
        raise ValueError('101 数据站返回业务错误')
    data = payload.get('data')
    values = data.get('_fieldValues') if isinstance(data, dict) else None
    if not isinstance(values, dict) or not values:
        raise ValueError('101 数据站暂无统计数据')
    return _decode_object(next(iter(values.values())))


def _stamp():
    return datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')


def statistics_dates(now=None):
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError('Statistics date requires a timezone-aware timestamp')
    today = now.astimezone(timezone(timedelta(hours=8))).date()
    return [(today - timedelta(days=offset)).strftime('%Y%m%d') for offset in range(1, 8)]


def _tier(rank, total):
    boundaries = []
    for fraction in (.04, .15, .30, .40):
        boundaries.append(max(boundaries[-1] if boundaries else 1, math.floor(total * fraction + .5)))
    return next((i for i, boundary in enumerate(boundaries) if rank <= boundary), 4)


def _champions(fields, metadata):
    raw = fields.get('listcollect')
    if not isinstance(raw, str) or not raw.strip():
        raise ValueError('101 英雄榜为空')
    heroes = metadata.get('hero')
    if not isinstance(heroes, list):
        raise ValueError('101 英雄字典结构变化')
    names = {int(h['heroId']): h for h in heroes if isinstance(h, dict) and str(h.get('heroId', '')).isdigit()}
    rows, seen = [], set()
    for value in raw.split('#'):
        if not value:
            continue
        columns = value.split('_')
        if len(columns) < 5 or not columns[0].isdigit() or not columns[1].isdigit():
            raise ValueError('101 英雄榜条目结构变化')
        cid, rank = int(columns[0]), int(columns[1])
        meta = names.get(cid)
        if not meta or cid in seen or rank < 1:
            raise ValueError('101 英雄榜与英雄字典不匹配')
        seen.add(cid)
        roles = [str(r).lower() for r in meta.get('roles', []) + meta.get('tags', [])]
        rows.append({'id': cid, 'raw_rank': rank, 'metadata': meta, 'roles': roles, 'tier': 4})
    for role in ROLES:
        bucket = [row for row in rows if role in row['roles']]
        for index, row in enumerate(bucket, 1):
            row['tier'] = min(row['tier'], _tier(index, len(bucket)))
    for row in rows:
        if not row['roles']:
            row['tier'] = _tier(row['raw_rank'], len(rows))
    rows.sort(key=lambda r: (r['tier'], r['raw_rank']))
    result = []
    for rank, row in enumerate(rows, 1):
        meta = row['metadata']
        name, slug = meta.get('title') or meta.get('name'), meta.get('alias')
        if not name or not slug:
            raise ValueError('101 英雄缺少名称或标识')
        result.append(asdict(Champion(row['id'], name, slug.lower(), row['tier'], rank)))
    if not result:
        raise ValueError('101 英雄榜为空')
    return result


def fetch_champions():
    metadata = _metadata(HERO_LIST)
    failure = None
    for date in statistics_dates():
        source = API + 'fuwen_aram_hero_rank_v2?dtstatdate=' + date
        try:
            fields = _fields(fetch_json(source))
            champions = _champions(fields, metadata)
        except (OSError, ValueError) as error:
            failure = error
            continue
        return {'champions': champions, 'source_id': SOURCE_ID, 'source_name': SOURCE_NAME,
                'source': source, 'patch': metadata.get('version'),
                'stat_date': str(fields.get('dtstatdate') or date), 'fetched_at': _stamp(),
                'tier_verification': '101 E0/Ya: best role tier, rounded 4/15/30/40% boundaries; source order within roles'}
    raise ValueError('101 最近七天均无可用英雄榜') from failure


def _augments(fields, champion_id, metadata):
    raw = fields.get('augment_json_irank')
    if not isinstance(raw, str) or not raw:
        raise ValueError('101 缺少海克斯评级数据')
    entries = {int(a['augmentID']): a for a in metadata
               if isinstance(a, dict) and str(a.get('augmentID', '')).isdigit()} if isinstance(metadata, list) else {}
    result, seen = [], set()
    for group in raw.split('&'):
        key, separator, value = group.partition(':')
        if not separator or key.strip() != '255':
            continue
        for entry in value.split('#'):
            if not entry:
                continue
            parts = entry.split('|')
            if (len(parts) != 6 or not all(p.isdigit() for p in parts[:3])
                    or int(parts[0]) < 1 or int(parts[1]) != champion_id
                    or parts[3] != '255' or parts[5] not in 'SABC' or len(parts[5]) != 1):
                raise ValueError('101 海克斯评级条目不完整或英雄不匹配')
            try:
                pick_rate = float(parts[4])
            except ValueError as error:
                raise ValueError('101 海克斯选取率无效') from error
            if not math.isfinite(pick_rate) or not 0 <= pick_rate <= 1:
                raise ValueError('101 海克斯选取率无效')
            aid = int(parts[2])
            meta = entries.get(aid, {})
            name, rarity = meta.get('name_cn'), RARITIES.get(meta.get('level'))
            if aid in seen or not isinstance(name, str) or not name.strip() or rarity is None:
                raise ValueError('101 海克斯字典不完整或包含重复条目')
            seen.add(aid)
            if is_placeholder_name(name.strip()):
                continue
            result.append(asdict(Augment(aid, name.strip(), 'SABC'.index(parts[5]), rarity)))
    if not result:
        raise ValueError('101 缺少综合海克斯评级（255）')
    return result


def catalog_augments(metadata):
    """Live Mayhem (KIWI) titles without ratings; PBE, retired and placeholder rows are excluded."""
    if not isinstance(metadata, list):
        raise ValueError('101 海克斯字典结构变化')
    result, seen = [], set()
    for row in metadata:
        if not isinstance(row, dict) or not str(row.get('augmentID', '')).isdigit():
            continue
        aid, name = int(row['augmentID']), row.get('name_cn')
        modes = {mode.strip() for mode in str(row.get('mode') or '').split(',')}
        rarity = RARITIES.get(row.get('level'))
        if ('KIWI' not in modes or str(row.get('isPBE')) == '1' or rarity is None or aid in seen
                or not isinstance(name, str) or not name.strip() or is_placeholder_name(name.strip())):
            continue
        seen.add(aid)
        result.append(Augment(aid, name.strip(), None, rarity))
    if not result:
        raise ValueError('101 海克斯字典为空')
    return result


def fetch_augment_catalog():
    # A direct read: the in-process metadata cache would keep a pre-patch dictionary.
    return {'augments': [asdict(a) for a in catalog_augments(fetch_json(AUGMENTS))],
            'source_id': SOURCE_ID, 'source_name': SOURCE_NAME, 'source': AUGMENTS, 'fetched_at': _stamp(),
            'filter': 'mode contains KIWI; isPBE, empty names and internal placeholder keys excluded; tier unrated'}


def _optional_rows(raw):
    try:
        if isinstance(raw, str):
            raw = json.loads(raw)
        if isinstance(raw, dict):
            return list(raw.values())
        return raw if isinstance(raw, list) else []
    except ValueError:
        return []


def _recommendations(fields, metadata):
    rows = metadata.get('items') if isinstance(metadata, dict) else None
    names = {str(row['itemId']): row.get('name') for row in rows
             if isinstance(row, dict) and 'itemId' in row} if isinstance(rows, list) else {}
    result = []
    core = [row for row in _optional_rows(fields.get('itemcore_json')) if isinstance(row, dict)]
    def winrate(row):
        try:
            rate = float(row.get('winrate', 0))
            return rate if math.isfinite(rate) else 0
        except (TypeError, ValueError):
            return 0
    core.sort(key=winrate, reverse=True)  # Stable ties retain the API's ordinal, matching q0.
    sources = [('核心装备', re.split('[&,]', str(core[0].get('itemcore', ''))))] if core else []
    shoes = fields.get('itemshoes')
    if isinstance(shoes, str) and shoes:
        sources.append(('鞋子', shoes.split('#')[0].split('$')[0].split(',')))
    for category, ids in sources:
        if not ids or any(not i.strip().isdigit() or int(i) <= 0 for i in ids):
            continue
        items = [{'id': int(i), 'name': names.get(str(int(i))) or f'装备 {int(i)}'} for i in ids]
        if len({i['id'] for i in items}) == len(items):
            result.append(asdict(Build(items, category)))
    return result


def fetch_hero(champion, on_ready=None):
    source = API + f'fuwen_hero_rank?championid={champion.id}'
    # These four public responses are independent; a slow CDN must not add
    # its latency to each of the other three requests.
    with ThreadPoolExecutor(max_workers=4, thread_name_prefix='qq101') as pool:
        statistics = pool.submit(fetch_json, source)
        augment_meta = pool.submit(_metadata, AUGMENTS)
        hero_meta = pool.submit(_metadata, ASSETS + f'hero/{champion.id}.js', optional=True)
        item_meta = pool.submit(_metadata, ITEMS, optional=True)
        fields = _fields(statistics.result())
        augments = _augments(fields, champion.id, augment_meta.result())
        if on_ready:
            # Validated source ratings and skill priority do not depend on
            # optional display metadata. Publish a separate snapshot.
            on_ready(_hero_result(champion, source, fields, augments,
                                  hero_meta.result() if hero_meta.done() else {},
                                  item_meta.result() if item_meta.done() else {}))
        details = hero_meta.result()
        items = item_meta.result()
    return _hero_result(champion, source, fields, augments, details, items)


def _hero_result(champion, source, fields, augments, details, items):
    skills = _optional_rows(fields.get('skill_json'))
    priority = []
    if skills and isinstance(skills[0], dict):
        priority = [{'1': 'Q', '2': 'W', '3': 'E'}.get(k, k) for k in str(skills[0].get('qwe', '')).split('&')]
        priority = priority[:2] if len(priority) == 3 and set(priority) == {'Q', 'W', 'E'} else []
    icons = {}
    spells = details.get('spells') if isinstance(details, dict) else None
    for spell in spells if isinstance(spells, list) else []:
        if not isinstance(spell, dict):
            continue
        key, url = str(spell.get('spellKey', '')).upper(), spell.get('abilityIconPath')
        if (key in ('Q', 'W', 'E') and str(spell.get('heroId')) == str(champion.id)
                and isinstance(url, str) and url.startswith('https://game.gtimg.cn/') and url.lower().endswith('.png')):
            icons[key] = url
    return {'champion_id': champion.id, 'name': champion.name, 'augments': augments,
            'builds': _recommendations(fields, items),
            'skill_priority': priority, 'skill_icons': icons, 'summoner_spells': [],
            'tier_labels': {str(k): v for k, v in TIER_LABELS.items()},
            'source_id': SOURCE_ID, 'source_name': SOURCE_NAME, 'source': source,
            'build_source': source, 'build_mode': 'aram-mayhem', 'build_mode_verified': True,
            'build_verification': '101 official Hextech ARAM fuwen_hero_rank endpoint; champion id and 255 augment group validated',
            'recommendation_order': '101 q0: core winrate descending (stable source ties); first boots and first skill summary',
            'patch': details.get('version') if isinstance(details, dict) else None,
            'stat_date': str(fields.get('dtstatdate') or ''), 'fetched_at': _stamp()}
