"""Qt bridge for the QML spike: reuses the Tk-free data, LCU, asset and hotkey modules."""
import logging
import os
import threading
import time
from dataclasses import replace
from pathlib import Path

from PySide6.QtCore import (QAbstractListModel, QByteArray, QModelIndex, QObject, Property,
                            QTimer, Qt, Signal, Slot)

from aram_demo.advice_icons import AdviceIconCache
from aram_demo.cache import DataStore, is_fresh
from aram_demo.companion_state import MAYHEM_QUEUES, PLAYING, SessionTracker
from aram_demo.hotkeys import Hotkeys
from aram_demo.lcu import ClientState, LCUClient, live_champion_id
from aram_demo.models import sort_champions
from aram_demo.visual_assets import VisualAssetCache
from aram_demo.windows import LeagueWindow, find_league_window, foreground_is_ours, panel_position

POLL_MS, DISCONNECTED_POLL_MS, WINDOW_MS = 2000, 6000, 500
SPELL_NAMES = {6: '疾跑', 11: '惩戒', 12: '传送', 13: '清晰', 14: '点燃', 21: '屏障'}
PREVIEW_HEROES = [222, 90, 99, 201, 86, 17]
log = logging.getLogger('aram_demo.qml_spike')


PANEL_W, PANEL_H = 360, 540


def file_url(path):
    return Path(os.path.abspath(path)).as_uri() if path else ''


def screen_at(px, py):
    """Return the QScreen holding a physical point and its device pixel ratio."""
    from PySide6.QtGui import QGuiApplication
    for screen in QGuiApplication.screens():
        g, ratio = screen.geometry(), screen.devicePixelRatio()
        if g.x() <= px < g.x() + g.width() * ratio and g.y() <= py < g.y() + g.height() * ratio:
            return screen, ratio
    screen = QGuiApplication.primaryScreen()
    return screen, screen.devicePixelRatio()


def to_logical(screen, ratio, px, py):
    g = screen.geometry()
    return round(g.x() + (px - g.x()) / ratio), round(g.y() + (py - g.y()) / ratio)


class CandidateModel(QAbstractListModel):
    """Row diffing keeps delegates alive, so hover state and move transitions survive updates."""
    ROLES = ('cid', 'name', 'title', 'tier', 'portrait', 'selected')

    def __init__(self):
        super().__init__()
        self.rows = []

    def roleNames(self):
        return {Qt.UserRole + i: QByteArray(name.encode()) for i, name in enumerate(self.ROLES)}

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.rows)

    def data(self, index, role):
        if not index.isValid() or not 0 <= role - Qt.UserRole < len(self.ROLES):
            return None
        return self.rows[index.row()][self.ROLES[role - Qt.UserRole]]

    def update(self, rows):
        wanted = [row['cid'] for row in rows]
        for i in reversed(range(len(self.rows))):
            if self.rows[i]['cid'] not in wanted:
                self.beginRemoveRows(QModelIndex(), i, i); del self.rows[i]; self.endRemoveRows()
        for target, row in enumerate(rows):
            current = [r['cid'] for r in self.rows]
            if row['cid'] not in current:
                self.beginInsertRows(QModelIndex(), target, target); self.rows.insert(target, row); self.endInsertRows()
                continue
            source = current.index(row['cid'])
            if source != target:
                self.beginMoveRows(QModelIndex(), source, source, QModelIndex(), target)
                self.rows.insert(target, self.rows.pop(source)); self.endMoveRows()
            if self.rows[target] != row:
                self.rows[target] = row
                self.dataChanged.emit(self.index(target), self.index(target))


class Bridge(QObject):
    viewChanged = Signal()
    geometryChanged = Signal()
    _deliver = Signal(object, object)   # worker → GUI thread (queued)
    _call = Signal(object)

    def __init__(self, store, preview=False, services=True):
        super().__init__()
        self.store, self.preview, self.services = store, preview, services
        self.tracker = SessionTracker(); self.state = self.tracker.state
        self.champions = {c.id: c for c in store.champions()}
        self.settings = store.read('settings.json') or {}
        self.client = LCUClient()
        self.visual = VisualAssetCache(store.root, store.seed_root)
        self.advice = AdviceIconCache(store.root, store.seed_root)
        self.data = None
        self.loading = self.images_loading = False
        self.error = ''
        self.poll_pending = False
        self.fetching = set()
        self.visual_requested = None
        self.collapsed = False
        self._visible = False
        self._geometry = {'x': 0, 'y': 0}
        self._offset = (0, 0)
        self._view = {}
        self.candidates = CandidateModel()
        self._deliver.connect(lambda callback, value: callback(value), Qt.QueuedConnection)
        self._call.connect(lambda callback: callback(), Qt.QueuedConnection)
        self.hotkeys = Hotkeys(lambda: None, lambda: self._call.emit(self.refresh),
                               lambda: self._call.emit(self.collapse),
                               on_toggle=lambda: self._call.emit(self.toggle),
                               bindings=self.settings.get('hotkeys'))
        self.poll_timer = QTimer(self); self.poll_timer.timeout.connect(self.poll)
        self.window_timer = QTimer(self); self.window_timer.timeout.connect(self.present)
        self.preview_timer = QTimer(self); self.preview_timer.timeout.connect(self.preview_next)
        self._preview_index = 0
        self._publish()

    # ---- lifecycle -------------------------------------------------------
    def start(self):
        if self.services:
            self.hotkeys.start()
        if self.preview:
            self.on_client_state(ClientState('ChampSelect', 222, PREVIEW_HEROES, queue_id=2400))
        else:
            self.poll_timer.start(100)
        self.window_timer.start(WINDOW_MS)

    @Slot()
    def stop(self):
        self.hotkeys.stop()
        for timer in (self.poll_timer, self.window_timer, self.preview_timer):
            timer.stop()

    def background(self, job, callback, done=None):
        def worker():
            try:
                result, error = job(), None
            except Exception as exc:  # surfaced in the view, like the Tk app
                result, error = None, str(exc)[:160]
            def finish(_):
                if done:
                    done()
                if error:
                    log.warning('background failed: %s', error)
                    self.error = error; self._publish()
                else:
                    callback(result)
            self._deliver.emit(finish, None)
        threading.Thread(target=worker, daemon=True).start()

    # ---- client state ------------------------------------------------------
    def poll(self):
        self.poll_timer.setInterval(DISCONNECTED_POLL_MS if self.state.phase == 'Disconnected' else POLL_MS)
        if self.poll_pending:
            return
        self.poll_pending = True
        champions, known = list(self.champions.values()), self.state.queue_id
        def read():
            self.client.install_path = self.settings.get('install_path')
            raw = self.client.read_state()
            if not raw.champion_id and raw.phase in PLAYING and (raw.queue_id in MAYHEM_QUEUES or raw.queue_id is None and known in MAYHEM_QUEUES):
                raw = replace(raw, champion_id=live_champion_id(champions))
            return raw
        self.background(read, self.on_client_state, done=lambda: setattr(self, 'poll_pending', False))

    def on_client_state(self, raw):
        old = self.state
        self.state = self.tracker.update(raw)
        if (raw.phase, self.state.champion_id) != (old.phase, old.champion_id):
            log.info('client phase=%s stage=%s hero=%s queue=%s', raw.phase, self.state.stage, self.state.champion_id, self.state.queue_id)
        if self.state.stage == 'hidden':
            self.collapsed = False
        if self.state.champion_id != old.champion_id or self.state.stage != old.stage:
            self.load_data()
        if self.state.candidate_ids != old.candidate_ids:
            self.refresh_visuals()
        self._publish(); self.present()

    def load_data(self):
        cid = self.state.champion_id
        self.data = self.store.hero(cid) if cid else None
        self.error = ''
        self.refresh_visuals(); self.refresh_spell_icons()
        if cid in self.champions and self.services and not self.preview and not is_fresh(self.data):
            self.fetch_hero(cid)

    def fetch_hero(self, cid):
        store, key = self.store, (id(self.store), cid)
        if key in self.fetching or cid not in self.champions:
            return
        self.fetching.add(key); self._set_loading()
        def loaded(data):
            if self.store is store and self.state.champion_id == cid and data:
                self.data = data; self.refresh_spell_icons(); self._publish()
        def ready(partial):
            self._deliver.emit(loaded, partial)
        def finished():
            self.fetching.discard(key); self._set_loading()
        self.background(lambda: store.refresh(self.champions[cid], on_ready=ready), loaded, done=finished)

    def refresh_visuals(self):
        requests = []
        for cid in [self.state.champion_id, *self.state.candidate_ids]:
            if cid in self.champions:
                requests.append(('portrait', cid))
        if self.state.champion_id in self.champions:
            requests.append(('splash', self.state.champion_id))
        requests = [r for r in dict.fromkeys(requests) if self.visual.state(*r) != 'cached']
        if not requests or not self.services or self.preview or tuple(requests) == self.visual_requested:
            return
        self.visual_requested = tuple(requests)
        self.images_loading = True; self._publish()
        def finished():
            self.images_loading = False
        self.background(lambda: self.visual.ensure(requests), lambda _: self._publish(), done=finished)

    def refresh_spell_icons(self):
        urls = [s.get('icon_url', '') for s in (self.data or {}).get('summoner_spells', [])]
        urls = [u for u in urls if u and self.advice.path(u) is None]
        if urls and self.services and not self.preview:
            self.background(lambda: self.advice.ensure(urls), lambda _: self._publish())

    def _set_loading(self):
        self.loading = (id(self.store), self.state.champion_id) in self.fetching
        self._publish()

    # ---- view model ------------------------------------------------------
    def _publish(self):
        state, cid = self.state, self.state.champion_id
        hero = self.champions.get(cid)
        info = self.visual.champion_info(cid) if cid else {}
        data = self.data if (self.data and self.data.get('champion_id') == cid and self.data.get('build_mode_verified')
                             and self.data.get('build_mode') == 'aram-mayhem') else {}
        spells = []
        for spell in data.get('summoner_spells', [])[:2]:
            spells.append({'name': SPELL_NAMES.get(spell.get('id'), spell.get('name', '')),
                           'icon': file_url(self.advice.path(spell.get('icon_url', '')))})
        ids = list(dict.fromkeys(state.candidate_ids))
        ordered = [h.id for h in sort_champions([self.champions[i] for i in ids if i in self.champions])]
        ordered += [i for i in ids if i not in self.champions]
        rows = []
        for i in ordered:
            row_info, row_hero = self.visual.champion_info(i), self.champions.get(i)
            rows.append({'cid': i, 'name': row_info.get('name') or (row_hero.name if row_hero else f'英雄{i}'),
                         'title': row_info.get('title', ''),
                         'tier': row_hero.tier_label if row_hero and row_hero.tier is not None else '—',
                         'portrait': file_url(self.visual.path('portrait', i)), 'selected': i == cid})
        self.candidates.update(rows)
        focus = self.visual.champion_focus(cid) if cid else (.72, .42)
        caption = self.store.source_name + ' · ' + ('加载中' if self.loading else '缓存资料' if self.data else '暂无资料')
        self._view = {
            'stage': state.stage, 'heroId': cid or 0,
            'heroName': info.get('name') or (hero.name if hero else '等待选择'),
            'heroTitle': info.get('title', '') if cid else '',
            'heroTier': hero.tier_label if hero and hero.tier is not None else '—',
            'splash': file_url(self.visual.path('splash', cid)) if cid else '',
            'focusX': focus[0], 'focusY': focus[1],
            'spells': spells, 'spellSupplement': data.get('source_id') == 'qq101' and data.get('summoner_source') == 'opgg',
            'source': self.store.source, 'caption': caption, 'loading': self.loading or self.images_loading,
            'error': self.error, 'toggleKey': self.hotkeys.bindings['toggle'], 'refreshKey': self.hotkeys.bindings['refresh'],
            'visible': self._visible, 'collapsed': self.collapsed, 'preview': self.preview,
        }
        self.viewChanged.emit()

    @Property('QVariantMap', notify=viewChanged)
    def view(self):
        return self._view

    @Property(QObject, constant=True)
    def candidateModel(self):
        return self.candidates

    @Property('QVariantMap', notify=geometryChanged)
    def geometry(self):
        return self._geometry

    # ---- placement and visibility ----------------------------------------
    def locate(self, stage):
        if self.preview:
            from PySide6.QtGui import QGuiApplication
            screen = QGuiApplication.primaryScreen()
            work, ratio = screen.availableGeometry(), screen.devicePixelRatio()
            w, h = round(work.width() * ratio), round(work.height() * ratio)
            return LeagueWindow(0, (max(0, w - 1100), 100, w - 350, h - 120), (0, 0, w, h), True)
        return find_league_window(stage)

    @Slot()
    def present(self):
        stage = self.state.stage
        anchor = self.locate(stage) if stage != 'hidden' else None
        visible = bool(anchor and (self.preview or anchor.foreground or foreground_is_ours()))
        if anchor:
            # Win32 rectangles are physical pixels; Qt windows use per-screen logical pixels.
            screen, ratio = screen_at(anchor.rect[2], anchor.rect[1])
            x, y = panel_position(anchor.rect, anchor.work_area, round(PANEL_W * ratio), round(PANEL_H * ratio))
            lx, ly = to_logical(screen, ratio, x, y)
            left, top = to_logical(screen, ratio, *anchor.work_area[:2])
            right, bottom = to_logical(screen, ratio, *anchor.work_area[2:])
            geometry = {'x': lx + self._offset[0], 'y': ly + self._offset[1], 'ratio': ratio,
                        'workLeft': left, 'workTop': top, 'workRight': right, 'workBottom': bottom}
            if geometry != self._geometry:
                self._geometry = geometry; self.geometryChanged.emit()
        self.hotkeys.set_overlay_visible(visible and not self.collapsed)
        if visible != self._visible:
            self._visible = visible; self._publish()

    @Slot(int, int)
    def moved(self, dx, dy):
        self._offset = (self._offset[0] + dx, self._offset[1] + dy)

    # ---- actions -----------------------------------------------------------
    @Slot()
    def collapse(self):
        if self.state.stage != 'hidden':
            self.collapsed = True; self._publish()

    @Slot()
    def expand(self):
        self.collapsed = False; self._publish()

    @Slot()
    def toggle(self):
        if self.state.stage != 'hidden':
            self.collapsed = not self.collapsed; self._publish()

    @Slot(str)
    def selectSource(self, source):
        if source == self.store.source:
            return
        self.store.retire()
        self.store = DataStore(self.store.root, self.store.seed_root, source=source)
        identities = {cid: replace(h, tier=None, rank=None) for cid, h in self.champions.items()}
        identities.update({c.id: c for c in self.store.champions()})
        self.champions = identities
        self.fetching.clear(); self.load_data(); self._publish()

    @Slot()
    def refresh(self):
        self.visual_requested = None
        self.refresh_visuals()
        if self.state.champion_id:
            self.fetch_hero(self.state.champion_id)

    @Slot()
    def preview_next(self):
        """Preview: pick the next candidate, as a player swapping from the bench would."""
        self._preview_index = (self._preview_index + 1) % len(PREVIEW_HEROES)
        self.on_client_state(ClientState('ChampSelect', PREVIEW_HEROES[self._preview_index], PREVIEW_HEROES, queue_id=2400))

    @Slot(int)
    def pick(self, cid):
        log.info('candidate clicked hero=%s', cid)
        if self.preview:
            self.on_client_state(ClientState('ChampSelect', cid, PREVIEW_HEROES, queue_id=2400))
