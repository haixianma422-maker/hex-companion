"""Read public page data without executing embedded JavaScript."""
import json
import re
import urllib.request
from urllib.parse import urlparse
from html import unescape

from .models import Augment, Build, Champion

BASE = 'https://op.gg/zh-cn/lol/modes/aram-mayhem'


def verify_mayhem_page(html, url):
    parsed = urlparse(url)
    if parsed.scheme != 'https' or parsed.hostname != 'op.gg' or not re.fullmatch(
            r'/(?:[a-z]{2}-[a-z]{2}/)?lol/modes/aram-mayhem/[a-z0-9]+/(?:build|items)', parsed.path):
        return False
    title = re.search(r'<title>(.*?)</title>', html, re.S)
    if not title or not any(label in unescape(title.group(1)) for label in ('海克斯大乱斗', 'ARAM: Mayhem')):
        return False
    return any(isinstance(value, dict) and value.get('isAramMayhem') is True
               for node in flight_nodes(html) for value in walk(node))


def fetch_html(url):
    with urllib.request.urlopen(url, timeout=18) as response:
        return response.read(6_000_000).decode('utf-8')


def flight_nodes(html):
    chunks = []
    pattern = r'<script>self\.__next_f\.push\((.*?)\)</script>'
    for match in re.finditer(pattern, html, re.S):
        try:
            part = json.loads(match.group(1))
        except json.JSONDecodeError:
            continue
        if isinstance(part, list) and len(part) > 1 and isinstance(part[1], str):
            chunks.append(part[1])
    for line in ''.join(chunks).splitlines():
        try:
            yield json.loads(line.partition(':')[2])
        except json.JSONDecodeError:
            continue


def walk(value):
    yield value
    children = value.values() if isinstance(value, dict) else value if isinstance(value, list) else []
    for child in children:
        if isinstance(child, (dict, list)):
            yield from walk(child)


def integer(value):
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def parse_champions(html):
    found = {}
    for node in flight_nodes(html):
        for value in walk(node):
            if not isinstance(value, dict) or not {'champion_id', 'key', 'name'} <= value.keys():
                continue
            cid = integer(value['champion_id'])
            if cid and value['name'] and value['key']:
                found[cid] = Champion(cid, value['name'], value['key'], integer(value.get('tier')), integer(value.get('rank')))
    if not found:
        raise ValueError('未找到英雄数据，OP.GG 页面结构可能已变化')
    return list(found.values())


def parse_augments(html):
    found = {}
    for node in flight_nodes(html):
        for value in walk(node):
            if not isinstance(value, dict) or not {'id', 'name', 'tier', 'rarity', 'performance'} <= value.keys():
                continue
            aid = integer(value['id'])
            if aid and isinstance(value['name'], str) and value['name'].strip():
                found[aid] = Augment(aid, value['name'].strip(), integer(value['tier']), integer(value['rarity']))
    if not found:
        raise ValueError('未找到具名海克斯数据，OP.GG 页面结构可能已变化')
    return list(found.values())


def parse_builds(html):
    result = {}
    for node in flight_nodes(html):
        for value in walk(node):
            if not isinstance(value, list) or len(value) != 4 or value[1] != 'tr':
                continue
            row_key = value[2]
            if not isinstance(row_key, str):
                continue
            items = []
            seen = set()
            for props in walk(value[3]):
                if not isinstance(props, dict) or props.get('metaType') != 'item':
                    continue
                iid = integer(props.get('metaId'))
                if not iid or iid in seen:
                    continue
                seen.add(iid)
                name = next((x['alt'] for x in walk(props) if isinstance(x, dict) and isinstance(x.get('alt'), str)), f'装备 {iid}')
                items.append({'id': iid, 'name': name})
            if items:
                category = '核心装备' if 'core' in row_key else '鞋子' if 'boot' in row_key else '出门装'
                result[row_key] = Build(items, category)
    if not result:
        raise ValueError('未找到出装组合，OP.GG 页面结构可能已变化')
    return list(result.values())


def parse_recommendations(html):
    """Keep the first complete source recommendation; alternatives stay separate."""
    priority, spells = [], []
    for node in flight_nodes(html):
        for row in walk(node):
            if not isinstance(row, list) or len(row) != 4 or row[1] != 'tr':
                continue
            props = [value for value in walk(row[3]) if isinstance(value, dict)]
            if not priority:
                keys = [value.get('extraData') for value in props if value.get('metaType') == 'skill']
                if len(keys) == 3 and all(isinstance(key, str) for key in keys) and set(keys) == {'Q', 'W', 'E'}:
                    priority = keys[:2]
            if not spells:
                pair = []
                for value in props:
                    if value.get('metaType') != 'spell':
                        continue
                    sid = integer(value.get('metaId'))
                    name = next((child['alt'].strip() for child in walk(value)
                                 if isinstance(child, dict) and isinstance(child.get('alt'), str)
                                 and child['alt'].strip()), '')
                    if sid and name:
                        pair.append({'id': sid, 'name': name})
                if len(pair) == 2 and pair[0]['id'] != pair[1]['id']:
                    spells = pair
            if priority and spells:
                return {'skill_priority': priority, 'summoner_spells': spells}
    return {'skill_priority': priority, 'summoner_spells': spells}


def page_patch(html):
    match = re.search(r'/meta/images/lol/(\d+\.\d+(?:\.\d+)?)/', html)
    return match.group(1) if match else None


def parse_item_options(html):
    """Read labeled item-page sections; never mix starters with final items."""
    result = []
    seen = set()
    categories = {'核心装备': '核心装备', '鞋子': '鞋子', '出门装': '出门装', '装备': '后续装备'}
    for node in flight_nodes(html):
        for section in walk(node):
            if not isinstance(section, list) or len(section) != 4 or section[1] != 'section':
                continue
            title = next((v.get('children') for v in walk(section[3])
                          if isinstance(v, dict) and isinstance(v.get('children'), str)
                          and v['children'] in categories), None)
            if not title:
                continue
            for value in walk(section[3]):
                if not isinstance(value, dict):
                    continue
                raw = value.get('metaBuildItems') or value.get('metaStarterItems') or ([value['metaItem']] if value.get('metaItem') else [])
                items = [{'id': v['id'], 'name': v['name']} for v in raw
                         if isinstance(v, dict) and integer(v.get('id')) and isinstance(v.get('name'), str)]
                key = (title, tuple(item['id'] for item in items))
                if items and key not in seen:
                    seen.add(key)
                    result.append(Build(items, categories[title]))
    if not any(row.category == '后续装备' for row in result):
        raise ValueError('OP.GG 装备页缺少后续装备数据')
    return result
