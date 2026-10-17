"""Qt Quick overlay: the panel, its click-through shadow and the bubble, driven by CompanionApp.

CompanionApp passes Win32 rectangles in physical pixels. The panel and bubble adapters keep
that contract and publish plain view dictionaries that the QML in aram_demo/qml draws.
"""
import ctypes
import os
import threading
from pathlib import Path

from PySide6.QtCore import (QAbstractListModel, QByteArray, QModelIndex, QObject, Property, QTimer, QUrl, Qt,
                            Signal, Slot)
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuick import QQuickWindow   # lets PySide hand back QQuickWindow, not a bare QWindow

from .builds import recommended_items
from .models import augment_label, sort_champions
from .windows import panel_position

QML_DIR = Path(__file__).resolve().parent / 'qml'
WIDTH = 360
HEIGHT = {'select': 540, 'game': 580}
# Logical rows that stay fixed when a short work area makes the middle of the panel scroll.
TOP = {'select': 75, 'game': 68}
FOOTER = 58
SPELL_NAMES = {6: '疾跑', 11: '惩戒', 12: '传送', 13: '清晰', 14: '点燃', 21: '屏障'}
ITEM_NAMES = {3085: '卢安娜飓风', 3036: '多米尼克', 3006: '狂战士胫甲'}
SIDES = ('左侧', '中间', '右侧')


def system_motion_enabled():
    """Windows "show animations" preference (SPI_GETCLIENTAREAANIMATION)."""
    if os.name != 'nt':
        return True
    try:
        enabled = ctypes.c_int(1)
        ok = ctypes.windll.user32.SystemParametersInfoW(0x1042, 0, ctypes.byref(enabled), 0)
        return bool(enabled.value) if ok else False
    except (OSError, AttributeError):
        return False


def file_url(path):
    return Path(os.path.abspath(path)).as_uri() if path else ''


def screen_at(px, py):
    """The QScreen holding a physical point, and its device pixel ratio."""
    for screen in QGuiApplication.screens():
        g, ratio = screen.geometry(), screen.devicePixelRatio()
        if g.x() <= px < g.x() + g.width() * ratio and g.y() <= py < g.y() + g.height() * ratio:
            return screen, ratio
    screen = QGuiApplication.primaryScreen()
    return screen, screen.devicePixelRatio()


def to_logical(px, py):
    screen, ratio = screen_at(px, py)
    g = screen.geometry()
    return g.x() + (px - g.x()) / ratio, g.y() + (py - g.y()) / ratio


def to_physical(lx, ly):
    for screen in QGuiApplication.screens():
        g = screen.geometry()
        if g.contains(round(lx), round(ly)):
            ratio = screen.devicePixelRatio()
            return round(g.x() + (lx - g.x()) * ratio), round(g.y() + (ly - g.y()) * ratio)
    ratio = QGuiApplication.primaryScreen().devicePixelRatio()
    return round(lx * ratio), round(ly * ratio)


class RowModel(QAbstractListModel):
    """Rows matched by key: delegates survive updates, so hover state and transitions do too."""

    def __init__(self, roles, key):
        super().__init__()
        self.roles, self.key, self.rows = tuple(roles), key, []

    def roleNames(self):
        return {Qt.UserRole + i: QByteArray(name.encode()) for i, name in enumerate(self.roles)}

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.rows)

    def data(self, index, role):
        if not index.isValid() or not 0 <= role - Qt.UserRole < len(self.roles):
            return None
        return self.rows[index.row()].get(self.roles[role - Qt.UserRole])

    def update(self, rows):
        wanted = [row[self.key] for row in rows]
        for i in reversed(range(len(self.rows))):
            if self.rows[i][self.key] not in wanted:
                self.beginRemoveRows(QModelIndex(), i, i); del self.rows[i]; self.endRemoveRows()
        for target, row in enumerate(rows):
            current = [r[self.key] for r in self.rows]
            if row[self.key] not in current:
                self.beginInsertRows(QModelIndex(), target, target); self.rows.insert(target, row); self.endInsertRows()
                continue
            source = current.index(row[self.key])
            if source != target:
                self.beginMoveRows(QModelIndex(), source, source, QModelIndex(), target)
                self.rows.insert(target, self.rows.pop(source)); self.endMoveRows()
            if self.rows[target] != row:
                self.rows[target] = row
                self.dataChanged.emit(self.index(target), self.index(target))


class AssetUrls(QObject):
    """File URLs for cached images, validated on a worker thread.

    The caches decode an image to validate it, which takes milliseconds per file. Doing that
    during a repaint stalled animations, so the GUI thread only reads results from here.
    """
    resolved = Signal()
    _merge = Signal(object)

    def __init__(self):
        super().__init__()
        self.urls, self.pending, self.queue = {}, set(), []
        self._merge.connect(self._merged, Qt.QueuedConnection)

    def url(self, entry, lookup):
        if entry in self.urls:
            return self.urls[entry]
        if entry not in self.pending:
            self.pending.add(entry)
            self.queue.append((entry, lookup))
            if len(self.queue) == 1:
                QTimer.singleShot(0, self._resolve)
        return ''

    def busy(self):
        return bool(self.pending)

    def forget_missing(self):
        self.urls = {entry: url for entry, url in self.urls.items() if url}

    def _resolve(self):
        batch, self.queue = self.queue, []
        def work():
            result = {}
            for entry, lookup in batch:
                try:
                    result[entry] = file_url(lookup())
                except Exception:   # a damaged cache file shows as missing, like the Tk panel
                    result[entry] = ''
            self._merge.emit(result)
        threading.Thread(target=work, daemon=True).start()

    def _merged(self, result):
        self.pending.difference_update(result)
        self.urls.update(result)
        self.resolved.emit()


class CompanionPanel(QObject):
    """The mode-aware panel. CompanionApp calls render() and show_at(); QML draws `view`."""
    viewChanged = Signal()
    placeChanged = Signal()
    shownChanged = Signal()
    styleChanged = Signal()

    def __init__(self, on_scan, on_settings, on_hide, on_preview=None, on_source=None):
        super().__init__()
        self.on_scan, self.on_settings, self.on_hide = on_scan, on_settings, on_hide
        self.on_preview, self.on_source = on_preview, on_source
        self.on_refresh = self.on_correct = self.on_resize = None
        self.item_icons = self.advice_icons = self.visual_assets = None
        self.source_name = 'OP.GG'
        self.hotkey_bindings = {'scan': 'F6', 'refresh': 'F7', 'toggle': 'F8'}
        self.data_loading = self.images_loading = False
        self.network_error = self.images_error = ''
        self.manual_override = False
        self.signature = None
        self.visible = self.animate_hide = False
        self.stage = None
        self.zoom, self.ratio, self.motion = 1., 1., True
        self.offset = self.base = (0, 0)
        self.width, self.height = WIDTH, HEIGHT['select']
        self.visible_height = HEIGHT['select']
        self._anchor = self._last = self._context = None
        self._source_pending = False
        self._place = {'x': 0, 'y': 0, 'width': WIDTH, 'height': HEIGHT['select'], 'zoom': 1.}
        self._view, self._strings, self.assets_shown = {}, [], {}
        self._hidden_callback = None
        self.candidates = RowModel(('cid', 'name', 'tier', 'portrait', 'selected', 'tip'), 'cid')
        self.cards = RowModel(('slot', 'side', 'grade', 'name', 'long', 'hint', 'icon', 'tip', 'key'), 'slot')
        self.items = RowModel(('slot', 'name', 'icon', 'tip'), 'slot')
        self.assets = AssetUrls()
        self.assets.resolved.connect(self._rerender)

    # ---- CompanionApp interface -------------------------------------------
    def render(self, state, champions, data, matches, status, preview=False, scanning=False):
        self._last = (state, champions, data, matches, status, preview, scanning)
        if self.signature is None:          # CompanionApp clears it after downloads finish
            self.assets.forget_missing()
        context = (state.stage, state.champion_id, self.source_name)
        if self._context and self._context[:2] == context[:2] and self._context[2] != context[2]:
            self._source_pending = True
        elif self._context and self._context[:2] != context[:2]:
            self._source_pending = False
        if self._source_pending and not self.data_loading and (self.network_error or data):
            self._source_pending = False
        self._context = context
        if state.stage != self.stage:
            self.stage = state.stage
            if self._anchor:
                self._layout(self._anchor)
        view, self._strings = self._build(state, champions, data or {}, matches, status, scanning)
        self.signature = context
        if view != self._view:
            self._view = view
            self.viewChanged.emit()

    def show_at(self, anchor):
        self._layout(anchor)
        if not self.visible:
            self.visible = True
            self.shownChanged.emit()

    def _layout(self, anchor):
        self._anchor = anchor
        stage = 'game' if self.stage == 'game' else 'select'
        _, self.ratio = screen_at(anchor.rect[2], anchor.rect[1])
        left, top, right, bottom = anchor.work_area
        maximum = self._max_zoom()
        # Keep the default size scrolling on short work areas; user-scaled windows shrink to fit.
        if self.zoom > maximum + .001 and (abs(self.zoom - 1.) > .001 or self.width > right - left - 12):
            self.zoom = maximum
        scale = self.ratio * self.zoom
        self.width = round(WIDTH * scale)
        self.height = min(round(HEIGHT[stage] * scale), bottom - top - 12)
        self.visible_height = self.height / scale
        self.base = panel_position(anchor.rect, anchor.work_area, self.width, self.height)
        x = max(left, min(self.base[0] + self.offset[0], right - self.width))
        y = max(top, min(self.base[1] + self.offset[1], bottom - self.height))
        lx, ly = to_logical(x, y)
        place = {'x': round(lx), 'y': round(ly), 'width': self.width / self.ratio,
                 'height': self.height / self.ratio, 'zoom': self.zoom}
        if place != self._place:
            self._place = place
            self.placeChanged.emit()
        self._physical = (x, y)

    def hide(self, animate=False, done=None):
        if self.visible:
            self.visible = False
            self.animate_hide = animate and self.motion
            self._hidden_callback = done if self.animate_hide else None
            self.shownChanged.emit()
            if done and not self.animate_hide:
                done()
        elif done:
            done()

    def rect(self):
        x, y = getattr(self, '_physical', (0, 0))
        return x, y, self.width, self.height

    def set_motion(self, enabled):
        self.motion = bool(enabled) and system_motion_enabled()
        self.styleChanged.emit()

    def set_hotkeys(self, bindings):
        self.hotkey_bindings = dict(bindings)
        self._rerender()

    def set_zoom(self, zoom):
        try:
            zoom = float(zoom)
        except (TypeError, ValueError):
            zoom = 1.
        if zoom != zoom or zoom in (float('inf'), float('-inf')):
            zoom = 1.
        maximum = self._max_zoom()
        zoom = min(maximum, max(min(.65, maximum), zoom))
        if abs(zoom - self.zoom) < .001:
            return
        if self._anchor and getattr(self, '_physical', None):
            # Keep the current top-left corner where the user put it.
            old = self._physical
            self.zoom = zoom
            scale = self.ratio * zoom
            stage = 'game' if self.stage == 'game' else 'select'
            new_base = panel_position(self._anchor.rect, self._anchor.work_area, round(WIDTH * scale),
                                      round(HEIGHT[stage] * scale))
            self.offset = (old[0] - new_base[0], old[1] - new_base[1])
            self._layout(self._anchor)
        else:
            self.zoom = zoom

    def content_text(self):
        return '\n'.join(self._strings)

    def _max_zoom(self):
        if not self._anchor:
            return 2.5
        left, top, right, bottom = self._anchor.work_area
        stage = 'game' if self.stage == 'game' else 'select'
        return min(2.5, (right - left - 12) / (WIDTH * self.ratio), (bottom - top - 12) / (HEIGHT[stage] * self.ratio))

    def _rerender(self):
        if self._last:
            self.render(*self._last)

    def _asset(self, kind, key, lookup):
        url = self.assets.url((kind, key), lookup)
        self.assets_shown[(kind, key)] = bool(url)
        return url

    # ---- view model ----------------------------------------------------------
    def _build(self, state, champions, data, matches, status, scanning):
        """Strings and pictures for one frame; mirrors what the V2 Tk panel drew."""
        strings = []
        def say(text):
            strings.append(str(text))
            return str(text)
        self.assets_shown = {}
        game = state.stage == 'game'
        cid = state.champion_id
        hero = champions.get(cid)
        assets, advice_icons, item_icons = self.visual_assets, self.advice_icons, self.item_icons
        info = assets.champion_info(cid) if assets and cid else {}
        keys = self.hotkey_bindings
        view = {'stage': state.stage, 'game': game, 'top': TOP['game' if game else 'select'], 'footer': FOOTER,
                'baseHeight': HEIGHT['game' if game else 'select'],
                'title': say('海克斯随行'), 'sourcePending': self._source_pending,
                'statusLabel': say('选人中' if state.stage == 'select' else '对局中' if game else '等待连接'),
                'source': 'qq101' if self.source_name != 'OP.GG' else 'opgg', 'preview': bool(self.on_preview)}
        view['heroId'] = cid or 0
        view['heroName'] = say(info.get('name') or (hero.name if hero else '等待选择'))
        view['heroTitle'] = say(info.get('title', '') if cid else '')
        splash = self._asset('splash', cid, lambda: assets.path('splash', cid)) if assets and cid else ''
        focus = assets.champion_focus(cid) if assets and cid else (.72, .42)
        view.update(splash=splash, focusX=focus[0], focusY=focus[1])
        view['heroTip'] = '' if splash or not cid else ('插画加载中' if self.images_loading else '暂无英雄插画，保留真实名称')
        view['heroTier'] = say(hero.tier_label if hero and hero.tier is not None else '—') if not game else ''
        valid = (data.get('champion_id') == cid and data.get('build_mode_verified')
                 and data.get('build_mode') == 'aram-mayhem')
        advice = data if valid and state.stage in ('select', 'game') else {}
        if game:
            self._skills(view, say, advice, cid, assets, advice_icons)
            self._cards(view, say, data, matches, status, scanning, assets)
            self._build_items(view, say, data if valid else {}, item_icons)
        else:
            if state.stage == 'select':     # the lobby shows the hero and candidates only
                self._spells(view, say, advice, advice_icons)
            self._candidates(view, say, state, champions, assets)
        caption = self.source_name + ' · ' + ('加载中' if self.data_loading else '暂无资料' if not data else '缓存资料')
        view['caption'] = say(caption)
        view['footerTip'] = status + ('\n' + self.network_error if self.network_error else '')
        view['toggleText'] = say(keys['toggle'] + ' 收起')
        view['refreshKey'] = keys['refresh']
        view['refreshText'] = say('刷新 ' + keys['refresh'] if len(keys['refresh']) <= 4 else '刷新') if not game else ''
        if game:
            view['scanning'] = scanning
            view['scanText'] = say('识别中…' if scanning else '重新识别 ' + keys['scan'])
            view['refreshBadge'] = keys['refresh'] if len(keys['refresh']) <= 4 else ''
        return view, strings

    def _skills(self, view, say, advice, cid, assets, advice_icons):
        say('技能优先级')
        keys = advice.get('skill_priority', [])
        view['skills'], view['skillText'] = [], ''
        if not (len(keys) == 2 and all(k in ('Q', 'W', 'E') for k in keys) and len(set(keys)) == 2):
            view['skillText'] = say('暂无推荐')
            return
        local = assets.champion_skill_icons(cid) if assets else {}
        for key in keys:
            remote, fallback = advice.get('skill_icons', {}).get(key, ''), local.get(key, '')
            lookup = lambda r=remote, f=fallback: (advice_icons.path(r) or advice_icons.path(f)) if advice_icons else None
            icon = self.assets.url(('skill', remote, fallback), lookup)
            self.assets_shown[('skill', key)] = bool(icon)
            view['skills'].append({'key': say(key), 'icon': icon, 'tip': key + ' 技能' + ('' if icon else ' · 图标暂缺')})
        view['skillText'] = say(f'主 {keys[0]} › 副 {keys[1]}')

    def _spells(self, view, say, advice, advice_icons):
        say('召唤师技能')
        spells = advice.get('summoner_spells', [])
        view['spells'], view['spellText'] = [], ''
        if len(spells) != 2:
            view['spellText'] = say('暂无推荐')
        else:
            for spell in spells:
                url = spell.get('icon_url', '')
                icon = self.assets.url(('spell', url), lambda u=url: advice_icons.path(u) if advice_icons else None)
                self.assets_shown[('spell', spell.get('id'))] = bool(icon)
                view['spells'].append({'name': say(SPELL_NAMES.get(spell.get('id'), spell['name'])), 'icon': icon,
                                       'tip': spell['name'] + ('' if icon else ' · 图标暂缺')})
        supplemented = advice.get('source_id') == 'qq101' and advice.get('summoner_source') == 'opgg'
        view['spellSupplement'] = say('OP.GG 补充') if supplemented else ''

    def _candidates(self, view, say, state, champions, assets):
        say('可选英雄'); say('按梯队排序')
        ids = list(dict.fromkeys(state.candidate_ids))
        ordered = [h.id for h in sort_champions([champions[i] for i in ids if i in champions])]
        ordered += [i for i in ids if i not in champions]
        view['candidateEmpty'] = '' if ids else say('等待客户端返回候选英雄')
        rows = []
        for cid in ordered:
            info, hero = assets.champion_info(cid) if assets else {}, champions.get(cid)
            name = say(info.get('name') or (hero.name if hero else f'英雄{cid}'))
            tier = say(hero.tier_label if hero and hero.tier is not None else '—')
            portrait = self._asset('portrait', cid, lambda c=cid: assets.path('portrait', c)) if assets else ''
            rows.append({'cid': cid, 'name': name, 'tier': tier, 'portrait': portrait,
                         'selected': cid == state.champion_id, 'tip': name + ' · ' + (info.get('title') or '暂无档位')})
        self.candidates.update(rows)

    def _cards(self, view, say, data, matches, status, scanning, assets):
        say('海克斯推荐')
        index = {a['id']: a for a in data.get('augments', [])}
        rows, recognized = [], 0
        for slot in range(3):
            match = next((m for m in matches if m.slot == slot), None)
            augment = index.get(match.augment_id) if match else None
            grade = augment_label(augment.get('tier'), data.get('tier_labels')) if augment else '—'
            if grade not in tuple('SABCDE'):
                grade = '—'
            recognized += bool(augment)
            icon = self._asset('augment', augment['id'], lambda a=augment['id']: assets.path('augment', a)) \
                if augment and assets else ''
            name = augment['name'] if augment else '待确认'
            if grade != '—':
                hint = '手动修正' if self.manual_override else '已识别'
            else:
                hint = '暂无评级' if augment else '点击修正' if match and match.text else '等待识别'
            rows.append({'slot': slot, 'side': say(SIDES[slot]), 'grade': say(grade), 'name': say(name),
                         'long': len(name) > 5, 'hint': say(hint), 'icon': icon,
                         'tip': name + (' · 图标暂缺' if augment and not icon else '') + ' · 点击手动修正',
                         'key': f'{match.augment_id if match else None}|{match.status if match else ""}|{match.text if match else ""}'})
        self.cards.update(rows)
        view['recognized'] = say(f'已识别 {recognized} / 3')
        failed = any(text in status for text in ('未能确认', '截图失败', '识别失败'))
        view['cardStatus'] = say('正在切换来源…') if self._source_pending else say(status) if failed and not scanning else ''

    def _build_items(self, view, say, data, item_icons):
        say('核心出装'); say('英雄 / 模式推荐')
        items = recommended_items(data) if data else []
        rows = []
        for slot in range(4):
            item = items[slot] if slot < len(items) else None
            icon = self._asset('item', item['id'], lambda i=item['id']: item_icons.path(i)) if item and item_icons else ''
            name = ITEM_NAMES.get(item['id'], item['name']) if item else '暂无资料'
            rows.append({'slot': slot, 'name': say(name), 'icon': icon,
                         'tip': (item['name'] if item else '暂无装备推荐') + (' · 图标暂缺' if item and not icon else '')})
        self.items.update(rows)

    # ---- QML interface -------------------------------------------------------
    @Property('QVariantMap', notify=viewChanged)
    def view(self):
        return self._view

    @Property('QVariantMap', notify=placeChanged)
    def place(self):
        return self._place

    @Property(bool, notify=shownChanged)
    def shown(self):
        return self.visible

    @Property(bool, notify=shownChanged)
    def animateHide(self):
        return self.animate_hide

    @Property(bool, notify=styleChanged)
    def animated(self):
        return self.motion

    @Property(QObject, constant=True)
    def candidateModel(self):
        return self.candidates

    @Property(QObject, constant=True)
    def cardModel(self):
        return self.cards

    @Property(QObject, constant=True)
    def itemModel(self):
        return self.items

    @Slot()
    def hidden(self):
        """QML finished the hide animation."""
        callback, self._hidden_callback = self._hidden_callback, None
        if callback:
            callback()

    @Slot(int, int)
    def moved(self, lx, ly):
        """The user dragged the panel; later re-anchoring keeps this offset."""
        x, y = to_physical(lx, ly)
        self._physical = (x, y)
        self.offset = (x - self.base[0], y - self.base[1])

    @Slot(float)
    def resize(self, zoom):
        self.set_zoom(zoom)

    @Slot()
    def resized(self):
        if self.on_resize:
            self.on_resize(self.zoom)

    @Slot()
    def scan(self):
        self.on_scan()

    @Slot()
    def refresh(self):
        if self.on_refresh:
            self.on_refresh()

    @Slot()
    def collapse(self):
        self.on_hide()

    @Slot()
    def settings(self):
        self.on_settings()

    @Slot(int)
    def correct(self, slot):
        if self.on_correct:
            self.on_correct(slot)

    @Slot(str)
    def chooseSource(self, source):
        if self.on_source:
            self.on_source('OP.GG' if source == 'opgg' else '101 数据站')

    @Slot()
    def preview(self):
        if self.on_preview:
            self.on_preview()


class CompanionBubble(QObject):
    """The collapsed launcher. A click expands; a drag only moves it."""
    changed = Signal()

    def __init__(self, on_expand):
        super().__init__()
        self.on_expand = on_expand
        self.visible = self.animate_hide = self._user_position = False
        self.motion = True
        self.position = None
        screen = QGuiApplication.primaryScreen()
        ratio = screen.devicePixelRatio()
        self.size = round(40 * ratio)
        g = screen.availableGeometry()
        self.work_area = (0, 0, round(g.width() * ratio), round(g.height() * ratio))
        self.tip = '单击展开，拖动移动 · F8 展开/收起'

    def show_at(self, anchor, rectangle=None, animate=True):
        self.work_area = anchor.work_area
        _, ratio = screen_at(anchor.rect[2], anchor.rect[1])
        self.size = round(40 * ratio)
        if not self._user_position and rectangle:
            x, y, w, h = rectangle
            self.position = (x + w - self.size - 12 * ratio, y + h - self.size - 12 * ratio)
        x, y = self.position or (self.work_area[2] - self.size - 16, self.work_area[1] + 16)
        self._place(x, y)
        if not self.visible:
            self.visible = True
            self.changed.emit()

    def _place(self, x, y):
        left, top, right, bottom = self.work_area
        self.position = (max(left, min(round(x), right - self.size)), max(top, min(round(y), bottom - self.size)))
        self.changed.emit()

    def hide(self, animate=False):
        if self.visible:
            self.visible = False
            self.animate_hide = animate and self.motion
            self.changed.emit()

    def rect(self):
        x, y = self.position or (0, 0)
        return x, y, self.size, self.size

    def set_hotkeys(self, bindings):
        self.tip = '单击展开，拖动移动 · ' + bindings.get('toggle', 'F8') + ' 展开/收起'
        self.changed.emit()

    def set_motion(self, enabled):
        self.motion = bool(enabled) and system_motion_enabled()
        self.changed.emit()

    @Property('QVariantMap', notify=changed)
    def state(self):
        x, y = to_logical(*(self.position or (0, 0)))
        _, ratio = screen_at(*(self.position or (0, 0)))
        return {'shown': self.visible, 'animateHide': self.animate_hide, 'x': round(x), 'y': round(y),
                'size': self.size / ratio, 'tip': self.tip, 'animated': self.motion}

    @Slot(int, int)
    def moved(self, lx, ly):
        self._user_position = True
        self._place(*to_physical(lx, ly))

    @Slot()
    def expand(self):
        self.on_expand()


class Overlay(QObject):
    """Loads the overlay windows once; the settings dialog reuses this engine."""

    def __init__(self, panel, bubble):
        super().__init__()
        self.engine = QQmlApplicationEngine()
        context = self.engine.rootContext()
        context.setContextProperty('panel', panel)
        context.setContextProperty('bubble', bubble)
        before = set(QGuiApplication.topLevelWindows())
        self.engine.load(QUrl.fromLocalFile(str(QML_DIR / 'Overlay.qml')))
        if not self.engine.rootObjects():
            raise RuntimeError('界面文件加载失败')
        # Only this engine's windows; another overlay may still be shutting down.
        self.windows = {w.objectName(): w for w in QGuiApplication.topLevelWindows() if w not in before}

    def window(self, name):
        return self.windows.get(name)

    def close(self):
        for window in self.windows.values():
            window.hide()
        # Releases the windows and QML objects once control returns to the event loop.
        self.engine.deleteLater()
